from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.models import ScenarioInstance
from cover_opt.hashing import sha256_json
from cover_opt.heuristics.executor import DeterministicExecutor
from cover_opt.heuristics.patch import HeuristicPatch
from cover_opt.heuristics.schema import HeuristicDSL
from cover_opt.heuristics.static_verifier import dsl_signature
from cover_opt.objective.evaluator import ObjectiveEvaluator
from cover_opt.search.archive import CandidateArchive, CandidateRecord
from cover_opt.search.budgets import SearchBudgets
from cover_opt.search.counterexamples import CounterexampleArchive, CounterexampleRecord
from cover_opt.search.generation import (
    InitialProgramGenerator,
    PatchGenerationError,
    PatchGenerator,
    ScriptedPatchGenerator,
)
from cover_opt.search.options import SearchFeatures
from cover_opt.search.probes import CounterfactualWeightProbe
from cover_opt.search.refiner import (
    ObjectivePatchEvaluation,
    PatchRejectionFeedback,
    RefinementContext,
    TargetedRefiner,
)
from cover_opt.search.replay import CounterexampleReplayScheduler
from cover_opt.verifier.conflict_graph import ConflictGraphBuilder
from cover_opt.verifier.plan_verifier import PlanVerifier


class SearchStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch_proposals: int = Field(ge=0, default=0)
    initial_generation_calls: int = Field(ge=0, default=0)
    patch_generation_calls: int = Field(ge=0, default=0)
    total_llm_calls: int = Field(ge=0, default=0)
    evaluator_calls: int = Field(ge=0, default=0)
    accepted_patches: int = Field(ge=0, default=0)
    rejected_patches: int = Field(ge=0, default=0)
    numeric_probes: int = Field(ge=0, default=0)
    outcome_rejections: int = Field(ge=0, default=0)
    counterexample_replays: int = Field(ge=0, default=0)
    first_feasible_patch_proposal: int | None = Field(ge=0, default=None)
    wall_time_ms: float = Field(ge=0, default=0.0)


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[CandidateRecord]
    best_candidate_id: str | None
    stop_reason: str
    statistics: SearchStatistics
    trajectory: list[dict]
    counterexamples: list[CounterexampleRecord] = Field(default_factory=list)
    replay_queue: list[str] = Field(default_factory=list)
    diverse_candidate_ids: list[str] = Field(default_factory=list)
    semantic_patch_rejections: list[PatchRejectionFeedback] = Field(
        default_factory=list
    )
    objective_patch_evaluations: list[ObjectivePatchEvaluation] = Field(
        default_factory=list
    )
    initial_generation_trace: list[dict] = Field(default_factory=list)
    features: SearchFeatures = Field(default_factory=SearchFeatures)
    controller_version: str = "0.9.0"


class SearchController:
    version = "0.9.0"

    @staticmethod
    def _patch_semantic_signature(patch: HeuristicPatch) -> str:
        return sha256_json(
            {
                "version": patch.version,
                "operations": [
                    item.model_dump(mode="json") for item in patch.operations
                ],
            }
        )

    @staticmethod
    def _behavior_signature(record: CandidateRecord) -> str:
        return sha256_json(
            {
                "placement": record.execution.plan.placement,
                "routes": [
                    item.model_dump(mode="json")
                    for item in record.execution.plan.routes
                ],
                "violations": [
                    {
                        "type": item.violation_type.value,
                        "magnitude": round(item.magnitude, 9),
                        "entities": sorted(item.entities),
                    }
                    for item in record.verification.violations
                ],
            }
        )

    @staticmethod
    def _violation_magnitudes(record: CandidateRecord) -> dict[str, float]:
        result: dict[str, float] = {}
        for violation in record.verification.violations:
            key = violation.violation_type.value
            result[key] = result.get(key, 0.0) + violation.magnitude
        return result

    @classmethod
    def _feasibility_improved(
        cls,
        parent: CandidateRecord,
        child: CandidateRecord,
    ) -> bool:
        if child.verification.feasible:
            return not parent.verification.feasible
        if parent.verification.feasible:
            return False
        parent_values = cls._violation_magnitudes(parent)
        child_values = cls._violation_magnitudes(child)
        if not set(child_values).issubset(parent_values):
            return False
        no_worse = all(
            child_values[key] <= parent_values[key] + 1e-9
            for key in child_values
        )
        strictly_better = (
            set(child_values) < set(parent_values)
            or any(
                child_values[key] < parent_values[key] - 1e-9
                for key in child_values
            )
        )
        return no_worse and strictly_better

    def __init__(
        self,
        *,
        k_paths: int = 3,
        features: SearchFeatures | None = None,
    ) -> None:
        self.features = features or SearchFeatures()
        self.executor = DeterministicExecutor(
            k_paths=k_paths,
            enable_repair_actions=self.features.repair_actions_enabled,
            feasible_masks_enabled=self.features.feasible_masks_enabled,
        )
        self.plan_verifier = PlanVerifier()
        self.objective_evaluator = ObjectiveEvaluator()
        self.conflict_builder = ConflictGraphBuilder()
        self.refiner = TargetedRefiner(feedback_mode=self.features.feedback_mode)
        self.replay_scheduler = CounterexampleReplayScheduler()

    def _evaluate_candidate(
        self,
        *,
        scenario: ScenarioInstance,
        program: HeuristicDSL,
        candidate_id: str,
        parent_id: str | None,
        iteration: int,
    ) -> CandidateRecord:
        execution = self.executor.execute(
            scenario,
            program,
            candidate_id=candidate_id,
            run_id="search_controller",
        )
        verification = self.plan_verifier.verify(scenario, execution.plan)
        if verification.feasible:
            objective = self.objective_evaluator.evaluate(
                scenario,
                execution.plan,
                verification,
                planning_time_ms=execution.planning_time_ms,
            )
            conflict_graph = None
            category = "feasible_elite"
        elif execution.failure_reason is None and verification.violations:
            objective = None
            conflict_graph = self.conflict_builder.build(verification)
            category = "repairable"
        else:
            objective = None
            conflict_graph = (
                self.conflict_builder.build(verification)
                if verification.violations
                else None
            )
            category = "rejected"
        return CandidateRecord(
            candidate_id=candidate_id,
            parent_id=parent_id,
            iteration=iteration,
            program=program,
            ast_signature=dsl_signature(program),
            execution=execution,
            verification=verification,
            objective=objective,
            conflict_graph=conflict_graph,
            category=category,
        )

    def run(
        self,
        *,
        scenario: ScenarioInstance,
        initial_program: HeuristicDSL,
        additional_initial_programs: list[HeuristicDSL] | None = None,
        initial_generator: InitialProgramGenerator | None = None,
        initial_generation_count: int = 0,
        generator: PatchGenerator,
        budgets: SearchBudgets,
    ) -> SearchResult:
        if initial_generation_count < 0:
            raise ValueError("initial_generation_count must be non-negative")
        if initial_generator is None and initial_generation_count != 0:
            raise ValueError(
                "initial_generation_count requires an initial_generator"
            )
        started = time.perf_counter()
        archive = CandidateArchive()
        counterexamples = CounterexampleArchive()
        statistics = SearchStatistics()
        trajectory: list[dict] = []
        patch_rejections: dict[str, PatchRejectionFeedback] = {}
        objective_patch_evaluations: list[ObjectivePatchEvaluation] = []
        generated_initial_programs: list[HeuristicDSL] = []
        initial_generation_trace: list[dict] = []
        if initial_generator is not None and initial_generation_count > 0:
            allowed_generation_count = initial_generation_count
            allowed_generation_count = min(
                allowed_generation_count,
                budgets.effective_max_total_llm_calls,
            )
            event_start = len(initial_generator.events)
            generated_initial_programs = initial_generator.generate_candidates(
                scenario,
                count=allowed_generation_count,
            )
            generation_events = initial_generator.events[event_start:]
            initial_generation_trace = [
                event.model_dump(mode="json")
                if hasattr(event, "model_dump")
                else dict(event)
                for event in generation_events
            ]
            statistics.initial_generation_calls = len(generation_events)
            statistics.total_llm_calls = len(generation_events)
            trajectory.append(
                {
                    "event": "initial_generation_completed",
                    "requested_count": initial_generation_count,
                    "attempted_count": len(generation_events),
                    "accepted_count": len(generated_initial_programs),
                "limited_by_total_llm_budget": (
                        allowed_generation_count < initial_generation_count
                    ),
                }
            )
        initial_programs = [
            initial_program,
            *(additional_initial_programs or []),
            *generated_initial_programs,
        ]
        multi_start = len(initial_programs) > 1
        initial_records: list[CandidateRecord] = []
        initial_counterexamples: dict[str, CounterexampleRecord] = {}
        seen_initial_signatures: set[str] = set()
        for index, program in enumerate(initial_programs):
            if statistics.evaluator_calls >= budgets.max_evaluator_calls:
                break
            signature = dsl_signature(program)
            if signature in seen_initial_signatures:
                trajectory.append(
                    {
                        "event": "initial_candidate_skipped",
                        "source_index": index,
                        "reason": "duplicate_ast_signature",
                        "ast_signature": signature,
                    }
                )
                continue
            seen_initial_signatures.add(signature)
            candidate_id = (
                f"candidate_init_{index:03d}" if multi_start else "candidate_000"
            )
            record = self._evaluate_candidate(
                scenario=scenario,
                program=program,
                candidate_id=candidate_id,
                parent_id=None,
                iteration=0,
            )
            archive.add(record)
            initial_records.append(record)
            statistics.evaluator_calls += 1
            record_counterexample = None
            if (
                self.features.counterexample_memory_enabled
                and not record.verification.feasible
            ):
                record_counterexample = counterexamples.observe(
                    scenario=scenario,
                    verification=record.verification,
                    candidate_id=record.candidate_id,
                    ast_signature=record.ast_signature,
                    iteration=record.iteration,
                    conflict_graph_signature=(
                        record.conflict_graph.graph_signature
                        if record.conflict_graph
                        else None
                    ),
                )
                initial_counterexamples[record.candidate_id] = record_counterexample
            if record.verification.feasible:
                statistics.first_feasible_patch_proposal = 0
            event = {
                "event": "candidate_evaluated",
                "candidate_id": record.candidate_id,
                "category": record.category,
                "feasible": record.verification.feasible,
                "ast_signature": record.ast_signature,
                "counterexample_id": (
                    record_counterexample.counterexample_id
                    if record_counterexample
                    else None
                ),
            }
            if multi_start:
                event["source"] = (
                    "fixed_initial" if index == 0 else "generated_initial"
                )
                event["source_index"] = index
            trajectory.append(event)

        if not initial_records:
            raise RuntimeError("evaluator budget does not allow an initial candidate")
        current = (
            archive.best_feasible()
            or archive.best_repairable()
            or initial_records[0]
        )
        current_counterexample = initial_counterexamples.get(current.candidate_id)
        if multi_start:
            trajectory.append(
                {
                    "event": "initial_candidate_selected",
                    "candidate_id": current.candidate_id,
                    "source": (
                        "fixed_initial"
                        if current.candidate_id == "candidate_init_000"
                        else "generated_initial"
                    ),
                    "selection": (
                        "best_feasible_objective"
                        if current.verification.feasible
                        else "lowest_violation_burden"
                    ),
                    "evaluated_candidate_ids": [
                        record.candidate_id for record in initial_records
                    ],
                }
            )
        if current.verification.feasible and (
            budgets.stop_on_first_feasible
            or not self.features.objective_refinement_enabled
        ):
            stop_reason = "initial_candidate_feasible"
        else:
            stop_reason = "generator_exhausted"
            iteration = 1
            while True:
                elapsed = time.perf_counter() - started
                if elapsed >= budgets.max_wall_time_seconds:
                    stop_reason = "wall_time_budget"
                    break
                if statistics.evaluator_calls >= budgets.max_evaluator_calls:
                    stop_reason = "evaluator_budget"
                    break
                if statistics.patch_proposals >= budgets.max_patch_proposals:
                    stop_reason = "patch_budget"
                    break
                if (
                    getattr(generator, "counts_as_llm_call", False)
                    and statistics.total_llm_calls
                    >= budgets.effective_max_total_llm_calls
                ):
                    stop_reason = "llm_call_budget"
                    break
                if current.verification.feasible and (
                    budgets.stop_on_first_feasible
                    or not self.features.objective_refinement_enabled
                ):
                    stop_reason = "first_feasible"
                    break

                if (
                    not current.verification.feasible
                    and self.features.counterexample_memory_enabled
                    and self.features.counterexample_replay_enabled
                    and statistics.counterexample_replays
                    < budgets.max_counterexample_replays
                ):
                    selection = self.replay_scheduler.select(
                        candidates=archive,
                        counterexamples=counterexamples,
                        iteration=iteration,
                        max_replays_per_counterexample=(
                            budgets.max_replays_per_counterexample
                        ),
                    )
                    if selection is not None:
                        current = selection.parent
                        current_counterexample = selection.counterexample
                        statistics.counterexample_replays += 1
                        trajectory.append(
                            {
                                "event": "counterexample_replayed",
                                "iteration": iteration,
                                "counterexample_id": (
                                    selection.counterexample.counterexample_id
                                ),
                                "counterexample_signature": (
                                    selection.counterexample.signature
                                ),
                                "parent_candidate_id": selection.parent.candidate_id,
                                "priority": list(selection.priority),
                                "replay_count": (
                                    selection.counterexample.replay_count
                                ),
                            }
                        )

                objective_incumbent = None
                if current.verification.feasible:
                    incumbent = archive.best_feasible()
                    if current.objective is None or incumbent is None or incumbent.objective is None:
                        raise RuntimeError("feasible archive record is missing an objective")
                    objective_incumbent = incumbent
                    context = self.refiner.build_objective_context(
                        parent=current.program,
                        scenario=scenario,
                        verification=current.verification,
                        execution=current.execution,
                        objective=current.objective,
                        incumbent_objective=incumbent.objective,
                        previous_patch_rejections=list(patch_rejections.values()),
                        previous_objective_evaluations=objective_patch_evaluations,
                    )
                else:
                    context = self.refiner.build_context(
                        parent=current.program,
                        scenario=scenario,
                        verification=current.verification,
                        counterexample_summary=(
                            current_counterexample.prompt_summary()
                            if current_counterexample
                            else None
                        ),
                        previous_patch_rejections=list(patch_rejections.values()),
                    )
                try:
                    if getattr(generator, "counts_as_llm_call", False):
                        statistics.patch_generation_calls += 1
                        statistics.total_llm_calls += 1
                    patch = generator.propose(context)
                except PatchGenerationError as exc:
                    statistics.patch_proposals += 1
                    statistics.rejected_patches += 1
                    trajectory.append(
                        {
                            "event": "patch_generation_failed",
                            "parent_id": current.candidate_id,
                            "error": str(exc),
                            "details": exc.details,
                        }
                    )
                    iteration += 1
                    continue
                if patch is None:
                    stop_reason = "generator_exhausted"
                    break
                statistics.patch_proposals += 1
                patch_payload = patch.model_dump(mode="json")
                patch_signature = self._patch_semantic_signature(patch)
                repeated_objective_index = next(
                    (
                        index
                        for index, item in enumerate(objective_patch_evaluations)
                        if item.patch_signature == patch_signature
                        and not item.improved
                    ),
                    None,
                )
                if patch_signature in patch_rejections:
                    previous = patch_rejections[patch_signature]
                    patch_rejections[patch_signature] = previous.model_copy(
                        update={"occurrence_count": previous.occurrence_count + 1}
                    )
                    statistics.rejected_patches += 1
                    trajectory.append(
                        {
                            "event": "duplicate_patch_rejected",
                            "parent_id": current.candidate_id,
                            "patch": patch_payload,
                            "patch_signature": patch_signature,
                            "errors": ["duplicate of a previously rejected patch"],
                            "previous_errors": previous.errors,
                        }
                    )
                    iteration += 1
                    continue
                if repeated_objective_index is not None:
                    previous = objective_patch_evaluations[
                        repeated_objective_index
                    ]
                    objective_patch_evaluations[
                        repeated_objective_index
                    ] = previous.model_copy(
                        update={"occurrence_count": previous.occurrence_count + 1}
                    )
                    statistics.rejected_patches += 1
                    trajectory.append(
                        {
                            "event": "duplicate_patch_rejected",
                            "parent_id": current.candidate_id,
                            "patch": patch_payload,
                            "patch_signature": patch_signature,
                            "errors": [
                                "duplicate of a previously non-improving objective patch"
                            ],
                            "previous_objective_improvement": previous.improvement,
                        }
                    )
                    iteration += 1
                    continue
                proposal_parent = current
                application = self.refiner.apply_patch(
                    parent=proposal_parent.program,
                    patch=patch,
                    context=context,
                )
                trajectory.append(
                    {
                        "event": "patch_evaluated",
                        "parent_id": current.candidate_id,
                        "patch": patch_payload,
                        "patch_signature": patch_signature,
                        "allowed_components": context.allowed_components,
                        "conflict_graph_signature": (
                            context.conflict_graph.graph_signature
                        ),
                        "feedback_mode": context.feedback_mode,
                        "refinement_phase": context.refinement_phase,
                        "accepted": application.accepted,
                        "errors": application.errors,
                        "changed_components": application.changed_components,
                        "parent_signature": application.parent_signature,
                        "child_signature": application.child_signature,
                    }
                )
                if not application.accepted or application.program is None:
                    statistics.rejected_patches += 1
                    patch_rejections[patch_signature] = PatchRejectionFeedback(
                        patch_signature=patch_signature,
                        patch=patch_payload,
                        errors=application.errors,
                    )
                    iteration += 1
                    continue
                statistics.accepted_patches += 1
                child = self._evaluate_candidate(
                    scenario=scenario,
                    program=application.program,
                    candidate_id=f"candidate_{iteration:03d}",
                    parent_id=proposal_parent.candidate_id,
                    iteration=iteration,
                )
                statistics.evaluator_calls += 1
                child_counterexample = None
                if (
                    self.features.counterexample_memory_enabled
                    and not child.verification.feasible
                ):
                    child_counterexample = counterexamples.observe(
                        scenario=scenario,
                        verification=child.verification,
                        candidate_id=child.candidate_id,
                        ast_signature=child.ast_signature,
                        iteration=child.iteration,
                        conflict_graph_signature=(
                            child.conflict_graph.graph_signature
                            if child.conflict_graph
                            else None
                        ),
                    )
                if (
                    child.verification.feasible
                    and statistics.first_feasible_patch_proposal is None
                ):
                    statistics.first_feasible_patch_proposal = (
                        statistics.patch_proposals
                    )
                objective_evaluation = None
                if (
                    proposal_parent.verification.feasible
                    and proposal_parent.objective is not None
                    and child.verification.feasible
                    and child.objective is not None
                ):
                    improvement = (
                        proposal_parent.objective.weighted_objective
                        - child.objective.weighted_objective
                    )
                    objective_evaluation = ObjectivePatchEvaluation(
                        patch_signature=patch_signature,
                        patch=patch_payload,
                        parent_candidate_id=proposal_parent.candidate_id,
                        child_candidate_id=child.candidate_id,
                        parent_weighted_objective=(
                            proposal_parent.objective.weighted_objective
                        ),
                        child_weighted_objective=child.objective.weighted_objective,
                        improvement=improvement,
                        improved=improvement > 1e-9,
                    )
                    objective_patch_evaluations.append(objective_evaluation)
                behaviorally_unchanged = (
                    self._behavior_signature(proposal_parent)
                    == self._behavior_signature(child)
                )
                feasibility_improved = None
                outcome_rejected = False
                if context.refinement_phase == "feasibility":
                    feasibility_improved = self._feasibility_improved(
                        proposal_parent,
                        child,
                    )
                    if not feasibility_improved:
                        outcome_rejected = True
                        statistics.outcome_rejections += 1
                        statistics.rejected_patches += 1
                        reason = (
                            "deterministic execution produced unchanged placement, "
                            "routes, and violation profile; choose a different causal "
                            "component or operation"
                            if behaviorally_unchanged
                            else "deterministic verification did not improve any "
                            "violation without worsening another; revise the causal "
                            "direction or component"
                        )
                        patch_rejections[patch_signature] = PatchRejectionFeedback(
                            patch_signature=patch_signature,
                            patch=patch_payload,
                            errors=[reason],
                        )
                if (
                    self.features.counterexample_memory_enabled
                    and current_counterexample is not None
                    and child_counterexample is not None
                    and (
                        outcome_rejected
                        or child_counterexample.signature
                        == current_counterexample.signature
                    )
                ):
                    failed_counterexample = counterexamples.mark_repair_failure(
                        current_counterexample.signature
                    )
                    if (
                        child_counterexample.signature
                        == failed_counterexample.signature
                    ):
                        child_counterexample = failed_counterexample
                    if outcome_rejected:
                        current_counterexample = failed_counterexample
                if archive.add(child):
                    if outcome_rejected:
                        archive.block_expansion(
                            child.candidate_id,
                            reason="outcome_rejected",
                        )
                        current = proposal_parent
                    elif (
                        objective_evaluation is not None
                        and not objective_evaluation.improved
                    ):
                        current = objective_incumbent or archive.best_feasible() or current
                        current_counterexample = None
                    else:
                        current = child
                        current_counterexample = child_counterexample
                trajectory.append(
                    {
                        "event": "candidate_evaluated",
                        "candidate_id": child.candidate_id,
                        "parent_id": child.parent_id,
                        "category": child.category,
                        "feasible": child.verification.feasible,
                        "ast_signature": child.ast_signature,
                        "behaviorally_unchanged": behaviorally_unchanged,
                        "feasibility_improved": feasibility_improved,
                        "outcome_rejected": outcome_rejected,
                        "counterexample_id": (
                            child_counterexample.counterexample_id
                            if child_counterexample
                            else None
                        ),
                    }
                )
                objective_probe_needed = (
                    objective_evaluation is not None
                    and not objective_evaluation.improved
                )
                feasibility_probe_needed = (
                    context.refinement_phase == "feasibility"
                    and outcome_rejected
                    and (
                        not behaviorally_unchanged
                        or "node_score" in application.changed_components
                    )
                )
                if (
                    self.features.counterfactual_weight_probe_enabled
                    and (objective_probe_needed or feasibility_probe_needed)
                    and statistics.evaluator_calls < budgets.max_evaluator_calls
                ):
                    probe_patches = CounterfactualWeightProbe.propose_all(
                        parent=proposal_parent.program,
                        patch=patch,
                        blocked_operator_targets=context.blocked_operator_targets,
                    )
                    for probe_index, probe_patch in enumerate(probe_patches, 1):
                        if statistics.evaluator_calls >= budgets.max_evaluator_calls:
                            break
                        probe_signature = self._patch_semantic_signature(probe_patch)
                        seen_probe = (
                            probe_signature in patch_rejections
                            or any(
                                item.patch_signature == probe_signature
                                for item in objective_patch_evaluations
                            )
                        )
                        if seen_probe:
                            continue
                        probe_application = self.refiner.apply_patch(
                            parent=proposal_parent.program,
                            patch=probe_patch,
                            context=context,
                        )
                        trajectory.append(
                            {
                                "event": "counterfactual_probe_evaluated",
                                "parent_id": proposal_parent.candidate_id,
                                "patch": probe_patch.model_dump(mode="json"),
                                "patch_signature": probe_signature,
                                "accepted": probe_application.accepted,
                                "errors": probe_application.errors,
                                "changed_components": (
                                    probe_application.changed_components
                                ),
                                "source_patch_signature": patch_signature,
                            }
                        )
                        if (
                            not probe_application.accepted
                            or probe_application.program is None
                        ):
                            continue
                        statistics.accepted_patches += 1
                        statistics.numeric_probes += 1
                        probe_child = self._evaluate_candidate(
                            scenario=scenario,
                            program=probe_application.program,
                            candidate_id=(
                                f"candidate_{iteration:03d}_probe_{probe_index:02d}"
                            ),
                            parent_id=proposal_parent.candidate_id,
                            iteration=iteration,
                        )
                        statistics.evaluator_calls += 1
                        probe_evaluation = None
                        probe_feasibility_improved = None
                        if context.refinement_phase == "feasibility":
                            probe_feasibility_improved = self._feasibility_improved(
                                proposal_parent,
                                probe_child,
                            )
                        if (
                            probe_child.verification.feasible
                            and probe_child.objective is not None
                            and proposal_parent.objective is not None
                        ):
                            probe_improvement = (
                                proposal_parent.objective.weighted_objective
                                - probe_child.objective.weighted_objective
                            )
                            probe_evaluation = ObjectivePatchEvaluation(
                                patch_signature=probe_signature,
                                patch=probe_patch.model_dump(mode="json"),
                                parent_candidate_id=proposal_parent.candidate_id,
                                child_candidate_id=probe_child.candidate_id,
                                parent_weighted_objective=(
                                    proposal_parent.objective.weighted_objective
                                ),
                                child_weighted_objective=(
                                    probe_child.objective.weighted_objective
                                ),
                                improvement=probe_improvement,
                                improved=probe_improvement > 1e-9,
                                source="counterfactual_probe",
                            )
                            objective_patch_evaluations.append(probe_evaluation)
                        archive.add(probe_child)
                        if (
                            probe_evaluation is not None
                            and probe_evaluation.improved
                        ):
                            current = probe_child
                            current_counterexample = None
                        elif probe_feasibility_improved:
                            current = probe_child
                            current_counterexample = None
                            if (
                                probe_child.verification.feasible
                                and statistics.first_feasible_patch_proposal is None
                            ):
                                statistics.first_feasible_patch_proposal = (
                                    statistics.patch_proposals
                                )
                        trajectory.append(
                            {
                                "event": "candidate_evaluated",
                                "candidate_id": probe_child.candidate_id,
                                "parent_id": probe_child.parent_id,
                                "category": probe_child.category,
                                "feasible": probe_child.verification.feasible,
                                "ast_signature": probe_child.ast_signature,
                                "counterexample_id": None,
                                "source": "counterfactual_probe",
                                "feasibility_improved": (
                                    probe_feasibility_improved
                                ),
                            }
                        )
                        if (
                            (probe_evaluation is not None and probe_evaluation.improved)
                            or probe_feasibility_improved
                        ):
                            break
                if current.verification.feasible and budgets.stop_on_first_feasible:
                    stop_reason = "first_feasible"
                    break
                iteration += 1

        statistics.wall_time_ms = (time.perf_counter() - started) * 1000.0
        best = archive.best_feasible()
        diverse = (
            archive.diverse_feasible(limit=3, min_distance=0.05)
            if self.features.structural_diversity_enabled
            else []
        )
        replay_queue = [
            record.counterexample_id
            for record in counterexamples.ranked_for_replay()
        ]
        return SearchResult(
            records=archive.records,
            best_candidate_id=best.candidate_id if best else None,
            stop_reason=stop_reason,
            statistics=statistics,
            trajectory=trajectory,
            counterexamples=counterexamples.records,
            replay_queue=replay_queue,
            diverse_candidate_ids=[record.candidate_id for record in diverse],
            semantic_patch_rejections=list(patch_rejections.values()),
            objective_patch_evaluations=objective_patch_evaluations,
            initial_generation_trace=initial_generation_trace,
            features=self.features,
        )

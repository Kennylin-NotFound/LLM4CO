from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.config import AblationSuiteConfig, load_yaml
from cover_opt.domain.models import ScenarioInstance
from cover_opt.heuristics.handcrafted import (
    capacity_first,
    latency_first,
    latency_no_repair,
    migration_aware,
)
from cover_opt.llm.heuristic_generator import (
    HeuristicGenerationTrace,
    LLMHeuristicGenerator,
)
from cover_opt.llm.patch_generator import LLMPatchGenerator, PatchGenerationTrace
from cover_opt.llm.replay import ReplayLLM
from cover_opt.search.controller import SearchController, SearchResult
from cover_opt.search.generation import ScriptedPatchGenerator


class AblationVariantResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_id: str
    passed: bool
    checks: dict[str, bool]
    scenario_hash: str
    initial_violation_types: list[str]
    changed_components: list[str]
    prompt_contract: dict
    generation_trace: list[PatchGenerationTrace]
    initial_generation_trace: list[HeuristicGenerationTrace] = Field(
        default_factory=list
    )
    search_result: SearchResult


class AblationSuiteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_id: str
    passed: bool
    variant_count: int = Field(ge=2)
    passed_variant_count: int = Field(ge=0)
    variants: list[AblationVariantResult]
    runner_version: str = "1.0.0"


class AblationRunner:
    version = "1.0.0"

    @staticmethod
    def _program(name: str):
        programs = {
            "latency_first": latency_first,
            "capacity_first": capacity_first,
            "migration_aware": migration_aware,
            "latency_no_repair": latency_no_repair,
        }
        return programs[name]()

    @staticmethod
    def _scenario(path, overrides) -> ScenarioInstance:
        payload = load_yaml(path)
        payload.update(overrides.model_dump(mode="json", exclude_none=True))
        return ScenarioInstance.model_validate(payload)

    def run(self, config: AblationSuiteConfig) -> AblationSuiteResult:
        variant_results: list[AblationVariantResult] = []
        for variant in config.variants:
            scenario = self._scenario(
                variant.scenario_path,
                variant.scenario_overrides,
            )
            generation_events: list[PatchGenerationTrace] = []
            initial_generation_events: list[HeuristicGenerationTrace] = []
            initial_generator = None
            if variant.initial_generator == "replay":
                initial_generator = LLMHeuristicGenerator(
                    llm=ReplayLLM.from_file(variant.initial_replay_file),
                    prompt_template=variant.initial_prompt_path.read_text(
                        encoding="utf-8"
                    ),
                )
            if variant.generator == "replay":
                generator = LLMPatchGenerator.from_template_file(
                    llm=ReplayLLM.from_file(variant.replay_file),
                    path=variant.prompt_path,
                )
            else:
                generator = ScriptedPatchGenerator([])

            result = SearchController(features=variant.features).run(
                scenario=scenario,
                initial_program=self._program(variant.initial_heuristic),
                initial_generator=initial_generator,
                initial_generation_count=variant.initial_candidate_count,
                generator=generator,
                budgets=variant.budgets,
            )
            if initial_generator is not None:
                initial_generation_events = initial_generator.events
            if isinstance(generator, LLMPatchGenerator):
                generation_events = generator.events

            patch_events = [
                event
                for event in result.trajectory
                if event["event"] == "patch_evaluated"
            ]
            changed_components = sorted(
                {
                    component
                    for event in patch_events
                    for component in event["changed_components"]
                }
            )
            final_feasible = bool(result.best_candidate_id)
            initial = result.records[0]
            initial_records = [
                record
                for record in result.records
                if record.iteration == 0 and record.parent_id is None
            ]
            initial_selection = next(
                (
                    event
                    for event in result.trajectory
                    if event["event"] == "initial_candidate_selected"
                ),
                None,
            )
            initial_violation_types = sorted(
                {
                    violation.violation_type.value
                    for violation in initial.verification.violations
                }
            )
            checks = {
                "stop_reason": result.stop_reason == variant.expectation.stop_reason,
                "final_feasible": (
                    final_feasible == variant.expectation.final_feasible
                ),
                "initial_category": (
                    initial.category == variant.expectation.initial_category
                ),
                "accepted_patches": (
                    result.statistics.accepted_patches
                    == variant.expectation.accepted_patches
                ),
                "rejected_patches": (
                    result.statistics.rejected_patches
                    == variant.expectation.rejected_patches
                ),
                "evaluator_calls": (
                    result.statistics.evaluator_calls
                    == variant.expectation.evaluator_calls
                ),
                "counterexample_count": (
                    len(result.counterexamples)
                    == variant.expectation.counterexample_count
                ),
                "changed_components": (
                    changed_components == variant.expectation.changed_components
                ),
                "counterexample_replays": (
                    variant.expectation.counterexample_replays is None
                    or result.statistics.counterexample_replays
                    == variant.expectation.counterexample_replays
                ),
                "initial_candidate_count": (
                    variant.expectation.initial_candidate_count is None
                    or len(initial_records)
                    == variant.expectation.initial_candidate_count
                ),
                "selected_initial_source": (
                    variant.expectation.selected_initial_source is None
                    or (
                        initial_selection is not None
                        and initial_selection["source"]
                        == variant.expectation.selected_initial_source
                    )
                ),
                "initial_generation_calls": (
                    variant.expectation.initial_generation_calls is None
                    or result.statistics.initial_generation_calls
                    == variant.expectation.initial_generation_calls
                ),
                "patch_generation_calls": (
                    variant.expectation.patch_generation_calls is None
                    or result.statistics.patch_generation_calls
                    == variant.expectation.patch_generation_calls
                ),
                "total_llm_calls": (
                    variant.expectation.total_llm_calls is None
                    or result.statistics.total_llm_calls
                    == variant.expectation.total_llm_calls
                ),
            }
            prompt_contract = {
                "request_purpose": (
                    generation_events[0].request.purpose
                    if generation_events
                    else None
                ),
                "feedback_mode": (
                    generation_events[0].request.metadata.get("feedback_mode")
                    if generation_events
                    else None
                ),
                "contains_constraint_decision_graph": (
                    '"constraint_decision_graph"' in generation_events[0].request.prompt
                    if generation_events
                    else False
                ),
                "contains_counterexample_summary": (
                    '"counterexample_summary":null'
                    not in generation_events[0].request.prompt
                    if generation_events
                    else False
                ),
                "contains_feedback_details": (
                    any(
                        token in generation_events[0].request.prompt
                        for token in (
                            '"violations"',
                            '"constraint_decision_graph"',
                        )
                    )
                    if generation_events
                    else False
                ),
                "feasible_masks_enabled": result.features.feasible_masks_enabled,
                "counterexample_replay_enabled": (
                    result.features.counterexample_replay_enabled
                ),
                "initial_generation_calls": len(initial_generation_events),
                "initial_generation_accepted": sum(
                    event.status == "accepted"
                    for event in initial_generation_events
                ),
            }
            variant_results.append(
                AblationVariantResult(
                    variant_id=variant.variant_id,
                    passed=all(checks.values()),
                    checks=checks,
                    scenario_hash=scenario.stable_hash,
                    initial_violation_types=initial_violation_types,
                    changed_components=changed_components,
                    prompt_contract=prompt_contract,
                    generation_trace=generation_events,
                    initial_generation_trace=initial_generation_events,
                    search_result=result,
                )
            )

        passed_count = sum(item.passed for item in variant_results)
        return AblationSuiteResult(
            suite_id=config.suite_id,
            passed=passed_count == len(variant_results),
            variant_count=len(variant_results),
            passed_variant_count=passed_count,
            variants=variant_results,
        )

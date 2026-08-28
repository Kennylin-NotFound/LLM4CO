from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.baselines.code_runner import SolverCodeRunner
from cover_opt.baselines.models import GeneratedSolverArtifact, SolverExecutionOutcome
from cover_opt.domain.deployment import build_deployment_plan
from cover_opt.domain.models import ScenarioInstance, VerificationReport
from cover_opt.evaluation.solvers import SolverResult
from cover_opt.hashing import canonical_json
from cover_opt.llm.protocol import LLMProtocol, LLMRequest, LLMResponse, build_request
from cover_opt.objective.evaluator import ObjectiveEvaluator
from cover_opt.verifier.plan_verifier import PlanVerifier


class SolverGenerationBudgets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_llm_calls: int = Field(ge=1, default=3)
    max_execution_attempts: int = Field(ge=1, default=3)
    max_evaluator_calls: int = Field(ge=1, default=1)
    max_wall_time_seconds: float = Field(gt=0.0, default=30.0)


class SolverGenerationStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_calls: int = Field(ge=0, default=0)
    execution_attempts: int = Field(ge=0, default=0)
    evaluator_calls: int = Field(ge=0, default=0)
    execution_errors: int = Field(ge=0, default=0)
    modeling_errors: int = Field(ge=0, default=0)
    wall_time_ms: float = Field(ge=0.0, default=0.0)


class SolverGenerationTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int = Field(ge=0)
    request: LLMRequest
    response: LLMResponse
    artifact: GeneratedSolverArtifact
    execution: SolverExecutionOutcome
    feedback_category: Literal["none", "execution_error", "modeling_error"]
    verification: VerificationReport | None = None


class CurrentPaperBaselineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "feasible",
        "budget_exhausted",
        "generation_error",
        "runner_error",
    ]
    stop_reason: str
    solver_result: SolverResult | None = None
    statistics: SolverGenerationStatistics
    trajectory: list[SolverGenerationTrace]
    runner_safe_mode: str
    evidence_boundary: str = (
        "reconstructed_control_flow_with_replayed_code_execution_not_numeric_reproduction"
    )
    baseline_version: str = "1.0.0"


class CurrentPaperSolverGenBaseline:
    version = "1.0.0"

    def __init__(
        self,
        *,
        llm: LLMProtocol,
        runner: SolverCodeRunner,
        generation_template: str,
        correction_template: str,
    ) -> None:
        required_generation = {"{{SCENARIO_JSON}}", "{{ARTIFACT_SCHEMA_JSON}}"}
        required_correction = {"{{FEEDBACK_JSON}}", "{{ARTIFACT_SCHEMA_JSON}}"}
        if not all(token in generation_template for token in required_generation):
            raise ValueError("generation template is missing required placeholders")
        if not all(token in correction_template for token in required_correction):
            raise ValueError("correction template is missing required placeholders")
        self.llm = llm
        self.runner = runner
        self.generation_template = generation_template
        self.correction_template = correction_template
        self.verifier = PlanVerifier()
        self.evaluator = ObjectiveEvaluator()

    @staticmethod
    def _scenario_payload(scenario: ScenarioInstance) -> dict:
        return {
            "scenario_id": scenario.scenario_id,
            "scenario_hash": scenario.stable_hash,
            "nodes": [node.model_dump(mode="json") for node in scenario.nodes],
            "services": [
                service.model_dump(mode="json") for service in scenario.services
            ],
            "service_edges": [
                edge.model_dump(mode="json") for edge in scenario.service_edges
            ],
            "previous_placement": scenario.previous_placement,
            "qos_latency_ms": scenario.qos_latency_ms,
            "migration_budget": scenario.migration_budget,
            "objective": scenario.objective.model_dump(mode="json"),
        }

    def _request(
        self,
        *,
        scenario: ScenarioInstance,
        iteration: int,
        feedback: dict | None,
    ) -> LLMRequest:
        schema = canonical_json(GeneratedSolverArtifact.model_json_schema())
        if feedback is None:
            purpose = "current_paper_solver_generate"
            prompt = self.generation_template.replace(
                "{{SCENARIO_JSON}}",
                canonical_json(self._scenario_payload(scenario)),
            ).replace("{{ARTIFACT_SCHEMA_JSON}}", schema)
        else:
            category = feedback["category"]
            purpose = f"current_paper_solver_correct_{category}"
            prompt = self.correction_template.replace(
                "{{FEEDBACK_JSON}}",
                canonical_json(feedback),
            ).replace("{{ARTIFACT_SCHEMA_JSON}}", schema)
        return build_request(
            purpose=purpose,
            prompt=prompt,
            expected_output="GeneratedSolverArtifact JSON object",
            metadata={
                "baseline": "reconstructed_current_paper_solvergen",
                "scenario_hash": scenario.stable_hash,
                "iteration": iteration,
            },
        )

    def run(
        self,
        *,
        scenario: ScenarioInstance,
        budgets: SolverGenerationBudgets,
    ) -> CurrentPaperBaselineResult:
        started = time.perf_counter()
        statistics = SolverGenerationStatistics()
        trajectory: list[SolverGenerationTrace] = []
        feedback = None
        status = "budget_exhausted"
        stop_reason = "llm_call_budget"
        solver_result = None

        for iteration in range(budgets.max_llm_calls):
            if time.perf_counter() - started >= budgets.max_wall_time_seconds:
                stop_reason = "wall_time_budget"
                break
            if statistics.execution_attempts >= budgets.max_execution_attempts:
                stop_reason = "execution_budget"
                break
            request = self._request(
                scenario=scenario,
                iteration=iteration,
                feedback=feedback,
            )
            statistics.llm_calls += 1
            try:
                response = self.llm.generate(request)
                artifact = GeneratedSolverArtifact.model_validate(response.parsed)
                if artifact.iteration != iteration:
                    raise ValueError(
                        "generated artifact iteration mismatch: "
                        f"expected={iteration}, actual={artifact.iteration}"
                    )
            except Exception:
                statistics.wall_time_ms = (time.perf_counter() - started) * 1000.0
                return CurrentPaperBaselineResult(
                    status="generation_error",
                    stop_reason="generation_or_schema_error",
                    statistics=statistics,
                    trajectory=trajectory,
                    runner_safe_mode=self.runner.safe_mode,
                )
            try:
                execution = self.runner.execute(artifact)
                statistics.execution_attempts += 1
            except Exception:
                statistics.wall_time_ms = (time.perf_counter() - started) * 1000.0
                return CurrentPaperBaselineResult(
                    status="runner_error",
                    stop_reason="runner_replay_error",
                    statistics=statistics,
                    trajectory=trajectory,
                    runner_safe_mode=self.runner.safe_mode,
                )

            verification = None
            feedback_category: Literal[
                "none", "execution_error", "modeling_error"
            ] = "none"
            if execution.status == "success":
                if statistics.evaluator_calls >= budgets.max_evaluator_calls:
                    trajectory.append(
                        SolverGenerationTrace(
                            iteration=iteration,
                            request=request,
                            response=response,
                            artifact=artifact,
                            execution=execution,
                            feedback_category="none",
                        )
                    )
                    stop_reason = "evaluator_budget"
                    break
                plan = build_deployment_plan(
                    scenario=scenario,
                    placement=execution.placement,
                    routes=execution.routes,
                    method="reconstructed_current_paper_solvergen",
                    candidate_id=f"solvergen_{iteration:03d}",
                    run_id="current_paper_replay",
                )
                verification = self.verifier.verify(scenario, plan)
                statistics.evaluator_calls += 1
                if verification.feasible:
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    objective = self.evaluator.evaluate(
                        scenario,
                        plan,
                        verification,
                        planning_time_ms=elapsed_ms,
                    )
                    solver_result = SolverResult(
                        solver_name="reconstructed_current_paper_solvergen",
                        status="feasible",
                        plan=plan,
                        verification=verification,
                        objective=objective,
                        candidates_evaluated=statistics.evaluator_calls,
                        placement_assignments_considered=0,
                        planning_time_ms=elapsed_ms,
                        optimality_proven=False,
                        scope=(
                            "replayed ChatGPT-4/Gurobi-style solver-generation "
                            "control flow with shared verification"
                        ),
                        best_signature=artifact.artifact_hash,
                    )
                    status = "feasible"
                    stop_reason = "verified_plan"
                else:
                    execution = SolverExecutionOutcome(
                        attempt=execution.attempt,
                        status="modeling_error",
                        error_type="validation",
                        message=(
                            "shared PlanVerifier rejected generated solver output: "
                            + ",".join(
                                item.violation_type.value
                                for item in verification.violations
                            )
                        ),
                        solver_status="shared_verifier_rejected",
                    )

            if execution.status == "execution_error":
                statistics.execution_errors += 1
                feedback_category = "execution_error"
            elif execution.status == "modeling_error":
                statistics.modeling_errors += 1
                feedback_category = "modeling_error"

            trajectory.append(
                SolverGenerationTrace(
                    iteration=iteration,
                    request=request,
                    response=response,
                    artifact=artifact,
                    execution=execution,
                    feedback_category=feedback_category,
                    verification=verification,
                )
            )
            if status == "feasible":
                break
            feedback = {
                "category": feedback_category,
                "iteration": iteration,
                "artifact_hash": artifact.artifact_hash,
                "solver_status": execution.solver_status,
                "error_type": execution.error_type,
                "message": execution.message,
                "code_excerpt": artifact.code[:1000],
            }

        statistics.wall_time_ms = (time.perf_counter() - started) * 1000.0
        return CurrentPaperBaselineResult(
            status=status,
            stop_reason=stop_reason,
            solver_result=solver_result,
            statistics=statistics,
            trajectory=trajectory,
            runner_safe_mode=self.runner.safe_mode,
        )

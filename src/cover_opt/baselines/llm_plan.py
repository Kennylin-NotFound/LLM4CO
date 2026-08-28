from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.deployment import build_deployment_plan
from cover_opt.domain.models import RouteAssignment, ScenarioInstance
from cover_opt.evaluation.solvers import SolverResult
from cover_opt.hashing import canonical_json, sha256_json
from cover_opt.llm.protocol import LLMProtocol, LLMRequest, LLMResponse, build_request
from cover_opt.objective.evaluator import ObjectiveEvaluator
from cover_opt.verifier.plan_verifier import PlanVerifier


class DirectPlanArtifact(BaseModel):
    """Minimal one-shot plan contract without scenario identity binding."""

    model_config = ConfigDict(extra="forbid")

    placement: dict[str, str] = Field(min_length=1)
    routes: list[RouteAssignment]


class StructuredPlanArtifact(BaseModel):
    """Versioned one-shot plan contract bound to one scenario snapshot."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"]
    scenario_id: str = Field(min_length=1)
    scenario_hash: str = Field(min_length=1)
    placement: dict[str, str] = Field(min_length=1)
    routes: list[RouteAssignment]


class LLMPlanGenerationTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: LLMRequest
    response: LLMResponse | None = None
    generation_status: Literal[
        "schema_valid",
        "backend_error",
        "schema_error",
        "scenario_mismatch",
    ]
    artifact: dict[str, Any] | None = None
    error: str | None = None


class LLMPlanBaselineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_name: Literal["direct_llm_plan", "structured_llm_plan"]
    status: Literal["feasible", "infeasible", "generation_error"]
    stop_reason: str
    solver_result: SolverResult | None = None
    llm_calls: int = Field(ge=0)
    trajectory: list[LLMPlanGenerationTrace]
    evidence_boundary: str = (
        "one_shot_replay_control_evidence_not_live_llm_performance"
    )
    baseline_version: str = "1.0.0"


class _OneShotLLMPlanBaseline:
    baseline_name: Literal["direct_llm_plan", "structured_llm_plan"]
    purpose: str
    artifact_type: type[DirectPlanArtifact] | type[StructuredPlanArtifact]
    required_placeholders: tuple[str, ...]

    def __init__(self, *, llm: LLMProtocol, prompt_template: str) -> None:
        if not all(token in prompt_template for token in self.required_placeholders):
            raise ValueError(
                f"{self.baseline_name} prompt is missing required placeholders"
            )
        self.llm = llm
        self.prompt_template = prompt_template
        self.verifier = PlanVerifier()
        self.evaluator = ObjectiveEvaluator()

    @classmethod
    def from_template_file(
        cls,
        *,
        llm: LLMProtocol,
        path: Path,
    ) -> "_OneShotLLMPlanBaseline":
        return cls(llm=llm, prompt_template=path.read_text(encoding="utf-8"))

    @staticmethod
    def _scenario_payload(scenario: ScenarioInstance) -> dict[str, Any]:
        return {
            "scenario_id": scenario.scenario_id,
            "scenario_hash": scenario.stable_hash,
            "nodes": [item.model_dump(mode="json") for item in scenario.nodes],
            "links": [item.model_dump(mode="json") for item in scenario.links],
            "services": [
                item.model_dump(mode="json") for item in scenario.services
            ],
            "service_edges": [
                item.model_dump(mode="json") for item in scenario.service_edges
            ],
            "previous_placement": scenario.previous_placement,
            "qos_latency_ms": scenario.qos_latency_ms,
            "migration_budget": scenario.migration_budget,
            "objective": scenario.objective.model_dump(mode="json"),
        }

    def _request(self, scenario: ScenarioInstance) -> LLMRequest:
        prompt = self.prompt_template.replace(
            "{{SCENARIO_JSON}}",
            canonical_json(self._scenario_payload(scenario)),
        )
        if "{{ARTIFACT_SCHEMA_JSON}}" in prompt:
            prompt = prompt.replace(
                "{{ARTIFACT_SCHEMA_JSON}}",
                canonical_json(self.artifact_type.model_json_schema()),
            )
        return build_request(
            purpose=self.purpose,
            prompt=prompt,
            expected_output=f"{self.artifact_type.__name__} JSON object",
            metadata={
                "baseline": self.baseline_name,
                "scenario_id": scenario.scenario_id,
                "scenario_hash": scenario.stable_hash,
                "one_shot": True,
            },
        )

    def _validate_scenario_binding(
        self,
        scenario: ScenarioInstance,
        artifact: DirectPlanArtifact | StructuredPlanArtifact,
    ) -> None:
        del scenario, artifact

    def run(self, scenario: ScenarioInstance) -> LLMPlanBaselineResult:
        started = time.perf_counter()
        request = self._request(scenario)
        response: LLMResponse | None = None
        try:
            response = self.llm.generate(request)
        except Exception as exc:
            return LLMPlanBaselineResult(
                baseline_name=self.baseline_name,
                status="generation_error",
                stop_reason="backend_error",
                llm_calls=1,
                trajectory=[
                    LLMPlanGenerationTrace(
                        request=request,
                        generation_status="backend_error",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                ],
            )

        try:
            artifact = self.artifact_type.model_validate(response.parsed)
        except Exception as exc:
            return LLMPlanBaselineResult(
                baseline_name=self.baseline_name,
                status="generation_error",
                stop_reason="schema_error",
                llm_calls=1,
                trajectory=[
                    LLMPlanGenerationTrace(
                        request=request,
                        response=response,
                        generation_status="schema_error",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                ],
            )

        try:
            self._validate_scenario_binding(scenario, artifact)
        except ValueError as exc:
            return LLMPlanBaselineResult(
                baseline_name=self.baseline_name,
                status="generation_error",
                stop_reason="scenario_mismatch",
                llm_calls=1,
                trajectory=[
                    LLMPlanGenerationTrace(
                        request=request,
                        response=response,
                        generation_status="scenario_mismatch",
                        artifact=artifact.model_dump(mode="json"),
                        error=str(exc),
                    )
                ],
            )

        plan = build_deployment_plan(
            scenario=scenario,
            placement=artifact.placement,
            routes=artifact.routes,
            method=self.baseline_name,
            candidate_id=f"{self.baseline_name}_candidate_000",
            run_id=f"{self.baseline_name}_one_shot",
        )
        verification = self.verifier.verify(scenario, plan)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        objective = (
            self.evaluator.evaluate(
                scenario,
                plan,
                verification,
                planning_time_ms=elapsed_ms,
            )
            if verification.feasible
            else None
        )
        signature = sha256_json(
            {
                "placement": plan.placement,
                "routes": [item.model_dump(mode="json") for item in plan.routes],
            }
        )
        solver_result = SolverResult(
            solver_name=self.baseline_name,
            status="feasible" if verification.feasible else "infeasible",
            plan=plan,
            verification=verification,
            objective=objective,
            candidates_evaluated=1,
            placement_assignments_considered=1,
            planning_time_ms=elapsed_ms,
            optimality_proven=False,
            scope=(
                "one LLM plan generation followed by shared verification; "
                "no feedback, search, or repair"
            ),
            best_signature=signature if verification.feasible else None,
        )
        return LLMPlanBaselineResult(
            baseline_name=self.baseline_name,
            status="feasible" if verification.feasible else "infeasible",
            stop_reason="verified_plan" if verification.feasible else "infeasible_plan",
            solver_result=solver_result,
            llm_calls=1,
            trajectory=[
                LLMPlanGenerationTrace(
                    request=request,
                    response=response,
                    generation_status="schema_valid",
                    artifact=artifact.model_dump(mode="json"),
                )
            ],
        )


class DirectLLMPlanBaseline(_OneShotLLMPlanBaseline):
    baseline_name = "direct_llm_plan"
    purpose = "direct_llm_plan"
    artifact_type = DirectPlanArtifact
    required_placeholders = ("{{SCENARIO_JSON}}",)


class StructuredLLMPlanBaseline(_OneShotLLMPlanBaseline):
    baseline_name = "structured_llm_plan"
    purpose = "structured_llm_plan"
    artifact_type = StructuredPlanArtifact
    required_placeholders = ("{{SCENARIO_JSON}}", "{{ARTIFACT_SCHEMA_JSON}}")

    def _validate_scenario_binding(
        self,
        scenario: ScenarioInstance,
        artifact: DirectPlanArtifact | StructuredPlanArtifact,
    ) -> None:
        if not isinstance(artifact, StructuredPlanArtifact):
            raise TypeError("structured baseline requires StructuredPlanArtifact")
        if artifact.scenario_id != scenario.scenario_id:
            raise ValueError(
                "structured plan scenario_id mismatch: "
                f"expected={scenario.scenario_id}, actual={artifact.scenario_id}"
            )
        if artifact.scenario_hash != scenario.stable_hash:
            raise ValueError(
                "structured plan scenario_hash mismatch: "
                f"expected={scenario.stable_hash}, actual={artifact.scenario_hash}"
            )

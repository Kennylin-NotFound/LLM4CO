from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from cover_opt.hashing import canonical_json
from cover_opt.heuristics.patch import HeuristicPatch
from cover_opt.llm.protocol import LLMProtocol, LLMRequest, LLMResponse, build_request
from cover_opt.search.generation import PatchGenerationError
from cover_opt.search.refiner import RefinementContext


class PatchGenerationTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["schema_valid", "backend_error", "schema_error"]
    request: LLMRequest
    request_fingerprint: str
    response: LLMResponse | None = None
    error: str | None = None
    adapter_version: str = "1.0.0"


class LLMPatchGenerator:
    counts_as_llm_call = True

    def __init__(
        self,
        *,
        llm: LLMProtocol,
        prompt_template: str,
        purpose: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        if "{{CONTEXT_JSON}}" not in prompt_template:
            raise ValueError("prompt template is missing {{CONTEXT_JSON}}")
        if "{{PATCH_SCHEMA_JSON}}" not in prompt_template:
            raise ValueError("prompt template is missing {{PATCH_SCHEMA_JSON}}")
        self.llm = llm
        self.prompt_template = prompt_template
        self.purpose = purpose
        self.prompt_version = prompt_version
        self.events: list[PatchGenerationTrace] = []

    @classmethod
    def from_template_file(
        cls,
        *,
        llm: LLMProtocol,
        path: Path,
        purpose: str | None = None,
        prompt_version: str | None = None,
    ) -> "LLMPatchGenerator":
        with path.resolve().open("r", encoding="utf-8") as handle:
            return cls(
                llm=llm,
                prompt_template=handle.read(),
                purpose=purpose,
                prompt_version=prompt_version,
            )

    def _request(self, context: RefinementContext) -> LLMRequest:
        context_payload = {
            "parent_dsl": context.parent_dsl,
            "scenario_summary": context.scenario_summary,
            "feedback": context.feedback_payload,
            "operator_catalog": context.operator_catalog,
            "patch_affordances": context.patch_affordances,
            "execution_summary": context.execution_summary,
            "feedback_mode": context.feedback_mode,
            "refinement_phase": context.refinement_phase,
            "allowed_components": context.allowed_components,
            "allowed_features": context.allowed_features,
            "allowed_repair_actions": context.allowed_repair_actions,
            "objective_gap": context.objective_gap,
            "max_patch_operations": context.max_patch_operations,
            "counterexample_summary": context.counterexample_summary,
            "previous_patch_rejections": [
                item.model_dump(mode="json")
                for item in context.previous_patch_rejections
            ],
            "previous_objective_evaluations": [
                item.model_dump(mode="json")
                for item in context.previous_objective_evaluations
            ],
            "blocked_operator_targets": context.blocked_operator_targets,
        }
        prompt = self.prompt_template.replace(
            "{{CONTEXT_JSON}}",
            canonical_json(context_payload),
        ).replace(
            "{{PATCH_SCHEMA_JSON}}",
            canonical_json(HeuristicPatch.model_json_schema()),
        )
        purpose_by_mode = {
            "none": "no_feedback_patch",
            "generic": "generic_patch",
            "conflict_directed": "conflict_patch",
        }
        purpose = self.purpose or purpose_by_mode[context.feedback_mode]
        prompt_version = self.prompt_version or f"{purpose}_v1"
        return build_request(
            purpose=purpose,
            prompt=prompt,
            expected_output="HeuristicPatch JSON object, schema version 1.0",
            metadata={
                "prompt_version": prompt_version,
                "feedback_mode": context.feedback_mode,
                "refinement_phase": context.refinement_phase,
                "scenario_hash": context.scenario_summary["scenario_hash"],
                "conflict_graph_signature": (
                    context.conflict_graph.graph_signature
                    if context.feedback_mode != "none"
                    else None
                ),
                "allowed_components": context.allowed_components,
                "allowed_features": context.allowed_features,
                "allowed_repair_actions": context.allowed_repair_actions,
            },
        )

    def propose(self, context: RefinementContext) -> HeuristicPatch:
        request = self._request(context)
        try:
            response = self.llm.generate(request)
        except Exception as exc:
            trace = PatchGenerationTrace(
                status="backend_error",
                request=request,
                request_fingerprint=request.fingerprint,
                error=f"{type(exc).__name__}: {exc}",
            )
            self.events.append(trace)
            raise PatchGenerationError(
                "LLM patch backend failed",
                details=trace.model_dump(mode="json"),
            ) from exc

        try:
            patch = HeuristicPatch.model_validate(response.parsed)
        except ValidationError as exc:
            trace = PatchGenerationTrace(
                status="schema_error",
                request=request,
                request_fingerprint=request.fingerprint,
                response=response,
                error=str(exc),
            )
            self.events.append(trace)
            raise PatchGenerationError(
                "LLM response is not a valid HeuristicPatch",
                details=trace.model_dump(mode="json"),
            ) from exc

        self.events.append(
            PatchGenerationTrace(
                status="schema_valid",
                request=request,
                request_fingerprint=request.fingerprint,
                response=response,
            )
        )
        return patch

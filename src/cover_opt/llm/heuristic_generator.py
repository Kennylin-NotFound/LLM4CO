from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.models import ScenarioInstance
from cover_opt.hashing import canonical_json
from cover_opt.heuristics.schema import HeuristicDSL
from cover_opt.heuristics.static_verifier import DSLStaticVerifier, dsl_signature
from cover_opt.llm.protocol import LLMProtocol, LLMRequest, LLMResponse, build_request
from cover_opt.search.refiner import OPERATOR_CATALOG
from cover_opt.simulator.link_state import effective_rate_mbps


class InitialHeuristicGenerationError(RuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any]) -> None:
        super().__init__(message)
        self.details = details


class HeuristicGenerationTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "accepted",
        "backend_error",
        "schema_or_static_error",
        "duplicate",
    ]
    proposal_index: int
    request: LLMRequest
    request_fingerprint: str
    response: LLMResponse | None = None
    ast_signature: str | None = None
    errors: list[str] = Field(default_factory=list)
    adapter_version: str = "1.0.0"


class LLMHeuristicGenerator:
    counts_as_llm_call = True

    def __init__(
        self,
        *,
        llm: LLMProtocol,
        prompt_template: str,
        prompt_version: str = "initial_heuristic_v1",
    ) -> None:
        required = (
            "{{SCENARIO_JSON}}",
            "{{OPERATOR_CATALOG_JSON}}",
            "{{DSL_SCHEMA_JSON}}",
            "{{PROPOSAL_INDEX}}",
        )
        missing = [item for item in required if item not in prompt_template]
        if missing:
            raise ValueError(f"prompt template is missing placeholders: {missing}")
        self.llm = llm
        self.prompt_template = prompt_template
        self.prompt_version = prompt_version
        self.static_verifier = DSLStaticVerifier()
        self.events: list[HeuristicGenerationTrace] = []

    @staticmethod
    def _scenario_payload(scenario: ScenarioInstance) -> dict[str, Any]:
        return {
            "scenario_id": scenario.scenario_id,
            "scenario_hash": scenario.stable_hash,
            "time_slot": scenario.time_slot,
            "slot_duration_seconds": scenario.slot_duration_seconds,
            "nodes": [
                {
                    "node_id": node.node_id,
                    "compute_capacity": node.compute_capacity,
                    "memory_capacity": node.memory_capacity,
                    "compute_rate_mips": node.compute_rate_mips,
                }
                for node in scenario.nodes
            ],
            "links": [
                {
                    "link_id": link.link_id,
                    "source": link.source,
                    "target": link.target,
                    "effective_rate_mbps": effective_rate_mbps(link),
                    "available_from": link.available_from,
                    "available_until": link.available_until,
                }
                for link in scenario.links
            ],
            "services": [
                {
                    "service_id": service.service_id,
                    "compute_demand": service.compute_demand,
                    "memory_demand": service.memory_demand,
                    "workload_mi": service.workload_mi,
                    "eligible_nodes": service.eligible_nodes,
                }
                for service in scenario.services
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
        scenario: ScenarioInstance,
        *,
        proposal_index: int,
    ) -> LLMRequest:
        prompt = (
            self.prompt_template.replace(
                "{{SCENARIO_JSON}}",
                canonical_json(self._scenario_payload(scenario)),
            )
            .replace(
                "{{OPERATOR_CATALOG_JSON}}",
                canonical_json(OPERATOR_CATALOG),
            )
            .replace(
                "{{DSL_SCHEMA_JSON}}",
                canonical_json(HeuristicDSL.model_json_schema()),
            )
            .replace("{{PROPOSAL_INDEX}}", str(proposal_index))
        )
        return build_request(
            purpose="initial_heuristic",
            prompt=prompt,
            expected_output="HeuristicDSL JSON object, schema version 1.0",
            metadata={
                "prompt_version": self.prompt_version,
                "proposal_index": proposal_index,
                "scenario_hash": scenario.stable_hash,
            },
        )

    def generate_one(
        self,
        scenario: ScenarioInstance,
        *,
        proposal_index: int,
    ) -> HeuristicDSL:
        request = self._request(scenario, proposal_index=proposal_index)
        try:
            response = self.llm.generate(request)
        except Exception as exc:
            trace = HeuristicGenerationTrace(
                status="backend_error",
                proposal_index=proposal_index,
                request=request,
                request_fingerprint=request.fingerprint,
                errors=[f"{type(exc).__name__}: {exc}"],
            )
            self.events.append(trace)
            raise InitialHeuristicGenerationError(
                "LLM initial heuristic backend failed",
                details=trace.model_dump(mode="json"),
            ) from exc

        program, verification = self.static_verifier.parse_and_verify(
            response.parsed,
            scenario,
        )
        if program is None:
            trace = HeuristicGenerationTrace(
                status="schema_or_static_error",
                proposal_index=proposal_index,
                request=request,
                request_fingerprint=request.fingerprint,
                response=response,
                errors=verification.errors,
            )
            self.events.append(trace)
            raise InitialHeuristicGenerationError(
                "LLM response is not a valid initial heuristic",
                details=trace.model_dump(mode="json"),
            )

        signature = dsl_signature(program)
        self.events.append(
            HeuristicGenerationTrace(
                status="accepted",
                proposal_index=proposal_index,
                request=request,
                request_fingerprint=request.fingerprint,
                response=response,
                ast_signature=signature,
                errors=[],
            )
        )
        return program

    def generate_candidates(
        self,
        scenario: ScenarioInstance,
        *,
        count: int,
    ) -> list[HeuristicDSL]:
        if count < 0:
            raise ValueError("count must be non-negative")
        candidates: list[HeuristicDSL] = []
        signatures: set[str] = set()
        for proposal_index in range(count):
            try:
                program = self.generate_one(
                    scenario,
                    proposal_index=proposal_index,
                )
            except InitialHeuristicGenerationError:
                continue
            signature = dsl_signature(program)
            if signature in signatures:
                event = self.events[-1]
                self.events[-1] = event.model_copy(update={"status": "duplicate"})
                continue
            signatures.add(signature)
            candidates.append(program)
        return candidates

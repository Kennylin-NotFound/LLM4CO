from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.config import DeepSeekLivePilotConfig
from cover_opt.domain.models import ScenarioInstance
from cover_opt.evaluation.protocol import FormalExperimentProtocol
from cover_opt.hashing import sha256_text, sha256_tree
from cover_opt.heuristics.handcrafted import (
    capacity_first,
    latency_first,
    latency_no_repair,
    migration_aware,
)
from cover_opt.llm.deepseek import DeepSeekChatLLM, DeepSeekChatSettings
from cover_opt.llm.patch_generator import LLMPatchGenerator, PatchGenerationTrace
from cover_opt.llm.protocol import LLMProtocol
from cover_opt.search.controller import SearchController, SearchResult
from cover_opt.simulator.scenario_factory import load_scenario


class PilotModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PilotScenarioRecord(PilotModel):
    seed: int
    profile_id: str
    perturbations: dict[str, float]
    scenario: ScenarioInstance


class PilotCaseResult(PilotModel):
    seed: int
    profile_id: str
    scenario_hash: str
    scenario: ScenarioInstance
    initial_violation_types: list[str]
    final_violation_types: list[str]
    final_feasible: bool
    calls_to_first_feasible: int | None
    llm_calls: int = Field(ge=0)
    evaluator_calls: int = Field(ge=1)
    schema_failures: int = Field(ge=0)
    backend_failures: int = Field(ge=0)
    semantic_patch_rejections: int = Field(ge=0)
    duplicate_patch_rejections: int = Field(ge=0)
    cached_responses: int = Field(ge=0)
    billed_input_tokens: int = Field(ge=0)
    billed_output_tokens: int = Field(ge=0)
    estimated_cost_cny: float = Field(ge=0.0)
    observed_system_fingerprints: list[str]
    generation_trace: list[PatchGenerationTrace]
    search_result: SearchResult


class PilotSummary(PilotModel):
    case_count: int = Field(ge=1)
    feasible_count: int = Field(ge=0)
    feasible_rate: float = Field(ge=0.0, le=1.0)
    schema_failures: int = Field(ge=0)
    backend_failures: int = Field(ge=0)
    semantic_patch_rejections: int = Field(ge=0)
    duplicate_patch_rejections: int = Field(ge=0)
    total_llm_calls: int = Field(ge=0)
    total_evaluator_calls: int = Field(ge=0)
    total_cached_responses: int = Field(ge=0)
    total_billed_input_tokens: int = Field(ge=0)
    total_billed_output_tokens: int = Field(ge=0)
    total_estimated_cost_cny: float = Field(ge=0.0)
    mean_calls_to_first_feasible: float | None = None
    observed_system_fingerprints: list[str]


class DeepSeekLivePilotResult(PilotModel):
    pilot_id: str
    protocol_id: str
    protocol_hash: str
    stage_id: Literal["live_pilot"]
    claim_eligible: Literal[False] = False
    prompt_version: str
    prompt_hash: str
    code_tree_hash: str
    cases: list[PilotCaseResult] = Field(min_length=1)
    summary: PilotSummary
    evidence_status: str = (
        "live_pilot_diagnostic_evidence_not_claim_eligible_performance_evidence"
    )
    runner_version: str = "1.1.0"


class StaticPilotScenarioFactory:
    version = "1.0.0"

    _previous_placements = [
        {"ingest": "sat-a", "analyze": "sat-b", "respond": "sat-c"},
        {"ingest": "sat-b", "analyze": "sat-b", "respond": "sat-b"},
        {"ingest": "sat-a", "analyze": "sat-a", "respond": "sat-b"},
        {"ingest": "sat-b", "analyze": "sat-c", "respond": "sat-c"},
        {"ingest": "sat-b", "analyze": "sat-b", "respond": "sat-c"},
    ]

    @staticmethod
    def _factor(rng: random.Random, low: float, high: float) -> float:
        return round(rng.uniform(low, high), 6)

    @staticmethod
    def _validate_previous_placement(scenario: ScenarioInstance) -> None:
        nodes = {node.node_id: node for node in scenario.nodes}
        services = {service.service_id: service for service in scenario.services}
        compute = {node_id: 0.0 for node_id in nodes}
        memory = {node_id: 0.0 for node_id in nodes}
        for service_id, node_id in scenario.previous_placement.items():
            service = services[service_id]
            if node_id not in service.eligible_nodes:
                raise ValueError("pilot previous placement violates node eligibility")
            compute[node_id] += service.compute_demand
            memory[node_id] += service.memory_demand
        for node_id, node in nodes.items():
            if (
                compute[node_id] > node.compute_capacity
                or memory[node_id] > node.memory_capacity
            ):
                raise ValueError("pilot previous placement violates node capacity")

    def build(
        self,
        *,
        base: ScenarioInstance,
        seed: int,
        ordinal: int,
    ) -> PilotScenarioRecord:
        if not 0 <= ordinal < len(self._previous_placements):
            raise ValueError("pilot scenario ordinal is outside the fixed profile set")
        rng = random.Random(seed)
        compute_rate_factor = self._factor(rng, 0.90, 1.10)
        link_rate_factor = self._factor(rng, 0.88, 1.12)
        distance_factor = self._factor(rng, 0.92, 1.08)
        workload_factor = self._factor(rng, 0.90, 1.10)
        data_factor = self._factor(rng, 0.88, 1.12)
        payload = base.model_dump(mode="json")
        payload["scenario_id"] = f"pilot_static_seed_{seed}"
        payload["seed"] = seed
        payload["generator_version"] = f"pilot-static-{self.version}"
        payload["migration_budget"] = 0
        payload["qos_latency_ms"] = max(float(payload["qos_latency_ms"]), 300.0)
        payload["previous_placement"] = dict(self._previous_placements[ordinal])
        for node in payload["nodes"]:
            node["compute_rate_mips"] = round(
                node["compute_rate_mips"] * compute_rate_factor,
                6,
            )
        for link in payload["links"]:
            link["transmission_rate_mbps"] = round(
                link["transmission_rate_mbps"] * link_rate_factor,
                6,
            )
            link["bandwidth_mbps"] = round(
                link["bandwidth_mbps"] * link_rate_factor,
                6,
            )
            link["distance_km"] = round(
                link["distance_km"] * distance_factor,
                6,
            )
        for service in payload["services"]:
            service["workload_mi"] = round(
                service["workload_mi"] * workload_factor,
                6,
            )
        for edge in payload["service_edges"]:
            edge["data_volume_mbit"] = round(
                edge["data_volume_mbit"] * data_factor,
                6,
            )
        payload["provenance"]["source_reference"] = (
            "docs/live_pilot_protocol.md#bounded-static-pilot-scenarios"
        )
        payload["provenance"]["notes"] = (
            "Deterministic bounded perturbation for live method diagnostics; "
            "not a calibrated network simulation."
        )
        scenario = ScenarioInstance.model_validate(payload)
        self._validate_previous_placement(scenario)
        return PilotScenarioRecord(
            seed=seed,
            profile_id=f"migration_lock_profile_{ordinal}",
            perturbations={
                "compute_rate_factor": compute_rate_factor,
                "link_rate_factor": link_rate_factor,
                "distance_factor": distance_factor,
                "workload_factor": workload_factor,
                "data_factor": data_factor,
            },
            scenario=scenario,
        )


class DeepSeekLivePilotRunner:
    version = "1.1.0"

    def __init__(
        self,
        *,
        llm_factory: Callable[[DeepSeekChatSettings], LLMProtocol] | None = None,
    ) -> None:
        self.llm_factory = llm_factory or DeepSeekChatLLM.from_settings
        self.scenario_factory = StaticPilotScenarioFactory()

    @staticmethod
    def _validate_contract(
        config: DeepSeekLivePilotConfig,
        protocol: FormalExperimentProtocol,
        prompt_hash: str,
    ) -> list[int]:
        if prompt_hash != config.expected_prompt_hash:
            raise ValueError(
                "pilot Prompt hash mismatch: "
                f"expected={config.expected_prompt_hash}, actual={prompt_hash}"
            )
        if not protocol.live_model_lock.live_calls_allowed:
            raise ValueError("formal protocol has live calls disabled")
        if protocol.live_model_lock.provider != "deepseek":
            raise ValueError("formal protocol provider is not deepseek")
        if protocol.live_model_lock.model_snapshot != config.llm.model:
            raise ValueError("pilot model does not match protocol model lock")
        if (
            protocol.live_model_lock.system_fingerprint
            != config.llm.expected_system_fingerprint
        ):
            raise ValueError("pilot fingerprint does not match protocol lock")
        if protocol.live_model_lock.temperature != config.llm.temperature:
            raise ValueError("pilot temperature does not match protocol lock")
        if protocol.live_model_lock.top_p != config.llm.top_p:
            raise ValueError("pilot top_p does not match protocol lock")
        stage = next(
            (item for item in protocol.stages if item.stage_id == config.stage_id),
            None,
        )
        if stage is None or stage.purpose != "pilot" or stage.claim_eligible:
            raise ValueError("live_pilot stage contract is missing or claim eligible")
        if stage.llm_repetitions != 1:
            raise ValueError("pilot runner currently requires one LLM repetition")
        method = next(
            item for item in protocol.methods if item.method_id == "cover_opt_full"
        )
        if config.budgets.max_patch_proposals > method.max_llm_calls:
            raise ValueError("pilot LLM budget exceeds cover_opt_full contract")
        if config.budgets.max_evaluator_calls > method.max_evaluator_calls:
            raise ValueError("pilot evaluator budget exceeds cover_opt_full contract")
        worst_case_cost = len(stage.scenario_seeds) * (
            config.budgets.max_patch_proposals
            * (
                config.cost_policy.assumed_max_input_tokens_per_call
                * config.cost_policy.input_cache_miss_cny_per_million
                + config.llm.max_tokens
                * config.cost_policy.output_cny_per_million
            )
            / 1_000_000
        )
        if worst_case_cost > config.cost_policy.max_total_cost_cny:
            raise ValueError(
                f"pilot worst-case cost {worst_case_cost:.6f} exceeds cap"
            )
        return stage.scenario_seeds

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
    def _case_result(
        *,
        scenario_record: PilotScenarioRecord,
        generation_trace: list[PatchGenerationTrace],
        search_result: SearchResult,
        config: DeepSeekLivePilotConfig,
    ) -> PilotCaseResult:
        initial = search_result.records[0]
        final = next(
            (
                item
                for item in search_result.records
                if item.candidate_id == search_result.best_candidate_id
            ),
            search_result.records[-1],
        )
        responses = [
            item.response for item in generation_trace if item.response is not None
        ]
        billed = [item for item in responses if not item.cached]
        input_tokens = sum(item.usage.input_tokens for item in billed)
        output_tokens = sum(item.usage.output_tokens for item in billed)
        cost = (
            input_tokens
            * config.cost_policy.input_cache_miss_cny_per_million
            + output_tokens * config.cost_policy.output_cny_per_million
        ) / 1_000_000
        return PilotCaseResult(
            seed=scenario_record.seed,
            profile_id=scenario_record.profile_id,
            scenario_hash=scenario_record.scenario.stable_hash,
            scenario=scenario_record.scenario,
            initial_violation_types=sorted(
                {
                    item.violation_type.value
                    for item in initial.verification.violations
                }
            ),
            final_violation_types=sorted(
                {
                    item.violation_type.value
                    for item in final.verification.violations
                }
            ),
            final_feasible=final.verification.feasible,
            calls_to_first_feasible=(
                search_result.statistics.first_feasible_patch_proposal
            ),
            llm_calls=len(generation_trace),
            evaluator_calls=search_result.statistics.evaluator_calls,
            schema_failures=sum(
                item.status == "schema_error" for item in generation_trace
            ),
            backend_failures=sum(
                item.status == "backend_error" for item in generation_trace
            ),
            semantic_patch_rejections=sum(
                item.occurrence_count
                for item in search_result.semantic_patch_rejections
            ),
            duplicate_patch_rejections=sum(
                item["event"] == "duplicate_patch_rejected"
                for item in search_result.trajectory
            ),
            cached_responses=sum(item.cached for item in responses),
            billed_input_tokens=input_tokens,
            billed_output_tokens=output_tokens,
            estimated_cost_cny=cost,
            observed_system_fingerprints=sorted(
                {
                    str(item.metadata["system_fingerprint"])
                    for item in responses
                    if item.metadata.get("system_fingerprint")
                }
            ),
            generation_trace=generation_trace,
            search_result=search_result,
        )

    @staticmethod
    def _summary(cases: list[PilotCaseResult]) -> PilotSummary:
        successful_calls = [
            item.calls_to_first_feasible
            for item in cases
            if item.calls_to_first_feasible is not None
        ]
        feasible_count = sum(item.final_feasible for item in cases)
        return PilotSummary(
            case_count=len(cases),
            feasible_count=feasible_count,
            feasible_rate=feasible_count / len(cases),
            schema_failures=sum(item.schema_failures for item in cases),
            backend_failures=sum(item.backend_failures for item in cases),
            semantic_patch_rejections=sum(
                item.semantic_patch_rejections for item in cases
            ),
            duplicate_patch_rejections=sum(
                item.duplicate_patch_rejections for item in cases
            ),
            total_llm_calls=sum(item.llm_calls for item in cases),
            total_evaluator_calls=sum(item.evaluator_calls for item in cases),
            total_cached_responses=sum(item.cached_responses for item in cases),
            total_billed_input_tokens=sum(
                item.billed_input_tokens for item in cases
            ),
            total_billed_output_tokens=sum(
                item.billed_output_tokens for item in cases
            ),
            total_estimated_cost_cny=sum(
                item.estimated_cost_cny for item in cases
            ),
            mean_calls_to_first_feasible=(
                sum(successful_calls) / len(successful_calls)
                if successful_calls
                else None
            ),
            observed_system_fingerprints=sorted(
                {
                    fingerprint
                    for item in cases
                    for fingerprint in item.observed_system_fingerprints
                }
            ),
        )

    def run(
        self,
        *,
        config: DeepSeekLivePilotConfig,
        protocol: FormalExperimentProtocol,
    ) -> DeepSeekLivePilotResult:
        prompt_text = config.prompt_path.read_text(encoding="utf-8")
        prompt_hash = sha256_text(prompt_text)
        seeds = self._validate_contract(config, protocol, prompt_hash)
        base = load_scenario(config.base_scenario_path)
        cases: list[PilotCaseResult] = []
        for ordinal, seed in enumerate(seeds):
            scenario_record = self.scenario_factory.build(
                base=base,
                seed=seed,
                ordinal=ordinal,
            )
            generator = LLMPatchGenerator(
                llm=self.llm_factory(config.llm),
                prompt_template=prompt_text,
                prompt_version=config.prompt_version,
            )
            search_result = SearchController(features=config.features).run(
                scenario=scenario_record.scenario,
                initial_program=self._program(config.initial_heuristic),
                generator=generator,
                budgets=config.budgets,
            )
            cases.append(
                self._case_result(
                    scenario_record=scenario_record,
                    generation_trace=generator.events,
                    search_result=search_result,
                    config=config,
                )
            )
        summary = self._summary(cases)
        if summary.total_estimated_cost_cny > config.cost_policy.max_total_cost_cny:
            raise ValueError("observed pilot cost exceeded the configured cap")
        source_root = Path(__file__).resolve().parents[1]
        return DeepSeekLivePilotResult(
            pilot_id=config.pilot_id,
            protocol_id=protocol.protocol_id,
            protocol_hash=protocol.protocol_hash,
            stage_id=config.stage_id,
            prompt_version=config.prompt_version,
            prompt_hash=prompt_hash,
            code_tree_hash=sha256_tree(source_root),
            cases=cases,
            summary=summary,
        )

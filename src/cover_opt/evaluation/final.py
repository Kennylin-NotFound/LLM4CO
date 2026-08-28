from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.baselines.llm_plan import (
    DirectLLMPlanBaseline,
    LLMPlanBaselineResult,
    StructuredLLMPlanBaseline,
)
from cover_opt.config import DeepSeekPairedFinalConfig
from cover_opt.domain.deployment import build_deployment_plan
from cover_opt.domain.models import ScenarioInstance, VerificationReport
from cover_opt.evaluation.protocol import FormalExperimentProtocol, MethodBudget
from cover_opt.evaluation.solvers import (
    ExactEnumerationOracle,
    HeuristicBaseline,
    RandomBaseline,
    SolverResult,
)
from cover_opt.hashing import sha256_file, sha256_json, sha256_text, sha256_tree
from cover_opt.heuristics.executor import DeterministicExecutor
from cover_opt.heuristics.handcrafted import (
    capacity_no_repair,
    latency_first,
    latency_no_repair,
)
from cover_opt.llm.deepseek import DeepSeekChatLLM, DeepSeekChatSettings
from cover_opt.llm.patch_generator import LLMPatchGenerator, PatchGenerationTrace
from cover_opt.llm.protocol import LLMProtocol, LLMRequest, LLMResponse, build_request
from cover_opt.objective.evaluator import ObjectiveEvaluator
from cover_opt.search.budgets import SearchBudgets
from cover_opt.search.controller import SearchController, SearchResult
from cover_opt.simulator.link_state import select_deterministic_routes
from cover_opt.simulator.scenario_factory import load_scenario
from cover_opt.verifier.plan_verifier import PlanVerifier


class FinalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FinalScenarioRecord(FinalModel):
    seed: int
    profile_id: Literal[
        "migration_lock",
        "qos_tight",
        "joint_constraint",
        "objective_control",
    ]
    perturbations: dict[str, float]
    qos_anchor_latency_ms: float
    expected_initial_violation_types: list[str]
    scenario: ScenarioInstance


class PreflightCase(FinalModel):
    seed: int
    profile_id: str
    scenario_hash: str
    initial_placement: dict[str, str]
    initial_violation_types: list[str]
    initial_feasible: bool
    oracle_status: str
    oracle_optimality_proven: bool
    oracle_weighted_objective: float | None
    solver_results: list[SolverResult]
    checks_passed: bool


class CostForecast(FinalModel):
    llm_run_count: int = Field(ge=0)
    maximum_llm_calls: int = Field(ge=0)
    assumed_input_tokens_per_call: int = Field(ge=1)
    maximum_output_tokens_per_call: int = Field(ge=1)
    worst_case_cost_cny: float = Field(ge=0.0)
    configured_cost_cap_cny: float = Field(gt=0.0)


class PairedFinalPreflight(FinalModel):
    experiment_id: str
    protocol_id: str
    protocol_version: str
    protocol_hash: str
    config_hash: str
    code_tree_hash: str
    scenario_factory_version: str
    scenario_set_hash: str
    prompt_hashes: dict[str, str]
    cases: list[PreflightCase]
    cost_forecast: CostForecast
    passed: bool
    evidence_status: str = "offline_preflight_not_live_performance_evidence"
    runner_version: str = "1.0.0"


class FinalRunRecord(FinalModel):
    run_key: str
    experiment_id: str
    protocol_hash: str
    config_hash: str
    code_tree_hash: str
    scenario_seed: int
    scenario_profile: str
    scenario_hash: str
    llm_repetition: int
    method_id: str
    method_family: str
    provider: str
    model_snapshot: str
    prompt_hash: str | None
    request_parameters: dict[str, Any]
    budget: dict[str, Any]
    status: str
    final_feasible: bool
    weighted_objective: float | None
    candidate_set_gap_pct: float | None
    calls_to_first_feasible: int | None
    violation_burden: float
    schema_failures: int = Field(ge=0, default=0)
    backend_failures: int = Field(ge=0, default=0)
    llm_calls: int = Field(ge=0)
    evaluator_calls: int = Field(ge=0)
    cached_responses: int = Field(ge=0, default=0)
    billed_input_tokens: int = Field(ge=0, default=0)
    billed_output_tokens: int = Field(ge=0, default=0)
    estimated_cost_cny: float = Field(ge=0.0, default=0.0)
    wall_time_ms: float = Field(ge=0.0)
    stop_reason: str
    observed_system_fingerprints: list[str]
    infrastructure_failure: bool = False
    result_payload: dict[str, Any]
    runner_version: str = "1.0.0"


class PairedFinalManifest(FinalModel):
    experiment_id: str
    protocol_hash: str
    config_hash: str
    code_tree_hash: str
    scenario_set_hash: str
    expected_run_count: int
    completed_run_count: int
    infrastructure_failure_count: int
    total_billed_input_tokens: int
    total_billed_output_tokens: int
    total_estimated_cost_cny: float
    run_files: list[str]
    complete: bool
    evidence_status: str = "claim_eligible_only_after_statistics_and_quality_gates"
    runner_version: str = "1.0.0"


class PairedFinalScenarioFactory:
    version = "paired-static-1.1.0"
    profiles = (
        "migration_lock",
        "qos_tight",
        "joint_constraint",
        "objective_control",
    )
    previous_aab = {
        "ingest": "sat-a",
        "analyze": "sat-a",
        "respond": "sat-b",
    }
    previous_bbb = {
        "ingest": "sat-b",
        "analyze": "sat-b",
        "respond": "sat-b",
    }

    @staticmethod
    def _factor(rng: random.Random, low: float, high: float) -> float:
        return round(rng.uniform(low, high), 6)

    @staticmethod
    def _anchor_latency(payload: dict[str, Any]) -> float:
        draft = dict(payload)
        draft["qos_latency_ms"] = 1_000_000.0
        draft["migration_budget"] = len(draft["services"])
        draft["previous_placement"] = dict(PairedFinalScenarioFactory.previous_bbb)
        scenario = ScenarioInstance.model_validate(draft)
        routes = select_deterministic_routes(
            scenario,
            PairedFinalScenarioFactory.previous_bbb,
            k_paths=3,
        )
        plan = build_deployment_plan(
            scenario=scenario,
            placement=PairedFinalScenarioFactory.previous_bbb,
            routes=routes,
            method="qos_anchor",
            candidate_id="qos_anchor",
            run_id="scenario_factory",
        )
        verification = PlanVerifier().verify(scenario, plan)
        return ObjectiveEvaluator().evaluate(
            scenario,
            plan,
            verification,
        ).e2e_latency_ms

    def build(self, *, base: ScenarioInstance, seed: int) -> FinalScenarioRecord:
        if not (200 <= seed <= 219 or 300 <= seed <= 319):
            raise ValueError(
                "paired-final factory only accepts frozen seed cohorts "
                "200..219 or 300..319"
            )
        rng = random.Random(seed)
        factors = {
            "compute_rate_factor": self._factor(rng, 0.85, 1.15),
            "link_rate_factor": self._factor(rng, 0.80, 1.20),
            "distance_factor": self._factor(rng, 0.90, 1.10),
            "workload_factor": self._factor(rng, 0.80, 1.20),
            "data_factor": self._factor(rng, 0.80, 1.20),
        }
        payload = base.model_dump(mode="json")
        profile_id = self.profiles[(seed - 200) % len(self.profiles)]
        payload["scenario_id"] = f"paired_final_{profile_id}_seed_{seed}"
        payload["seed"] = seed
        payload["generator_version"] = self.version
        for node in payload["nodes"]:
            node["compute_rate_mips"] = round(
                node["compute_rate_mips"] * factors["compute_rate_factor"], 6
            )
        for link in payload["links"]:
            link["transmission_rate_mbps"] = round(
                link["transmission_rate_mbps"] * factors["link_rate_factor"], 6
            )
            link["bandwidth_mbps"] = round(
                link["bandwidth_mbps"] * factors["link_rate_factor"], 6
            )
            link["distance_km"] = round(
                link["distance_km"] * factors["distance_factor"], 6
            )
        for service in payload["services"]:
            service["workload_mi"] = round(
                service["workload_mi"] * factors["workload_factor"], 6
            )
        for edge in payload["service_edges"]:
            edge["data_volume_mbit"] = round(
                edge["data_volume_mbit"] * factors["data_factor"], 6
            )

        anchor = self._anchor_latency(payload)
        tight_qos = round(anchor * 1.05, 6)
        relaxed_qos = round(max(300.0, anchor * 2.0), 6)
        if profile_id == "migration_lock":
            payload["previous_placement"] = dict(self.previous_bbb)
            payload["migration_budget"] = 0
            payload["qos_latency_ms"] = relaxed_qos
            expected = ["migration_budget"]
        elif profile_id == "qos_tight":
            payload["previous_placement"] = dict(self.previous_aab)
            payload["migration_budget"] = 3
            payload["qos_latency_ms"] = tight_qos
            expected = ["qos_latency"]
        elif profile_id == "joint_constraint":
            payload["previous_placement"] = dict(self.previous_bbb)
            payload["migration_budget"] = 0
            payload["qos_latency_ms"] = tight_qos
            expected = ["migration_budget", "qos_latency"]
        else:
            payload["previous_placement"] = dict(self.previous_aab)
            payload["migration_budget"] = 3
            payload["qos_latency_ms"] = relaxed_qos
            expected = []
        payload["provenance"]["source_reference"] = (
            "docs/paired_final_protocol.md#scenario-profiles"
        )
        payload["provenance"]["notes"] = (
            "Controlled deterministic stress benchmark for method comparison; "
            "not a calibrated satellite-network simulation."
        )
        scenario = ScenarioInstance.model_validate(payload)
        return FinalScenarioRecord(
            seed=seed,
            profile_id=profile_id,
            perturbations=factors,
            qos_anchor_latency_ms=anchor,
            expected_initial_violation_types=expected,
            scenario=scenario,
        )


class RunBoundLLM:
    """Bind cache identity to one preregistered run without changing the prompt."""

    def __init__(self, inner: LLMProtocol, *, run_key: str) -> None:
        self.inner = inner
        self.provider = inner.provider
        self.model = inner.model
        self.run_key = run_key
        self.call_index = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.call_index += 1
        metadata = dict(request.metadata)
        metadata.update(
            {
                "paired_final_run_key": self.run_key,
                "paired_final_call_index": self.call_index,
            }
        )
        bound = build_request(
            purpose=request.purpose,
            prompt=request.prompt,
            expected_output=request.expected_output,
            metadata=metadata,
        )
        return self.inner.generate(bound)


def _write_json_atomic(path: Path, payload: Any) -> Path:
    output = path.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(output)
    return output


def _final_verification(search_result: SearchResult) -> VerificationReport:
    record = next(
        (
            item
            for item in search_result.records
            if item.candidate_id == search_result.best_candidate_id
        ),
        search_result.records[-1],
    )
    return record.verification


class PairedFinalRunner:
    version = "1.0.0"

    def __init__(
        self,
        *,
        llm_factory: Callable[[DeepSeekChatSettings], LLMProtocol] | None = None,
    ) -> None:
        self.scenario_factory = PairedFinalScenarioFactory()
        self.llm_factory = llm_factory or DeepSeekChatLLM.from_settings

    @staticmethod
    def _stage(protocol: FormalExperimentProtocol):
        return next(item for item in protocol.stages if item.stage_id == "paired_final")

    @staticmethod
    def _method(protocol: FormalExperimentProtocol, method_id: str) -> MethodBudget:
        return next(item for item in protocol.methods if item.method_id == method_id)

    @staticmethod
    def _program(name: str):
        programs = {"latency_first": latency_first}
        if name not in programs:
            raise ValueError(f"unsupported paired-final initial heuristic: {name}")
        return programs[name]()

    @staticmethod
    def _prompt_path(protocol_path: Path, method: MethodBudget) -> Path | None:
        if method.prompt_path is None:
            return None
        path = Path(method.prompt_path)
        return path if path.is_absolute() else protocol_path.resolve().parent / path

    def _validate_contract(
        self,
        *,
        config: DeepSeekPairedFinalConfig,
        protocol: FormalExperimentProtocol,
    ) -> tuple[list[int], dict[str, str]]:
        if protocol.version not in {"1.3.0", "1.4.0"}:
            raise ValueError("paired-final runner requires protocol v1.3.0 or v1.4.0")
        lock = protocol.live_model_lock
        if not lock.live_calls_allowed or lock.provider != "deepseek":
            raise ValueError("paired-final protocol is not unlocked for DeepSeek")
        if lock.model_snapshot != config.llm.model:
            raise ValueError("paired-final model does not match protocol lock")
        if lock.system_fingerprint != config.llm.expected_system_fingerprint:
            raise ValueError("paired-final system fingerprint does not match lock")
        if lock.temperature != config.llm.temperature or lock.top_p != config.llm.top_p:
            raise ValueError("paired-final sampling parameters do not match lock")
        if lock.max_output_tokens != config.llm.max_tokens:
            raise ValueError("paired-final token budget does not match lock")
        methods = {item.method_id: item for item in protocol.methods}
        unknown = set(config.method_ids) - set(methods)
        if unknown:
            raise ValueError(f"paired-final config has unknown methods: {sorted(unknown)}")
        prompt_hashes: dict[str, str] = {}
        for method_id in config.method_ids:
            method = methods[method_id]
            if method.family in {"one_shot_llm", "iterative_llm"}:
                if not method.live_comparable or not method.claim_eligible:
                    raise ValueError(f"method {method_id} is not live-claim comparable")
                path = self._prompt_path(config.protocol_path, method)
                if path is None:
                    raise ValueError(f"method {method_id} has no prompt path")
                actual = sha256_text(path.read_text(encoding="utf-8"))
                if actual != method.prompt_hash:
                    raise ValueError(
                        f"method {method_id} prompt hash mismatch: "
                        f"expected={method.prompt_hash}, actual={actual}"
                    )
                prompt_hashes[method_id] = actual
        stage = self._stage(protocol)
        if not stage.claim_eligible or stage.llm_repetitions != 3:
            raise ValueError("paired-final stage must be claim eligible with 3 repetitions")
        return stage.scenario_seeds, prompt_hashes

    def _forecast(
        self,
        *,
        config: DeepSeekPairedFinalConfig,
        protocol: FormalExperimentProtocol,
        seed_count: int,
    ) -> CostForecast:
        repetitions = self._stage(protocol).llm_repetitions
        llm_methods = [
            self._method(protocol, method_id)
            for method_id in config.method_ids
            if self._method(protocol, method_id).max_llm_calls > 0
        ]
        maximum_calls = seed_count * repetitions * sum(
            method.max_llm_calls for method in llm_methods
        )
        per_call = (
            config.cost_policy.assumed_max_input_tokens_per_call
            * config.cost_policy.input_cache_miss_cny_per_million
            + config.llm.max_tokens * config.cost_policy.output_cny_per_million
        ) / 1_000_000
        worst = maximum_calls * per_call
        if worst > config.cost_policy.max_total_cost_cny:
            raise ValueError(
                f"paired-final worst-case cost {worst:.6f} exceeds configured cap"
            )
        return CostForecast(
            llm_run_count=seed_count * repetitions * len(llm_methods),
            maximum_llm_calls=maximum_calls,
            assumed_input_tokens_per_call=(
                config.cost_policy.assumed_max_input_tokens_per_call
            ),
            maximum_output_tokens_per_call=config.llm.max_tokens,
            worst_case_cost_cny=worst,
            configured_cost_cap_cny=config.cost_policy.max_total_cost_cny,
        )

    def preflight(
        self,
        *,
        config: DeepSeekPairedFinalConfig,
        protocol: FormalExperimentProtocol,
        config_hash: str,
    ) -> PairedFinalPreflight:
        seeds, prompt_hashes = self._validate_contract(
            config=config,
            protocol=protocol,
        )
        base = load_scenario(config.base_scenario_path)
        cases: list[PreflightCase] = []
        scenario_index: list[dict[str, Any]] = []
        for seed in seeds:
            record = self.scenario_factory.build(base=base, seed=seed)
            scenario = record.scenario
            initial_execution = DeterministicExecutor(
                k_paths=config.k_paths,
                enable_repair_actions=False,
            ).execute(
                scenario,
                latency_no_repair(),
                method="paired_final_initial_contract",
                candidate_id="initial_contract",
                run_id="preflight",
            )
            initial_verification = PlanVerifier().verify(
                scenario,
                initial_execution.plan,
            )
            initial_types = sorted(
                {item.violation_type.value for item in initial_verification.violations}
            )
            oracle = ExactEnumerationOracle(
                k_paths=config.k_paths,
                max_candidates=config.exact_max_candidates,
                max_wall_time_seconds=config.exact_max_wall_time_seconds,
            ).solve(scenario)
            baselines = [
                oracle,
                HeuristicBaseline(
                    "latency_greedy",
                    latency_no_repair(),
                    k_paths=config.k_paths,
                ).solve(scenario),
                HeuristicBaseline(
                    "capacity_greedy",
                    capacity_no_repair(),
                    k_paths=config.k_paths,
                ).solve(scenario),
                RandomBaseline(
                    samples=config.random_samples,
                    seed=seed,
                    k_paths=config.k_paths,
                ).solve(scenario),
            ]
            checks_passed = (
                initial_types == record.expected_initial_violation_types
                and oracle.status == "feasible"
                and oracle.optimality_proven
                and oracle.objective is not None
            )
            cases.append(
                PreflightCase(
                    seed=seed,
                    profile_id=record.profile_id,
                    scenario_hash=scenario.stable_hash,
                    initial_placement=initial_execution.plan.placement,
                    initial_violation_types=initial_types,
                    initial_feasible=initial_verification.feasible,
                    oracle_status=oracle.status,
                    oracle_optimality_proven=oracle.optimality_proven,
                    oracle_weighted_objective=(
                        oracle.objective.weighted_objective
                        if oracle.objective
                        else None
                    ),
                    solver_results=baselines,
                    checks_passed=checks_passed,
                )
            )
            scenario_index.append(
                {
                    "seed": seed,
                    "profile_id": record.profile_id,
                    "scenario_hash": scenario.stable_hash,
                }
            )
        profile_counts = {
            profile: sum(item.profile_id == profile for item in cases)
            for profile in self.scenario_factory.profiles
        }
        passed = (
            all(item.checks_passed for item in cases)
            and all(value == 5 for value in profile_counts.values())
            and len({item.scenario_hash for item in cases}) == len(cases)
        )
        source_root = Path(__file__).resolve().parents[1]
        return PairedFinalPreflight(
            experiment_id=config.experiment_id,
            protocol_id=protocol.protocol_id,
            protocol_version=protocol.version,
            protocol_hash=protocol.protocol_hash,
            config_hash=config_hash,
            code_tree_hash=sha256_tree(source_root),
            scenario_factory_version=self.scenario_factory.version,
            scenario_set_hash=sha256_json(scenario_index),
            prompt_hashes=prompt_hashes,
            cases=cases,
            cost_forecast=self._forecast(
                config=config,
                protocol=protocol,
                seed_count=len(seeds),
            ),
            passed=passed,
        )

    @staticmethod
    def _oracle_values(preflight: PairedFinalPreflight) -> dict[int, float]:
        return {
            item.seed: item.oracle_weighted_objective
            for item in preflight.cases
            if item.oracle_weighted_objective is not None
        }

    @staticmethod
    def _usage(events: list[PatchGenerationTrace]) -> tuple[int, int, int, list[str]]:
        responses = [item.response for item in events if item.response is not None]
        billed = [item for item in responses if not item.cached]
        return (
            sum(item.usage.input_tokens for item in billed),
            sum(item.usage.output_tokens for item in billed),
            sum(item.cached for item in responses),
            sorted(
                {
                    str(item.metadata["system_fingerprint"])
                    for item in responses
                    if item.metadata.get("system_fingerprint")
                }
            ),
        )

    def _run_one_shot(
        self,
        *,
        method: MethodBudget,
        scenario: ScenarioInstance,
        llm: LLMProtocol,
        prompt_path: Path,
    ) -> tuple[LLMPlanBaselineResult, list[LLMResponse]]:
        baseline_type = {
            "direct_llm_plan": DirectLLMPlanBaseline,
            "structured_llm_plan": StructuredLLMPlanBaseline,
        }[method.method_id]
        result = baseline_type.from_template_file(llm=llm, path=prompt_path).run(
            scenario
        )
        responses = [
            item.response for item in result.trajectory if item.response is not None
        ]
        return result, responses

    def _record_one_shot(
        self,
        *,
        common: dict[str, Any],
        result: LLMPlanBaselineResult,
        responses: list[LLMResponse],
        oracle_value: float,
        config: DeepSeekPairedFinalConfig,
        elapsed_ms: float,
    ) -> FinalRunRecord:
        solver = result.solver_result
        verification = solver.verification if solver else None
        feasible = bool(verification and verification.feasible)
        objective = solver.objective if solver else None
        billed = [item for item in responses if not item.cached]
        input_tokens = sum(item.usage.input_tokens for item in billed)
        output_tokens = sum(item.usage.output_tokens for item in billed)
        value = objective.weighted_objective if objective else None
        return FinalRunRecord(
            **common,
            status=result.status,
            final_feasible=feasible,
            weighted_objective=value,
            candidate_set_gap_pct=(
                (value - oracle_value) / oracle_value * 100.0
                if value is not None and oracle_value > 0
                else None
            ),
            calls_to_first_feasible=1 if feasible else None,
            violation_burden=float(len(verification.violations)) if verification else 1.0,
            schema_failures=sum(
                item.generation_status in {"schema_error", "scenario_mismatch"}
                for item in result.trajectory
            ),
            backend_failures=sum(
                item.generation_status == "backend_error" for item in result.trajectory
            ),
            llm_calls=result.llm_calls,
            evaluator_calls=1 if solver else 0,
            cached_responses=sum(item.cached for item in responses),
            billed_input_tokens=input_tokens,
            billed_output_tokens=output_tokens,
            estimated_cost_cny=(
                input_tokens
                * config.cost_policy.input_cache_miss_cny_per_million
                + output_tokens * config.cost_policy.output_cny_per_million
            )
            / 1_000_000,
            wall_time_ms=elapsed_ms,
            stop_reason=result.stop_reason,
            observed_system_fingerprints=sorted(
                {
                    str(item.metadata["system_fingerprint"])
                    for item in responses
                    if item.metadata.get("system_fingerprint")
                }
            ),
            infrastructure_failure=(
                result.stop_reason == "backend_error" and not responses
            ),
            result_payload=result.model_dump(mode="json"),
        )

    def _record_search(
        self,
        *,
        common: dict[str, Any],
        result: SearchResult,
        events: list[PatchGenerationTrace],
        oracle_value: float,
        config: DeepSeekPairedFinalConfig,
        elapsed_ms: float,
    ) -> FinalRunRecord:
        best = next(
            (
                item
                for item in result.records
                if item.candidate_id == result.best_candidate_id
            ),
            result.records[-1],
        )
        verification = best.verification
        value = best.objective.weighted_objective if best.objective else None
        input_tokens, output_tokens, cached, fingerprints = self._usage(events)
        backend_failures = sum(item.status == "backend_error" for item in events)
        return FinalRunRecord(
            **common,
            status="feasible" if verification.feasible else "infeasible",
            final_feasible=verification.feasible,
            weighted_objective=value,
            candidate_set_gap_pct=(
                (value - oracle_value) / oracle_value * 100.0
                if value is not None and oracle_value > 0
                else None
            ),
            calls_to_first_feasible=result.statistics.first_feasible_patch_proposal,
            violation_burden=float(len(verification.violations)),
            schema_failures=sum(item.status == "schema_error" for item in events),
            backend_failures=backend_failures,
            llm_calls=len(events),
            evaluator_calls=result.statistics.evaluator_calls,
            cached_responses=cached,
            billed_input_tokens=input_tokens,
            billed_output_tokens=output_tokens,
            estimated_cost_cny=(
                input_tokens
                * config.cost_policy.input_cache_miss_cny_per_million
                + output_tokens * config.cost_policy.output_cny_per_million
            )
            / 1_000_000,
            wall_time_ms=elapsed_ms,
            stop_reason=result.stop_reason,
            observed_system_fingerprints=fingerprints,
            infrastructure_failure=(
                bool(events) and backend_failures == len(events)
                and all(item.response is None for item in events)
            ),
            result_payload={
                "generation_trace": [item.model_dump(mode="json") for item in events],
                "search_result": result.model_dump(mode="json"),
            },
        )

    def _execute_llm_run(
        self,
        *,
        config: DeepSeekPairedFinalConfig,
        protocol: FormalExperimentProtocol,
        preflight: PairedFinalPreflight,
        scenario_record: FinalScenarioRecord,
        method: MethodBudget,
        repetition: int,
    ) -> FinalRunRecord:
        run_key = f"{method.method_id}__s{scenario_record.seed}__r{repetition}"
        bound_llm = RunBoundLLM(
            self.llm_factory(config.llm),
            run_key=run_key,
        )
        prompt_path = self._prompt_path(config.protocol_path, method)
        if prompt_path is None:
            raise ValueError(f"method {method.method_id} has no prompt")
        common = {
            "run_key": run_key,
            "experiment_id": config.experiment_id,
            "protocol_hash": protocol.protocol_hash,
            "config_hash": preflight.config_hash,
            "code_tree_hash": preflight.code_tree_hash,
            "scenario_seed": scenario_record.seed,
            "scenario_profile": scenario_record.profile_id,
            "scenario_hash": scenario_record.scenario.stable_hash,
            "llm_repetition": repetition,
            "method_id": method.method_id,
            "method_family": method.family,
            "provider": protocol.live_model_lock.provider,
            "model_snapshot": protocol.live_model_lock.model_snapshot,
            "prompt_hash": method.prompt_hash,
            "request_parameters": {
                "temperature": config.llm.temperature,
                "top_p": config.llm.top_p,
                "max_tokens": config.llm.max_tokens,
                "thinking": config.llm.thinking,
                "expected_system_fingerprint": config.llm.expected_system_fingerprint,
            },
            "budget": {
                "max_llm_calls": method.max_llm_calls,
                "max_evaluator_calls": method.max_evaluator_calls,
                "max_wall_time_seconds": method.max_wall_time_seconds,
                "stop_on_first_feasible": method.stop_on_first_feasible,
            },
        }
        oracle_value = self._oracle_values(preflight)[scenario_record.seed]
        started = time.perf_counter()
        if method.family == "one_shot_llm":
            result, responses = self._run_one_shot(
                method=method,
                scenario=scenario_record.scenario,
                llm=bound_llm,
                prompt_path=prompt_path,
            )
            return self._record_one_shot(
                common=common,
                result=result,
                responses=responses,
                oracle_value=oracle_value,
                config=config,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
        if method.features is None or method.initial_heuristic is None:
            raise ValueError(f"iterative method {method.method_id} lacks feature contract")
        generator = LLMPatchGenerator.from_template_file(
            llm=bound_llm,
            path=prompt_path,
            prompt_version=(
                f"paired_final_v{protocol.version.replace('.', '_')}_"
                f"{method.prompt_hash[:12]}"
            ),
        )
        result = SearchController(
            k_paths=config.k_paths,
            features=method.features,
        ).run(
            scenario=scenario_record.scenario,
            initial_program=self._program(method.initial_heuristic),
            generator=generator,
            budgets=SearchBudgets(
                max_patch_proposals=method.max_llm_calls,
                max_total_llm_calls=method.max_llm_calls,
                max_evaluator_calls=method.max_evaluator_calls,
                max_wall_time_seconds=method.max_wall_time_seconds,
                stop_on_first_feasible=method.stop_on_first_feasible,
            ),
        )
        return self._record_search(
            common=common,
            result=result,
            events=generator.events,
            oracle_value=oracle_value,
            config=config,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )

    @staticmethod
    def _run_path(root: Path, method_id: str, seed: int, repetition: int) -> Path:
        return root / "runs" / method_id / f"seed_{seed}" / f"rep_{repetition}.json"

    @staticmethod
    def _load_existing(
        path: Path,
        *,
        protocol_hash: str,
        config_hash: str,
        code_tree_hash: str,
    ) -> FinalRunRecord | None:
        if not path.exists():
            return None
        record = FinalRunRecord.model_validate_json(path.read_text(encoding="utf-8"))
        if (
            record.protocol_hash != protocol_hash
            or record.config_hash != config_hash
            or record.code_tree_hash != code_tree_hash
        ):
            raise ValueError(f"stale paired-final artifact cannot be resumed: {path}")
        return record

    def _materialize_non_llm(
        self,
        *,
        config: DeepSeekPairedFinalConfig,
        protocol: FormalExperimentProtocol,
        preflight: PairedFinalPreflight,
    ) -> list[FinalRunRecord]:
        root = config.artifacts_root.resolve()
        records: list[FinalRunRecord] = []
        for case in preflight.cases:
            solver_by_name = {item.solver_name: item for item in case.solver_results}
            for method_id in config.method_ids:
                method = self._method(protocol, method_id)
                if method.family not in {"non_llm", "oracle"}:
                    continue
                path = self._run_path(root, method_id, case.seed, 0)
                existing = self._load_existing(
                    path,
                    protocol_hash=preflight.protocol_hash,
                    config_hash=preflight.config_hash,
                    code_tree_hash=preflight.code_tree_hash,
                )
                if existing is not None:
                    records.append(existing)
                    continue
                solver = solver_by_name[method_id]
                verification = solver.verification
                value = solver.objective.weighted_objective if solver.objective else None
                oracle_value = self._oracle_values(preflight)[case.seed]
                record = FinalRunRecord(
                    run_key=f"{method_id}__s{case.seed}__r0",
                    experiment_id=config.experiment_id,
                    protocol_hash=preflight.protocol_hash,
                    config_hash=preflight.config_hash,
                    code_tree_hash=preflight.code_tree_hash,
                    scenario_seed=case.seed,
                    scenario_profile=case.profile_id,
                    scenario_hash=case.scenario_hash,
                    llm_repetition=0,
                    method_id=method_id,
                    method_family=method.family,
                    provider="deterministic",
                    model_snapshot="not_applicable",
                    prompt_hash=None,
                    request_parameters={},
                    budget={
                        "max_evaluator_calls": method.max_evaluator_calls,
                        "max_wall_time_seconds": method.max_wall_time_seconds,
                    },
                    status=solver.status,
                    final_feasible=bool(verification and verification.feasible),
                    weighted_objective=value,
                    candidate_set_gap_pct=(
                        (value - oracle_value) / oracle_value * 100.0
                        if value is not None and oracle_value > 0
                        else None
                    ),
                    calls_to_first_feasible=0 if solver.status == "feasible" else None,
                    violation_burden=(
                        float(len(verification.violations)) if verification else 1.0
                    ),
                    llm_calls=0,
                    evaluator_calls=solver.candidates_evaluated,
                    wall_time_ms=solver.planning_time_ms,
                    stop_reason=solver.status,
                    observed_system_fingerprints=[],
                    result_payload=solver.model_dump(mode="json"),
                )
                _write_json_atomic(path, record.model_dump(mode="json"))
                records.append(record)
        return records

    def run_live(
        self,
        *,
        config: DeepSeekPairedFinalConfig,
        protocol: FormalExperimentProtocol,
        preflight: PairedFinalPreflight,
    ) -> PairedFinalManifest:
        if not preflight.passed:
            raise ValueError("paired-final live run requires a passing offline preflight")
        if preflight.protocol_hash != protocol.protocol_hash:
            raise ValueError("preflight protocol hash no longer matches")
        source_root = Path(__file__).resolve().parents[1]
        current_code_hash = sha256_tree(source_root)
        if current_code_hash != preflight.code_tree_hash:
            raise ValueError("source tree changed after paired-final preflight")
        seeds, _ = self._validate_contract(config=config, protocol=protocol)
        base = load_scenario(config.base_scenario_path)
        scenarios = {
            seed: self.scenario_factory.build(base=base, seed=seed) for seed in seeds
        }
        records = self._materialize_non_llm(
            config=config,
            protocol=protocol,
            preflight=preflight,
        )
        llm_methods = [
            self._method(protocol, method_id)
            for method_id in config.method_ids
            if self._method(protocol, method_id).family
            in {"one_shot_llm", "iterative_llm"}
        ]
        repetitions = self._stage(protocol).llm_repetitions
        root = config.artifacts_root.resolve()
        if llm_methods:
            for seed in seeds:
                for repetition in range(repetitions):
                    offset = (seed - seeds[0] + repetition) % len(llm_methods)
                    ordered = llm_methods[offset:] + llm_methods[:offset]
                    for method in ordered:
                        path = self._run_path(root, method.method_id, seed, repetition)
                        existing = self._load_existing(
                            path,
                            protocol_hash=preflight.protocol_hash,
                            config_hash=preflight.config_hash,
                            code_tree_hash=preflight.code_tree_hash,
                        )
                        if existing is not None:
                            records.append(existing)
                            continue
                        record = self._execute_llm_run(
                            config=config,
                            protocol=protocol,
                            preflight=preflight,
                            scenario_record=scenarios[seed],
                            method=method,
                            repetition=repetition,
                        )
                        if record.infrastructure_failure:
                            failure_path = root / "failures" / f"{record.run_key}.json"
                            _write_json_atomic(
                                failure_path,
                                record.model_dump(mode="json"),
                            )
                            continue
                        _write_json_atomic(path, record.model_dump(mode="json"))
                        records.append(record)
                        observed_cost = sum(item.estimated_cost_cny for item in records)
                        if observed_cost > config.cost_policy.max_total_cost_cny:
                            raise ValueError("observed paired-final cost exceeded cap")
        run_files = sorted(
            str(path.resolve().relative_to(root))
            for path in (root / "runs").rglob("*.json")
        )
        expected = len(seeds) * (
            sum(
                1
                for method_id in config.method_ids
                if self._method(protocol, method_id).family in {"non_llm", "oracle"}
            )
            + repetitions * len(llm_methods)
        )
        failures = list((root / "failures").rglob("*.json")) if (root / "failures").exists() else []
        manifest = PairedFinalManifest(
            experiment_id=config.experiment_id,
            protocol_hash=preflight.protocol_hash,
            config_hash=preflight.config_hash,
            code_tree_hash=preflight.code_tree_hash,
            scenario_set_hash=preflight.scenario_set_hash,
            expected_run_count=expected,
            completed_run_count=len(run_files),
            infrastructure_failure_count=len(failures),
            total_billed_input_tokens=sum(item.billed_input_tokens for item in records),
            total_billed_output_tokens=sum(item.billed_output_tokens for item in records),
            total_estimated_cost_cny=sum(item.estimated_cost_cny for item in records),
            run_files=run_files,
            complete=len(run_files) == expected and not failures,
        )
        _write_json_atomic(root / "manifest.json", manifest.model_dump(mode="json"))
        return manifest


def save_preflight(path: Path, preflight: PairedFinalPreflight) -> Path:
    return _write_json_atomic(path, preflight.model_dump(mode="json"))


def load_preflight(path: Path) -> PairedFinalPreflight:
    return PairedFinalPreflight.model_validate_json(path.read_text(encoding="utf-8"))


def artifact_hash(path: Path) -> str:
    return sha256_file(path)

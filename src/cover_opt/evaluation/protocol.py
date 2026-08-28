from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from cover_opt.hashing import sha256_json
from cover_opt.search.options import SearchFeatures


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExperimentStage(ProtocolModel):
    stage_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    purpose: Literal["control", "pilot", "final"]
    scenario_seeds: list[int] = Field(min_length=1)
    llm_repetitions: int = Field(ge=1)
    claim_eligible: bool

    @model_validator(mode="after")
    def unique_seeds(self) -> "ExperimentStage":
        if len(self.scenario_seeds) != len(set(self.scenario_seeds)):
            raise ValueError(f"stage {self.stage_id} has duplicate scenario seeds")
        if self.purpose != "final" and self.claim_eligible:
            raise ValueError("only a final stage can be claim eligible")
        return self


class LiveModelLock(ProtocolModel):
    live_calls_allowed: bool
    provider: str = Field(min_length=1)
    model_snapshot: str = Field(min_length=1)
    system_fingerprint: str | None = None
    temperature: float = Field(ge=0.0, le=2.0)
    top_p: float = Field(gt=0.0, le=1.0)
    max_output_tokens: int = Field(ge=1)
    seed_control: Literal["required", "preferred", "unavailable"]
    locked_request_fields: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def protect_unset_live_model(self) -> "LiveModelLock":
        unset = self.provider == "UNSET_GATED" or self.model_snapshot == "UNSET_GATED"
        if unset and self.live_calls_allowed:
            raise ValueError("live calls cannot be enabled before provider/model lock")
        if self.live_calls_allowed and not self.system_fingerprint:
            raise ValueError("live calls require an observed system fingerprint")
        return self


class MethodBudget(ProtocolModel):
    method_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    family: Literal["non_llm", "one_shot_llm", "iterative_llm", "oracle"]
    implementation_status: Literal["implemented", "planned", "gated"]
    max_llm_calls: int = Field(ge=0)
    max_evaluator_calls: int = Field(ge=1)
    max_wall_time_seconds: float = Field(gt=0.0)
    live_comparable: bool = True
    claim_eligible: bool = True
    prompt_path: str | None = None
    prompt_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    initial_heuristic: str | None = None
    features: SearchFeatures | None = None
    stop_on_first_feasible: bool = True

    @model_validator(mode="after")
    def family_budget_contract(self) -> "MethodBudget":
        if self.family in {"non_llm", "oracle"} and self.max_llm_calls != 0:
            raise ValueError(f"{self.method_id} cannot consume LLM calls")
        if self.family == "one_shot_llm" and self.max_llm_calls != 1:
            raise ValueError(f"{self.method_id} must use exactly one LLM call")
        if self.family == "iterative_llm" and self.max_llm_calls < 1:
            raise ValueError(f"{self.method_id} requires a positive LLM budget")
        if self.claim_eligible and self.family in {"one_shot_llm", "iterative_llm"}:
            if not self.prompt_path or not self.prompt_hash:
                raise ValueError(
                    f"claim-eligible LLM method {self.method_id} requires a frozen prompt"
                )
        if self.family == "iterative_llm" and self.claim_eligible:
            if self.initial_heuristic is None or self.features is None:
                raise ValueError(
                    f"claim-eligible iterative method {self.method_id} requires "
                    "an initial heuristic and feature contract"
                )
        if not self.live_comparable and self.claim_eligible:
            raise ValueError("a non-comparable method cannot be claim eligible")
        return self


class MetricSpec(ProtocolModel):
    metric_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    direction: Literal["minimize", "maximize", "report_only"]
    population: Literal["all_cases", "jointly_feasible", "successful_runs"]
    primary: bool = False


class PlannedComparison(ProtocolModel):
    comparison_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    treatment: str
    control: str
    claim_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    required_stage: str
    primary_metrics: list[str] = Field(min_length=1)


class StatisticalPolicy(ProtocolModel):
    paired_by: list[str] = Field(min_length=1)
    confidence_level: float = Field(gt=0.5, lt=1.0)
    binary_test: str = Field(min_length=1)
    continuous_test: str = Field(min_length=1)
    interval_method: str = Field(min_length=1)
    multiple_comparison_correction: str = Field(min_length=1)
    minimum_paired_scenarios: int = Field(ge=2)
    report_effect_sizes: bool = True
    inferential_unit: Literal["scenario_seed", "scenario_seed_repetition"] = (
        "scenario_seed_repetition"
    )
    repetition_aggregation: str | None = None
    bootstrap_unit: Literal["paired_run", "scenario_seed"] = "paired_run"
    primary_metric_by_comparison: dict[str, str] = Field(default_factory=dict)


class ClaimGate(ProtocolModel):
    claim_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    comparison_id: str
    required_stage: str
    conditions: list[str] = Field(min_length=1)
    current_status: Literal["planned", "supported", "not_supported"] = "planned"


class ArtifactPolicy(ProtocolModel):
    required_run_fields: list[str] = Field(min_length=1)
    required_result_fields: list[str] = Field(min_length=1)
    retain_full_trajectory: bool
    exclusion_rules: list[str] = Field(min_length=1)
    failed_runs_remain_in_feasibility_denominator: bool


class FormalExperimentProtocol(ProtocolModel):
    protocol_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: Literal["frozen_before_live_call"]
    frozen_on: date
    evidence_boundaries: list[str] = Field(min_length=1)
    final_scenario_contract: dict[str, object] | None = None
    stages: list[ExperimentStage] = Field(min_length=3)
    live_model_lock: LiveModelLock
    methods: list[MethodBudget] = Field(min_length=2)
    metrics: list[MetricSpec] = Field(min_length=2)
    comparisons: list[PlannedComparison] = Field(min_length=1)
    statistics: StatisticalPolicy
    claim_gates: list[ClaimGate] = Field(min_length=1)
    artifacts: ArtifactPolicy

    @staticmethod
    def _unique(values: list[str], label: str) -> None:
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate {label} identifiers")

    @model_validator(mode="after")
    def validate_references(self) -> "FormalExperimentProtocol":
        if self.version >= "1.3.0" and self.final_scenario_contract is None:
            raise ValueError("protocol version 1.3+ requires a final scenario contract")
        stage_ids = [item.stage_id for item in self.stages]
        method_ids = [item.method_id for item in self.methods]
        metric_ids = [item.metric_id for item in self.metrics]
        comparison_ids = [item.comparison_id for item in self.comparisons]
        claim_ids = [item.claim_id for item in self.claim_gates]
        for values, label in (
            (stage_ids, "stage"),
            (method_ids, "method"),
            (metric_ids, "metric"),
            (comparison_ids, "comparison"),
            (claim_ids, "claim"),
        ):
            self._unique(values, label)

        stage_set = set(stage_ids)
        method_set = set(method_ids)
        metric_set = set(metric_ids)
        comparison_set = set(comparison_ids)
        final_stages = {
            item.stage_id
            for item in self.stages
            if item.purpose == "final" and item.claim_eligible
        }
        if not final_stages:
            raise ValueError("protocol requires a claim-eligible final stage")
        for item in self.comparisons:
            if item.treatment not in method_set or item.control not in method_set:
                raise ValueError(f"comparison {item.comparison_id} has unknown method")
            if item.required_stage not in stage_set:
                raise ValueError(f"comparison {item.comparison_id} has unknown stage")
            if not set(item.primary_metrics).issubset(metric_set):
                raise ValueError(f"comparison {item.comparison_id} has unknown metric")
            treatment = next(
                method for method in self.methods if method.method_id == item.treatment
            )
            control = next(
                method for method in self.methods if method.method_id == item.control
            )
            if not treatment.claim_eligible or not control.claim_eligible:
                raise ValueError(
                    f"comparison {item.comparison_id} uses a non-claim-eligible method"
                )
        if self.statistics.primary_metric_by_comparison:
            if set(self.statistics.primary_metric_by_comparison) != comparison_set:
                raise ValueError("primary statistic map must cover every comparison")
            for comparison_id, metric_id in (
                self.statistics.primary_metric_by_comparison.items()
            ):
                comparison = next(
                    item for item in self.comparisons
                    if item.comparison_id == comparison_id
                )
                if metric_id not in comparison.primary_metrics:
                    raise ValueError(
                        f"primary statistic for {comparison_id} is not preregistered"
                    )
        for gate in self.claim_gates:
            if gate.comparison_id not in comparison_set:
                raise ValueError(f"claim {gate.claim_id} has unknown comparison")
            if gate.required_stage not in final_stages:
                raise ValueError(f"claim {gate.claim_id} must require a final stage")
            comparison = next(
                item
                for item in self.comparisons
                if item.comparison_id == gate.comparison_id
            )
            if comparison.claim_id != gate.claim_id:
                raise ValueError(f"claim {gate.claim_id} comparison linkage mismatch")
        if not any(item.primary for item in self.metrics):
            raise ValueError("protocol requires at least one primary metric")
        return self

    @property
    def protocol_hash(self) -> str:
        return sha256_json(self)


def load_formal_experiment_protocol(path: Path) -> FormalExperimentProtocol:
    resolved = path.resolve()
    with resolved.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected a YAML mapping in {resolved}")
    return FormalExperimentProtocol.model_validate(payload)

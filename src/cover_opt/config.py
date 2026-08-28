from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cover_opt.heuristics.patch import HeuristicPatch
from cover_opt.baselines.current_paper import SolverGenerationBudgets
from cover_opt.llm.deepseek import DeepSeekChatSettings
from cover_opt.search.budgets import SearchBudgets
from cover_opt.search.options import SearchFeatures


HeuristicName = Literal[
    "latency_first",
    "capacity_first",
    "migration_aware",
    "latency_no_repair",
]


class BudgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_llm_calls: int = Field(ge=0)
    max_evaluator_calls: int = Field(ge=0)
    max_wall_time_seconds: float = Field(gt=0)


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["mock", "replay"]
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    version: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    seed: int = Field(ge=0)
    scenario_path: Path
    prompt_path: Path
    budgets: BudgetConfig
    llm: LLMConfig
    mock_candidate: dict[str, Any]

    @model_validator(mode="after")
    def validate_smoke_budget(self) -> "ExperimentConfig":
        if self.budgets.max_llm_calls < 1:
            raise ValueError("offline smoke requires at least one LLM call")
        return self


class LoadedExperiment(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: ExperimentConfig


class ScenarioOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    migration_budget: int | None = Field(default=None, ge=0)
    qos_latency_ms: float | None = Field(default=None, gt=0)


class ScriptedSearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    scenario_path: Path
    scenario_overrides: ScenarioOverrides = Field(default_factory=ScenarioOverrides)
    initial_heuristic: HeuristicName
    budgets: SearchBudgets
    patches: list[HeuristicPatch]


class LoadedScriptedSearch(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: ScriptedSearchConfig


class ReplaySearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    scenario_path: Path
    scenario_overrides: ScenarioOverrides = Field(default_factory=ScenarioOverrides)
    initial_heuristic: HeuristicName
    prompt_path: Path
    replay_file: Path
    budgets: SearchBudgets


class LoadedReplaySearch(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: ReplaySearchConfig


class ReplayExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_reason: str = Field(min_length=1)
    final_feasible: bool
    initial_violation_types: list[str] = Field(min_length=1)
    generation_status: Literal["schema_valid", "backend_error", "schema_error"]


class ReplayRegressionCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    scenario_path: Path
    scenario_overrides: ScenarioOverrides = Field(default_factory=ScenarioOverrides)
    initial_heuristic: HeuristicName
    replay_file: Path
    budgets: SearchBudgets
    expectation: ReplayExpectation


class ReplayRegressionSuiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    prompt_path: Path
    cases: list[ReplayRegressionCase] = Field(min_length=1)


class LoadedReplayRegressionSuite(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: ReplayRegressionSuiteConfig


class BaselineSmokeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    scenario_path: Path
    scenario_overrides: ScenarioOverrides = Field(default_factory=ScenarioOverrides)
    k_paths: int = Field(ge=1, le=16, default=3)
    exact_max_candidates: int = Field(ge=1, default=100_000)
    exact_max_wall_time_seconds: float = Field(gt=0.0, default=30.0)
    random_samples: int = Field(ge=1, default=32)
    random_seed: int = Field(ge=0, default=0)


class LoadedBaselineSmoke(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: BaselineSmokeConfig


class AblationExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_reason: str = Field(min_length=1)
    final_feasible: bool
    initial_category: Literal["feasible_elite", "repairable", "rejected"]
    accepted_patches: int = Field(ge=0)
    rejected_patches: int = Field(ge=0)
    evaluator_calls: int = Field(ge=1)
    counterexample_count: int = Field(ge=0)
    changed_components: list[str] = Field(default_factory=list)
    counterexample_replays: int | None = Field(ge=0, default=None)
    initial_candidate_count: int | None = Field(ge=1, default=None)
    selected_initial_source: Literal[
        "fixed_initial", "generated_initial"
    ] | None = None
    initial_generation_calls: int | None = Field(ge=0, default=None)
    patch_generation_calls: int | None = Field(ge=0, default=None)
    total_llm_calls: int | None = Field(ge=0, default=None)


class AblationRunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    scenario_path: Path
    scenario_overrides: ScenarioOverrides = Field(default_factory=ScenarioOverrides)
    initial_heuristic: HeuristicName
    generator: Literal["none", "replay"]
    prompt_path: Path | None = None
    replay_file: Path | None = None
    initial_generator: Literal["none", "replay"] = "none"
    initial_prompt_path: Path | None = None
    initial_replay_file: Path | None = None
    initial_candidate_count: int = Field(ge=0, le=8, default=0)
    features: SearchFeatures = Field(default_factory=SearchFeatures)
    budgets: SearchBudgets
    expectation: AblationExpectation

    @model_validator(mode="after")
    def validate_generator_files(self) -> "AblationRunConfig":
        if self.generator == "replay" and (
            self.prompt_path is None or self.replay_file is None
        ):
            raise ValueError("replay ablation requires prompt_path and replay_file")
        if self.generator == "none" and (
            self.prompt_path is not None or self.replay_file is not None
        ):
            raise ValueError("none generator cannot declare prompt_path or replay_file")
        if self.initial_generator == "replay" and (
            self.initial_prompt_path is None
            or self.initial_replay_file is None
            or self.initial_candidate_count < 1
        ):
            raise ValueError(
                "replay initial generator requires prompt, replay file, and count"
            )
        if self.initial_generator == "none" and (
            self.initial_prompt_path is not None
            or self.initial_replay_file is not None
            or self.initial_candidate_count != 0
        ):
            raise ValueError(
                "none initial generator cannot declare generation inputs"
            )
        return self


class AblationSuiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    variants: list[AblationRunConfig] = Field(min_length=2)


class LoadedAblationSuite(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: AblationSuiteConfig


class ReplayCampaignSeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    scenario_path: Path
    scenario_overrides: ScenarioOverrides = Field(default_factory=ScenarioOverrides)
    initial_heuristic: HeuristicName
    replay_file: Path
    budgets: SearchBudgets


class ReplayCampaignControl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    replay_files: list[Path] = Field(min_length=1)
    budgets: SearchBudgets
    max_scenario_replays: int = Field(ge=1)
    max_replays_per_counterexample: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_replay_capacity(self) -> "ReplayCampaignControl":
        if len(self.replay_files) < self.max_scenario_replays:
            raise ValueError(
                "replay_files must cover every configured scenario replay"
            )
        return self


class ReplayCampaignExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_reason: Literal["replay_budget", "no_replayable_counterexample"]
    seed_runs: int = Field(ge=1)
    scenario_replays: int = Field(ge=0)
    resolved_counterexamples: int = Field(ge=0)
    persisted_counterexamples: int = Field(ge=0)


class ReplayCampaignConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    prompt_path: Path
    features: SearchFeatures = Field(default_factory=SearchFeatures)
    seeds: list[ReplayCampaignSeedConfig] = Field(min_length=1)
    replay: ReplayCampaignControl
    expectation: ReplayCampaignExpectation

    @model_validator(mode="after")
    def validate_campaign_boundary(self) -> "ReplayCampaignConfig":
        if not self.features.counterexample_memory_enabled:
            raise ValueError("campaign replay requires counterexample memory")
        if self.features.counterexample_replay_enabled:
            raise ValueError(
                "internal replay must be disabled so campaign replay is observable"
            )
        return self


class LoadedReplayCampaign(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: ReplayCampaignConfig


class CurrentPaperReplayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    scenario_path: Path
    scenario_overrides: ScenarioOverrides = Field(default_factory=ScenarioOverrides)
    generation_prompt_path: Path
    correction_prompt_path: Path
    llm_replay_file: Path
    runner_replay_file: Path
    budgets: SolverGenerationBudgets


class LoadedCurrentPaperReplay(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: CurrentPaperReplayConfig


class LLMPlanReplayExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["feasible", "infeasible", "generation_error"]
    stop_reason: str = Field(min_length=1)
    final_feasible: bool


class LLMPlanReplayCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    baseline: Literal["direct_llm_plan", "structured_llm_plan"]
    scenario_path: Path
    scenario_overrides: ScenarioOverrides = Field(default_factory=ScenarioOverrides)
    prompt_path: Path
    replay_file: Path
    expectation: LLMPlanReplayExpectation


class LLMPlanReplaySuiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    cases: list[LLMPlanReplayCase] = Field(min_length=2)


class LoadedLLMPlanReplaySuite(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: LLMPlanReplaySuiteConfig


class DeepSeekStructuredSmokeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    protocol_path: Path
    scenario_path: Path
    scenario_overrides: ScenarioOverrides = Field(default_factory=ScenarioOverrides)
    prompt_path: Path
    llm: DeepSeekChatSettings


class LoadedDeepSeekStructuredSmoke(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: DeepSeekStructuredSmokeConfig


class DeepSeekSearchSmokeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    protocol_path: Path
    scenario_path: Path
    scenario_overrides: ScenarioOverrides = Field(default_factory=ScenarioOverrides)
    initial_heuristic: HeuristicName
    prompt_path: Path
    prompt_version: str = Field(min_length=1)
    features: SearchFeatures = Field(default_factory=SearchFeatures)
    budgets: SearchBudgets
    llm: DeepSeekChatSettings


class LoadedDeepSeekSearchSmoke(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: DeepSeekSearchSmokeConfig


class PilotCostPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_cache_miss_cny_per_million: float = Field(ge=0.0)
    output_cny_per_million: float = Field(ge=0.0)
    assumed_max_input_tokens_per_call: int = Field(ge=1)
    max_total_cost_cny: float = Field(gt=0.0)


class DeepSeekLivePilotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pilot_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    protocol_path: Path
    stage_id: Literal["live_pilot"] = "live_pilot"
    base_scenario_path: Path
    prompt_path: Path
    expected_prompt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_version: str = Field(min_length=1)
    initial_heuristic: HeuristicName
    features: SearchFeatures = Field(default_factory=SearchFeatures)
    budgets: SearchBudgets
    cost_policy: PilotCostPolicy
    llm: DeepSeekChatSettings


class LoadedDeepSeekLivePilot(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: DeepSeekLivePilotConfig


class PairedFinalCostPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_cache_miss_cny_per_million: float = Field(ge=0.0)
    output_cny_per_million: float = Field(ge=0.0)
    assumed_max_input_tokens_per_call: int = Field(ge=1)
    max_total_cost_cny: float = Field(gt=0.0)


class DeepSeekPairedFinalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    protocol_path: Path
    stage_id: Literal["paired_final"] = "paired_final"
    base_scenario_path: Path
    artifacts_root: Path
    method_ids: list[str] = Field(min_length=1)
    k_paths: int = Field(ge=1, le=16, default=3)
    exact_max_candidates: int = Field(ge=1, default=100_000)
    exact_max_wall_time_seconds: float = Field(gt=0.0, default=30.0)
    random_samples: int = Field(ge=1, default=12)
    cost_policy: PairedFinalCostPolicy
    llm: DeepSeekChatSettings

    @field_validator("method_ids")
    @classmethod
    def unique_method_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("paired-final method_ids must be unique")
        return value


class LoadedDeepSeekPairedFinal(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw: dict[str, Any]
    config: DeepSeekPairedFinalConfig


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected a YAML mapping in {path}")
    return payload


def load_experiment(path: Path) -> LoadedExperiment:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    for key in ("scenario_path", "prompt_path"):
        value = Path(materialized[key])
        materialized[key] = value if value.is_absolute() else resolved.parent / value
    config = ExperimentConfig.model_validate(materialized)
    return LoadedExperiment(path=resolved, raw=raw, config=config)


def load_scripted_search(path: Path) -> LoadedScriptedSearch:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    scenario_path = Path(materialized["scenario_path"])
    materialized["scenario_path"] = (
        scenario_path if scenario_path.is_absolute() else resolved.parent / scenario_path
    )
    config = ScriptedSearchConfig.model_validate(materialized)
    return LoadedScriptedSearch(path=resolved, raw=raw, config=config)


def load_replay_search(path: Path) -> LoadedReplaySearch:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    for key in ("scenario_path", "prompt_path", "replay_file"):
        value = Path(materialized[key])
        materialized[key] = value if value.is_absolute() else resolved.parent / value
    config = ReplaySearchConfig.model_validate(materialized)
    return LoadedReplaySearch(path=resolved, raw=raw, config=config)


def load_replay_regression_suite(path: Path) -> LoadedReplayRegressionSuite:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    prompt_path = Path(materialized["prompt_path"])
    materialized["prompt_path"] = (
        prompt_path if prompt_path.is_absolute() else resolved.parent / prompt_path
    )
    cases = []
    for raw_case in materialized["cases"]:
        case = dict(raw_case)
        for key in ("scenario_path", "replay_file"):
            value = Path(case[key])
            case[key] = value if value.is_absolute() else resolved.parent / value
        cases.append(case)
    materialized["cases"] = cases
    config = ReplayRegressionSuiteConfig.model_validate(materialized)
    return LoadedReplayRegressionSuite(path=resolved, raw=raw, config=config)


def load_baseline_smoke(path: Path) -> LoadedBaselineSmoke:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    scenario_path = Path(materialized["scenario_path"])
    materialized["scenario_path"] = (
        scenario_path if scenario_path.is_absolute() else resolved.parent / scenario_path
    )
    config = BaselineSmokeConfig.model_validate(materialized)
    return LoadedBaselineSmoke(path=resolved, raw=raw, config=config)


def load_ablation_suite(path: Path) -> LoadedAblationSuite:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    variants = []
    for raw_variant in materialized["variants"]:
        variant = dict(raw_variant)
        for key in (
            "scenario_path",
            "prompt_path",
            "replay_file",
            "initial_prompt_path",
            "initial_replay_file",
        ):
            if variant.get(key) is None:
                continue
            value = Path(variant[key])
            variant[key] = value if value.is_absolute() else resolved.parent / value
        variants.append(variant)
    materialized["variants"] = variants
    config = AblationSuiteConfig.model_validate(materialized)
    return LoadedAblationSuite(path=resolved, raw=raw, config=config)


def load_replay_campaign(path: Path) -> LoadedReplayCampaign:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    prompt_path = Path(materialized["prompt_path"])
    materialized["prompt_path"] = (
        prompt_path if prompt_path.is_absolute() else resolved.parent / prompt_path
    )

    seeds = []
    for raw_seed in materialized["seeds"]:
        seed = dict(raw_seed)
        for key in ("scenario_path", "replay_file"):
            value = Path(seed[key])
            seed[key] = value if value.is_absolute() else resolved.parent / value
        seeds.append(seed)
    materialized["seeds"] = seeds

    replay = dict(materialized["replay"])
    replay["replay_files"] = [
        value if value.is_absolute() else resolved.parent / value
        for raw_path in replay["replay_files"]
        for value in [Path(raw_path)]
    ]
    materialized["replay"] = replay
    config = ReplayCampaignConfig.model_validate(materialized)
    return LoadedReplayCampaign(path=resolved, raw=raw, config=config)


def load_current_paper_replay(path: Path) -> LoadedCurrentPaperReplay:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    for key in (
        "scenario_path",
        "generation_prompt_path",
        "correction_prompt_path",
        "llm_replay_file",
        "runner_replay_file",
    ):
        value = Path(materialized[key])
        materialized[key] = value if value.is_absolute() else resolved.parent / value
    config = CurrentPaperReplayConfig.model_validate(materialized)
    return LoadedCurrentPaperReplay(path=resolved, raw=raw, config=config)


def load_llm_plan_replay_suite(path: Path) -> LoadedLLMPlanReplaySuite:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    cases = []
    for raw_case in materialized["cases"]:
        case = dict(raw_case)
        for key in ("scenario_path", "prompt_path", "replay_file"):
            value = Path(case[key])
            case[key] = value if value.is_absolute() else resolved.parent / value
        cases.append(case)
    materialized["cases"] = cases
    config = LLMPlanReplaySuiteConfig.model_validate(materialized)
    return LoadedLLMPlanReplaySuite(path=resolved, raw=raw, config=config)


def load_deepseek_structured_smoke(path: Path) -> LoadedDeepSeekStructuredSmoke:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    for key in ("protocol_path", "scenario_path", "prompt_path"):
        value = Path(materialized[key])
        materialized[key] = value if value.is_absolute() else resolved.parent / value
    llm = dict(materialized["llm"])
    if llm.get("cache_dir") is not None:
        cache_dir = Path(llm["cache_dir"])
        llm["cache_dir"] = (
            cache_dir if cache_dir.is_absolute() else resolved.parent / cache_dir
        )
    materialized["llm"] = llm
    config = DeepSeekStructuredSmokeConfig.model_validate(materialized)
    return LoadedDeepSeekStructuredSmoke(path=resolved, raw=raw, config=config)


def load_deepseek_search_smoke(path: Path) -> LoadedDeepSeekSearchSmoke:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    for key in ("protocol_path", "scenario_path", "prompt_path"):
        value = Path(materialized[key])
        materialized[key] = value if value.is_absolute() else resolved.parent / value
    llm = dict(materialized["llm"])
    if llm.get("cache_dir") is not None:
        cache_dir = Path(llm["cache_dir"])
        llm["cache_dir"] = (
            cache_dir if cache_dir.is_absolute() else resolved.parent / cache_dir
        )
    materialized["llm"] = llm
    config = DeepSeekSearchSmokeConfig.model_validate(materialized)
    return LoadedDeepSeekSearchSmoke(path=resolved, raw=raw, config=config)


def load_deepseek_live_pilot(path: Path) -> LoadedDeepSeekLivePilot:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    for key in ("protocol_path", "base_scenario_path", "prompt_path"):
        value = Path(materialized[key])
        materialized[key] = value if value.is_absolute() else resolved.parent / value
    llm = dict(materialized["llm"])
    if llm.get("cache_dir") is not None:
        cache_dir = Path(llm["cache_dir"])
        llm["cache_dir"] = (
            cache_dir if cache_dir.is_absolute() else resolved.parent / cache_dir
        )
    materialized["llm"] = llm
    config = DeepSeekLivePilotConfig.model_validate(materialized)
    return LoadedDeepSeekLivePilot(path=resolved, raw=raw, config=config)


def load_deepseek_paired_final(path: Path) -> LoadedDeepSeekPairedFinal:
    resolved = path.resolve()
    raw = load_yaml(resolved)
    materialized = dict(raw)
    for key in ("protocol_path", "base_scenario_path", "artifacts_root"):
        value = Path(materialized[key])
        materialized[key] = value if value.is_absolute() else resolved.parent / value
    llm = dict(materialized["llm"])
    if llm.get("cache_dir") is not None:
        cache_dir = Path(llm["cache_dir"])
        llm["cache_dir"] = (
            cache_dir if cache_dir.is_absolute() else resolved.parent / cache_dir
        )
    materialized["llm"] = llm
    config = DeepSeekPairedFinalConfig.model_validate(materialized)
    return LoadedDeepSeekPairedFinal(path=resolved, raw=raw, config=config)

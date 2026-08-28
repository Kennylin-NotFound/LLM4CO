from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.models import ScenarioInstance
from cover_opt.heuristics.schema import HeuristicDSL
from cover_opt.search.archive import CandidateRecord
from cover_opt.search.budgets import SearchBudgets
from cover_opt.search.controller import SearchController, SearchResult
from cover_opt.search.counterexamples import CounterexampleArchive, CounterexampleRecord
from cover_opt.search.generation import PatchGenerator
from cover_opt.search.options import SearchFeatures


class PersistentCounterexampleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counterexample: CounterexampleRecord
    scenario: ScenarioInstance
    parent_program: HeuristicDSL
    parent_candidate_id: str
    source_run_id: str
    parent_violation_burden: float = Field(ge=0.0)
    resolved: bool = False
    store_version: str = "1.0.0"


class CounterexampleCampaignStore:
    def __init__(self) -> None:
        self._entries: dict[str, PersistentCounterexampleEntry] = {}

    @staticmethod
    def _eligible_parent(
        result: SearchResult,
        counterexample: CounterexampleRecord,
    ) -> CandidateRecord | None:
        candidate_ids = set(counterexample.candidate_ids)
        candidates = [
            record
            for record in result.records
            if record.candidate_id in candidate_ids
            and record.category == "repairable"
            and record.expansion_eligible
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda record: (
                record.violation_burden,
                record.iteration,
                record.ast_signature,
            ),
        )

    def observe_run(
        self,
        *,
        run_id: str,
        scenario: ScenarioInstance,
        result: SearchResult,
    ) -> None:
        for counterexample in result.counterexamples:
            parent = self._eligible_parent(result, counterexample)
            if parent is None:
                continue
            existing = self._entries.get(counterexample.signature)
            if existing is None:
                self._entries[counterexample.signature] = (
                    PersistentCounterexampleEntry(
                        counterexample=counterexample,
                        scenario=scenario,
                        parent_program=parent.program,
                        parent_candidate_id=parent.candidate_id,
                        source_run_id=run_id,
                        parent_violation_burden=parent.violation_burden,
                    )
                )
                continue

            merged_archive = CounterexampleArchive()
            merged_archive.merge(existing.counterexample)
            merged_counterexample = merged_archive.merge(counterexample)
            replace_parent = (
                parent.violation_burden < existing.parent_violation_burden - 1e-12
            )
            self._entries[counterexample.signature] = existing.model_copy(
                update={
                    "counterexample": merged_counterexample,
                    "scenario": scenario if replace_parent else existing.scenario,
                    "parent_program": (
                        parent.program if replace_parent else existing.parent_program
                    ),
                    "parent_candidate_id": (
                        parent.candidate_id
                        if replace_parent
                        else existing.parent_candidate_id
                    ),
                    "source_run_id": (
                        run_id if replace_parent else existing.source_run_id
                    ),
                    "parent_violation_burden": min(
                        parent.violation_burden,
                        existing.parent_violation_burden,
                    ),
                }
            )

    @staticmethod
    def priority(entry: PersistentCounterexampleEntry) -> tuple[float, ...]:
        record = entry.counterexample
        return (
            float(record.repair_failures),
            float(record.observation_count),
            float(len(record.violation_types)),
            record.max_violation_burden,
            -float(record.replay_count),
        )

    def select(
        self,
        *,
        max_replays_per_counterexample: int,
        replay_iteration: int,
    ) -> PersistentCounterexampleEntry | None:
        candidates = [
            entry
            for entry in self._entries.values()
            if not entry.resolved
            and entry.counterexample.repair_failures > 0
            and entry.counterexample.replay_count
            < max_replays_per_counterexample
        ]
        if not candidates:
            return None
        selected = min(
            candidates,
            key=lambda entry: (
                tuple(-value for value in self.priority(entry)),
                entry.counterexample.signature,
            ),
        )
        counterexamples = CounterexampleArchive()
        counterexamples.merge(selected.counterexample)
        replayed = counterexamples.mark_replayed(
            selected.counterexample.signature,
            iteration=replay_iteration,
        )
        updated = selected.model_copy(update={"counterexample": replayed})
        self._entries[selected.counterexample.signature] = updated
        return updated

    def mark_resolved(self, signature: str) -> PersistentCounterexampleEntry:
        if signature not in self._entries:
            raise KeyError(f"unknown counterexample signature: {signature}")
        existing = self._entries[signature]
        updated = existing.model_copy(update={"resolved": True})
        self._entries[signature] = updated
        return updated

    @property
    def entries(self) -> list[PersistentCounterexampleEntry]:
        return [self._entries[key] for key in sorted(self._entries)]


@dataclass(frozen=True)
class CampaignSeedRun:
    run_id: str
    scenario: ScenarioInstance
    initial_program: HeuristicDSL
    generator: PatchGenerator
    budgets: SearchBudgets


ReplayGeneratorFactory = Callable[
    [PersistentCounterexampleEntry, int], PatchGenerator
]


class CampaignRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    phase: Literal["seed", "scenario_replay"]
    scenario_id: str
    scenario_hash: str
    source_counterexample_id: str | None = None
    source_run_id: str | None = None
    source_candidate_id: str | None = None
    search_result: SearchResult


class ReplayCampaignStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_runs: int = Field(ge=0)
    scenario_replays: int = Field(ge=0)
    resolved_counterexamples: int = Field(ge=0)
    total_evaluator_calls: int = Field(ge=0)
    total_patch_proposals: int = Field(ge=0)
    total_initial_generation_calls: int = Field(ge=0)
    total_patch_generation_calls: int = Field(ge=0)
    total_llm_calls: int = Field(ge=0)


class ReplayCampaignResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: list[CampaignRunRecord]
    counterexample_store: list[PersistentCounterexampleEntry]
    trajectory: list[dict]
    statistics: ReplayCampaignStatistics
    stop_reason: Literal["replay_budget", "no_replayable_counterexample"]
    runner_version: str = "1.0.0"


class CounterexampleReplayCampaignRunner:
    version = "1.0.0"

    def run(
        self,
        *,
        seeds: list[CampaignSeedRun],
        replay_generator_factory: ReplayGeneratorFactory,
        replay_budgets: SearchBudgets,
        features: SearchFeatures,
        max_scenario_replays: int,
        max_replays_per_counterexample: int,
    ) -> ReplayCampaignResult:
        if not seeds:
            raise ValueError("campaign requires at least one seed run")
        if max_scenario_replays < 0:
            raise ValueError("max_scenario_replays must be non-negative")
        if max_replays_per_counterexample < 1:
            raise ValueError("max_replays_per_counterexample must be positive")

        store = CounterexampleCampaignStore()
        runs: list[CampaignRunRecord] = []
        trajectory: list[dict] = []
        total_evaluator_calls = 0
        total_patch_proposals = 0
        total_initial_generation_calls = 0
        total_patch_generation_calls = 0
        total_llm_calls = 0

        for seed in seeds:
            result = SearchController(features=features).run(
                scenario=seed.scenario,
                initial_program=seed.initial_program,
                generator=seed.generator,
                budgets=seed.budgets,
            )
            store.observe_run(
                run_id=seed.run_id,
                scenario=seed.scenario,
                result=result,
            )
            total_evaluator_calls += result.statistics.evaluator_calls
            total_patch_proposals += result.statistics.patch_proposals
            total_initial_generation_calls += (
                result.statistics.initial_generation_calls
            )
            total_patch_generation_calls += result.statistics.patch_generation_calls
            total_llm_calls += result.statistics.total_llm_calls
            runs.append(
                CampaignRunRecord(
                    run_id=seed.run_id,
                    phase="seed",
                    scenario_id=seed.scenario.scenario_id,
                    scenario_hash=seed.scenario.stable_hash,
                    search_result=result,
                )
            )
            trajectory.append(
                {
                    "event": "campaign_seed_completed",
                    "run_id": seed.run_id,
                    "scenario_id": seed.scenario.scenario_id,
                    "scenario_hash": seed.scenario.stable_hash,
                    "best_candidate_id": result.best_candidate_id,
                }
            )

        scenario_replays = 0
        resolved_counterexamples = 0
        stop_reason: Literal[
            "replay_budget", "no_replayable_counterexample"
        ] = "replay_budget"
        while scenario_replays < max_scenario_replays:
            selected = store.select(
                max_replays_per_counterexample=max_replays_per_counterexample,
                replay_iteration=scenario_replays + 1,
            )
            if selected is None:
                stop_reason = "no_replayable_counterexample"
                break
            replay_index = scenario_replays + 1
            run_id = f"scenario_replay_{replay_index:03d}"
            trajectory.append(
                {
                    "event": "campaign_scenario_replayed",
                    "run_id": run_id,
                    "counterexample_id": selected.counterexample.counterexample_id,
                    "counterexample_signature": selected.counterexample.signature,
                    "scenario_id": selected.scenario.scenario_id,
                    "scenario_hash": selected.scenario.stable_hash,
                    "source_run_id": selected.source_run_id,
                    "source_candidate_id": selected.parent_candidate_id,
                    "replay_count": selected.counterexample.replay_count,
                    "priority": list(store.priority(selected)),
                }
            )
            generator = replay_generator_factory(selected, replay_index)
            result = SearchController(features=features).run(
                scenario=selected.scenario,
                initial_program=selected.parent_program,
                generator=generator,
                budgets=replay_budgets,
            )
            store.observe_run(
                run_id=run_id,
                scenario=selected.scenario,
                result=result,
            )
            if result.best_candidate_id is not None:
                store.mark_resolved(selected.counterexample.signature)
                resolved_counterexamples += 1
            total_evaluator_calls += result.statistics.evaluator_calls
            total_patch_proposals += result.statistics.patch_proposals
            total_initial_generation_calls += (
                result.statistics.initial_generation_calls
            )
            total_patch_generation_calls += result.statistics.patch_generation_calls
            total_llm_calls += result.statistics.total_llm_calls
            runs.append(
                CampaignRunRecord(
                    run_id=run_id,
                    phase="scenario_replay",
                    scenario_id=selected.scenario.scenario_id,
                    scenario_hash=selected.scenario.stable_hash,
                    source_counterexample_id=(
                        selected.counterexample.counterexample_id
                    ),
                    source_run_id=selected.source_run_id,
                    source_candidate_id=selected.parent_candidate_id,
                    search_result=result,
                )
            )
            scenario_replays += 1

        return ReplayCampaignResult(
            runs=runs,
            counterexample_store=store.entries,
            trajectory=trajectory,
            statistics=ReplayCampaignStatistics(
                seed_runs=len(seeds),
                scenario_replays=scenario_replays,
                resolved_counterexamples=resolved_counterexamples,
                total_evaluator_calls=total_evaluator_calls,
                total_patch_proposals=total_patch_proposals,
                total_initial_generation_calls=total_initial_generation_calls,
                total_patch_generation_calls=total_patch_generation_calls,
                total_llm_calls=total_llm_calls,
            ),
            stop_reason=stop_reason,
        )

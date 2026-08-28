from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from cover_opt.search.archive import CandidateArchive, CandidateRecord
from cover_opt.search.counterexamples import CounterexampleArchive, CounterexampleRecord


class ReplaySelection(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    counterexample: CounterexampleRecord
    parent: CandidateRecord
    priority: tuple[float, ...]


class CounterexampleReplayScheduler:
    @staticmethod
    def _priority(record: CounterexampleRecord) -> tuple[float, ...]:
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
        candidates: CandidateArchive,
        counterexamples: CounterexampleArchive,
        iteration: int,
        max_replays_per_counterexample: int,
    ) -> ReplaySelection | None:
        for record in counterexamples.ranked_for_replay():
            if record.repair_failures < 1:
                continue
            if record.replay_count >= max_replays_per_counterexample:
                continue
            parent = candidates.best_repairable(
                candidate_ids=record.candidate_ids,
            )
            if parent is None:
                continue
            replayed = counterexamples.mark_replayed(
                record.signature,
                iteration=iteration,
            )
            return ReplaySelection(
                counterexample=replayed,
                parent=parent,
                priority=self._priority(replayed),
            )
        return None

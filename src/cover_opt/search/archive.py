from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from cover_opt.domain.models import VerificationReport
from cover_opt.heuristics.executor import ExecutionResult
from cover_opt.heuristics.schema import HeuristicDSL
from cover_opt.objective.evaluator import ObjectiveReport
from cover_opt.verifier.conflict_graph import ConstraintDecisionConflictGraph
from cover_opt.search.diversity import dsl_structural_distance


class CandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    parent_id: str | None
    iteration: int
    program: HeuristicDSL
    ast_signature: str
    execution: ExecutionResult
    verification: VerificationReport
    objective: ObjectiveReport | None = None
    conflict_graph: ConstraintDecisionConflictGraph | None = None
    category: Literal["feasible_elite", "repairable", "rejected"]
    expansion_eligible: bool = True
    expansion_block_reason: str | None = None

    @property
    def violation_burden(self) -> float:
        return sum(violation.magnitude for violation in self.verification.violations)


class CandidateArchive:
    def __init__(self) -> None:
        self.records: list[CandidateRecord] = []
        self._signatures: set[str] = set()

    def add(self, record: CandidateRecord) -> bool:
        if record.ast_signature in self._signatures:
            return False
        self._signatures.add(record.ast_signature)
        self.records.append(record)
        return True

    def feasible(self) -> list[CandidateRecord]:
        return [record for record in self.records if record.category == "feasible_elite"]

    def repairable(self) -> list[CandidateRecord]:
        return [record for record in self.records if record.category == "repairable"]

    def rejected(self) -> list[CandidateRecord]:
        return [record for record in self.records if record.category == "rejected"]

    def get(self, candidate_id: str) -> CandidateRecord | None:
        return next(
            (record for record in self.records if record.candidate_id == candidate_id),
            None,
        )

    def block_expansion(
        self,
        candidate_id: str,
        *,
        reason: str,
    ) -> CandidateRecord:
        for index, record in enumerate(self.records):
            if record.candidate_id != candidate_id:
                continue
            updated = record.model_copy(
                update={
                    "expansion_eligible": False,
                    "expansion_block_reason": reason,
                }
            )
            self.records[index] = updated
            return updated
        raise KeyError(f"unknown candidate_id: {candidate_id}")

    def best_repairable(
        self,
        *,
        candidate_ids: list[str] | None = None,
    ) -> CandidateRecord | None:
        allowed = set(candidate_ids) if candidate_ids is not None else None
        candidates = [
            record
            for record in self.repairable()
            if record.expansion_eligible
            if allowed is None or record.candidate_id in allowed
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda record: (
                record.violation_burden,
                -record.iteration,
                record.ast_signature,
            ),
        )

    def best_feasible(self) -> CandidateRecord | None:
        feasible = self.feasible()
        if not feasible:
            return None
        return min(
            feasible,
            key=self._quality_key,
        )

    @staticmethod
    def _quality_key(record: CandidateRecord) -> tuple[float, int, str]:
        return (
            record.objective.weighted_objective if record.objective else float("inf"),
            record.iteration,
            record.ast_signature,
        )

    def diverse_feasible(
        self,
        *,
        limit: int,
        min_distance: float = 0.0,
    ) -> list[CandidateRecord]:
        if limit < 1:
            raise ValueError("diversity selection limit must be positive")
        if not 0.0 <= min_distance <= 1.0:
            raise ValueError("min_distance must be within [0, 1]")
        remaining = sorted(self.feasible(), key=self._quality_key)
        if not remaining:
            return []

        selected = [remaining.pop(0)]
        while remaining and len(selected) < limit:
            scored = [
                (
                    min(
                        dsl_structural_distance(
                            candidate.program,
                            chosen.program,
                        ).total
                        for chosen in selected
                    ),
                    candidate,
                )
                for candidate in remaining
            ]
            best_distance = max(distance for distance, _ in scored)
            if best_distance < min_distance:
                break
            next_candidate = min(
                (
                    candidate
                    for distance, candidate in scored
                    if abs(distance - best_distance) <= 1e-12
                ),
                key=self._quality_key,
            )
            selected.append(next_candidate)
            remaining.remove(next_candidate)
        return selected

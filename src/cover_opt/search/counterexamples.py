from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.models import ScenarioInstance, VerificationReport, ViolationType
from cover_opt.hashing import sha256_json


class CounterexampleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counterexample_id: str = Field(min_length=1)
    signature: str = Field(min_length=64, max_length=64)
    scenario_id: str = Field(min_length=1)
    scenario_hash: str = Field(min_length=64, max_length=64)
    violation_types: list[ViolationType] = Field(min_length=1)
    entities: list[str] = Field(min_length=1)
    observation_count: int = Field(ge=1)
    repair_failures: int = Field(ge=0)
    replay_count: int = Field(ge=0, default=0)
    last_replayed_iteration: int | None = Field(ge=0, default=None)
    candidate_ids: list[str] = Field(min_length=1)
    ast_signatures: list[str] = Field(min_length=1)
    first_iteration: int = Field(ge=0)
    last_iteration: int = Field(ge=0)
    max_violation_burden: float = Field(ge=0.0)
    latest_conflict_graph_signature: str | None = None
    archive_version: str = "1.0.0"

    def prompt_summary(self) -> dict:
        return {
            "counterexample_id": self.counterexample_id,
            "signature": self.signature,
            "violation_types": [item.value for item in self.violation_types],
            "entities": self.entities,
            "observation_count": self.observation_count,
            "repair_failures": self.repair_failures,
            "replay_count": self.replay_count,
            "max_violation_burden": self.max_violation_burden,
        }


class CounterexampleArchive:
    def __init__(self) -> None:
        self._records: dict[str, CounterexampleRecord] = {}

    @staticmethod
    def _pattern(
        scenario: ScenarioInstance,
        verification: VerificationReport,
    ) -> tuple[str, list[ViolationType], list[str]]:
        if verification.feasible:
            raise ValueError("a feasible verification report is not a counterexample")
        violation_patterns = sorted(
            (
                violation.violation_type.value,
                tuple(sorted(violation.entities)),
            )
            for violation in verification.violations
        )
        signature = sha256_json(
            {
                "scenario_hash": scenario.stable_hash,
                "violations": violation_patterns,
            }
        )
        violation_types = sorted(
            {violation.violation_type for violation in verification.violations},
            key=lambda item: item.value,
        )
        entities = sorted(
            {
                entity
                for violation in verification.violations
                for entity in violation.entities
            }
        )
        return signature, violation_types, entities

    def observe(
        self,
        *,
        scenario: ScenarioInstance,
        verification: VerificationReport,
        candidate_id: str,
        ast_signature: str,
        iteration: int,
        conflict_graph_signature: str | None,
    ) -> CounterexampleRecord:
        signature, violation_types, entities = self._pattern(scenario, verification)
        burden = sum(violation.magnitude for violation in verification.violations)
        existing = self._records.get(signature)
        if existing is None:
            record = CounterexampleRecord(
                counterexample_id=f"cex_{signature[:12]}",
                signature=signature,
                scenario_id=scenario.scenario_id,
                scenario_hash=scenario.stable_hash,
                violation_types=violation_types,
                entities=entities,
                observation_count=1,
                repair_failures=0,
                candidate_ids=[candidate_id],
                ast_signatures=[ast_signature],
                first_iteration=iteration,
                last_iteration=iteration,
                max_violation_burden=burden,
                latest_conflict_graph_signature=conflict_graph_signature,
            )
        else:
            candidate_ids = list(existing.candidate_ids)
            if candidate_id not in candidate_ids:
                candidate_ids.append(candidate_id)
            ast_signatures = list(existing.ast_signatures)
            if ast_signature not in ast_signatures:
                ast_signatures.append(ast_signature)
            record = existing.model_copy(
                update={
                    "observation_count": existing.observation_count + 1,
                    "candidate_ids": candidate_ids,
                    "ast_signatures": ast_signatures,
                    "last_iteration": iteration,
                    "max_violation_burden": max(
                        existing.max_violation_burden,
                        burden,
                    ),
                    "latest_conflict_graph_signature": conflict_graph_signature,
                }
            )
        self._records[signature] = record
        return record

    def mark_repair_failure(self, signature: str) -> CounterexampleRecord:
        if signature not in self._records:
            raise KeyError(f"unknown counterexample signature: {signature}")
        existing = self._records[signature]
        updated = existing.model_copy(
            update={"repair_failures": existing.repair_failures + 1}
        )
        self._records[signature] = updated
        return updated

    def mark_replayed(
        self,
        signature: str,
        *,
        iteration: int,
    ) -> CounterexampleRecord:
        if signature not in self._records:
            raise KeyError(f"unknown counterexample signature: {signature}")
        existing = self._records[signature]
        updated = existing.model_copy(
            update={
                "replay_count": existing.replay_count + 1,
                "last_replayed_iteration": iteration,
            }
        )
        self._records[signature] = updated
        return updated

    def merge(self, incoming: CounterexampleRecord) -> CounterexampleRecord:
        existing = self._records.get(incoming.signature)
        if existing is None:
            self._records[incoming.signature] = incoming.model_copy(deep=True)
            return self._records[incoming.signature]
        candidate_ids = list(existing.candidate_ids)
        for candidate_id in incoming.candidate_ids:
            if candidate_id not in candidate_ids:
                candidate_ids.append(candidate_id)
        ast_signatures = list(existing.ast_signatures)
        for ast_signature in incoming.ast_signatures:
            if ast_signature not in ast_signatures:
                ast_signatures.append(ast_signature)
        merged = existing.model_copy(
            update={
                "observation_count": (
                    existing.observation_count + incoming.observation_count
                ),
                "repair_failures": existing.repair_failures + incoming.repair_failures,
                "replay_count": existing.replay_count + incoming.replay_count,
                "last_replayed_iteration": max(
                    (
                        value
                        for value in (
                            existing.last_replayed_iteration,
                            incoming.last_replayed_iteration,
                        )
                        if value is not None
                    ),
                    default=None,
                ),
                "candidate_ids": candidate_ids,
                "ast_signatures": ast_signatures,
                "first_iteration": min(
                    existing.first_iteration,
                    incoming.first_iteration,
                ),
                "last_iteration": max(
                    existing.last_iteration,
                    incoming.last_iteration,
                ),
                "max_violation_burden": max(
                    existing.max_violation_burden,
                    incoming.max_violation_burden,
                ),
                "latest_conflict_graph_signature": (
                    incoming.latest_conflict_graph_signature
                ),
            }
        )
        self._records[incoming.signature] = merged
        return merged

    @property
    def records(self) -> list[CounterexampleRecord]:
        return [self._records[key] for key in sorted(self._records)]

    def ranked_for_replay(self, limit: int | None = None) -> list[CounterexampleRecord]:
        if limit is not None and limit < 1:
            raise ValueError("replay limit must be positive")
        ranked = sorted(
            self._records.values(),
            key=lambda record: (
                -record.repair_failures,
                -record.observation_count,
                -len(record.violation_types),
                -record.max_violation_burden,
                record.replay_count,
                record.signature,
            ),
        )
        return ranked if limit is None else ranked[:limit]

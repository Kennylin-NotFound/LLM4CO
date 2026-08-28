from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from cover_opt.baselines.models import GeneratedSolverArtifact, SolverExecutionOutcome


class SolverRunnerReplayMiss(LookupError):
    pass


class SolverCodeRunner(Protocol):
    safe_mode: str

    def execute(self, artifact: GeneratedSolverArtifact) -> SolverExecutionOutcome:
        """Execute or replay one generated solver artifact."""


class ReplaySolverCodeRunner:
    safe_mode = "replay_only_no_code_execution"

    def __init__(self, entries: list[dict]) -> None:
        if not entries:
            raise ValueError("solver runner replay requires at least one entry")
        self._entries = list(entries)
        self._position = 0

    @classmethod
    def from_file(cls, path: Path) -> "ReplaySolverCodeRunner":
        with path.resolve().open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("format_version") != "1.0":
            raise ValueError("unsupported solver-runner replay format_version")
        entries = payload.get("entries")
        if not isinstance(entries, list):
            raise ValueError("solver-runner replay entries must be a list")
        return cls(entries)

    def execute(self, artifact: GeneratedSolverArtifact) -> SolverExecutionOutcome:
        if self._position >= len(self._entries):
            raise SolverRunnerReplayMiss(
                f"no solver execution replay remains for iteration={artifact.iteration}"
            )
        entry = self._entries[self._position]
        expected_iteration = entry.get("expected_iteration")
        if expected_iteration is not None and expected_iteration != artifact.iteration:
            raise SolverRunnerReplayMiss(
                "solver execution replay iteration mismatch: "
                f"expected={expected_iteration}, actual={artifact.iteration}"
            )
        expected_hash = entry.get("expected_artifact_hash")
        if expected_hash and expected_hash != artifact.artifact_hash:
            raise SolverRunnerReplayMiss(
                "solver execution replay artifact mismatch: "
                f"expected={expected_hash}, actual={artifact.artifact_hash}"
            )
        self._position += 1
        payload = dict(entry)
        payload.pop("expected_iteration", None)
        return SolverExecutionOutcome.model_validate(payload)

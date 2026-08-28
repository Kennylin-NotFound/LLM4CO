from __future__ import annotations

from typing import Any, Protocol

from cover_opt.domain.models import ScenarioInstance
from cover_opt.heuristics.patch import HeuristicPatch
from cover_opt.heuristics.schema import HeuristicDSL
from cover_opt.search.refiner import RefinementContext


class PatchGenerationError(RuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class PatchGenerator(Protocol):
    def propose(self, context: RefinementContext) -> HeuristicPatch | None:
        """Return one bounded patch, or None when no proposal is available."""


class InitialProgramGenerator(Protocol):
    events: list[Any]

    def generate_candidates(
        self,
        scenario: ScenarioInstance,
        *,
        count: int,
    ) -> list[HeuristicDSL]:
        """Generate up to count typed initial heuristics."""


class ScriptedPatchGenerator:
    counts_as_llm_call = False

    def __init__(self, patches: list[HeuristicPatch]) -> None:
        self._patches = list(patches)
        self.call_count = 0

    def propose(self, context: RefinementContext) -> HeuristicPatch | None:
        del context
        if self.call_count >= len(self._patches):
            return None
        patch = self._patches[self.call_count]
        self.call_count += 1
        return patch

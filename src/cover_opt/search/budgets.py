from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SearchBudgets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_patch_proposals: int = Field(ge=0, default=4)
    max_total_llm_calls: int | None = Field(ge=0, default=None)
    max_evaluator_calls: int = Field(ge=1, default=5)
    max_wall_time_seconds: float = Field(gt=0, default=30.0)
    max_counterexample_replays: int = Field(ge=0, default=4)
    max_replays_per_counterexample: int = Field(ge=1, default=2)
    stop_on_first_feasible: bool = True

    @property
    def effective_max_total_llm_calls(self) -> int:
        if self.max_total_llm_calls is not None:
            return self.max_total_llm_calls
        return self.max_patch_proposals

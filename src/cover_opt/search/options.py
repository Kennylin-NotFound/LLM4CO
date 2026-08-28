from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class SearchFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_mode: Literal["none", "generic", "conflict_directed"] = (
        "conflict_directed"
    )
    feasible_masks_enabled: bool = True
    repair_actions_enabled: bool = True
    counterexample_memory_enabled: bool = True
    counterexample_replay_enabled: bool = False
    structural_diversity_enabled: bool = True
    objective_refinement_enabled: bool = False
    counterfactual_weight_probe_enabled: bool = False

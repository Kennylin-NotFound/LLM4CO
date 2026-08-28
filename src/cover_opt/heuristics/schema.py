from __future__ import annotations

import math
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DSLModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceFeature(str, Enum):
    CRITICAL_PATH_RANK = "critical_path_rank"
    RESOURCE_DEMAND_RATIO = "resource_demand_ratio"
    SUCCESSOR_COUNT = "successor_count"
    WORKLOAD_RATIO = "workload_ratio"


class NodeFeature(str, Enum):
    RESIDUAL_COMPUTE_RATIO = "residual_compute_ratio"
    RESIDUAL_MEMORY_RATIO = "residual_memory_ratio"
    DEPENDENCY_LATENCY = "dependency_latency"
    PREDICTED_CONTACT_DURATION = "predicted_contact_duration"
    MIGRATION_PENALTY = "migration_penalty"


class PathFeature(str, Enum):
    PATH_LATENCY = "path_latency"
    BOTTLENECK_BANDWIDTH = "bottleneck_bandwidth"
    HOP_COUNT = "hop_count"
    CONTACT_DURATION = "contact_duration"


class RepairAction(str, Enum):
    REROUTE = "reroute"
    MOVE_BOTTLENECK_SERVICE = "move_bottleneck_service"
    SWAP_SERVICES = "swap_services"
    BOUNDED_BACKTRACK = "bounded_backtrack"


class WeightedTerm(DSLModel):
    weight: float

    @field_validator("weight")
    @classmethod
    def finite_weight(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("DSL weights must be finite")
        return value


class ServiceTerm(WeightedTerm):
    feature: ServiceFeature


class NodeTerm(WeightedTerm):
    feature: NodeFeature


class PathTerm(WeightedTerm):
    feature: PathFeature


class ServiceOrderRule(DSLModel):
    op: Literal["weighted_sum"] = "weighted_sum"
    terms: list[ServiceTerm] = Field(min_length=1, max_length=8)
    direction: Literal["ascending", "descending"] = "descending"


class NodeScoreRule(DSLModel):
    op: Literal["weighted_sum"] = "weighted_sum"
    terms: list[NodeTerm] = Field(min_length=1, max_length=8)


class PathScoreRule(DSLModel):
    op: Literal["weighted_sum"] = "weighted_sum"
    terms: list[PathTerm] = Field(min_length=1, max_length=8)


class HeuristicDSL(DSLModel):
    version: Literal["1.0"] = "1.0"
    service_order: ServiceOrderRule
    node_score: NodeScoreRule
    path_score: PathScoreRule
    repair_policy: list[RepairAction] = Field(default_factory=list, max_length=4)


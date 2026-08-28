from __future__ import annotations

import math
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cover_opt.hashing import sha256_json


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(StrictModel):
    source_class: Literal["original_paper", "public_reference", "synthetic_assumption"]
    source_reference: str = Field(min_length=1)
    notes: str = ""


class ComputeNode(StrictModel):
    node_id: str = Field(min_length=1)
    compute_capacity: float = Field(gt=0)
    memory_capacity: float = Field(gt=0)
    compute_rate_mips: float = Field(gt=0)
    position_km: tuple[float, float, float] | None = None

    @field_validator("compute_capacity", "memory_capacity", "compute_rate_mips")
    @classmethod
    def finite_resources(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("node resource values must be finite")
        return value

    @field_validator("position_km")
    @classmethod
    def finite_position(
        cls, value: tuple[float, float, float] | None
    ) -> tuple[float, float, float] | None:
        if value is not None and not all(math.isfinite(item) for item in value):
            raise ValueError("node position values must be finite")
        return value


class NetworkLink(StrictModel):
    link_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    distance_km: float = Field(gt=0)
    transmission_rate_mbps: float = Field(gt=0)
    bandwidth_mbps: float = Field(gt=0)
    available_from: int = Field(ge=0)
    available_until: int = Field(ge=0)
    bidirectional: bool = True
    link_class: Literal["fixture", "intra_plane", "inter_plane"] = "fixture"

    @model_validator(mode="after")
    def validate_link(self) -> "NetworkLink":
        numeric = (
            self.distance_km,
            self.transmission_rate_mbps,
            self.bandwidth_mbps,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("link numeric values must be finite")
        if self.source == self.target:
            raise ValueError("self links are not allowed")
        if self.available_until < self.available_from:
            raise ValueError("link availability window is reversed")
        return self


class Microservice(StrictModel):
    service_id: str = Field(min_length=1)
    compute_demand: float = Field(ge=0)
    memory_demand: float = Field(ge=0)
    workload_mi: float = Field(ge=0)
    eligible_nodes: list[str] = Field(min_length=1)

    @field_validator("compute_demand", "memory_demand", "workload_mi")
    @classmethod
    def finite_demands(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("service demand values must be finite")
        return value

    @field_validator("eligible_nodes")
    @classmethod
    def unique_eligible_nodes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("eligible_nodes must be unique")
        return value


class ServiceEdge(StrictModel):
    edge_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    data_volume_mbit: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_edge(self) -> "ServiceEdge":
        if self.source == self.target:
            raise ValueError("service self dependencies are not allowed")
        if not math.isfinite(self.data_volume_mbit):
            raise ValueError("data_volume_mbit must be finite")
        return self


class ObjectiveWeights(StrictModel):
    latency: float = Field(ge=0, default=1.0)
    load_imbalance: float = Field(ge=0, default=0.0)
    migration_cost: float = Field(ge=0, default=0.0)
    energy_proxy: float = Field(ge=0, default=0.0)

    @model_validator(mode="after")
    def validate_weights(self) -> "ObjectiveWeights":
        values = (
            self.latency,
            self.load_imbalance,
            self.migration_cost,
            self.energy_proxy,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("objective weights must be finite")
        if not any(value > 0 for value in values):
            raise ValueError("at least one objective weight must be positive")
        return self


class ScenarioInstance(StrictModel):
    scenario_id: str = Field(min_length=1)
    seed: int = Field(ge=0)
    time_slot: int = Field(ge=0)
    generator_version: str = Field(min_length=1)
    slot_duration_seconds: float = Field(gt=0)
    nodes: list[ComputeNode] = Field(min_length=1)
    links: list[NetworkLink]
    services: list[Microservice] = Field(min_length=1)
    service_edges: list[ServiceEdge]
    previous_placement: dict[str, str]
    qos_latency_ms: float = Field(gt=0)
    migration_budget: int = Field(ge=0)
    objective: ObjectiveWeights
    provenance: Provenance

    @model_validator(mode="after")
    def validate_references_and_dag(self) -> "ScenarioInstance":
        node_ids = [node.node_id for node in self.nodes]
        service_ids = [service.service_id for service in self.services]
        link_ids = [link.link_id for link in self.links]
        edge_ids = [edge.edge_id for edge in self.service_edges]

        for label, identifiers in (
            ("node", node_ids),
            ("service", service_ids),
            ("link", link_ids),
            ("service edge", edge_ids),
        ):
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{label} identifiers must be unique")

        node_set = set(node_ids)
        service_set = set(service_ids)
        for link in self.links:
            if link.source not in node_set or link.target not in node_set:
                raise ValueError(f"link {link.link_id} references an unknown node")
        for service in self.services:
            unknown = set(service.eligible_nodes) - node_set
            if unknown:
                raise ValueError(
                    f"service {service.service_id} has unknown eligible nodes: {sorted(unknown)}"
                )
        for edge in self.service_edges:
            if edge.source not in service_set or edge.target not in service_set:
                raise ValueError(f"service edge {edge.edge_id} references an unknown service")
        for service_id, node_id in self.previous_placement.items():
            if service_id not in service_set or node_id not in node_set:
                raise ValueError("previous_placement references an unknown entity")

        if not math.isfinite(self.qos_latency_ms):
            raise ValueError("qos_latency_ms must be finite")
        self._assert_acyclic(service_ids)
        return self

    def _assert_acyclic(self, service_ids: list[str]) -> None:
        indegree = {service_id: 0 for service_id in service_ids}
        successors = {service_id: [] for service_id in service_ids}
        for edge in self.service_edges:
            indegree[edge.target] += 1
            successors[edge.source].append(edge.target)
        ready = sorted(key for key, degree in indegree.items() if degree == 0)
        visited = 0
        while ready:
            current = ready.pop(0)
            visited += 1
            for successor in successors[current]:
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    ready.append(successor)
                    ready.sort()
        if visited != len(service_ids):
            raise ValueError("service dependency graph must be acyclic")

    @property
    def stable_hash(self) -> str:
        return sha256_json(self)


class PlanStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class RouteAssignment(StrictModel):
    edge_id: str = Field(min_length=1)
    path: list[str] = Field(min_length=1)


class MigrationRecord(StrictModel):
    service_id: str = Field(min_length=1)
    source_node: str | None = None
    target_node: str = Field(min_length=1)
    cost: float = Field(ge=0)


class DeploymentPlan(StrictModel):
    placement: dict[str, str]
    routes: list[RouteAssignment]
    resource_snapshot: dict[str, dict[str, float]] = Field(default_factory=dict)
    migrations: list[MigrationRecord] = Field(default_factory=list)
    status: PlanStatus
    method: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)


class ViolationType(str, Enum):
    UNIQUE_PLACEMENT = "unique_placement"
    NODE_ELIGIBILITY = "node_eligibility"
    NODE_CAPACITY = "node_capacity"
    ROUTE_CONNECTIVITY = "route_connectivity"
    LINK_BANDWIDTH = "link_bandwidth"
    QOS_LATENCY = "qos_latency"
    MIGRATION_BUDGET = "migration_budget"


AttributionMethod = Literal[
    "direct",
    "exact_resource_share",
    "exact_flow_share",
    "exact_event_share",
    "proxy_uniform",
]


class ConstraintViolation(StrictModel):
    violation_type: ViolationType
    magnitude: float = Field(ge=0)
    entities: list[str] = Field(min_length=1)
    contributing_decisions: list[str] = Field(default_factory=list)
    decision_contributions: dict[str, float] = Field(default_factory=dict)
    attribution_method: AttributionMethod = "proxy_uniform"
    dsl_components: list[str] = Field(default_factory=list)
    message: str = Field(min_length=1)

    @field_validator("magnitude")
    @classmethod
    def finite_magnitude(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("violation magnitude must be finite")
        return value

    @model_validator(mode="after")
    def validate_contributions(self) -> "ConstraintViolation":
        unknown = set(self.decision_contributions) - set(self.contributing_decisions)
        if unknown:
            raise ValueError(
                f"decision contribution keys are not declared decisions: {sorted(unknown)}"
            )
        values = self.decision_contributions.values()
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("decision contributions must be finite and non-negative")
        return self


class VerificationReport(StrictModel):
    feasible: bool
    violations: list[ConstraintViolation]
    verifier_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_consistency(self) -> "VerificationReport":
        if self.feasible and self.violations:
            raise ValueError("a feasible report cannot contain violations")
        if not self.feasible and not self.violations:
            raise ValueError("an infeasible report must contain at least one violation")
        return self


class HeuristicProgram(StrictModel):
    version: str = Field(min_length=1)
    service_order: dict[str, Any]
    node_score: dict[str, Any]
    path_score: dict[str, Any]
    repair_policy: list[str]
    parent_ids: list[str] = Field(default_factory=list)
    patch_history: list[dict[str, Any]] = Field(default_factory=list)
    static_verification: Literal["not_checked", "valid", "invalid"] = "not_checked"
    ast_signature: str | None = None

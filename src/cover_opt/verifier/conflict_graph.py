from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.models import VerificationReport
from cover_opt.hashing import sha256_json
from cover_opt.verifier.violations import (
    FEATURES_BY_VIOLATION,
    REPAIR_ACTIONS_BY_VIOLATION,
)


COMPONENT_ORDER = {
    "service_order": 0,
    "node_score": 1,
    "path_score": 2,
    "repair_policy": 3,
}


class ConflictNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    kind: Literal["constraint", "decision"]
    label: str
    magnitude: float = Field(ge=0, default=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConflictEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    constraint_id: str
    decision_id: str
    contribution: float = Field(ge=0)


class ConstraintDecisionConflictGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[ConflictNode]
    edges: list[ConflictEdge]
    allowed_components: list[str]
    allowed_features: dict[str, list[str]] = Field(default_factory=dict)
    allowed_repair_actions: list[str] = Field(default_factory=list)
    source_verifier_version: str
    graph_signature: str

    def constraint_nodes(self) -> list[ConflictNode]:
        return [node for node in self.nodes if node.kind == "constraint"]

    def decision_nodes(self) -> list[ConflictNode]:
        return [node for node in self.nodes if node.kind == "decision"]


class ConflictGraphBuilder:
    version = "0.1.0"

    def build(
        self, report: VerificationReport
    ) -> ConstraintDecisionConflictGraph:
        nodes: list[ConflictNode] = []
        edges: list[ConflictEdge] = []
        decision_ids: set[str] = set()
        allowed_components: set[str] = set()
        allowed_features: dict[str, set[str]] = {}
        allowed_repair_actions: set[str] = set()

        ordered_violations = sorted(
            enumerate(report.violations),
            key=lambda item: (
                -item[1].magnitude,
                item[1].violation_type.value,
                item[0],
            ),
        )
        for rank, (original_index, violation) in enumerate(ordered_violations):
            constraint_id = (
                f"constraint:{rank:03d}:{violation.violation_type.value}"
            )
            nodes.append(
                ConflictNode(
                    node_id=constraint_id,
                    kind="constraint",
                    label=violation.violation_type.value,
                    magnitude=violation.magnitude,
                    metadata={
                        "entities": violation.entities,
                        "message": violation.message,
                        "original_index": original_index,
                        "dsl_components": violation.dsl_components,
                        "attribution_method": violation.attribution_method,
                    },
                )
            )
            allowed_components.update(violation.dsl_components)
            for component, features in FEATURES_BY_VIOLATION[
                violation.violation_type
            ].items():
                allowed_features.setdefault(component, set()).update(features)
            allowed_repair_actions.update(
                REPAIR_ACTIONS_BY_VIOLATION[violation.violation_type]
            )
            decisions = violation.contributing_decisions
            if decisions:
                default_contribution = 1.0 / len(decisions)
            else:
                default_contribution = 0.0
            for decision in sorted(decisions):
                decision_id = f"decision:{decision}"
                if decision_id not in decision_ids:
                    decision_ids.add(decision_id)
                    nodes.append(
                        ConflictNode(
                            node_id=decision_id,
                            kind="decision",
                            label=decision,
                        )
                    )
                edges.append(
                    ConflictEdge(
                        constraint_id=constraint_id,
                        decision_id=decision_id,
                        contribution=violation.decision_contributions.get(
                            decision, default_contribution
                        ),
                    )
                )

        nodes = sorted(nodes, key=lambda node: (node.kind, node.node_id))
        edges = sorted(
            edges,
            key=lambda edge: (
                edge.constraint_id,
                -edge.contribution,
                edge.decision_id,
            ),
        )
        components = sorted(
            allowed_components,
            key=lambda component: COMPONENT_ORDER.get(component, 99),
        )
        feature_payload = {
            component: sorted(features)
            for component, features in sorted(allowed_features.items())
        }
        repair_actions = sorted(allowed_repair_actions)
        signature_payload = {
            "nodes": [node.model_dump(mode="json") for node in nodes],
            "edges": [edge.model_dump(mode="json") for edge in edges],
            "allowed_components": components,
            "allowed_features": feature_payload,
            "allowed_repair_actions": repair_actions,
            "source_verifier_version": report.verifier_version,
        }
        return ConstraintDecisionConflictGraph(
            nodes=nodes,
            edges=edges,
            allowed_components=components,
            allowed_features=feature_payload,
            allowed_repair_actions=repair_actions,
            source_verifier_version=report.verifier_version,
            graph_signature=sha256_json(signature_payload),
        )

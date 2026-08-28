from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.models import ScenarioInstance, VerificationReport
from cover_opt.heuristics.executor import ExecutionResult
from cover_opt.heuristics.patch import (
    AuthorizedPatchApplier,
    HeuristicPatch,
    PatchApplicationResult,
)
from cover_opt.heuristics.schema import HeuristicDSL
from cover_opt.heuristics.static_verifier import canonical_dsl_payload, dsl_signature
from cover_opt.objective.evaluator import ObjectiveReport
from cover_opt.simulator.latency import evaluate_dag_latency
from cover_opt.verifier.conflict_graph import (
    ConflictGraphBuilder,
    ConstraintDecisionConflictGraph,
)


class PatchRejectionFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch_signature: str = Field(min_length=64, max_length=64)
    patch: dict[str, Any]
    errors: list[str] = Field(min_length=1)
    occurrence_count: int = Field(ge=1, default=1)


class ObjectivePatchEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patch_signature: str = Field(min_length=64, max_length=64)
    patch: dict[str, Any]
    parent_candidate_id: str = Field(min_length=1)
    child_candidate_id: str = Field(min_length=1)
    parent_weighted_objective: float = Field(ge=0.0)
    child_weighted_objective: float = Field(ge=0.0)
    improvement: float
    improved: bool
    occurrence_count: int = Field(ge=1, default=1)
    source: Literal["llm_proposal", "counterfactual_probe"] = "llm_proposal"


class RefinementContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_dsl: dict[str, Any]
    scenario_summary: dict[str, Any]
    conflict_graph: ConstraintDecisionConflictGraph
    feedback_mode: Literal["none", "generic", "conflict_directed"]
    refinement_phase: Literal["feasibility", "objective"] = "feasibility"
    feedback_payload: dict[str, Any]
    operator_catalog: dict[str, Any]
    patch_affordances: dict[str, Any]
    execution_summary: dict[str, Any] | None = None
    allowed_components: list[str]
    allowed_features: dict[str, list[str]] = Field(default_factory=dict)
    allowed_repair_actions: list[str] = Field(default_factory=list)
    objective_gap: float | None = None
    counterexample_summary: dict[str, Any] | None = None
    previous_patch_rejections: list[PatchRejectionFeedback] = Field(
        default_factory=list
    )
    previous_objective_evaluations: list[ObjectivePatchEvaluation] = Field(
        default_factory=list
    )
    blocked_operator_targets: list[str] = Field(default_factory=list)
    max_patch_operations: int = Field(ge=1, le=8, default=4)


ALL_DSL_COMPONENTS = [
    "service_order",
    "node_score",
    "path_score",
    "repair_policy",
]


OPERATOR_CATALOG = {
    "service_order": {
        "effect": "orders services before placement; it does not select nodes",
        "features": {
            "critical_path_rank": "larger means more downstream critical work",
            "resource_demand_ratio": "larger means higher relative resource demand",
            "successor_count": "number of direct service successors",
            "workload_ratio": "service workload magnitude",
        },
    },
    "node_score": {
        "effect": "selects the placement node with the largest weighted score",
        "features": {
            "residual_compute_ratio": "larger favors remaining compute capacity",
            "residual_memory_ratio": "larger favors remaining memory capacity",
            "dependency_latency": "larger means higher predecessor communication latency",
            "predicted_contact_duration": "larger means a longer contact window",
            "migration_penalty": (
                "equals 1 when the node differs from previous placement and 0 "
                "otherwise; a negative weight discourages migrations"
            ),
        },
    },
    "path_score": {
        "effect": "selects a route after placement; it cannot change node placement",
        "features": {
            "path_latency": "larger means higher route latency",
            "bottleneck_bandwidth": "larger means more path bandwidth",
            "hop_count": "number of physical links",
            "contact_duration": "minimum remaining contact time on the path",
        },
    },
    "repair_policy": {
        "effect": (
            "runs bounded local repair after construction; changing the policy "
            "does not directly change the primary node score"
        ),
        "actions": [
            "reroute",
            "move_bottleneck_service",
            "swap_services",
            "bounded_backtrack",
        ],
    },
    "patch_operations": {
        "add_term": "adds an available feature that is absent from a score component",
        "set_weight": "changes exactly one feature already present in a score component",
        "remove_term": "removes exactly one existing score feature",
        "set_direction": "changes only service_order ascending/descending direction",
        "set_repair_policy": "replaces the post-construction repair action sequence",
    },
}


class TargetedRefiner:
    def __init__(
        self,
        *,
        feedback_mode: Literal["none", "generic", "conflict_directed"] = (
            "conflict_directed"
        ),
    ) -> None:
        self.graph_builder = ConflictGraphBuilder()
        self.patch_applier = AuthorizedPatchApplier()
        self.feedback_mode = feedback_mode

    @staticmethod
    def _all_allowed_features() -> dict[str, list[str]]:
        return {
            component: list(OPERATOR_CATALOG[component]["features"])
            for component in ("service_order", "node_score", "path_score")
        }

    @staticmethod
    def _patch_affordances(
        parent: HeuristicDSL,
        *,
        allowed_components: list[str],
        allowed_features: dict[str, list[str]],
        allowed_repair_actions: list[str],
    ) -> dict[str, Any]:
        payload = parent.model_dump(mode="json")
        result: dict[str, Any] = {}
        for component in ("service_order", "node_score", "path_score"):
            if component not in allowed_components:
                continue
            existing = [
                item["feature"] for item in payload[component]["terms"]
            ]
            available = allowed_features.get(component, [])
            result[component] = {
                "existing_terms_for_set_or_remove": [
                    feature for feature in existing if feature in available
                ],
                "absent_terms_for_add": [
                    feature for feature in available if feature not in existing
                ],
            }
        if "service_order" in result:
            result["service_order"]["current_direction"] = payload[
                "service_order"
            ]["direction"]
        if "repair_policy" in allowed_components:
            result["repair_policy"] = {
                "current_actions": [
                    action
                    for action in payload["repair_policy"]
                    if action in allowed_repair_actions
                ],
                "available_actions": allowed_repair_actions,
            }
        return result

    @staticmethod
    def _filtered_operator_catalog(
        *,
        allowed_components: list[str],
        allowed_features: dict[str, list[str]],
        allowed_repair_actions: list[str],
    ) -> dict[str, Any]:
        catalog = copy.deepcopy(OPERATOR_CATALOG)
        for component in ("service_order", "node_score", "path_score"):
            permitted = set(allowed_features.get(component, []))
            catalog[component]["features"] = {
                feature: description
                for feature, description in catalog[component]["features"].items()
                if component in allowed_components and feature in permitted
            }
        catalog["repair_policy"]["actions"] = (
            allowed_repair_actions
            if "repair_policy" in allowed_components
            else []
        )
        return catalog

    @staticmethod
    def _execution_summary(
        scenario: ScenarioInstance,
        execution: ExecutionResult,
    ) -> dict[str, Any]:
        decisions = []
        decision_stages = {"service_order", "placement", "routing"}
        total_decisions = sum(
            item.get("stage") in decision_stages for item in execution.trace
        )
        for item in execution.trace:
            if item.get("stage") not in decision_stages:
                continue
            decisions.append(item)
            if len(decisions) >= 16:
                break
        return {
            "placement": execution.plan.placement,
            "routes": [
                route.model_dump(mode="json") for route in execution.plan.routes
            ],
            "decision_trace": decisions,
            "latency_breakdown": evaluate_dag_latency(
                scenario,
                execution.plan,
            ).model_dump(mode="json"),
            "trace_truncated": len(decisions) < total_decisions,
        }

    @staticmethod
    def _operation_target(operation: Any) -> str:
        payload = (
            operation.model_dump(mode="json")
            if hasattr(operation, "model_dump")
            else dict(operation)
        )
        component = payload["component"]
        feature = payload.get("feature")
        suffix = f"{component}.{feature}" if feature else component
        return f"{payload['op']}:{suffix}"

    @classmethod
    def _blocked_targets(
        cls,
        evaluations: list[ObjectivePatchEvaluation],
        *,
        threshold: int = 2,
    ) -> list[str]:
        counts: dict[str, int] = {}
        for evaluation in evaluations:
            if evaluation.improved:
                continue
            for operation in evaluation.patch["operations"]:
                target = cls._operation_target(operation)
                counts[target] = counts.get(target, 0) + evaluation.occurrence_count
        return sorted(target for target, count in counts.items() if count >= threshold)

    def build_context(
        self,
        *,
        parent: HeuristicDSL,
        scenario: ScenarioInstance,
        verification: VerificationReport,
        objective_gap: float | None = None,
        counterexample_summary: dict[str, Any] | None = None,
        previous_patch_rejections: list[PatchRejectionFeedback] | None = None,
    ) -> RefinementContext:
        conflict_graph = self.graph_builder.build(verification)
        if self.feedback_mode == "conflict_directed":
            allowed_components = conflict_graph.allowed_components
            allowed_features = conflict_graph.allowed_features
            allowed_repair_actions = conflict_graph.allowed_repair_actions
            feedback_payload = {
                "mode": "conflict_directed",
                "constraint_decision_graph": conflict_graph.model_dump(mode="json"),
            }
        elif self.feedback_mode == "generic":
            allowed_components = ALL_DSL_COMPONENTS
            allowed_features = self._all_allowed_features()
            allowed_repair_actions = list(
                OPERATOR_CATALOG["repair_policy"]["actions"]
            )
            feedback_payload = {
                "mode": "generic",
                "violations": [
                    {
                        "violation_type": violation.violation_type.value,
                        "magnitude": violation.magnitude,
                        "entities": violation.entities,
                        "message": violation.message,
                    }
                    for violation in verification.violations
                ],
            }
        else:
            allowed_components = ALL_DSL_COMPONENTS
            allowed_features = self._all_allowed_features()
            allowed_repair_actions = list(
                OPERATOR_CATALOG["repair_policy"]["actions"]
            )
            feedback_payload = {"mode": "none"}
            counterexample_summary = None
            previous_patch_rejections = []
        return RefinementContext(
            parent_dsl=canonical_dsl_payload(parent),
            scenario_summary={
                "scenario_id": scenario.scenario_id,
                "scenario_hash": scenario.stable_hash,
                "time_slot": scenario.time_slot,
                "node_count": len(scenario.nodes),
                "service_count": len(scenario.services),
                "dependency_count": len(scenario.service_edges),
                "qos_latency_ms": scenario.qos_latency_ms,
                "migration_budget": scenario.migration_budget,
                "objective_weights": scenario.objective.model_dump(mode="json"),
            },
            conflict_graph=conflict_graph,
            feedback_mode=self.feedback_mode,
            feedback_payload=feedback_payload,
            operator_catalog=self._filtered_operator_catalog(
                allowed_components=allowed_components,
                allowed_features=allowed_features,
                allowed_repair_actions=allowed_repair_actions,
            ),
            patch_affordances=self._patch_affordances(
                parent,
                allowed_components=allowed_components,
                allowed_features=allowed_features,
                allowed_repair_actions=allowed_repair_actions,
            ),
            allowed_components=allowed_components,
            allowed_features=allowed_features,
            allowed_repair_actions=allowed_repair_actions,
            objective_gap=objective_gap,
            counterexample_summary=counterexample_summary,
            previous_patch_rejections=previous_patch_rejections or [],
        )

    def build_objective_context(
        self,
        *,
        parent: HeuristicDSL,
        scenario: ScenarioInstance,
        verification: VerificationReport,
        execution: ExecutionResult,
        objective: ObjectiveReport,
        incumbent_objective: ObjectiveReport,
        previous_patch_rejections: list[PatchRejectionFeedback] | None = None,
        previous_objective_evaluations: list[ObjectivePatchEvaluation] | None = None,
    ) -> RefinementContext:
        if not verification.feasible:
            raise ValueError("objective refinement requires a verifier-approved parent")
        conflict_graph = self.graph_builder.build(verification)
        objective_gap = max(
            0.0,
            objective.weighted_objective - incumbent_objective.weighted_objective,
        )
        objective_evaluations = previous_objective_evaluations or []
        blocked_targets = self._blocked_targets(objective_evaluations)
        allowed_components = ["service_order", "node_score", "path_score"]
        allowed_features = self._all_allowed_features()
        return RefinementContext(
            parent_dsl=canonical_dsl_payload(parent),
            scenario_summary={
                "scenario_id": scenario.scenario_id,
                "scenario_hash": scenario.stable_hash,
                "time_slot": scenario.time_slot,
                "node_count": len(scenario.nodes),
                "service_count": len(scenario.services),
                "dependency_count": len(scenario.service_edges),
                "qos_latency_ms": scenario.qos_latency_ms,
                "migration_budget": scenario.migration_budget,
                "objective_weights": scenario.objective.model_dump(mode="json"),
            },
            conflict_graph=conflict_graph,
            feedback_mode=self.feedback_mode,
            refinement_phase="objective",
            feedback_payload={
                "mode": "objective_directed",
                "current_objective": objective.model_dump(mode="json"),
                "incumbent_objective": incumbent_objective.model_dump(mode="json"),
                "current_weighted_contributions": {
                    "latency": scenario.objective.latency * objective.e2e_latency_ms,
                    "load_imbalance": (
                        scenario.objective.load_imbalance * objective.load_imbalance
                    ),
                    "migration_cost": (
                        scenario.objective.migration_cost * objective.migration_cost
                    ),
                    "energy_proxy": (
                        scenario.objective.energy_proxy * objective.energy_proxy
                    ),
                },
                "requirement": (
                    "minimize weighted_objective while preserving all hard constraints"
                ),
            },
            operator_catalog=self._filtered_operator_catalog(
                allowed_components=allowed_components,
                allowed_features=allowed_features,
                allowed_repair_actions=[],
            ),
            patch_affordances=self._patch_affordances(
                parent,
                allowed_components=allowed_components,
                allowed_features=allowed_features,
                allowed_repair_actions=[],
            ),
            execution_summary=self._execution_summary(scenario, execution),
            allowed_components=allowed_components,
            allowed_features=allowed_features,
            allowed_repair_actions=[],
            objective_gap=objective_gap,
            counterexample_summary=None,
            previous_patch_rejections=previous_patch_rejections or [],
            previous_objective_evaluations=objective_evaluations,
            blocked_operator_targets=blocked_targets,
        )

    def apply_patch(
        self,
        *,
        parent: HeuristicDSL,
        patch: HeuristicPatch,
        context: RefinementContext,
    ) -> PatchApplicationResult:
        if len(patch.operations) > context.max_patch_operations:
            return PatchApplicationResult(
                accepted=False,
                errors=[
                    f"patch has {len(patch.operations)} operations; "
                    f"context allows {context.max_patch_operations}"
                ],
                changed_components=[],
                parent_signature=dsl_signature(parent),
            )
        blocked = sorted(
            {
                target
                for operation in patch.operations
                if (target := self._operation_target(operation))
                in context.blocked_operator_targets
            }
        )
        if blocked:
            return PatchApplicationResult(
                accepted=False,
                errors=[
                    "operator targets blocked after repeated non-improvement: "
                    + ", ".join(blocked)
                ],
                changed_components=sorted(
                    {operation.component for operation in patch.operations}
                ),
                parent_signature=dsl_signature(parent),
            )
        return self.patch_applier.apply(
            parent,
            patch,
            allowed_components=context.allowed_components,
            allowed_features=context.allowed_features,
            allowed_repair_actions=context.allowed_repair_actions,
        )

from __future__ import annotations

from cover_opt.domain.models import (
    AttributionMethod,
    ConstraintViolation,
    ViolationType,
)


COMPONENTS_BY_VIOLATION: dict[ViolationType, tuple[str, ...]] = {
    ViolationType.UNIQUE_PLACEMENT: ("service_order", "repair_policy"),
    ViolationType.NODE_ELIGIBILITY: ("node_score", "repair_policy"),
    ViolationType.NODE_CAPACITY: (
        "service_order",
        "node_score",
        "repair_policy",
    ),
    ViolationType.ROUTE_CONNECTIVITY: ("path_score", "repair_policy"),
    ViolationType.LINK_BANDWIDTH: ("path_score", "repair_policy"),
    ViolationType.QOS_LATENCY: (
        "service_order",
        "node_score",
        "path_score",
        "repair_policy",
    ),
    ViolationType.MIGRATION_BUDGET: ("node_score", "repair_policy"),
}


FEATURES_BY_VIOLATION: dict[
    ViolationType, dict[str, tuple[str, ...]]
] = {
    ViolationType.UNIQUE_PLACEMENT: {
        "service_order": (
            "critical_path_rank",
            "resource_demand_ratio",
            "successor_count",
            "workload_ratio",
        ),
    },
    ViolationType.NODE_ELIGIBILITY: {"node_score": ()},
    ViolationType.NODE_CAPACITY: {
        "service_order": ("resource_demand_ratio", "workload_ratio"),
        "node_score": (
            "residual_compute_ratio",
            "residual_memory_ratio",
        ),
    },
    ViolationType.ROUTE_CONNECTIVITY: {
        "path_score": (
            "bottleneck_bandwidth",
            "hop_count",
            "contact_duration",
        ),
    },
    ViolationType.LINK_BANDWIDTH: {
        "path_score": (
            "bottleneck_bandwidth",
            "hop_count",
            "contact_duration",
        ),
    },
    ViolationType.QOS_LATENCY: {
        "service_order": (
            "critical_path_rank",
            "successor_count",
            "workload_ratio",
        ),
        "node_score": (
            "dependency_latency",
            "predicted_contact_duration",
            "residual_compute_ratio",
            "residual_memory_ratio",
        ),
        "path_score": (
            "path_latency",
            "hop_count",
            "contact_duration",
        ),
    },
    ViolationType.MIGRATION_BUDGET: {
        "node_score": ("migration_penalty",),
    },
}


REPAIR_ACTIONS_BY_VIOLATION: dict[ViolationType, tuple[str, ...]] = {
    ViolationType.UNIQUE_PLACEMENT: ("bounded_backtrack",),
    ViolationType.NODE_ELIGIBILITY: (
        "move_bottleneck_service",
        "bounded_backtrack",
    ),
    ViolationType.NODE_CAPACITY: (
        "move_bottleneck_service",
        "swap_services",
        "bounded_backtrack",
    ),
    ViolationType.ROUTE_CONNECTIVITY: ("reroute",),
    ViolationType.LINK_BANDWIDTH: ("reroute",),
    ViolationType.QOS_LATENCY: (
        "reroute",
        "move_bottleneck_service",
        "swap_services",
    ),
    ViolationType.MIGRATION_BUDGET: (
        "move_bottleneck_service",
        "swap_services",
    ),
}


def make_violation(
    *,
    violation_type: ViolationType,
    magnitude: float,
    entities: list[str],
    decisions: list[str],
    message: str,
    contributions: dict[str, float] | None = None,
    attribution_method: AttributionMethod = "proxy_uniform",
) -> ConstraintViolation:
    return ConstraintViolation(
        violation_type=violation_type,
        magnitude=max(0.0, magnitude),
        entities=entities,
        contributing_decisions=decisions,
        decision_contributions=contributions or {},
        attribution_method=attribution_method,
        dsl_components=list(COMPONENTS_BY_VIOLATION[violation_type]),
        message=message,
    )

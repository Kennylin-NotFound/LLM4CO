from __future__ import annotations

from cover_opt.heuristics.schema import HeuristicDSL


def latency_first() -> HeuristicDSL:
    return HeuristicDSL.model_validate(
        {
            "version": "1.0",
            "service_order": {
                "op": "weighted_sum",
                "terms": [
                    {"feature": "critical_path_rank", "weight": 0.7},
                    {"feature": "workload_ratio", "weight": 0.3},
                ],
                "direction": "descending",
            },
            "node_score": {
                "op": "weighted_sum",
                "terms": [
                    {"feature": "dependency_latency", "weight": -0.7},
                    {"feature": "residual_compute_ratio", "weight": 0.3},
                ],
            },
            "path_score": {
                "op": "weighted_sum",
                "terms": [
                    {"feature": "path_latency", "weight": -0.8},
                    {"feature": "bottleneck_bandwidth", "weight": 0.2},
                ],
            },
            "repair_policy": ["reroute", "bounded_backtrack"],
        }
    )


def capacity_first() -> HeuristicDSL:
    return HeuristicDSL.model_validate(
        {
            "version": "1.0",
            "service_order": {
                "op": "weighted_sum",
                "terms": [
                    {"feature": "resource_demand_ratio", "weight": 0.8},
                    {"feature": "successor_count", "weight": 0.2},
                ],
                "direction": "descending",
            },
            "node_score": {
                "op": "weighted_sum",
                "terms": [
                    {"feature": "residual_compute_ratio", "weight": 0.6},
                    {"feature": "residual_memory_ratio", "weight": 0.4},
                ],
            },
            "path_score": {
                "op": "weighted_sum",
                "terms": [{"feature": "path_latency", "weight": -1.0}],
            },
            "repair_policy": ["move_bottleneck_service", "bounded_backtrack"],
        }
    )


def migration_aware() -> HeuristicDSL:
    payload = latency_first().model_dump(mode="json")
    payload["node_score"]["terms"].append(
        {"feature": "migration_penalty", "weight": -0.5}
    )
    return HeuristicDSL.model_validate(payload)


def latency_no_repair() -> HeuristicDSL:
    payload = latency_first().model_dump(mode="json")
    payload["repair_policy"] = []
    return HeuristicDSL.model_validate(payload)


def capacity_no_repair() -> HeuristicDSL:
    payload = capacity_first().model_dump(mode="json")
    payload["repair_policy"] = []
    return HeuristicDSL.model_validate(payload)

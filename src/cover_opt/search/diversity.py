from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.heuristics.schema import HeuristicDSL, WeightedTerm


class StructuralDistance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_order: float = Field(ge=0.0, le=1.0)
    node_score: float = Field(ge=0.0, le=1.0)
    path_score: float = Field(ge=0.0, le=1.0)
    repair_policy: float = Field(ge=0.0, le=1.0)
    total: float = Field(ge=0.0, le=1.0)
    metric_version: str = "1.0.0"


def _feature_name(term: WeightedTerm) -> str:
    feature = term.feature
    return feature.value if hasattr(feature, "value") else str(feature)


def _rule_distance(
    left_terms: Sequence[WeightedTerm],
    right_terms: Sequence[WeightedTerm],
) -> float:
    left = {_feature_name(term): term.weight for term in left_terms}
    right = {_feature_name(term): term.weight for term in right_terms}
    union = set(left) | set(right)
    intersection = set(left) & set(right)
    support_distance = 1.0 - (len(intersection) / len(union))

    numerator = sum(abs(left.get(name, 0.0) - right.get(name, 0.0)) for name in union)
    denominator = sum(abs(left.get(name, 0.0)) + abs(right.get(name, 0.0)) for name in union)
    weight_distance = numerator / denominator if denominator else 0.0
    return 0.5 * support_distance + 0.5 * weight_distance


def _ordered_sequence_distance(left: Sequence[str], right: Sequence[str]) -> float:
    if not left and not right:
        return 0.0
    previous = [0] * (len(right) + 1)
    for left_item in left:
        current = [0]
        for index, right_item in enumerate(right, start=1):
            if left_item == right_item:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(current[-1], previous[index]))
        previous = current
    lcs_length = previous[-1]
    return 1.0 - (lcs_length / max(len(left), len(right)))


def dsl_structural_distance(
    left: HeuristicDSL,
    right: HeuristicDSL,
) -> StructuralDistance:
    service_rule_distance = _rule_distance(
        left.service_order.terms,
        right.service_order.terms,
    )
    direction_distance = float(
        left.service_order.direction != right.service_order.direction
    )
    service_order = 0.8 * service_rule_distance + 0.2 * direction_distance
    node_score = _rule_distance(left.node_score.terms, right.node_score.terms)
    path_score = _rule_distance(left.path_score.terms, right.path_score.terms)
    repair_policy = _ordered_sequence_distance(
        [action.value for action in left.repair_policy],
        [action.value for action in right.repair_policy],
    )
    total = (service_order + node_score + path_score + repair_policy) / 4.0
    return StructuralDistance(
        service_order=service_order,
        node_score=node_score,
        path_score=path_score,
        repair_policy=repair_policy,
        total=total,
    )

from __future__ import annotations

from cover_opt.heuristics.patch import HeuristicPatch, SetWeightOperation
from cover_opt.heuristics.schema import HeuristicDSL


class CounterfactualWeightProbe:
    """Expand one LLM-selected score component into a bounded numeric neighborhood."""

    version = "1.0.0"

    @staticmethod
    def propose_all(
        *,
        parent: HeuristicDSL,
        patch: HeuristicPatch,
        blocked_operator_targets: list[str] | None = None,
    ) -> list[HeuristicPatch]:
        if len(patch.operations) != 1:
            return []
        operation = patch.operations[0]
        if operation.component not in {"service_order", "node_score", "path_score"}:
            return []
        blocked = set(blocked_operator_targets or [])
        terms = parent.model_dump(mode="json")[operation.component]["terms"]
        probes: list[HeuristicPatch] = []
        if isinstance(operation, SetWeightOperation) and operation.weight != 0:
            target = f"set_weight:{operation.component}.{operation.feature}"
            current = next(
                (
                    item["weight"]
                    for item in terms
                    if item["feature"] == operation.feature
                ),
                None,
            )
            counterfactual = -operation.weight
            if (
                target not in blocked
                and current is not None
                and abs(counterfactual - current) > 1e-12
            ):
                probes.append(
                    CounterfactualWeightProbe._patch(
                        component=operation.component,
                        feature=operation.feature,
                        weight=counterfactual,
                        rationale="LLM-selected feature sign-flip probe.",
                    )
                )
        selected_feature = getattr(operation, "feature", None)
        for term in terms:
            feature = term["feature"]
            weight = term["weight"]
            target = f"set_weight:{operation.component}.{feature}"
            if feature == selected_feature or weight == 0 or target in blocked:
                continue
            probes.append(
                CounterfactualWeightProbe._patch(
                    component=operation.component,
                    feature=feature,
                    weight=-weight,
                    rationale="Component-neighborhood sign-flip probe.",
                )
            )
        return probes

    @staticmethod
    def _patch(
        *,
        component: str,
        feature: str,
        weight: float,
        rationale: str,
    ) -> HeuristicPatch:
        return HeuristicPatch.model_validate(
            {
                "operations": [
                    {
                        "op": "set_weight",
                        "component": component,
                        "feature": feature,
                        "weight": weight,
                    }
                ],
                "rationale": rationale,
            }
        )

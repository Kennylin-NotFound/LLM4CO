from __future__ import annotations

import copy
import math
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cover_opt.heuristics.schema import HeuristicDSL, RepairAction
from cover_opt.heuristics.static_verifier import (
    DSLStaticVerifier,
    DSLVerificationReport,
    dsl_signature,
)


ScoreComponent = Literal["service_order", "node_score", "path_score"]


class PatchModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WeightedPatchOperation(PatchModel):
    component: ScoreComponent
    feature: str = Field(min_length=1)
    weight: float

    @field_validator("weight")
    @classmethod
    def finite_weight(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("patch weights must be finite")
        return value


class SetWeightOperation(WeightedPatchOperation):
    op: Literal["set_weight"]


class AddTermOperation(WeightedPatchOperation):
    op: Literal["add_term"]


class RemoveTermOperation(PatchModel):
    op: Literal["remove_term"]
    component: ScoreComponent
    feature: str = Field(min_length=1)


class SetDirectionOperation(PatchModel):
    op: Literal["set_direction"]
    component: Literal["service_order"]
    direction: Literal["ascending", "descending"]


class SetRepairPolicyOperation(PatchModel):
    op: Literal["set_repair_policy"]
    component: Literal["repair_policy"]
    actions: list[RepairAction] = Field(max_length=4)


PatchOperation = Annotated[
    Union[
        SetWeightOperation,
        AddTermOperation,
        RemoveTermOperation,
        SetDirectionOperation,
        SetRepairPolicyOperation,
    ],
    Field(discriminator="op"),
]


class HeuristicPatch(PatchModel):
    version: Literal["1.0"] = "1.0"
    operations: list[PatchOperation] = Field(min_length=1, max_length=8)
    rationale: str = Field(default="", max_length=500)


class PatchApplicationResult(PatchModel):
    accepted: bool
    program: HeuristicDSL | None = None
    errors: list[str]
    changed_components: list[str]
    parent_signature: str
    child_signature: str | None = None
    static_verification: DSLVerificationReport | None = None


class AuthorizedPatchApplier:
    def __init__(self) -> None:
        self.static_verifier = DSLStaticVerifier()

    def apply(
        self,
        parent: HeuristicDSL,
        patch: HeuristicPatch,
        *,
        allowed_components: list[str],
        allowed_features: dict[str, list[str]] | None = None,
        allowed_repair_actions: list[str] | None = None,
    ) -> PatchApplicationResult:
        parent_signature = dsl_signature(parent)
        allowed = set(allowed_components)
        unauthorized = sorted(
            {
                operation.component
                for operation in patch.operations
                if operation.component not in allowed
            }
        )
        if unauthorized:
            return PatchApplicationResult(
                accepted=False,
                errors=[f"unauthorized components: {unauthorized}"],
                changed_components=[],
                parent_signature=parent_signature,
            )

        if allowed_features is not None:
            unauthorized_features = sorted(
                {
                    f"{operation.component}.{operation.feature}"
                    for operation in patch.operations
                    if hasattr(operation, "feature")
                    and operation.feature
                    not in set(allowed_features.get(operation.component, []))
                }
            )
            if unauthorized_features:
                return PatchApplicationResult(
                    accepted=False,
                    errors=[f"unauthorized features: {unauthorized_features}"],
                    changed_components=[],
                    parent_signature=parent_signature,
                )

        if allowed_repair_actions is not None:
            permitted_actions = set(allowed_repair_actions)
            unauthorized_actions = sorted(
                {
                    action.value
                    for operation in patch.operations
                    if isinstance(operation, SetRepairPolicyOperation)
                    for action in operation.actions
                    if action.value not in permitted_actions
                }
            )
            if unauthorized_actions:
                return PatchApplicationResult(
                    accepted=False,
                    errors=[f"unauthorized repair actions: {unauthorized_actions}"],
                    changed_components=[],
                    parent_signature=parent_signature,
                )

        payload = copy.deepcopy(parent.model_dump(mode="json"))
        changed: set[str] = set()
        errors: list[str] = []
        for operation in patch.operations:
            changed.add(operation.component)
            if isinstance(operation, SetRepairPolicyOperation):
                payload["repair_policy"] = [action.value for action in operation.actions]
                continue
            if isinstance(operation, SetDirectionOperation):
                payload["service_order"]["direction"] = operation.direction
                continue

            terms = payload[operation.component]["terms"]
            matching = [
                index
                for index, term in enumerate(terms)
                if term["feature"] == operation.feature
            ]
            if isinstance(operation, SetWeightOperation):
                if len(matching) != 1:
                    errors.append(
                        f"set_weight requires exactly one existing term: "
                        f"{operation.component}.{operation.feature}"
                    )
                else:
                    terms[matching[0]]["weight"] = operation.weight
            elif isinstance(operation, AddTermOperation):
                if matching:
                    errors.append(
                        f"add_term target already exists: "
                        f"{operation.component}.{operation.feature}"
                    )
                else:
                    terms.append(
                        {"feature": operation.feature, "weight": operation.weight}
                    )
            elif isinstance(operation, RemoveTermOperation):
                if len(matching) != 1:
                    errors.append(
                        f"remove_term requires exactly one existing term: "
                        f"{operation.component}.{operation.feature}"
                    )
                else:
                    terms.pop(matching[0])

        if errors:
            return PatchApplicationResult(
                accepted=False,
                errors=errors,
                changed_components=sorted(changed),
                parent_signature=parent_signature,
            )
        child, static_report = self.static_verifier.parse_and_verify(payload)
        if child is None:
            return PatchApplicationResult(
                accepted=False,
                errors=static_report.errors,
                changed_components=sorted(changed),
                parent_signature=parent_signature,
                static_verification=static_report,
            )
        return PatchApplicationResult(
            accepted=True,
            program=child,
            errors=[],
            changed_components=sorted(changed),
            parent_signature=parent_signature,
            child_signature=dsl_signature(child),
            static_verification=static_report,
        )

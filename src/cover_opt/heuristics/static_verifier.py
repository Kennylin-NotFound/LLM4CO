from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from cover_opt.domain.models import ScenarioInstance
from cover_opt.hashing import sha256_json
from cover_opt.heuristics.schema import HeuristicDSL


class DSLVerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str]
    warnings: list[str]
    ast_signature: str | None = None
    verifier_version: str = "0.1.0"


def canonical_dsl_payload(program: HeuristicDSL) -> dict[str, Any]:
    payload = program.model_dump(mode="json")
    for component in ("service_order", "node_score", "path_score"):
        payload[component]["terms"] = sorted(
            payload[component]["terms"], key=lambda term: term["feature"]
        )
    return payload


def dsl_signature(program: HeuristicDSL) -> str:
    return sha256_json(canonical_dsl_payload(program))


class DSLStaticVerifier:
    version = "0.1.0"

    def parse_and_verify(
        self,
        payload: dict[str, Any],
        scenario: ScenarioInstance | None = None,
    ) -> tuple[HeuristicDSL | None, DSLVerificationReport]:
        try:
            program = HeuristicDSL.model_validate(payload)
        except ValidationError as exc:
            errors = [
                (
                    f"{'.'.join(str(part) for part in item['loc'])}: "
                    f"{item['msg']}; input={item.get('input')!r}"
                )
                for item in exc.errors()
            ]
            return None, DSLVerificationReport(valid=False, errors=errors, warnings=[])
        report = self.verify(program, scenario)
        return (program if report.valid else None), report

    def verify(
        self,
        program: HeuristicDSL,
        scenario: ScenarioInstance | None = None,
    ) -> DSLVerificationReport:
        errors: list[str] = []
        warnings: list[str] = []
        for component_name in ("service_order", "node_score", "path_score"):
            rule = getattr(program, component_name)
            features = [term.feature.value for term in rule.terms]
            if len(features) != len(set(features)):
                errors.append(f"{component_name} contains duplicate features")
            if all(term.weight == 0 for term in rule.terms):
                errors.append(f"{component_name} is a zero expression")

        repair_actions = [action.value for action in program.repair_policy]
        if len(repair_actions) != len(set(repair_actions)):
            errors.append("repair_policy contains duplicate actions")

        if scenario is not None and not scenario.previous_placement:
            migration_features = [
                term.feature.value for term in program.node_score.terms
            ]
            if "migration_penalty" in migration_features:
                warnings.append(
                    "migration_penalty is present but the scenario has no previous placement"
                )

        return DSLVerificationReport(
            valid=not errors,
            errors=errors,
            warnings=warnings,
            ast_signature=dsl_signature(program) if not errors else None,
            verifier_version=self.version,
        )

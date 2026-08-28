from __future__ import annotations

from pathlib import Path
from typing import Any

from cover_opt.config import load_yaml


EXPECTED_CONSTRAINTS = {
    "unique_placement",
    "node_eligibility",
    "node_capacity",
    "route_connectivity",
    "link_bandwidth",
    "qos_latency",
    "migration_budget",
}


def validate_research_contract(path: Path) -> dict[str, Any]:
    payload = load_yaml(path.resolve())
    required_sections = {
        "contract_version",
        "method_name",
        "scope",
        "symbols",
        "hard_constraints",
        "objective",
        "reproducibility",
        "claims",
    }
    missing_sections = sorted(required_sections - payload.keys())
    if missing_sections:
        raise ValueError(f"research contract missing sections: {missing_sections}")

    constraints = payload["hard_constraints"]
    if not isinstance(constraints, list):
        raise ValueError("hard_constraints must be a list")
    identifiers = [item.get("id") for item in constraints if isinstance(item, dict)]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("hard constraint identifiers must be unique")
    if set(identifiers) != EXPECTED_CONSTRAINTS:
        missing = sorted(EXPECTED_CONSTRAINTS - set(identifiers))
        extra = sorted(set(identifiers) - EXPECTED_CONSTRAINTS)
        raise ValueError(f"hard constraint mismatch: missing={missing}, extra={extra}")

    for item in constraints:
        if not item.get("verifier_key") or len(item.get("planned_tests", [])) < 2:
            raise ValueError(
                f"constraint {item.get('id')} requires a verifier key and two planned tests"
            )

    claims = payload["claims"]
    if not isinstance(claims, list) or not claims:
        raise ValueError("claims must be a non-empty list")
    unsupported_states = {
        claim.get("status") for claim in claims if claim.get("status") != "planned"
    }
    if unsupported_states:
        raise ValueError(
            "Phase 0 contract may only contain planned paper claims; "
            f"found {sorted(unsupported_states)}"
        )

    return {
        "method_name": payload["method_name"],
        "contract_version": payload["contract_version"],
        "constraint_count": len(constraints),
        "claim_count": len(claims),
        "status": "valid",
    }


from pathlib import Path

from cover_opt.contracts import validate_research_contract


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_research_contract_is_structurally_complete() -> None:
    summary = validate_research_contract(PROJECT_ROOT / "research_contract.yaml")

    assert summary == {
        "method_name": "COVER-Opt",
        "contract_version": "0.1.0",
        "constraint_count": 7,
        "claim_count": 3,
        "status": "valid",
    }


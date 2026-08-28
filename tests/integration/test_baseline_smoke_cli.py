import json
from pathlib import Path

from cover_opt.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs/experiments/baseline_smoke.yaml"


def test_baseline_smoke_persists_shared_solver_contract(tmp_path: Path) -> None:
    output = tmp_path / "baseline_smoke.json"

    exit_code = main(
        [
            "run-baseline-smoke",
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["evidence_status"] == (
        "small_fixture_baseline_interface_evidence_not_method_result"
    )
    assert payload["oracle_optimality_proven"] is True
    assert len(payload["solver_results"]) == 4
    assert all(item["verification"]["feasible"] for item in payload["solver_results"])
    assert all(item["candidate_set_gap_pct"] >= 0 for item in payload["comparisons"])

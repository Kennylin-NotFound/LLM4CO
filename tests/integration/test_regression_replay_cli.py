import json
from pathlib import Path

from cover_opt.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs/experiments/regression_replay_suite.yaml"


def test_multi_counterexample_regression_replay_suite(tmp_path: Path) -> None:
    output = tmp_path / "regression_replay.json"

    exit_code = main(
        [
            "run-regression-replay",
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["evidence_status"] == (
        "offline_regression_replay_evidence_not_live_llm_performance"
    )
    suite = payload["suite_result"]
    assert suite["passed"] is True
    assert suite["case_count"] == suite["passed_case_count"] == 2
    assert set(suite["violation_coverage"]) >= {
        "migration_budget",
        "route_connectivity",
        "unique_placement",
    }
    assert len(suite["counterexamples"]) == 2
    assert len(suite["replay_queue"]) == 2
    assert all(case["passed"] for case in suite["cases"])
    assert all(
        case["generation_trace"][0]["status"] == "schema_valid"
        for case in suite["cases"]
    )

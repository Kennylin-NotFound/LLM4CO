import json
from pathlib import Path

from cover_opt.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_one_shot_llm_plan_replay_suite_keeps_semantic_outcomes_distinct(
    tmp_path: Path,
) -> None:
    output = tmp_path / "llm_plan_replay_suite.json"

    exit_code = main(
        [
            "run-llm-plan-replay-suite",
            "--config",
            str(PROJECT_ROOT / "configs/experiments/llm_plan_replay_suite.yaml"),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["case_count"] == 2
    assert payload["passed_case_count"] == 2
    direct, structured = payload["cases"]
    assert direct["result"]["status"] == "infeasible"
    assert direct["result"]["solver_result"]["verification"]["feasible"] is False
    assert structured["result"]["status"] == "feasible"
    assert structured["result"]["solver_result"]["verification"]["feasible"] is True
    assert all(case["result"]["llm_calls"] == 1 for case in payload["cases"])

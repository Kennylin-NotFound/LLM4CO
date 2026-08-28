import json
from pathlib import Path

from cover_opt.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs/experiments/current_paper_replay.yaml"


def test_reconstructed_current_paper_replays_both_correction_classes(
    tmp_path: Path,
) -> None:
    output = tmp_path / "current_paper_replay.json"

    exit_code = main(
        [
            "run-current-paper-replay",
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["evidence_status"] == (
        "reconstructed_current_paper_control_flow_not_numeric_reproduction"
    )
    assert len(payload["known_reconstruction_gaps"]) == 4
    result = payload["baseline_result"]
    assert result["status"] == "feasible"
    assert result["stop_reason"] == "verified_plan"
    assert result["runner_safe_mode"] == "replay_only_no_code_execution"
    assert result["statistics"] == {
        "llm_calls": 3,
        "execution_attempts": 3,
        "evaluator_calls": 1,
        "execution_errors": 1,
        "modeling_errors": 1,
        "wall_time_ms": result["statistics"]["wall_time_ms"],
    }
    assert [item["feedback_category"] for item in result["trajectory"]] == [
        "execution_error",
        "modeling_error",
        "none",
    ]
    assert result["solver_result"]["verification"]["feasible"] is True
    assert result["solver_result"]["optimality_proven"] is False

import json
from pathlib import Path

from cover_opt.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs/experiments/replay_method_smoke.yaml"


def test_replay_method_smoke_cli_persists_generation_and_search_trace(
    tmp_path: Path,
) -> None:
    output = tmp_path / "replay_method_smoke.json"

    exit_code = main(
        [
            "run-replay-search",
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["evidence_status"] == (
        "replay_llm_control_flow_evidence_not_model_performance"
    )
    assert payload["generation_trace"][0]["status"] == "schema_valid"
    result = payload["search_result"]
    assert result["stop_reason"] == "first_feasible"
    assert result["best_candidate_id"] == "candidate_001"
    assert result["counterexamples"][0]["observation_count"] == 1
    assert result["replay_queue"] == [
        result["counterexamples"][0]["counterexample_id"]
    ]

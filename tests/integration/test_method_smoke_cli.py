import json
from pathlib import Path

from cover_opt.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_scripted_method_smoke_persists_bounded_trajectory(
    tmp_path: Path, capsys
) -> None:
    output = tmp_path / "method_smoke.json"

    exit_code = main(
        [
            "run-scripted-search",
            "--config",
            str(PROJECT_ROOT / "configs/experiments/method_smoke.yaml"),
            "--output",
            str(output),
        ]
    )
    summary = json.loads(capsys.readouterr().out)
    artifact = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert summary["stop_reason"] == "first_feasible"
    assert summary["candidate_count"] == 2
    assert summary["patch_proposals"] == 1
    assert summary["evaluator_calls"] == 2
    assert artifact["evidence_status"] == (
        "scripted_control_flow_evidence_not_llm_performance"
    )
    records = artifact["search_result"]["records"]
    assert [record["category"] for record in records] == [
        "repairable",
        "feasible_elite",
    ]


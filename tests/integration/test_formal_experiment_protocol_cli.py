import json
from pathlib import Path

from cover_opt.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_formal_experiment_protocol_cli_reports_frozen_gate(capsys) -> None:
    exit_code = main(
        [
            "validate-experiment-protocol",
            "--protocol",
            str(
                PROJECT_ROOT
                / "configs/experiments/formal_experiment_protocol.yaml"
            ),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "frozen_before_live_call"
    assert payload["live_calls_allowed"] is True
    assert payload["stage_count"] == 3
    assert payload["comparison_count"] == payload["claim_gate_count"] == 4

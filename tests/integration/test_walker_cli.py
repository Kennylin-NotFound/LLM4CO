import json
from pathlib import Path

from cover_opt.cli import main
from cover_opt.simulator.scenario_factory import load_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WALKER_CONFIG = PROJECT_ROOT / "configs/scenarios/walker_dynamic.yaml"


def test_cli_generates_reloadable_walker_scenario(tmp_path: Path, capsys) -> None:
    output = tmp_path / "walker_slot_3.json"

    exit_code = main(
        [
            "generate-walker",
            "--config",
            str(WALKER_CONFIG),
            "--time-slot",
            "3",
            "--output",
            str(output),
        ]
    )
    result = json.loads(capsys.readouterr().out)
    scenario = load_scenario(output)

    assert exit_code == 0
    assert result["scenario_hash"] == scenario.stable_hash
    assert result["node_count"] == 24
    assert result["link_count"] == len(scenario.links)
    assert scenario.time_slot == 3


def test_cli_writes_static_latency_breakdown(tmp_path: Path, capsys) -> None:
    output = tmp_path / "small_static_result.json"

    exit_code = main(
        [
            "simulate-static",
            "--scenario",
            str(PROJECT_ROOT / "configs/scenarios/small_static.yaml"),
            "--placement",
            str(PROJECT_ROOT / "configs/placements/small_static_previous.yaml"),
            "--output",
            str(output),
        ]
    )
    result = json.loads(capsys.readouterr().out)
    artifact = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert result["metric"] == "dag_sink_completion_ms"
    assert result["verification_status"] == "not_verified_phase_2"
    assert artifact["evidence_status"] == (
        "deterministic_kernel_evidence_not_plan_verification"
    )
    assert set(artifact["simulation"]["latency"]["service_timings"]) == {
        "ingest",
        "analyze",
        "respond",
    }

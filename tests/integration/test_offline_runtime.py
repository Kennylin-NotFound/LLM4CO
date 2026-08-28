import json
from pathlib import Path

from cover_opt.cli import main
from cover_opt.runtime import run_offline


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs/experiments/offline_smoke.yaml"
REPLAY_PATH = PROJECT_ROOT / "tests/fixtures/llm/replay_offline_smoke.json"


def test_mock_and_replay_runs_share_reproducibility_identity(tmp_path: Path) -> None:
    mock_dir, mock_manifest = run_offline(
        config_path=CONFIG_PATH,
        backend="mock",
        artifacts_root=tmp_path,
    )
    replay_dir, replay_manifest = run_offline(
        config_path=CONFIG_PATH,
        backend="replay",
        replay_file=REPLAY_PATH,
        artifacts_root=tmp_path,
    )

    assert mock_dir != replay_dir
    assert mock_manifest.status == replay_manifest.status == "completed"
    assert mock_manifest.config_hash == replay_manifest.config_hash
    assert mock_manifest.code_tree_hash == replay_manifest.code_tree_hash
    assert mock_manifest.prompt_hash == replay_manifest.prompt_hash
    assert mock_manifest.scenario_hashes == replay_manifest.scenario_hashes
    assert (mock_dir / "manifest.json").exists()
    assert (mock_dir / "traces/0001_request.json").exists()
    assert (mock_dir / "traces/0001_response.json").exists()
    result = json.loads((mock_dir / "result.json").read_text(encoding="utf-8"))
    assert result["evidence_status"] == "not_optimization_evidence"


def test_cli_validates_contract_and_runs_mock(tmp_path: Path, capsys) -> None:
    contract_exit = main(
        [
            "validate-contract",
            "--contract",
            str(PROJECT_ROOT / "research_contract.yaml"),
        ]
    )
    contract_output = json.loads(capsys.readouterr().out)

    run_exit = main(
        [
            "run-offline",
            "--config",
            str(CONFIG_PATH),
            "--llm",
            "mock",
            "--artifacts-root",
            str(tmp_path),
        ]
    )
    run_output = json.loads(capsys.readouterr().out)

    assert contract_exit == 0
    assert contract_output["status"] == "valid"
    assert run_exit == 0
    assert run_output["status"] == "completed"
    assert Path(run_output["run_dir"]).exists()


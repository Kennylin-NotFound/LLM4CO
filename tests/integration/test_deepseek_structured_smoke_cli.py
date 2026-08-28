import json
from pathlib import Path

from cover_opt.cli import main
from cover_opt.llm.deepseek import DeepSeekChatLLM
from cover_opt.llm.protocol import LLMResponse, LLMUsage


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_deepseek_structured_smoke_persists_live_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")

    def fake_generate(self, request):
        scenario_hash = request.metadata["scenario_hash"]
        parsed = {
            "schema_version": "1.0.0",
            "scenario_id": "small_static_v1",
            "scenario_hash": scenario_hash,
            "placement": {
                "analyze": "sat-b",
                "ingest": "sat-b",
                "respond": "sat-b",
            },
            "routes": [
                {"edge_id": "analyze-respond", "path": ["sat-b"]},
                {"edge_id": "ingest-analyze", "path": ["sat-b"]},
            ],
        }
        return LLMResponse(
            request_id=request.request_id,
            request_fingerprint=request.fingerprint,
            provider="deepseek",
            model="deepseek-v4-pro",
            raw_text=json.dumps(parsed),
            parsed=parsed,
            usage=LLMUsage(input_tokens=100, output_tokens=50),
            metadata={
                "system_fingerprint": "a307abda487cd1b463329ccb945ce396"
            },
        )

    monkeypatch.setattr(DeepSeekChatLLM, "generate", fake_generate)
    output = tmp_path / "deepseek_smoke.json"

    exit_code = main(
        [
            "run-deepseek-structured-smoke",
            "--config",
            str(
                PROJECT_ROOT
                / "configs/experiments/deepseek_v4pro_structured_smoke.yaml"
            ),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["evidence_status"] == (
        "single_live_smoke_not_pilot_or_performance_evidence"
    )
    assert payload["llm_settings"]["model"] == "deepseek-v4-pro"
    assert payload["baseline_result"]["status"] == "feasible"
    assert "test-only-key" not in output.read_text(encoding="utf-8")

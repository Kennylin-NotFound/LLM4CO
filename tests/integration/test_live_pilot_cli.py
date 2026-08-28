import json
from pathlib import Path

from cover_opt.cli import main
from cover_opt.llm.deepseek import DeepSeekChatLLM
from cover_opt.llm.protocol import LLMResponse, LLMUsage


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_live_pilot_cli_persists_five_non_claim_cases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")

    def fake_generate(self, request):
        parsed = {
            "version": "1.0",
            "operations": [
                {
                    "op": "add_term",
                    "component": "node_score",
                    "feature": "migration_penalty",
                    "weight": -10.0,
                }
            ],
            "rationale": "Respect the zero migration budget.",
        }
        return LLMResponse(
            request_id=request.request_id,
            request_fingerprint=request.fingerprint,
            provider="deepseek",
            model="deepseek-v4-pro",
            raw_text=json.dumps(parsed),
            parsed=parsed,
            usage=LLMUsage(input_tokens=200, output_tokens=50),
            metadata={
                "system_fingerprint": "a307abda487cd1b463329ccb945ce396"
            },
        )

    monkeypatch.setattr(DeepSeekChatLLM, "generate", fake_generate)
    output = tmp_path / "live_pilot.json"

    exit_code = main(
        [
            "run-deepseek-live-pilot",
            "--config",
            str(
                PROJECT_ROOT
                / "configs/experiments/deepseek_v4pro_live_pilot.yaml"
            ),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    result = payload["pilot_result"]
    assert result["stage_id"] == "live_pilot"
    assert result["claim_eligible"] is False
    assert result["summary"]["case_count"] == 5
    assert len({item["scenario_hash"] for item in result["cases"]}) == 5
    assert result["summary"]["schema_failures"] == 0
    assert result["prompt_hash"] == (
        "50946a993beb969645254054cdff3faae5508b0634a120d3a7075c91fd78b0db"
    )
    assert "test-only-key" not in output.read_text(encoding="utf-8")

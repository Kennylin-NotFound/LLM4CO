import json
from pathlib import Path

from cover_opt.cli import main
from cover_opt.llm.deepseek import DeepSeekChatLLM
from cover_opt.llm.protocol import LLMResponse, LLMUsage


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_deepseek_search_smoke_runs_typed_patch_through_verifier(
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
            usage=LLMUsage(input_tokens=200, output_tokens=60),
            metadata={
                "system_fingerprint": "a307abda487cd1b463329ccb945ce396"
            },
        )

    monkeypatch.setattr(DeepSeekChatLLM, "generate", fake_generate)
    output = tmp_path / "deepseek_search_smoke.json"

    exit_code = main(
        [
            "run-deepseek-search-smoke",
            "--config",
            str(
                PROJECT_ROOT
                / "configs/experiments/deepseek_v4pro_search_smoke.yaml"
            ),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["evidence_status"] == (
        "single_live_method_smoke_not_pilot_or_performance_evidence"
    )
    result = payload["search_result"]
    assert result["stop_reason"] == "first_feasible"
    assert result["best_candidate_id"] == "candidate_001"
    assert result["statistics"]["accepted_patches"] == 1
    assert result["statistics"]["evaluator_calls"] == 2
    assert payload["generation_trace"][0]["status"] == "schema_valid"
    assert "test-only-key" not in output.read_text(encoding="utf-8")

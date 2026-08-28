import json
from pathlib import Path

import pytest

from cover_opt.llm.deepseek import (
    DeepSeekChatLLM,
    DeepSeekChatSettings,
    DeepSeekTransportError,
)
from cover_opt.llm.protocol import build_request


class FakeTransport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def post_json(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def api_response(content: dict) -> dict:
    return {
        "id": "chat_fixture",
        "model": "deepseek-v4-pro",
        "system_fingerprint": "fp_fixture",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": json.dumps(content)},
            }
        ],
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "prompt_cache_hit_tokens": 3,
            "prompt_cache_miss_tokens": 8,
        },
    }


def test_deepseek_adapter_uses_json_chat_contract_without_exposing_key() -> None:
    transport = FakeTransport([api_response({"answer": "ok"})])
    llm = DeepSeekChatLLM(
        api_key="test-secret",
        settings=DeepSeekChatSettings(max_attempts=1),
        transport=transport,
    )
    request = build_request(
        purpose="test",
        prompt="Return JSON with an answer field.",
        expected_output="JSON object",
    )

    response = llm.generate(request)

    assert response.parsed == {"answer": "ok"}
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7
    call = transport.calls[0]
    assert call["url"] == "https://api.deepseek.com/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer test-secret"
    assert call["payload"]["response_format"] == {"type": "json_object"}
    assert call["payload"]["thinking"] == {"type": "disabled"}
    assert call["payload"]["temperature"] == 0.0
    assert "test-secret" not in response.model_dump_json()


def test_deepseek_adapter_retries_transient_failure() -> None:
    transport = FakeTransport(
        [
            DeepSeekTransportError(
                "rate limited", status_code=429, retryable=True
            ),
            api_response({"answer": "retried"}),
        ]
    )
    delays = []
    llm = DeepSeekChatLLM(
        api_key="test-secret",
        settings=DeepSeekChatSettings(
            max_attempts=2,
            initial_backoff_seconds=0.25,
        ),
        transport=transport,
        sleeper=delays.append,
    )

    response = llm.generate(
        build_request(
            purpose="retry",
            prompt="Return JSON.",
            expected_output="JSON object",
        )
    )

    assert response.parsed == {"answer": "retried"}
    assert len(transport.calls) == 2
    assert delays == [0.25]


def test_deepseek_file_cache_avoids_duplicate_call(tmp_path: Path) -> None:
    transport = FakeTransport([api_response({"answer": "cached"})])
    llm = DeepSeekChatLLM(
        api_key="test-secret",
        settings=DeepSeekChatSettings(
            max_attempts=1,
            cache_dir=tmp_path,
        ),
        transport=transport,
    )
    request = build_request(
        purpose="cache",
        prompt="Return JSON.",
        expected_output="JSON object",
    )

    first = llm.generate(request)
    second = llm.generate(request)

    assert first.cached is False
    assert second.cached is True
    assert second.parsed == first.parsed
    assert len(transport.calls) == 1
    cache_text = next(tmp_path.glob("*.json")).read_text(encoding="utf-8")
    assert "test-secret" not in cache_text


def test_deepseek_adapter_rejects_invalid_message_json() -> None:
    response = api_response({"answer": "unused"})
    response["choices"][0]["message"]["content"] = "not-json"
    llm = DeepSeekChatLLM(
        api_key="test-secret",
        settings=DeepSeekChatSettings(max_attempts=1),
        transport=FakeTransport([response]),
    )

    with pytest.raises(ValueError, match="not valid JSON"):
        llm.generate(
            build_request(
                purpose="invalid",
                prompt="Return JSON.",
                expected_output="JSON object",
            )
        )


def test_deepseek_adapter_rejects_model_fingerprint_drift() -> None:
    llm = DeepSeekChatLLM(
        api_key="test-secret",
        settings=DeepSeekChatSettings(
            max_attempts=1,
            expected_system_fingerprint="expected_fp",
        ),
        transport=FakeTransport([api_response({"answer": "unused"})]),
    )

    with pytest.raises(ValueError, match="system fingerprint mismatch"):
        llm.generate(
            build_request(
                purpose="fingerprint",
                prompt="Return JSON.",
                expected_output="JSON object",
            )
        )

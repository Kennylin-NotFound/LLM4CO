from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib import error, request

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cover_opt.hashing import sha256_json
from cover_opt.llm.protocol import LLMRequest, LLMResponse, LLMUsage


class DeepSeekChatSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Literal["deepseek-v4-pro", "deepseek-v4-flash"] = "deepseek-v4-pro"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    thinking: Literal["enabled", "disabled"] = "disabled"
    reasoning_effort: Literal["high", "max"] = "high"
    temperature: float = Field(ge=0.0, le=2.0, default=0.0)
    top_p: float = Field(gt=0.0, le=1.0, default=1.0)
    max_tokens: int = Field(ge=64, le=384_000, default=2048)
    timeout_seconds: float = Field(gt=0.0, default=120.0)
    max_attempts: int = Field(ge=1, le=6, default=3)
    initial_backoff_seconds: float = Field(ge=0.0, default=1.0)
    cache_dir: Path | None = None
    expected_system_fingerprint: str | None = None

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if normalized not in {
            "https://api.deepseek.com",
            "https://api.deepseek.com/v1",
        }:
            raise ValueError("DeepSeek base_url must use the official HTTPS API host")
        return normalized

    @field_validator("api_key_env")
    @classmethod
    def validate_api_key_env(cls, value: str) -> str:
        if not value or not value.replace("_", "").isalnum():
            raise ValueError("api_key_env must be a simple environment variable name")
        return value

    @property
    def request_identity(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"cache_dir", "api_key_env"})


class DeepSeekTransportError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class JSONTransport(Protocol):
    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


class UrllibJSONTransport:
    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        api_request = request.Request(
            url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(api_request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raw_error = exc.read(4096).decode("utf-8", errors="replace")
            retryable = exc.code in {408, 409, 429} or exc.code >= 500
            raise DeepSeekTransportError(
                f"DeepSeek HTTP {exc.code}: {raw_error}",
                status_code=exc.code,
                retryable=retryable,
            ) from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise DeepSeekTransportError(
                f"DeepSeek network error: {exc}",
                retryable=True,
            ) from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DeepSeekTransportError(
                "DeepSeek returned a non-JSON HTTP response",
                retryable=False,
            ) from exc
        if not isinstance(parsed, dict):
            raise DeepSeekTransportError(
                "DeepSeek HTTP response must be a JSON object",
                retryable=False,
            )
        return parsed


class DeepSeekChatLLM:
    provider = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        settings: DeepSeekChatSettings | None = None,
        transport: JSONTransport | None = None,
        sleeper=time.sleep,
    ) -> None:
        if not api_key.strip():
            raise ValueError("DeepSeek API key cannot be empty")
        self._api_key = api_key.strip()
        self.settings = settings or DeepSeekChatSettings()
        self.model = self.settings.model
        self.transport = transport or UrllibJSONTransport()
        self.sleeper = sleeper

    @classmethod
    def from_settings(
        cls,
        settings: DeepSeekChatSettings,
        *,
        transport: JSONTransport | None = None,
        sleeper=time.sleep,
    ) -> "DeepSeekChatLLM":
        api_key = os.environ.get(settings.api_key_env, "")
        if not api_key:
            raise RuntimeError(
                f"missing DeepSeek API key environment variable: {settings.api_key_env}"
            )
        return cls(
            api_key=api_key,
            settings=settings,
            transport=transport,
            sleeper=sleeper,
        )

    def _payload(self, llm_request: LLMRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return exactly one valid JSON object. Do not include "
                        "markdown fences or prose outside the JSON object."
                    ),
                },
                {"role": "user", "content": llm_request.prompt},
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
            "max_tokens": self.settings.max_tokens,
            "thinking": {"type": self.settings.thinking},
        }
        if self.settings.thinking == "enabled":
            payload["reasoning_effort"] = self.settings.reasoning_effort
        else:
            payload["temperature"] = self.settings.temperature
            payload["top_p"] = self.settings.top_p
        return payload

    def _cache_path(self, llm_request: LLMRequest) -> Path | None:
        if self.settings.cache_dir is None:
            return None
        cache_key = sha256_json(
            {
                "request_fingerprint": llm_request.fingerprint,
                "provider": self.provider,
                "settings": self.settings.request_identity,
            }
        )
        return self.settings.cache_dir.resolve() / f"{cache_key}.json"

    def _validate_system_fingerprint(self, response: LLMResponse) -> None:
        expected = self.settings.expected_system_fingerprint
        actual = response.metadata.get("system_fingerprint")
        if expected is not None and actual != expected:
            raise ValueError(
                "DeepSeek system fingerprint mismatch: "
                f"expected={expected}, actual={actual}"
            )

    @staticmethod
    def _read_cache(path: Path, llm_request: LLMRequest) -> LLMResponse | None:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        response = LLMResponse.model_validate(payload)
        if response.request_fingerprint != llm_request.fingerprint:
            raise ValueError("cached DeepSeek response fingerprint mismatch")
        metadata = dict(response.metadata)
        metadata["cache_file"] = str(path)
        return response.model_copy(update={"cached": True, "metadata": metadata})

    @staticmethod
    def _write_cache(path: Path, response: LLMResponse) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                response.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(path)

    def _call(self, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint = f"{self.settings.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        last_error: DeepSeekTransportError | None = None
        for attempt in range(self.settings.max_attempts):
            try:
                return self.transport.post_json(
                    url=endpoint,
                    headers=headers,
                    payload=payload,
                    timeout_seconds=self.settings.timeout_seconds,
                )
            except DeepSeekTransportError as exc:
                last_error = exc
                if not exc.retryable or attempt + 1 >= self.settings.max_attempts:
                    raise
                delay = self.settings.initial_backoff_seconds * (2**attempt)
                if delay:
                    self.sleeper(delay)
        raise RuntimeError("unreachable DeepSeek retry state") from last_error

    def generate(self, llm_request: LLMRequest) -> LLMResponse:
        cache_path = self._cache_path(llm_request)
        if cache_path is not None:
            cached = self._read_cache(cache_path, llm_request)
            if cached is not None:
                self._validate_system_fingerprint(cached)
                return cached

        started = time.perf_counter()
        api_response = self._call(self._payload(llm_request))
        try:
            choice = api_response["choices"][0]
            message = choice["message"]
            content = message["content"]
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("DeepSeek response is missing chat completion fields") from exc
        if finish_reason == "length":
            raise ValueError("DeepSeek JSON output was truncated at max_tokens")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("DeepSeek returned empty JSON content")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("DeepSeek message content is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("DeepSeek structured output must be a JSON object")

        usage_payload = api_response.get("usage") or {}
        response = LLMResponse(
            request_id=llm_request.request_id,
            request_fingerprint=llm_request.fingerprint,
            provider=self.provider,
            model=str(api_response.get("model") or self.settings.model),
            raw_text=content,
            parsed=parsed,
            usage=LLMUsage(
                input_tokens=int(usage_payload.get("prompt_tokens") or 0),
                output_tokens=int(usage_payload.get("completion_tokens") or 0),
            ),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            metadata={
                "api": "chat_completions",
                "requested_model": self.settings.model,
                "thinking": self.settings.thinking,
                "reasoning_effort": (
                    self.settings.reasoning_effort
                    if self.settings.thinking == "enabled"
                    else None
                ),
                "finish_reason": finish_reason,
                "response_id": api_response.get("id"),
                "system_fingerprint": api_response.get("system_fingerprint"),
                "prompt_cache_hit_tokens": int(
                    usage_payload.get("prompt_cache_hit_tokens") or 0
                ),
                "prompt_cache_miss_tokens": int(
                    usage_payload.get("prompt_cache_miss_tokens") or 0
                ),
            },
        )
        self._validate_system_fingerprint(response)
        if cache_path is not None:
            self._write_cache(cache_path, response)
        return response

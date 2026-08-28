from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.hashing import sha256_json


class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    expected_output: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", exclude={"request_id"})
        return sha256_json(payload)


class LLMUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0, default=0)
    output_tokens: int = Field(ge=0, default=0)


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    request_fingerprint: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    raw_text: str
    parsed: dict[str, Any]
    usage: LLMUsage = Field(default_factory=LLMUsage)
    latency_ms: float = Field(ge=0, default=0.0)
    cached: bool = False
    replayed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_request(
    *,
    purpose: str,
    prompt: str,
    expected_output: str,
    metadata: dict[str, Any] | None = None,
) -> LLMRequest:
    payload = {
        "purpose": purpose,
        "prompt": prompt,
        "expected_output": expected_output,
        "metadata": metadata or {},
    }
    request_id = f"req_{sha256_json(payload)[:16]}"
    return LLMRequest(request_id=request_id, **payload)


@runtime_checkable
class LLMProtocol(Protocol):
    provider: str
    model: str

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate one structured response for a recorded request."""


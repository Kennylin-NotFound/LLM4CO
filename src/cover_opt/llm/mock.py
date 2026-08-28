from __future__ import annotations

import copy

from cover_opt.hashing import canonical_json
from cover_opt.llm.protocol import LLMRequest, LLMResponse, LLMUsage


class MockLLM:
    def __init__(
        self,
        *,
        responses: dict[str, dict],
        provider: str = "offline-mock",
        model: str = "mock-cover-opt-v1",
    ) -> None:
        self.responses = copy.deepcopy(responses)
        self.provider = provider
        self.model = model
        self.call_count = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        if request.purpose not in self.responses:
            raise KeyError(f"no mock response configured for purpose={request.purpose!r}")
        self.call_count += 1
        parsed = copy.deepcopy(self.responses[request.purpose])
        return LLMResponse(
            request_id=request.request_id,
            request_fingerprint=request.fingerprint,
            provider=self.provider,
            model=self.model,
            raw_text=canonical_json(parsed),
            parsed=parsed,
            usage=LLMUsage(input_tokens=0, output_tokens=0),
            latency_ms=0.0,
            metadata={"synthetic": True, "call_index": self.call_count},
        )


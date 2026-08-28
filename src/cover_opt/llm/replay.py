from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from cover_opt.llm.protocol import LLMRequest, LLMResponse, LLMUsage


class ReplayMissError(LookupError):
    pass


class ReplayLLM:
    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self._entries_by_purpose: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entry in entries:
            purpose = entry.get("purpose")
            if not purpose:
                raise ValueError("every replay entry requires a purpose")
            self._entries_by_purpose[purpose].append(entry)
        self._positions: dict[str, int] = defaultdict(int)
        self.provider = "offline-replay"
        self.model = "replay"

    @classmethod
    def from_file(cls, path: Path) -> "ReplayLLM":
        with path.resolve().open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("format_version") != "1.0":
            raise ValueError("unsupported replay format_version")
        entries = payload.get("entries")
        if not isinstance(entries, list) or not entries:
            raise ValueError("replay file must contain at least one entry")
        return cls(entries)

    def generate(self, request: LLMRequest) -> LLMResponse:
        entries = self._entries_by_purpose.get(request.purpose, [])
        position = self._positions[request.purpose]
        if position >= len(entries):
            raise ReplayMissError(
                f"no replay entry remains for purpose={request.purpose!r}, "
                f"fingerprint={request.fingerprint}"
            )
        entry = entries[position]
        expected_fingerprint = entry.get("request_fingerprint")
        if expected_fingerprint and expected_fingerprint != request.fingerprint:
            raise ReplayMissError(
                "replay request fingerprint mismatch: "
                f"expected={expected_fingerprint}, actual={request.fingerprint}"
            )
        self._positions[request.purpose] += 1
        self.provider = entry.get("provider", self.provider)
        self.model = entry.get("model", self.model)
        usage = LLMUsage.model_validate(entry.get("usage", {}))
        return LLMResponse(
            request_id=request.request_id,
            request_fingerprint=request.fingerprint,
            provider=self.provider,
            model=self.model,
            raw_text=entry.get("raw_text", ""),
            parsed=entry.get("parsed", {}),
            usage=usage,
            latency_ms=float(entry.get("latency_ms", 0.0)),
            replayed=True,
            metadata={"replay_position": position},
        )


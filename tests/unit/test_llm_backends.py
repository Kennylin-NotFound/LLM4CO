from pathlib import Path

import pytest

from cover_opt.llm.mock import MockLLM
from cover_opt.llm.protocol import build_request
from cover_opt.llm.replay import ReplayLLM, ReplayMissError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPLAY_PATH = PROJECT_ROOT / "tests/fixtures/llm/replay_offline_smoke.json"


def make_request():
    return build_request(
        purpose="offline_candidate_stub",
        prompt="deterministic prompt",
        expected_output="json",
        metadata={"scenario_id": "fixture"},
    )


def test_mock_llm_is_deterministic_for_same_request() -> None:
    candidate = {"artifact_kind": "heuristic_candidate_stub", "version": "0.1"}
    llm = MockLLM(responses={"offline_candidate_stub": candidate})
    request = make_request()

    first = llm.generate(request)
    second = llm.generate(request)

    assert first.request_fingerprint == second.request_fingerprint
    assert first.raw_text == second.raw_text
    assert first.parsed == second.parsed == candidate
    assert first.metadata["synthetic"] is True


def test_replay_is_offline_and_bounded() -> None:
    llm = ReplayLLM.from_file(REPLAY_PATH)
    request = make_request()

    response = llm.generate(request)

    assert response.replayed is True
    assert response.parsed["validation_status"] == "unvalidated_phase_1"
    with pytest.raises(ReplayMissError, match="no replay entry remains"):
        llm.generate(request)


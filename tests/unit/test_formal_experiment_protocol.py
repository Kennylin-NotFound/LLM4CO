from pathlib import Path

import pytest
from pydantic import ValidationError

from cover_opt.evaluation.protocol import (
    FormalExperimentProtocol,
    load_formal_experiment_protocol,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = (
    PROJECT_ROOT / "configs/experiments/formal_experiment_protocol.yaml"
)


def test_frozen_protocol_has_claim_eligible_paired_final_stage() -> None:
    protocol = load_formal_experiment_protocol(PROTOCOL_PATH)

    assert protocol.status == "frozen_before_live_call"
    assert protocol.live_model_lock.live_calls_allowed is True
    assert protocol.live_model_lock.provider == "deepseek"
    assert protocol.live_model_lock.model_snapshot == "deepseek-v4-pro"
    assert protocol.live_model_lock.system_fingerprint == (
        "a307abda487cd1b463329ccb945ce396"
    )
    final = next(item for item in protocol.stages if item.stage_id == "paired_final")
    assert final.claim_eligible is True
    assert len(final.scenario_seeds) == 20
    assert final.llm_repetitions == 3
    assert protocol.statistics.minimum_paired_scenarios == 20
    assert protocol.version == "1.3.0"
    assert len(protocol.claim_gates) == len(protocol.comparisons) == 4
    assert protocol.final_scenario_contract is not None
    assert protocol.statistics.inferential_unit == "scenario_seed"
    assert len(protocol.protocol_hash) == 64


def test_unset_model_cannot_enable_live_calls() -> None:
    protocol = load_formal_experiment_protocol(PROTOCOL_PATH)
    payload = protocol.model_dump(mode="json")
    payload["live_model_lock"]["live_calls_allowed"] = True
    payload["live_model_lock"]["provider"] = "UNSET_GATED"

    with pytest.raises(ValidationError, match="provider/model lock"):
        FormalExperimentProtocol.model_validate(payload)

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from cover_opt.config import load_yaml
from cover_opt.domain.models import ScenarioInstance, VerificationReport


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "configs/scenarios/small_static.yaml"


def test_scenario_hash_is_stable() -> None:
    payload = load_yaml(SCENARIO_PATH)
    first = ScenarioInstance.model_validate(payload)
    second = ScenarioInstance.model_validate(deepcopy(payload))

    assert first.stable_hash == second.stable_hash
    assert len(first.stable_hash) == 64


def test_scenario_rejects_unknown_eligible_node() -> None:
    payload = load_yaml(SCENARIO_PATH)
    payload["services"][0]["eligible_nodes"].append("missing-node")

    with pytest.raises(ValidationError, match="unknown eligible nodes"):
        ScenarioInstance.model_validate(payload)


def test_scenario_rejects_cyclic_service_graph() -> None:
    payload = load_yaml(SCENARIO_PATH)
    payload["service_edges"].append(
        {
            "edge_id": "respond-ingest",
            "source": "respond",
            "target": "ingest",
            "data_volume_mbit": 1.0,
        }
    )

    with pytest.raises(ValidationError, match="must be acyclic"):
        ScenarioInstance.model_validate(payload)


def test_feasible_report_cannot_contain_violations() -> None:
    with pytest.raises(ValidationError, match="cannot contain violations"):
        VerificationReport.model_validate(
            {
                "feasible": True,
                "verifier_version": "test",
                "violations": [
                    {
                        "violation_type": "node_capacity",
                        "magnitude": 1.0,
                        "entities": ["sat-a"],
                        "message": "capacity exceeded",
                    }
                ],
            }
        )

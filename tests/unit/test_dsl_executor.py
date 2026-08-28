from copy import deepcopy
from pathlib import Path

from cover_opt.config import load_yaml
from cover_opt.domain.models import ScenarioInstance, ViolationType
from cover_opt.heuristics.executor import DeterministicExecutor
from cover_opt.heuristics.handcrafted import (
    capacity_first,
    capacity_no_repair,
    latency_first,
    latency_no_repair,
)
from cover_opt.heuristics.schema import HeuristicDSL
from cover_opt.simulator.scenario_factory import load_scenario
from cover_opt.verifier.plan_verifier import PlanVerifier


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "configs/scenarios/small_static.yaml"


def test_executor_is_deterministic_and_traceable() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    executor = DeterministicExecutor(k_paths=3)

    first = executor.execute(scenario, latency_first(), candidate_id="first")
    second = executor.execute(scenario, latency_first(), candidate_id="second")

    assert first.failure_reason is None
    assert first.plan.placement == second.plan.placement
    assert [route.model_dump() for route in first.plan.routes] == [
        route.model_dump() for route in second.plan.routes
    ]
    assert first.trace == second.trace
    assert first.trace[0]["stage"] == "service_order"
    assert {entry["stage"] for entry in first.trace} == {
        "service_order",
        "placement",
        "routing",
        "repair_policy",
    }


def test_executor_masks_ineligible_and_over_capacity_nodes() -> None:
    payload = load_yaml(SCENARIO_PATH)
    payload["nodes"][0]["compute_capacity"] = 2.0
    payload["nodes"][0]["memory_capacity"] = 2.0
    scenario = ScenarioInstance.model_validate(payload)

    result = DeterministicExecutor().execute(scenario, capacity_first())
    report = PlanVerifier().verify(scenario, result.plan)

    assert result.failure_reason is None
    assert result.plan.placement["analyze"] != "sat-a"
    assert all(
        violation.violation_type
        not in {ViolationType.NODE_ELIGIBILITY, ViolationType.NODE_CAPACITY}
        for violation in report.violations
    )
    for service in scenario.services:
        assert result.plan.placement[service.service_id] in service.eligible_nodes


def test_executor_returns_partial_plan_when_masks_remove_all_nodes() -> None:
    payload = load_yaml(SCENARIO_PATH)
    for node in payload["nodes"]:
        node["compute_capacity"] = 0.5
        node["memory_capacity"] = 0.5
    scenario = ScenarioInstance.model_validate(payload)

    result = DeterministicExecutor().execute(scenario, capacity_first())

    assert result.failure_reason is not None
    assert result.failure_reason.startswith("no_capacity_candidate:")
    assert result.plan.status.value == "partial"


def test_no_mask_ablation_exposes_invalid_candidates_to_shared_verifier() -> None:
    payload = load_yaml(SCENARIO_PATH)
    payload["nodes"][0]["compute_capacity"] = 100.0
    payload["nodes"][0]["memory_capacity"] = 100.0
    for service in payload["services"]:
        if service["service_id"] == "respond":
            service["eligible_nodes"] = ["sat-c"]
    scenario = ScenarioInstance.model_validate(payload)
    masked = DeterministicExecutor(
        enable_repair_actions=False,
        feasible_masks_enabled=True,
    ).execute(scenario, capacity_no_repair())
    unmasked = DeterministicExecutor(
        enable_repair_actions=False,
        feasible_masks_enabled=False,
    ).execute(scenario, capacity_no_repair())

    masked_report = PlanVerifier().verify(scenario, masked.plan)
    unmasked_report = PlanVerifier().verify(scenario, unmasked.plan)

    assert masked_report.feasible is True
    assert unmasked_report.feasible is False
    assert ViolationType.NODE_ELIGIBILITY in {
        item.violation_type for item in unmasked_report.violations
    }
    placement_events = [
        item for item in unmasked.trace if item["stage"] == "placement"
    ]
    assert placement_events
    assert all(item["feasible_masks_enabled"] is False for item in placement_events)
    assert all(
        item["candidate_policy"] == "all_nodes_unmasked"
        for item in placement_events
    )


def test_executor_reserves_shared_link_bandwidth_during_construction() -> None:
    payload = load_yaml(SCENARIO_PATH)
    payload["scenario_id"] = "executor_shared_bandwidth_v1"
    payload["nodes"] = payload["nodes"][:2]
    payload["links"] = [payload["links"][0]]
    payload["links"][0]["transmission_rate_mbps"] = 10.0
    payload["links"][0]["bandwidth_mbps"] = 10.0
    payload["services"] = [
        {
            "service_id": service_id,
            "compute_demand": 1.0,
            "memory_demand": 1.0,
            "workload_mi": 1.0,
            "eligible_nodes": [node_id],
        }
        for service_id, node_id in (
            ("source-a", "sat-a"),
            ("target-a", "sat-b"),
            ("source-b", "sat-a"),
            ("target-b", "sat-b"),
        )
    ]
    payload["service_edges"] = [
        {
            "edge_id": "flow-a",
            "source": "source-a",
            "target": "target-a",
            "data_volume_mbit": 6.0,
        },
        {
            "edge_id": "flow-b",
            "source": "source-b",
            "target": "target-b",
            "data_volume_mbit": 6.0,
        },
    ]
    payload["previous_placement"] = {
        service["service_id"]: service["eligible_nodes"][0]
        for service in payload["services"]
    }
    payload["qos_latency_ms"] = 10_000.0
    payload["migration_budget"] = 4
    scenario = ScenarioInstance.model_validate(payload)
    program_payload = latency_no_repair().model_dump(mode="json")
    program_payload["node_score"]["terms"] = [
        {"feature": "migration_penalty", "weight": -1.0}
    ]
    migration_locked = HeuristicDSL.model_validate(program_payload)

    masked = DeterministicExecutor(
        enable_repair_actions=False,
        feasible_masks_enabled=True,
    ).execute(scenario, migration_locked)
    unmasked = DeterministicExecutor(
        enable_repair_actions=False,
        feasible_masks_enabled=False,
    ).execute(scenario, migration_locked)

    assert masked.failure_reason == "no_feasible_path_or_bandwidth:flow-b"
    assert len(masked.plan.routes) == 1
    routing = [item for item in masked.trace if item["stage"] == "routing"]
    assert routing[0]["bandwidth_demand_mbps"] == 6.0
    assert routing[0]["residual_bandwidth_after_mbps"]["a-b"] == 4.0

    unmasked_report = PlanVerifier().verify(scenario, unmasked.plan)
    assert unmasked.failure_reason is None
    assert ViolationType.LINK_BANDWIDTH in {
        item.violation_type for item in unmasked_report.violations
    }

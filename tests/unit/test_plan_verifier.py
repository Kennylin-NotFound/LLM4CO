from copy import deepcopy
from pathlib import Path

import pytest

from cover_opt.config import load_yaml
from cover_opt.domain.deployment import build_deployment_plan
from cover_opt.domain.models import PlanStatus, RouteAssignment, ScenarioInstance, ViolationType
from cover_opt.objective.evaluator import ObjectiveEvaluator
from cover_opt.simulator.link_state import select_deterministic_routes
from cover_opt.simulator.scenario_factory import load_scenario
from cover_opt.simulator.static import StaticSimulator
from cover_opt.verifier.plan_verifier import PlanVerifier


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "configs/scenarios/small_static.yaml"


def violation_types(report):
    return {violation.violation_type for violation in report.violations}


def shared_bandwidth_scenario() -> ScenarioInstance:
    payload = load_yaml(SCENARIO_PATH)
    payload["scenario_id"] = "shared_bandwidth_v1"
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
    return ScenarioInstance.model_validate(payload)


def test_feasible_plan_is_approved_and_evaluated() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    plan = StaticSimulator(scenario).run(scenario.previous_placement).plan

    report = PlanVerifier().verify(scenario, plan)
    objective = ObjectiveEvaluator().evaluate(scenario, plan, report)

    assert report.feasible is True
    assert report.violations == []
    assert objective.e2e_latency_ms == pytest.approx(186.77021218903823)
    assert objective.migration_cost == 0.0


def test_missing_service_produces_structured_unique_placement_violation() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    plan = build_deployment_plan(
        scenario=scenario,
        placement={"ingest": "sat-a", "analyze": "sat-b"},
        routes=[],
        method="invalid_fixture",
        candidate_id="missing-service",
        run_id="test",
        status=PlanStatus.PARTIAL,
    )

    report = PlanVerifier().verify(scenario, plan)

    assert report.feasible is False
    assert ViolationType.UNIQUE_PLACEMENT in violation_types(report)
    unique = next(
        item
        for item in report.violations
        if item.violation_type == ViolationType.UNIQUE_PLACEMENT
    )
    assert unique.entities == ["respond"]
    assert "service_order" in unique.dsl_components
    assert unique.decision_contributions == {"place:respond@missing": 1.0}
    assert unique.attribution_method == "direct"


def test_capacity_violation_attributes_contributing_placements() -> None:
    payload = load_yaml(SCENARIO_PATH)
    payload["nodes"][1]["compute_capacity"] = 5.0
    scenario = ScenarioInstance.model_validate(payload)
    placement = {service.service_id: "sat-b" for service in scenario.services}
    routes = select_deterministic_routes(scenario, placement)
    plan = build_deployment_plan(
        scenario=scenario,
        placement=placement,
        routes=routes,
        method="invalid_fixture",
        candidate_id="capacity",
        run_id="test",
    )

    report = PlanVerifier().verify(scenario, plan)

    capacity = next(
        item
        for item in report.violations
        if item.violation_type == ViolationType.NODE_CAPACITY
    )
    assert capacity.entities == ["sat-b", "compute"]
    assert capacity.magnitude == pytest.approx(0.6)
    assert set(capacity.contributing_decisions) == {
        "place:ingest@sat-b",
        "place:analyze@sat-b",
        "place:respond@sat-b",
    }
    assert sum(capacity.decision_contributions.values()) == pytest.approx(1.0)
    assert capacity.attribution_method == "exact_resource_share"


def test_route_qos_bandwidth_and_migration_have_distinct_types() -> None:
    base = load_yaml(SCENARIO_PATH)

    route_scenario = ScenarioInstance.model_validate(deepcopy(base))
    route_plan = StaticSimulator(route_scenario).run(
        route_scenario.previous_placement
    ).plan.model_copy(deep=True)
    route_plan.routes[0] = RouteAssignment(
        edge_id=route_plan.routes[0].edge_id,
        path=["sat-a", "sat-c"],
    )
    route_report = PlanVerifier().verify(route_scenario, route_plan)
    assert ViolationType.ROUTE_CONNECTIVITY in violation_types(route_report)

    qos_payload = deepcopy(base)
    qos_payload["qos_latency_ms"] = 100.0
    qos_scenario = ScenarioInstance.model_validate(qos_payload)
    qos_plan = StaticSimulator(qos_scenario).run(qos_scenario.previous_placement).plan
    qos_report = PlanVerifier().verify(qos_scenario, qos_plan)
    assert ViolationType.QOS_LATENCY in violation_types(qos_report)
    qos = next(
        item
        for item in qos_report.violations
        if item.violation_type == ViolationType.QOS_LATENCY
    )
    assert qos.attribution_method == "proxy_uniform"

    bandwidth_payload = deepcopy(base)
    bandwidth_payload["service_edges"][0]["data_volume_mbit"] = 1000.0
    bandwidth_payload["qos_latency_ms"] = 20000.0
    bandwidth_scenario = ScenarioInstance.model_validate(bandwidth_payload)
    bandwidth_plan = StaticSimulator(bandwidth_scenario).run(
        bandwidth_scenario.previous_placement
    ).plan
    bandwidth_report = PlanVerifier().verify(bandwidth_scenario, bandwidth_plan)
    assert ViolationType.LINK_BANDWIDTH in violation_types(bandwidth_report)

    migration_payload = deepcopy(base)
    migration_payload["migration_budget"] = 0
    migration_scenario = ScenarioInstance.model_validate(migration_payload)
    placement = {service.service_id: "sat-b" for service in migration_scenario.services}
    migration_plan = build_deployment_plan(
        scenario=migration_scenario,
        placement=placement,
        routes=select_deterministic_routes(migration_scenario, placement),
        method="invalid_fixture",
        candidate_id="migration",
        run_id="test",
    )
    migration_report = PlanVerifier().verify(migration_scenario, migration_plan)
    assert ViolationType.MIGRATION_BUDGET in violation_types(migration_report)
    migration = next(
        item
        for item in migration_report.violations
        if item.violation_type == ViolationType.MIGRATION_BUDGET
    )
    assert migration.attribution_method == "exact_event_share"


def test_shared_link_bandwidth_is_aggregated_across_routes() -> None:
    scenario = shared_bandwidth_scenario()
    plan = build_deployment_plan(
        scenario=scenario,
        placement=scenario.previous_placement,
        routes=[
            RouteAssignment(edge_id="flow-a", path=["sat-a", "sat-b"]),
            RouteAssignment(edge_id="flow-b", path=["sat-a", "sat-b"]),
        ],
        method="shared-bandwidth-fixture",
        candidate_id="shared-bandwidth",
        run_id="test",
    )

    report = PlanVerifier().verify(scenario, plan)
    shared = [
        item
        for item in report.violations
        if item.violation_type == ViolationType.LINK_BANDWIDTH
        and item.entities == ["a-b", "time_slot:0"]
    ]

    assert len(shared) == 1
    assert shared[0].magnitude == pytest.approx(0.2)
    assert shared[0].contributing_decisions == ["route:flow-a", "route:flow-b"]
    assert shared[0].decision_contributions == {
        "route:flow-a": pytest.approx(0.5),
        "route:flow-b": pytest.approx(0.5),
    }
    assert shared[0].attribution_method == "exact_flow_share"


def test_objective_rejects_infeasible_plan() -> None:
    payload = load_yaml(SCENARIO_PATH)
    payload["qos_latency_ms"] = 1.0
    scenario = ScenarioInstance.model_validate(payload)
    plan = StaticSimulator(scenario).run(scenario.previous_placement).plan
    report = PlanVerifier().verify(scenario, plan)

    with pytest.raises(ValueError, match="verifier-approved"):
        ObjectiveEvaluator().evaluate(scenario, plan, report)

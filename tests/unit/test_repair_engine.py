from pathlib import Path

from cover_opt.domain.deployment import build_deployment_plan
from cover_opt.domain.models import ScenarioInstance
from cover_opt.heuristics.executor import DeterministicExecutor
from cover_opt.heuristics.handcrafted import latency_first
from cover_opt.heuristics.repair import DeterministicRepairEngine
from cover_opt.heuristics.schema import HeuristicDSL, RepairAction
from cover_opt.simulator.link_state import select_deterministic_routes
from cover_opt.simulator.scenario_factory import load_scenario
from cover_opt.verifier.plan_verifier import PlanVerifier


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "configs/scenarios/small_static.yaml"


def scenario_with(**updates) -> ScenarioInstance:
    payload = load_scenario(SCENARIO_PATH).model_dump(mode="json")
    payload.update(updates)
    return ScenarioInstance.model_validate(payload)


def program_with(*, repair_policy: list[str], path_latency_weight: float | None = None):
    payload = latency_first().model_dump(mode="json")
    payload["repair_policy"] = repair_policy
    if path_latency_weight is not None:
        payload["path_score"] = {
            "op": "weighted_sum",
            "terms": [
                {"feature": "path_latency", "weight": path_latency_weight}
            ],
        }
    return HeuristicDSL.model_validate(payload)


def repair_stage(result):
    return next(item for item in result.trace if item["stage"] == "repair_policy")


def test_move_action_repeats_strict_improvements_until_migration_is_feasible() -> None:
    scenario = scenario_with(migration_budget=0)
    result = DeterministicExecutor().execute(
        scenario,
        program_with(repair_policy=["move_bottleneck_service"]),
    )

    assert PlanVerifier().verify(scenario, result.plan).feasible is True
    assert result.plan.placement == scenario.previous_placement
    stage = repair_stage(result)
    assert stage["accepted_actions"] == 2
    assert stage["action_trace"][0]["accepted_rounds"] == 2


def test_reroute_action_replaces_a_high_latency_path() -> None:
    scenario = scenario_with(qos_latency_ms=130.0)
    result = DeterministicExecutor(k_paths=3).execute(
        scenario,
        program_with(repair_policy=["reroute"], path_latency_weight=1.0),
    )

    assert PlanVerifier().verify(scenario, result.plan).feasible is True
    stage = repair_stage(result)
    assert stage["accepted_actions"] == 1
    assert stage["action_trace"][0]["status"] == "accepted"
    routes = {route.edge_id: route.path for route in result.plan.routes}
    assert routes["analyze-respond"] == ["sat-a", "sat-b"]


def test_bounded_backtrack_recovers_from_a_greedy_capacity_dead_end() -> None:
    payload = load_scenario(SCENARIO_PATH).model_dump(mode="json")
    capacities = {
        "sat-a": (4.0, 4.0),
        "sat-b": (2.0, 2.0),
        "sat-c": (2.0, 2.0),
    }
    for node in payload["nodes"]:
        node["compute_capacity"], node["memory_capacity"] = capacities[
            node["node_id"]
        ]
    for service in payload["services"]:
        if service["service_id"] == "ingest":
            service["eligible_nodes"] = ["sat-a", "sat-b"]
        elif service["service_id"] == "analyze":
            service["eligible_nodes"] = ["sat-a"]
        else:
            service["eligible_nodes"] = ["sat-c"]
    payload["previous_placement"] = {
        "ingest": "sat-b",
        "analyze": "sat-a",
        "respond": "sat-c",
    }
    payload["migration_budget"] = 3
    payload["qos_latency_ms"] = 1000.0
    scenario = ScenarioInstance.model_validate(payload)

    result = DeterministicExecutor().execute(
        scenario,
        program_with(repair_policy=["bounded_backtrack"]),
    )

    assert result.failure_reason is None
    assert PlanVerifier().verify(scenario, result.plan).feasible is True
    assert result.plan.placement == scenario.previous_placement
    assert repair_stage(result)["action_trace"][0]["status"] == "accepted"


def test_swap_action_repairs_two_crossed_migrations() -> None:
    scenario = scenario_with(migration_budget=0)
    crossed = {
        "ingest": "sat-a",
        "analyze": "sat-c",
        "respond": "sat-b",
    }
    plan = build_deployment_plan(
        scenario=scenario,
        placement=crossed,
        routes=select_deterministic_routes(scenario, crossed),
        method="swap_fixture",
        candidate_id="swap",
        run_id="unit",
    )

    outcome = DeterministicRepairEngine().repair(
        scenario=scenario,
        plan=plan,
        actions=[RepairAction.SWAP_SERVICES],
    )

    assert outcome.verification.feasible is True
    assert outcome.plan.placement == scenario.previous_placement
    assert outcome.accepted_actions == 1

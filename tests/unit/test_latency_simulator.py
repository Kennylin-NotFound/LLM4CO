from pathlib import Path

import pytest

from cover_opt.config import load_yaml
from cover_opt.domain.models import ScenarioInstance
from cover_opt.domain.satellite_graph import NoFeasiblePathError, SatelliteGraph
from cover_opt.simulator.latency import processing_latency_ms
from cover_opt.simulator.link_state import (
    SPEED_OF_LIGHT_KM_PER_SECOND,
    link_latency,
)
from cover_opt.simulator.scenario_factory import load_scenario
from cover_opt.simulator.static import StaticSimulator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SMALL_SCENARIO = PROJECT_ROOT / "configs/scenarios/small_static.yaml"


def test_chain_latency_matches_hand_calculation() -> None:
    scenario = load_scenario(SMALL_SCENARIO)
    result = StaticSimulator(scenario).run(scenario.previous_placement)

    ingest_processing = 20.0 / 1000.0 * 1000.0
    first_communication = 4.0 / 80.0 * 1000.0 + (
        1500.0 / SPEED_OF_LIGHT_KM_PER_SECOND * 1000.0
    )
    analyze_processing = 40.0 / 800.0 * 1000.0
    second_communication = 2.0 / 60.0 * 1000.0 + (
        2100.0 / SPEED_OF_LIGHT_KM_PER_SECOND * 1000.0
    )
    respond_processing = 15.0 / 700.0 * 1000.0
    expected = (
        ingest_processing
        + first_communication
        + analyze_processing
        + second_communication
        + respond_processing
    )

    assert result.latency.e2e_latency_ms == pytest.approx(expected)
    assert result.latency.metric == "dag_sink_completion_ms"
    routes = {route.edge_id: route.path for route in result.plan.routes}
    assert routes["ingest-analyze"] == ["sat-a", "sat-b"]
    assert routes["analyze-respond"] == ["sat-b", "sat-c"]
    assert result.verification_status == "not_verified_phase_2"


def test_shortest_path_uses_end_to_end_link_latency() -> None:
    scenario = load_scenario(SMALL_SCENARIO)
    graph = SatelliteGraph(scenario)

    paths = graph.k_shortest_paths(
        "sat-a",
        "sat-c",
        k=2,
        link_weight=lambda link: link_latency(link, 2.0).total_ms,
    )

    assert paths == (("sat-a", "sat-c"), ("sat-a", "sat-b", "sat-c"))


def test_inactive_links_produce_no_path() -> None:
    payload = load_yaml(SMALL_SCENARIO)
    payload["time_slot"] = 11
    scenario = ScenarioInstance.model_validate(payload)
    graph = SatelliteGraph(scenario)

    with pytest.raises(NoFeasiblePathError, match="no active path"):
        graph.k_shortest_paths(
            "sat-a",
            "sat-c",
            k=1,
            link_weight=lambda link: link_latency(link, 1.0).total_ms,
        )


def test_multiple_predecessors_wait_for_last_arrival() -> None:
    payload = load_yaml(SMALL_SCENARIO)
    payload["nodes"] = [
        {
            "node_id": "only-node",
            "compute_capacity": 100.0,
            "memory_capacity": 100.0,
            "compute_rate_mips": 1000.0,
        }
    ]
    payload["links"] = []
    payload["services"] = [
        {
            "service_id": "a",
            "compute_demand": 1.0,
            "memory_demand": 1.0,
            "workload_mi": 10.0,
            "eligible_nodes": ["only-node"],
        },
        {
            "service_id": "b",
            "compute_demand": 1.0,
            "memory_demand": 1.0,
            "workload_mi": 20.0,
            "eligible_nodes": ["only-node"],
        },
        {
            "service_id": "c",
            "compute_demand": 1.0,
            "memory_demand": 1.0,
            "workload_mi": 5.0,
            "eligible_nodes": ["only-node"],
        },
    ]
    payload["service_edges"] = [
        {"edge_id": "a-c", "source": "a", "target": "c", "data_volume_mbit": 5.0},
        {"edge_id": "b-c", "source": "b", "target": "c", "data_volume_mbit": 5.0},
    ]
    payload["previous_placement"] = {"a": "only-node", "b": "only-node", "c": "only-node"}
    scenario = ScenarioInstance.model_validate(payload)

    result = StaticSimulator(scenario).run(scenario.previous_placement)

    assert result.latency.e2e_latency_ms == pytest.approx(25.0)
    assert result.latency.service_timings["c"].ready_ms == pytest.approx(20.0)
    assert result.latency.service_timings["c"].critical_predecessor == "b"
    assert all(timing.total_ms == 0.0 for timing in result.latency.edge_timings.values())


def test_processing_latency_rejects_invalid_rate() -> None:
    with pytest.raises(ValueError, match="must be finite and positive"):
        processing_latency_ms(1.0, 0.0)

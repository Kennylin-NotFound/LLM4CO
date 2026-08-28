from pathlib import Path

from cover_opt.simulator.scenario_factory import load_scenario
from cover_opt.domain.service_dag import ServiceDAG


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_service_dag_has_stable_topology_queries() -> None:
    scenario = load_scenario(PROJECT_ROOT / "configs/scenarios/small_static.yaml")
    dag = ServiceDAG(scenario)

    assert dag.topological_order() == ("ingest", "analyze", "respond")
    assert dag.sources() == ("ingest",)
    assert dag.sinks() == ("respond",)
    assert [edge.edge_id for edge in dag.incoming_edges("respond")] == [
        "analyze-respond"
    ]


from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.models import DeploymentPlan, ScenarioInstance
from cover_opt.domain.satellite_graph import SatelliteGraph
from cover_opt.domain.service_dag import ServiceDAG
from cover_opt.simulator.link_state import PathLatency, path_latency


class LatencyInputError(ValueError):
    pass


class ServiceTiming(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: str
    node_id: str
    ready_ms: float = Field(ge=0)
    processing_ms: float = Field(ge=0)
    finish_ms: float = Field(ge=0)
    critical_predecessor: str | None = None


class EdgeTiming(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str
    source_service: str
    target_service: str
    path: tuple[str, ...]
    link_ids: tuple[str, ...]
    transmission_ms: float = Field(ge=0)
    propagation_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class LatencyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str = "dag_sink_completion_ms"
    e2e_latency_ms: float = Field(ge=0)
    service_timings: dict[str, ServiceTiming]
    edge_timings: dict[str, EdgeTiming]
    sink_services: tuple[str, ...]


def processing_latency_ms(workload_mi: float, compute_rate_mips: float) -> float:
    if not math.isfinite(workload_mi) or workload_mi < 0:
        raise ValueError("workload_mi must be finite and non-negative")
    if not math.isfinite(compute_rate_mips) or compute_rate_mips <= 0:
        raise ValueError("compute_rate_mips must be finite and positive")
    return workload_mi / compute_rate_mips * 1000.0


def _validate_plan_entities(
    scenario: ScenarioInstance, plan: DeploymentPlan
) -> tuple[dict[str, object], dict[str, object]]:
    service_ids = {service.service_id for service in scenario.services}
    node_ids = {node.node_id for node in scenario.nodes}
    placement_ids = set(plan.placement)
    if placement_ids != service_ids:
        missing = sorted(service_ids - placement_ids)
        extra = sorted(placement_ids - service_ids)
        raise LatencyInputError(f"placement mismatch: missing={missing}, extra={extra}")
    unknown_nodes = sorted(set(plan.placement.values()) - node_ids)
    if unknown_nodes:
        raise LatencyInputError(f"placement references unknown nodes: {unknown_nodes}")

    route_by_edge: dict[str, object] = {}
    for route in plan.routes:
        if route.edge_id in route_by_edge:
            raise LatencyInputError(f"duplicate route for edge {route.edge_id}")
        route_by_edge[route.edge_id] = route
    expected_edges = {edge.edge_id for edge in scenario.service_edges}
    if set(route_by_edge) != expected_edges:
        missing = sorted(expected_edges - set(route_by_edge))
        extra = sorted(set(route_by_edge) - expected_edges)
        raise LatencyInputError(f"route mismatch: missing={missing}, extra={extra}")
    return route_by_edge, {node.node_id: node for node in scenario.nodes}


def _edge_timing(
    *,
    scenario: ScenarioInstance,
    plan: DeploymentPlan,
    graph: SatelliteGraph,
    edge,
    route,
) -> EdgeTiming:
    source_node = plan.placement[edge.source]
    target_node = plan.placement[edge.target]
    path = tuple(route.path)
    if not path or path[0] != source_node or path[-1] != target_node:
        raise LatencyInputError(
            f"route {edge.edge_id} endpoints do not match placement: "
            f"expected {source_node}->{target_node}, got {path}"
        )
    if source_node == target_node and path != (source_node,):
        raise LatencyInputError(
            f"same-node dependency {edge.edge_id} must use a one-node path"
        )
    timing: PathLatency = path_latency(graph, path, edge.data_volume_mbit)
    return EdgeTiming(
        edge_id=edge.edge_id,
        source_service=edge.source,
        target_service=edge.target,
        path=timing.path,
        link_ids=timing.link_ids,
        transmission_ms=timing.transmission_ms,
        propagation_ms=timing.propagation_ms,
        total_ms=timing.total_ms,
    )


def evaluate_dag_latency(
    scenario: ScenarioInstance, plan: DeploymentPlan
) -> LatencyReport:
    route_by_edge, node_by_id = _validate_plan_entities(scenario, plan)
    service_by_id = {service.service_id: service for service in scenario.services}
    dag = ServiceDAG(scenario)
    graph = SatelliteGraph(scenario)

    edge_timings = {
        edge.edge_id: _edge_timing(
            scenario=scenario,
            plan=plan,
            graph=graph,
            edge=edge,
            route=route_by_edge[edge.edge_id],
        )
        for edge in sorted(scenario.service_edges, key=lambda item: item.edge_id)
    }

    service_timings: dict[str, ServiceTiming] = {}
    for service_id in dag.topological_order():
        service = service_by_id[service_id]
        node_id = plan.placement[service_id]
        node = node_by_id[node_id]
        ready_ms = 0.0
        critical_predecessor: str | None = None
        for edge in dag.incoming_edges(service_id):
            arrival_ms = (
                service_timings[edge.source].finish_ms
                + edge_timings[edge.edge_id].total_ms
            )
            if arrival_ms > ready_ms:
                ready_ms = arrival_ms
                critical_predecessor = edge.source
        processing_ms = processing_latency_ms(
            service.workload_mi, node.compute_rate_mips
        )
        service_timings[service_id] = ServiceTiming(
            service_id=service_id,
            node_id=node_id,
            ready_ms=ready_ms,
            processing_ms=processing_ms,
            finish_ms=ready_ms + processing_ms,
            critical_predecessor=critical_predecessor,
        )

    sinks = dag.sinks()
    e2e_latency_ms = max(service_timings[sink].finish_ms for sink in sinks)
    return LatencyReport(
        e2e_latency_ms=e2e_latency_ms,
        service_timings=service_timings,
        edge_timings=edge_timings,
        sink_services=sinks,
    )


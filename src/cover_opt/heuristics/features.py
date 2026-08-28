from __future__ import annotations

import math
from collections import defaultdict

from cover_opt.domain.models import NetworkLink, ScenarioInstance, ServiceEdge
from cover_opt.domain.satellite_graph import NoFeasiblePathError, SatelliteGraph
from cover_opt.domain.service_dag import ServiceDAG
from cover_opt.heuristics.schema import NodeFeature, PathFeature, ServiceFeature
from cover_opt.simulator.link_state import effective_rate_mbps, link_latency, path_latency


UNREACHABLE_LATENCY_MS = 1.0e12


def normalize_feature(values: dict[str, float]) -> dict[str, float]:
    finite = [value for value in values.values() if math.isfinite(value)]
    if not finite:
        return {key: 1.0 for key in values}
    minimum = min(finite)
    maximum = max(finite)
    if maximum == minimum:
        return {
            key: (0.0 if math.isfinite(value) else 1.0)
            for key, value in values.items()
        }
    return {
        key: (
            (value - minimum) / (maximum - minimum)
            if math.isfinite(value)
            else 1.0
        )
        for key, value in values.items()
    }


def service_feature_values(
    scenario: ScenarioInstance,
) -> dict[str, dict[ServiceFeature, float]]:
    dag = ServiceDAG(scenario)
    services = {service.service_id: service for service in scenario.services}
    rank: dict[str, float] = {}
    for service_id in reversed(dag.topological_order()):
        successors = dag.outgoing_edges(service_id)
        downstream = max((rank[edge.target] for edge in successors), default=0.0)
        rank[service_id] = services[service_id].workload_mi + downstream
    max_compute = max(node.compute_capacity for node in scenario.nodes)
    max_memory = max(node.memory_capacity for node in scenario.nodes)
    return {
        service_id: {
            ServiceFeature.CRITICAL_PATH_RANK: rank[service_id],
            ServiceFeature.RESOURCE_DEMAND_RATIO: (
                services[service_id].compute_demand / max_compute
                + services[service_id].memory_demand / max_memory
            ),
            ServiceFeature.SUCCESSOR_COUNT: float(
                len(dag.outgoing_edges(service_id))
            ),
            ServiceFeature.WORKLOAD_RATIO: services[service_id].workload_mi,
        }
        for service_id in sorted(services)
    }


def _remaining_contact_seconds(
    scenario: ScenarioInstance, link: NetworkLink
) -> float:
    return (
        link.available_until - scenario.time_slot + 1
    ) * scenario.slot_duration_seconds


def _shortest_dependency_latency(
    *,
    scenario: ScenarioInstance,
    graph: SatelliteGraph,
    edge: ServiceEdge,
    source_node: str,
    target_node: str,
) -> float:
    try:
        paths = graph.k_shortest_paths(
            source_node,
            target_node,
            k=1,
            link_weight=lambda link: link_latency(
                link, edge.data_volume_mbit
            ).total_ms,
        )
    except NoFeasiblePathError:
        return UNREACHABLE_LATENCY_MS
    return path_latency(graph, paths[0], edge.data_volume_mbit).total_ms


def node_feature_values(
    *,
    scenario: ScenarioInstance,
    service_id: str,
    candidate_node_ids: list[str],
    placement: dict[str, str],
    residual_compute: dict[str, float],
    residual_memory: dict[str, float],
) -> dict[str, dict[NodeFeature, float]]:
    services = {service.service_id: service for service in scenario.services}
    nodes = {node.node_id: node for node in scenario.nodes}
    dag = ServiceDAG(scenario)
    graph = SatelliteGraph(scenario)
    service = services[service_id]
    incident_remaining: dict[str, list[float]] = defaultdict(list)
    for link in scenario.links:
        if link.available_from <= scenario.time_slot <= link.available_until:
            remaining = _remaining_contact_seconds(scenario, link)
            incident_remaining[link.source].append(remaining)
            incident_remaining[link.target].append(remaining)

    values: dict[str, dict[NodeFeature, float]] = {}
    for node_id in sorted(candidate_node_ids):
        dependency_latency = 0.0
        for edge in dag.incoming_edges(service_id):
            if edge.source not in placement:
                continue
            dependency_latency += _shortest_dependency_latency(
                scenario=scenario,
                graph=graph,
                edge=edge,
                source_node=placement[edge.source],
                target_node=node_id,
            )
        values[node_id] = {
            NodeFeature.RESIDUAL_COMPUTE_RATIO: (
                residual_compute[node_id] - service.compute_demand
            )
            / nodes[node_id].compute_capacity,
            NodeFeature.RESIDUAL_MEMORY_RATIO: (
                residual_memory[node_id] - service.memory_demand
            )
            / nodes[node_id].memory_capacity,
            NodeFeature.DEPENDENCY_LATENCY: dependency_latency,
            NodeFeature.PREDICTED_CONTACT_DURATION: max(
                incident_remaining[node_id], default=0.0
            ),
            NodeFeature.MIGRATION_PENALTY: float(
                scenario.previous_placement.get(service_id) != node_id
            ),
        }
    return values


def path_feature_values(
    *,
    scenario: ScenarioInstance,
    graph: SatelliteGraph,
    paths: tuple[tuple[str, ...], ...],
    data_volume_mbit: float,
) -> dict[str, dict[PathFeature, float]]:
    values: dict[str, dict[PathFeature, float]] = {}
    for path in paths:
        key = "->".join(path)
        links = graph.links_for_path(path)
        latency = path_latency(graph, path, data_volume_mbit).total_ms
        if links:
            bottleneck = min(effective_rate_mbps(link) for link in links)
            contact_duration = min(
                _remaining_contact_seconds(scenario, link) for link in links
            )
        else:
            active_links = [
                link
                for link in scenario.links
                if link.available_from <= scenario.time_slot <= link.available_until
            ]
            bottleneck = max(
                (effective_rate_mbps(link) for link in active_links), default=0.0
            )
            contact_duration = max(
                (_remaining_contact_seconds(scenario, link) for link in active_links),
                default=0.0,
            )
        values[key] = {
            PathFeature.PATH_LATENCY: latency,
            PathFeature.BOTTLENECK_BANDWIDTH: bottleneck,
            PathFeature.HOP_COUNT: float(len(links)),
            PathFeature.CONTACT_DURATION: contact_duration,
        }
    return values

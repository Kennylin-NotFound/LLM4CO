from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.models import NetworkLink, RouteAssignment, ScenarioInstance
from cover_opt.domain.satellite_graph import SatelliteGraph


SPEED_OF_LIGHT_KM_PER_SECOND = 299_792.458


class LinkLatency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transmission_ms: float = Field(ge=0)
    propagation_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class PathLatency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: tuple[str, ...]
    link_ids: tuple[str, ...]
    transmission_ms: float = Field(ge=0)
    propagation_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


def effective_rate_mbps(link: NetworkLink) -> float:
    return min(link.transmission_rate_mbps, link.bandwidth_mbps)


def slot_bandwidth_demand_mbps(
    data_volume_mbit: float,
    slot_duration_seconds: float,
) -> float:
    if not math.isfinite(data_volume_mbit) or data_volume_mbit < 0:
        raise ValueError("data_volume_mbit must be finite and non-negative")
    if not math.isfinite(slot_duration_seconds) or slot_duration_seconds <= 0:
        raise ValueError("slot_duration_seconds must be finite and positive")
    return data_volume_mbit / slot_duration_seconds


def path_has_bandwidth(
    graph: SatelliteGraph,
    path: list[str] | tuple[str, ...],
    *,
    demand_mbps: float,
    residual_bandwidth_mbps: dict[str, float],
) -> bool:
    return all(
        residual_bandwidth_mbps.get(link.link_id, 0.0) + 1e-12 >= demand_mbps
        for link in graph.links_for_path(path)
    )


def reserve_path_bandwidth(
    graph: SatelliteGraph,
    path: list[str] | tuple[str, ...],
    *,
    demand_mbps: float,
    residual_bandwidth_mbps: dict[str, float],
) -> dict[str, float]:
    if not path_has_bandwidth(
        graph,
        path,
        demand_mbps=demand_mbps,
        residual_bandwidth_mbps=residual_bandwidth_mbps,
    ):
        raise ValueError("path does not have enough residual bandwidth")
    updated = dict(residual_bandwidth_mbps)
    for link in graph.links_for_path(path):
        updated[link.link_id] -= demand_mbps
    return updated


def link_latency(link: NetworkLink, data_volume_mbit: float) -> LinkLatency:
    if not math.isfinite(data_volume_mbit) or data_volume_mbit < 0:
        raise ValueError("data_volume_mbit must be finite and non-negative")
    transmission_ms = data_volume_mbit / effective_rate_mbps(link) * 1000.0
    propagation_ms = link.distance_km / SPEED_OF_LIGHT_KM_PER_SECOND * 1000.0
    return LinkLatency(
        transmission_ms=transmission_ms,
        propagation_ms=propagation_ms,
        total_ms=transmission_ms + propagation_ms,
    )


def path_latency(
    graph: SatelliteGraph,
    path: list[str] | tuple[str, ...],
    data_volume_mbit: float,
) -> PathLatency:
    links = graph.links_for_path(path)
    timings = [link_latency(link, data_volume_mbit) for link in links]
    transmission_ms = sum(item.transmission_ms for item in timings)
    propagation_ms = sum(item.propagation_ms for item in timings)
    return PathLatency(
        path=tuple(path),
        link_ids=tuple(link.link_id for link in links),
        transmission_ms=transmission_ms,
        propagation_ms=propagation_ms,
        total_ms=transmission_ms + propagation_ms,
    )


def select_deterministic_routes(
    scenario: ScenarioInstance,
    placement: dict[str, str],
    *,
    k_paths: int = 3,
) -> list[RouteAssignment]:
    graph = SatelliteGraph(scenario)
    routes: list[RouteAssignment] = []
    for edge in sorted(scenario.service_edges, key=lambda item: item.edge_id):
        try:
            source_node = placement[edge.source]
            target_node = placement[edge.target]
        except KeyError as exc:
            raise ValueError(f"placement missing service {exc.args[0]}") from exc
        paths = graph.k_shortest_paths(
            source_node,
            target_node,
            k=k_paths,
            link_weight=lambda link: link_latency(link, edge.data_volume_mbit).total_ms,
        )
        routes.append(RouteAssignment(edge_id=edge.edge_id, path=list(paths[0])))
    return routes

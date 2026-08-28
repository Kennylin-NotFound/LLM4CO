from __future__ import annotations

from collections.abc import Callable
from itertools import islice

import networkx as nx

from cover_opt.domain.models import NetworkLink, ScenarioInstance


class NoFeasiblePathError(LookupError):
    pass


class SatelliteGraph:
    def __init__(self, scenario: ScenarioInstance) -> None:
        graph = nx.DiGraph()
        for node in sorted(scenario.nodes, key=lambda item: item.node_id):
            graph.add_node(node.node_id, node=node)

        for link in sorted(scenario.links, key=lambda item: item.link_id):
            if not self._is_active(link, scenario.time_slot):
                continue
            self._add_directed_link(graph, link.source, link.target, link)
            if link.bidirectional:
                self._add_directed_link(graph, link.target, link.source, link)
        self.graph = graph

    @staticmethod
    def _is_active(link: NetworkLink, time_slot: int) -> bool:
        return link.available_from <= time_slot <= link.available_until

    @staticmethod
    def _add_directed_link(
        graph: nx.DiGraph,
        source: str,
        target: str,
        link: NetworkLink,
    ) -> None:
        if graph.has_edge(source, target):
            existing = graph[source][target]["link"]
            raise ValueError(
                f"multiple active links for directed hop {source}->{target}: "
                f"{existing.link_id}, {link.link_id}"
            )
        graph.add_edge(source, target, link=link)

    def link_for_hop(self, source: str, target: str) -> NetworkLink:
        if not self.graph.has_edge(source, target):
            raise NoFeasiblePathError(f"inactive or missing hop: {source}->{target}")
        return self.graph[source][target]["link"]

    def links_for_path(self, path: list[str] | tuple[str, ...]) -> tuple[NetworkLink, ...]:
        if not path:
            raise ValueError("path must contain at least one node")
        return tuple(
            self.link_for_hop(source, target)
            for source, target in zip(path, path[1:])
        )

    def k_shortest_paths(
        self,
        source: str,
        target: str,
        *,
        k: int,
        link_weight: Callable[[NetworkLink], float],
    ) -> tuple[tuple[str, ...], ...]:
        if k < 1:
            raise ValueError("k must be positive")
        if source == target:
            if source not in self.graph:
                raise NoFeasiblePathError(f"unknown node: {source}")
            return ((source,),)
        try:
            generator = nx.shortest_simple_paths(
                self.graph,
                source,
                target,
                weight=lambda u, v, data: link_weight(data["link"]),
            )
            paths = [tuple(path) for path in islice(generator, k)]
        except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
            raise NoFeasiblePathError(f"no active path from {source} to {target}") from exc
        if not paths:
            raise NoFeasiblePathError(f"no active path from {source} to {target}")
        return tuple(
            sorted(
                paths,
                key=lambda path: (
                    sum(link_weight(link) for link in self.links_for_path(path)),
                    path,
                ),
            )
        )


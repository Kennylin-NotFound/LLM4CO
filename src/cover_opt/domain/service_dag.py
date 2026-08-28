from __future__ import annotations

import networkx as nx

from cover_opt.domain.models import ScenarioInstance, ServiceEdge


class ServiceDAG:
    def __init__(self, scenario: ScenarioInstance) -> None:
        graph = nx.DiGraph()
        for service in sorted(scenario.services, key=lambda item: item.service_id):
            graph.add_node(service.service_id)
        self._edges_by_pair: dict[tuple[str, str], ServiceEdge] = {}
        for edge in sorted(scenario.service_edges, key=lambda item: item.edge_id):
            pair = (edge.source, edge.target)
            if pair in self._edges_by_pair:
                raise ValueError(f"parallel service dependencies are not supported: {pair}")
            self._edges_by_pair[pair] = edge
            graph.add_edge(edge.source, edge.target, edge=edge)
        if not nx.is_directed_acyclic_graph(graph):
            raise ValueError("service dependency graph must be acyclic")
        self.graph = graph

    def topological_order(self) -> tuple[str, ...]:
        return tuple(nx.lexicographical_topological_sort(self.graph, key=str))

    def incoming_edges(self, service_id: str) -> tuple[ServiceEdge, ...]:
        edges = [
            self._edges_by_pair[(source, service_id)]
            for source in self.graph.predecessors(service_id)
        ]
        return tuple(sorted(edges, key=lambda edge: (edge.source, edge.edge_id)))

    def outgoing_edges(self, service_id: str) -> tuple[ServiceEdge, ...]:
        edges = [
            self._edges_by_pair[(service_id, target)]
            for target in self.graph.successors(service_id)
        ]
        return tuple(sorted(edges, key=lambda edge: (edge.target, edge.edge_id)))

    def sources(self) -> tuple[str, ...]:
        return tuple(sorted(node for node in self.graph if self.graph.in_degree(node) == 0))

    def sinks(self) -> tuple[str, ...]:
        return tuple(sorted(node for node in self.graph if self.graph.out_degree(node) == 0))


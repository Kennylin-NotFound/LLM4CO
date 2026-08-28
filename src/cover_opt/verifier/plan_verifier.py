from __future__ import annotations

from collections import defaultdict

from cover_opt.domain.models import (
    DeploymentPlan,
    ScenarioInstance,
    VerificationReport,
    ViolationType,
)
from cover_opt.domain.satellite_graph import NoFeasiblePathError, SatelliteGraph
from cover_opt.simulator.latency import LatencyInputError, evaluate_dag_latency
from cover_opt.simulator.link_state import (
    effective_rate_mbps,
    slot_bandwidth_demand_mbps,
)
from cover_opt.verifier.violations import make_violation


PLAN_VERIFIER_VERSION = "0.1.0"


def _normalized_contributions(
    values: dict[str, float],
) -> dict[str, float]:
    total = sum(max(0.0, value) for value in values.values())
    if total <= 0:
        if not values:
            return {}
        equal = 1.0 / len(values)
        return {key: equal for key in sorted(values)}
    return {key: max(0.0, value) / total for key, value in sorted(values.items())}


class PlanVerifier:
    version = PLAN_VERIFIER_VERSION

    def verify(
        self, scenario: ScenarioInstance, plan: DeploymentPlan
    ) -> VerificationReport:
        violations = []
        services = {service.service_id: service for service in scenario.services}
        nodes = {node.node_id: node for node in scenario.nodes}
        expected_services = set(services)
        actual_services = set(plan.placement)

        for service_id in sorted(expected_services - actual_services):
            decision = f"place:{service_id}@missing"
            violations.append(
                make_violation(
                    violation_type=ViolationType.UNIQUE_PLACEMENT,
                    magnitude=1.0,
                    entities=[service_id],
                    decisions=[decision],
                    contributions={decision: 1.0},
                    attribution_method="direct",
                    message=f"service {service_id} is not placed",
                )
            )
        for service_id in sorted(actual_services - expected_services):
            decision = f"place:{service_id}@{plan.placement[service_id]}"
            violations.append(
                make_violation(
                    violation_type=ViolationType.UNIQUE_PLACEMENT,
                    magnitude=1.0,
                    entities=[service_id],
                    decisions=[decision],
                    contributions={decision: 1.0},
                    attribution_method="direct",
                    message=f"placement contains unknown service {service_id}",
                )
            )

        valid_placements: dict[str, str] = {}
        for service_id in sorted(expected_services & actual_services):
            node_id = plan.placement[service_id]
            decision = f"place:{service_id}@{node_id}"
            if node_id not in nodes:
                violations.append(
                    make_violation(
                        violation_type=ViolationType.NODE_ELIGIBILITY,
                        magnitude=1.0,
                        entities=[service_id, node_id],
                        decisions=[decision],
                        contributions={decision: 1.0},
                        attribution_method="direct",
                        message=f"service {service_id} references unknown node {node_id}",
                    )
                )
                continue
            valid_placements[service_id] = node_id
            if node_id not in services[service_id].eligible_nodes:
                violations.append(
                    make_violation(
                        violation_type=ViolationType.NODE_ELIGIBILITY,
                        magnitude=1.0,
                        entities=[service_id, node_id],
                        decisions=[decision],
                        contributions={decision: 1.0},
                        attribution_method="direct",
                        message=f"node {node_id} is not eligible for service {service_id}",
                    )
                )

        demands: dict[str, dict[str, float]] = defaultdict(
            lambda: {"compute": 0.0, "memory": 0.0}
        )
        services_by_node: dict[str, list[str]] = defaultdict(list)
        for service_id, node_id in valid_placements.items():
            service = services[service_id]
            demands[node_id]["compute"] += service.compute_demand
            demands[node_id]["memory"] += service.memory_demand
            services_by_node[node_id].append(service_id)
        for node_id, resource_demands in sorted(demands.items()):
            node = nodes[node_id]
            for resource_name, capacity in (
                ("compute", node.compute_capacity),
                ("memory", node.memory_capacity),
            ):
                demand = resource_demands[resource_name]
                if demand <= capacity:
                    continue
                decision_values = {
                    f"place:{service_id}@{node_id}": (
                        services[service_id].compute_demand
                        if resource_name == "compute"
                        else services[service_id].memory_demand
                    )
                    for service_id in services_by_node[node_id]
                }
                decisions = sorted(decision_values)
                violations.append(
                    make_violation(
                        violation_type=ViolationType.NODE_CAPACITY,
                        magnitude=(demand - capacity) / capacity,
                        entities=[node_id, resource_name],
                        decisions=decisions,
                        contributions=_normalized_contributions(decision_values),
                        attribution_method="exact_resource_share",
                        message=(
                            f"{resource_name} demand {demand:.6g} exceeds "
                            f"capacity {capacity:.6g} on {node_id}"
                        ),
                    )
                )

        route_map = {}
        for route in plan.routes:
            if route.edge_id in route_map:
                decision = f"route:{route.edge_id}"
                violations.append(
                    make_violation(
                        violation_type=ViolationType.ROUTE_CONNECTIVITY,
                        magnitude=1.0,
                        entities=[route.edge_id],
                        decisions=[decision],
                        contributions={decision: 1.0},
                        attribution_method="direct",
                        message=f"duplicate route for dependency {route.edge_id}",
                    )
                )
            else:
                route_map[route.edge_id] = route

        graph = SatelliteGraph(scenario)
        routes_valid_for_latency = True
        bandwidth_demands: dict[str, dict[str, float]] = defaultdict(dict)
        for edge in sorted(scenario.service_edges, key=lambda item: item.edge_id):
            decision = f"route:{edge.edge_id}"
            route = route_map.get(edge.edge_id)
            if route is None:
                routes_valid_for_latency = False
                violations.append(
                    make_violation(
                        violation_type=ViolationType.ROUTE_CONNECTIVITY,
                        magnitude=1.0,
                        entities=[edge.edge_id],
                        decisions=[decision],
                        contributions={decision: 1.0},
                        attribution_method="direct",
                        message=f"dependency {edge.edge_id} has no route",
                    )
                )
                continue
            if edge.source not in valid_placements or edge.target not in valid_placements:
                routes_valid_for_latency = False
                continue
            expected_source = valid_placements[edge.source]
            expected_target = valid_placements[edge.target]
            if (
                not route.path
                or route.path[0] != expected_source
                or route.path[-1] != expected_target
            ):
                routes_valid_for_latency = False
                violations.append(
                    make_violation(
                        violation_type=ViolationType.ROUTE_CONNECTIVITY,
                        magnitude=1.0,
                        entities=[edge.edge_id],
                        decisions=[decision],
                        contributions={decision: 1.0},
                        attribution_method="direct",
                        message=f"route {edge.edge_id} endpoints do not match placement",
                    )
                )
                continue
            try:
                links = graph.links_for_path(route.path)
            except (NoFeasiblePathError, ValueError) as exc:
                routes_valid_for_latency = False
                violations.append(
                    make_violation(
                        violation_type=ViolationType.ROUTE_CONNECTIVITY,
                        magnitude=1.0,
                        entities=[edge.edge_id],
                        decisions=[decision],
                        contributions={decision: 1.0},
                        attribution_method="direct",
                        message=f"route {edge.edge_id} is disconnected: {exc}",
                    )
                )
                continue
            for link in links:
                transfer_seconds = edge.data_volume_mbit / effective_rate_mbps(link)
                available_seconds = (
                    link.available_until - scenario.time_slot + 1
                ) * scenario.slot_duration_seconds
                if transfer_seconds > available_seconds:
                    routes_valid_for_latency = False
                    violations.append(
                        make_violation(
                            violation_type=ViolationType.LINK_BANDWIDTH,
                            magnitude=(transfer_seconds - available_seconds)
                            / available_seconds,
                            entities=[edge.edge_id, link.link_id],
                            decisions=[decision],
                            contributions={decision: 1.0},
                            attribution_method="direct",
                            message=(
                                f"transfer on {link.link_id} requires {transfer_seconds:.6g}s "
                                f"but only {available_seconds:.6g}s is available"
                            ),
                        )
                    )
                bandwidth_demands[link.link_id][decision] = (
                    slot_bandwidth_demand_mbps(
                        edge.data_volume_mbit,
                        scenario.slot_duration_seconds,
                    )
                )

        links_by_id = {link.link_id: link for link in scenario.links}
        for link_id, decision_values in sorted(bandwidth_demands.items()):
            capacity = effective_rate_mbps(links_by_id[link_id])
            total_demand = sum(decision_values.values())
            if total_demand <= capacity + 1e-12:
                continue
            decisions = sorted(decision_values)
            violations.append(
                make_violation(
                    violation_type=ViolationType.LINK_BANDWIDTH,
                    magnitude=(total_demand - capacity) / capacity,
                    entities=[link_id, f"time_slot:{scenario.time_slot}"],
                    decisions=decisions,
                    contributions=_normalized_contributions(decision_values),
                    attribution_method="exact_flow_share",
                    message=(
                        f"aggregate demand {total_demand:.6g}Mbps exceeds shared "
                        f"capacity {capacity:.6g}Mbps on {link_id} in time slot "
                        f"{scenario.time_slot}"
                    ),
                )
            )

        unknown_routes = sorted(
            set(route_map) - {edge.edge_id for edge in scenario.service_edges}
        )
        for edge_id in unknown_routes:
            decision = f"route:{edge_id}"
            routes_valid_for_latency = False
            violations.append(
                make_violation(
                    violation_type=ViolationType.ROUTE_CONNECTIVITY,
                    magnitude=1.0,
                    entities=[edge_id],
                    decisions=[decision],
                    contributions={decision: 1.0},
                    attribution_method="direct",
                    message=f"route references unknown dependency {edge_id}",
                )
            )

        if (
            expected_services == actual_services
            and len(valid_placements) == len(expected_services)
            and routes_valid_for_latency
            and not any(
                violation.violation_type == ViolationType.ROUTE_CONNECTIVITY
                for violation in violations
            )
        ):
            try:
                latency = evaluate_dag_latency(scenario, plan).e2e_latency_ms
                if latency > scenario.qos_latency_ms:
                    decisions = sorted(
                        [
                            f"place:{service_id}@{node_id}"
                            for service_id, node_id in valid_placements.items()
                        ]
                        + [f"route:{edge.edge_id}" for edge in scenario.service_edges]
                    )
                    violations.append(
                        make_violation(
                            violation_type=ViolationType.QOS_LATENCY,
                            magnitude=(latency - scenario.qos_latency_ms)
                            / scenario.qos_latency_ms,
                            entities=[scenario.scenario_id],
                            decisions=decisions,
                            contributions=_normalized_contributions(
                                {decision: 1.0 for decision in decisions}
                            ),
                            attribution_method="proxy_uniform",
                            message=(
                                f"E2E latency {latency:.6g}ms exceeds QoS "
                                f"{scenario.qos_latency_ms:.6g}ms"
                            ),
                        )
                    )
            except LatencyInputError:
                routes_valid_for_latency = False

        migrations = [
            service_id
            for service_id, node_id in valid_placements.items()
            if scenario.previous_placement.get(service_id) != node_id
        ]
        if len(migrations) > scenario.migration_budget:
            decisions = [
                f"migrate:{service_id}:{scenario.previous_placement.get(service_id)}->{valid_placements[service_id]}"
                for service_id in sorted(migrations)
            ]
            violations.append(
                make_violation(
                    violation_type=ViolationType.MIGRATION_BUDGET,
                    magnitude=(len(migrations) - scenario.migration_budget)
                    / max(1, scenario.migration_budget),
                    entities=sorted(migrations),
                    decisions=decisions,
                    contributions=_normalized_contributions(
                        {decision: 1.0 for decision in decisions}
                    ),
                    attribution_method="exact_event_share",
                    message=(
                        f"migration count {len(migrations)} exceeds budget "
                        f"{scenario.migration_budget}"
                    ),
                )
            )

        return VerificationReport(
            feasible=not violations,
            violations=violations,
            verifier_version=self.version,
        )

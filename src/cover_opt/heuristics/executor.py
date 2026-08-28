from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.deployment import build_deployment_plan
from cover_opt.domain.models import DeploymentPlan, PlanStatus, RouteAssignment, ScenarioInstance
from cover_opt.domain.satellite_graph import NoFeasiblePathError, SatelliteGraph
from cover_opt.domain.service_dag import ServiceDAG
from cover_opt.heuristics.features import (
    node_feature_values,
    normalize_feature,
    path_feature_values,
    service_feature_values,
)
from cover_opt.heuristics.repair import DeterministicRepairEngine
from cover_opt.heuristics.schema import HeuristicDSL
from cover_opt.heuristics.static_verifier import DSLStaticVerifier, DSLVerificationReport
from cover_opt.simulator.link_state import (
    effective_rate_mbps,
    link_latency,
    path_has_bandwidth,
    reserve_path_bandwidth,
    slot_bandwidth_demand_mbps,
)


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: DeploymentPlan
    static_verification: DSLVerificationReport
    trace: list[dict[str, Any]]
    failure_reason: str | None = None
    planning_time_ms: float = Field(ge=0)
    executor_version: str = "0.3.0"


class DeterministicExecutor:
    version = "0.3.0"

    def __init__(
        self,
        *,
        k_paths: int = 3,
        max_repair_attempts: int = 24,
        enable_repair_actions: bool = True,
        feasible_masks_enabled: bool = True,
    ) -> None:
        if k_paths < 1:
            raise ValueError("k_paths must be positive")
        self.k_paths = k_paths
        self.enable_repair_actions = enable_repair_actions
        self.feasible_masks_enabled = feasible_masks_enabled
        self.static_verifier = DSLStaticVerifier()
        self.repair_engine = DeterministicRepairEngine(
            k_paths=k_paths,
            max_attempts=max_repair_attempts,
        )

    def _finish(
        self,
        *,
        scenario: ScenarioInstance,
        program: HeuristicDSL,
        plan: DeploymentPlan,
        static_report: DSLVerificationReport,
        trace: list[dict[str, Any]],
        failure_reason: str | None,
        started: float,
    ) -> ExecutionResult:
        if program.repair_policy and not self.enable_repair_actions:
            trace.append(
                {
                    "stage": "repair_policy",
                    "status": "disabled_by_ablation",
                    "actions": [action.value for action in program.repair_policy],
                    "attempt_count": 0,
                    "accepted_actions": 0,
                    "budget_exhausted": False,
                    "final_feasible": False,
                    "action_trace": [],
                }
            )
        elif program.repair_policy:
            repair = self.repair_engine.repair(
                scenario=scenario,
                plan=plan,
                actions=program.repair_policy,
            )
            trace.append(
                {
                    "stage": "repair_policy",
                    "actions": [action.value for action in program.repair_policy],
                    "attempt_count": repair.attempts,
                    "accepted_actions": repair.accepted_actions,
                    "budget_exhausted": repair.budget_exhausted,
                    "final_feasible": repair.verification.feasible,
                    "action_trace": repair.trace,
                }
            )
            plan = repair.plan
            if repair.verification.feasible:
                failure_reason = None
        return ExecutionResult(
            plan=plan,
            static_verification=static_report,
            trace=trace,
            failure_reason=failure_reason,
            planning_time_ms=(time.perf_counter() - started) * 1000.0,
        )

    @staticmethod
    def _weighted_scores(raw: dict[str, dict], terms) -> dict[str, float]:
        normalized_by_feature = {
            term.feature: normalize_feature(
                {
                    candidate: features[term.feature]
                    for candidate, features in raw.items()
                }
            )
            for term in terms
        }
        return {
            candidate: sum(
                term.weight * normalized_by_feature[term.feature][candidate]
                for term in terms
            )
            for candidate in raw
        }

    def _service_order(
        self, scenario: ScenarioInstance, program: HeuristicDSL
    ) -> tuple[list[str], dict[str, float]]:
        dag = ServiceDAG(scenario)
        raw = service_feature_values(scenario)
        scores = self._weighted_scores(raw, program.service_order.terms)
        indegree = {node: dag.graph.in_degree(node) for node in dag.graph.nodes}
        ready = {node for node, degree in indegree.items() if degree == 0}
        order: list[str] = []
        while ready:
            reverse = program.service_order.direction == "descending"
            if reverse:
                selected = min(ready, key=lambda node: (-scores[node], node))
            else:
                selected = min(ready, key=lambda node: (scores[node], node))
            ready.remove(selected)
            order.append(selected)
            for successor in dag.graph.successors(selected):
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    ready.add(successor)
        return order, scores

    @staticmethod
    def _path_window_feasible(
        scenario: ScenarioInstance,
        graph: SatelliteGraph,
        path: tuple[str, ...],
        data_volume_mbit: float,
    ) -> bool:
        for link in graph.links_for_path(path):
            transfer_seconds = data_volume_mbit / effective_rate_mbps(link)
            available_seconds = (
                link.available_until - scenario.time_slot + 1
            ) * scenario.slot_duration_seconds
            if transfer_seconds > available_seconds:
                return False
        return True

    def execute(
        self,
        scenario: ScenarioInstance,
        program: HeuristicDSL,
        *,
        method: str = "typed_dsl",
        candidate_id: str = "candidate",
        run_id: str = "local",
    ) -> ExecutionResult:
        started = time.perf_counter()
        static_report = self.static_verifier.verify(program, scenario)
        if not static_report.valid:
            plan = build_deployment_plan(
                scenario=scenario,
                placement={},
                routes=[],
                method=method,
                candidate_id=candidate_id,
                run_id=run_id,
                status=PlanStatus.FAILED,
            )
            return ExecutionResult(
                plan=plan,
                static_verification=static_report,
                trace=[],
                failure_reason="dsl_static_verification_failed",
                planning_time_ms=(time.perf_counter() - started) * 1000.0,
            )

        services = {service.service_id: service for service in scenario.services}
        nodes = {node.node_id: node for node in scenario.nodes}
        residual_compute = {
            node_id: node.compute_capacity for node_id, node in nodes.items()
        }
        residual_memory = {
            node_id: node.memory_capacity for node_id, node in nodes.items()
        }
        order, service_scores = self._service_order(scenario, program)
        trace: list[dict[str, Any]] = [
            {
                "stage": "service_order",
                "selected_order": order,
                "scores": service_scores,
            }
        ]
        placement: dict[str, str] = {}
        for service_id in order:
            service = services[service_id]
            if self.feasible_masks_enabled:
                candidates = [
                    node_id
                    for node_id in sorted(service.eligible_nodes)
                    if node_id in nodes
                    and residual_compute[node_id] >= service.compute_demand
                    and residual_memory[node_id] >= service.memory_demand
                ]
            else:
                candidates = sorted(nodes)
            if not candidates:
                plan = build_deployment_plan(
                    scenario=scenario,
                    placement=placement,
                    routes=[],
                    method=method,
                    candidate_id=candidate_id,
                    run_id=run_id,
                    status=PlanStatus.PARTIAL,
                )
                return self._finish(
                    scenario=scenario,
                    program=program,
                    plan=plan,
                    static_report=static_report,
                    trace=trace,
                    failure_reason=f"no_capacity_candidate:{service_id}",
                    started=started,
                )
            raw_features = node_feature_values(
                scenario=scenario,
                service_id=service_id,
                candidate_node_ids=candidates,
                placement=placement,
                residual_compute=residual_compute,
                residual_memory=residual_memory,
            )
            scores = self._weighted_scores(raw_features, program.node_score.terms)
            selected = min(candidates, key=lambda node_id: (-scores[node_id], node_id))
            placement[service_id] = selected
            residual_compute[selected] -= service.compute_demand
            residual_memory[selected] -= service.memory_demand
            trace.append(
                {
                    "stage": "placement",
                    "service_id": service_id,
                    "eligible_capacity_candidates": candidates,
                    "feasible_masks_enabled": self.feasible_masks_enabled,
                    "candidate_policy": (
                        "eligibility_and_capacity_masked"
                        if self.feasible_masks_enabled
                        else "all_nodes_unmasked"
                    ),
                    "raw_features": {
                        node_id: {
                            feature.value: value
                            for feature, value in features.items()
                        }
                        for node_id, features in raw_features.items()
                    },
                    "scores": scores,
                    "selected_node": selected,
                }
            )

        graph = SatelliteGraph(scenario)
        residual_bandwidth = {
            link.link_id: effective_rate_mbps(link)
            for link in scenario.links
            if link.available_from <= scenario.time_slot <= link.available_until
        }
        routes: list[RouteAssignment] = []
        for edge in sorted(scenario.service_edges, key=lambda item: item.edge_id):
            source = placement[edge.source]
            target = placement[edge.target]
            try:
                candidate_paths = graph.k_shortest_paths(
                    source,
                    target,
                    k=max(self.k_paths, self.k_paths * 3),
                    link_weight=lambda link: link_latency(
                        link, edge.data_volume_mbit
                    ).total_ms,
                )
            except NoFeasiblePathError:
                candidate_paths = ()
            if self.feasible_masks_enabled:
                bandwidth_demand = slot_bandwidth_demand_mbps(
                    edge.data_volume_mbit,
                    scenario.slot_duration_seconds,
                )
                feasible_paths = tuple(
                    path
                    for path in candidate_paths
                    if self._path_window_feasible(
                        scenario, graph, path, edge.data_volume_mbit
                    )
                    and path_has_bandwidth(
                        graph,
                        path,
                        demand_mbps=bandwidth_demand,
                        residual_bandwidth_mbps=residual_bandwidth,
                    )
                )[: self.k_paths]
            else:
                bandwidth_demand = slot_bandwidth_demand_mbps(
                    edge.data_volume_mbit,
                    scenario.slot_duration_seconds,
                )
                feasible_paths = tuple(candidate_paths[: self.k_paths])
            if not feasible_paths:
                plan = build_deployment_plan(
                    scenario=scenario,
                    placement=placement,
                    routes=routes,
                    method=method,
                    candidate_id=candidate_id,
                    run_id=run_id,
                    status=PlanStatus.PARTIAL,
                )
                return self._finish(
                    scenario=scenario,
                    program=program,
                    plan=plan,
                    static_report=static_report,
                    trace=trace,
                    failure_reason=f"no_feasible_path_or_bandwidth:{edge.edge_id}",
                    started=started,
                )
            raw_features = path_feature_values(
                scenario=scenario,
                graph=graph,
                paths=feasible_paths,
                data_volume_mbit=edge.data_volume_mbit,
            )
            scores = self._weighted_scores(raw_features, program.path_score.terms)
            selected_key = min(scores, key=lambda key: (-scores[key], key))
            selected_path = tuple(selected_key.split("->"))
            residual_before = dict(residual_bandwidth)
            if self.feasible_masks_enabled:
                residual_bandwidth = reserve_path_bandwidth(
                    graph,
                    selected_path,
                    demand_mbps=bandwidth_demand,
                    residual_bandwidth_mbps=residual_bandwidth,
                )
            else:
                for link in graph.links_for_path(selected_path):
                    residual_bandwidth[link.link_id] = (
                        residual_bandwidth.get(link.link_id, 0.0) - bandwidth_demand
                    )
            routes.append(
                RouteAssignment(edge_id=edge.edge_id, path=list(selected_path))
            )
            trace.append(
                {
                    "stage": "routing",
                    "edge_id": edge.edge_id,
                    "candidates": [list(path) for path in feasible_paths],
                    "feasible_masks_enabled": self.feasible_masks_enabled,
                    "candidate_policy": (
                        "contact_window_and_shared_bandwidth_masked"
                        if self.feasible_masks_enabled
                        else "top_k_paths_unmasked"
                    ),
                    "bandwidth_demand_mbps": bandwidth_demand,
                    "residual_bandwidth_before_mbps": residual_before,
                    "residual_bandwidth_after_mbps": residual_bandwidth,
                    "raw_features": {
                        key: {
                            feature.value: value
                            for feature, value in features.items()
                        }
                        for key, features in raw_features.items()
                    },
                    "scores": scores,
                    "selected_path": list(selected_path),
                }
            )

        plan = build_deployment_plan(
            scenario=scenario,
            placement=placement,
            routes=routes,
            method=method,
            candidate_id=candidate_id,
            run_id=run_id,
        )
        return self._finish(
            scenario=scenario,
            program=program,
            plan=plan,
            static_report=static_report,
            trace=trace,
            failure_reason=None,
            started=started,
        )

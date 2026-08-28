from __future__ import annotations

from collections.abc import Iterable
from itertools import combinations
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.deployment import build_deployment_plan
from cover_opt.domain.models import (
    DeploymentPlan,
    PlanStatus,
    RouteAssignment,
    ScenarioInstance,
    VerificationReport,
    ViolationType,
)
from cover_opt.domain.satellite_graph import NoFeasiblePathError, SatelliteGraph
from cover_opt.hashing import sha256_json
from cover_opt.heuristics.schema import RepairAction
from cover_opt.simulator.link_state import link_latency, select_deterministic_routes
from cover_opt.verifier.plan_verifier import PlanVerifier


class RepairOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: DeploymentPlan
    verification: VerificationReport
    trace: list[dict[str, Any]]
    attempts: int = Field(ge=0)
    accepted_actions: int = Field(ge=0)
    budget_exhausted: bool = False
    engine_version: str = "1.0.0"


class DeterministicRepairEngine:
    version = "1.0.0"

    def __init__(self, *, k_paths: int = 3, max_attempts: int = 24) -> None:
        if k_paths < 1:
            raise ValueError("k_paths must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.k_paths = k_paths
        self.max_attempts = max_attempts
        self.verifier = PlanVerifier()

    @staticmethod
    def _profile(report: VerificationReport) -> tuple[int, int, float, tuple[str, ...]]:
        return (
            0 if report.feasible else 1,
            len(report.violations),
            sum(violation.magnitude for violation in report.violations),
            tuple(sorted(item.violation_type.value for item in report.violations)),
        )

    @staticmethod
    def _plan_signature(plan: DeploymentPlan) -> str:
        return sha256_json(
            {
                "placement": plan.placement,
                "routes": [route.model_dump(mode="json") for route in plan.routes],
            }
        )

    def _build_plan(
        self,
        scenario: ScenarioInstance,
        placement: dict[str, str],
        source: DeploymentPlan,
    ) -> DeploymentPlan:
        try:
            routes = select_deterministic_routes(
                scenario,
                placement,
                k_paths=self.k_paths,
            )
        except (NoFeasiblePathError, ValueError):
            routes = []
        return build_deployment_plan(
            scenario=scenario,
            placement=placement,
            routes=routes,
            method=source.method,
            candidate_id=source.candidate_id,
            run_id=source.run_id,
            status=PlanStatus.COMPLETE,
        )

    @staticmethod
    def _involved_services(
        scenario: ScenarioInstance,
        report: VerificationReport,
    ) -> list[str]:
        known = {service.service_id for service in scenario.services}
        involved = {
            entity
            for violation in report.violations
            for entity in violation.entities
            if entity in known
        }
        for violation in report.violations:
            for decision in violation.contributing_decisions:
                if decision.startswith("place:"):
                    service_id = decision.split(":", 1)[1].split("@", 1)[0]
                    if service_id in known:
                        involved.add(service_id)
                elif decision.startswith("migrate:"):
                    service_id = decision.split(":", 2)[1]
                    if service_id in known:
                        involved.add(service_id)
        if involved:
            return sorted(involved)
        workloads = {
            service.service_id: service.workload_mi for service in scenario.services
        }
        return sorted(known, key=lambda service_id: (-workloads[service_id], service_id))

    def _reroute_candidates(
        self,
        scenario: ScenarioInstance,
        plan: DeploymentPlan,
    ) -> Iterable[DeploymentPlan]:
        if len(plan.placement) != len(scenario.services):
            return
        graph = SatelliteGraph(scenario)
        route_map = {route.edge_id: route for route in plan.routes}
        for edge in sorted(scenario.service_edges, key=lambda item: item.edge_id):
            source = plan.placement[edge.source]
            target = plan.placement[edge.target]
            try:
                paths = graph.k_shortest_paths(
                    source,
                    target,
                    k=self.k_paths,
                    link_weight=lambda link: link_latency(
                        link,
                        edge.data_volume_mbit,
                    ).total_ms,
                )
            except NoFeasiblePathError:
                continue
            for path in paths:
                if edge.edge_id in route_map and list(path) == route_map[edge.edge_id].path:
                    continue
                routes = dict(route_map)
                routes[edge.edge_id] = RouteAssignment(
                    edge_id=edge.edge_id,
                    path=list(path),
                )
                yield build_deployment_plan(
                    scenario=scenario,
                    placement=plan.placement,
                    routes=list(routes.values()),
                    method=plan.method,
                    candidate_id=plan.candidate_id,
                    run_id=plan.run_id,
                )

    def _move_candidates(
        self,
        scenario: ScenarioInstance,
        plan: DeploymentPlan,
        report: VerificationReport,
    ) -> Iterable[DeploymentPlan]:
        services = {service.service_id: service for service in scenario.services}
        for service_id in self._involved_services(scenario, report):
            current = plan.placement.get(service_id)
            preferred = scenario.previous_placement.get(service_id)
            targets = sorted(services[service_id].eligible_nodes)
            if preferred in targets:
                targets.remove(preferred)
                targets.insert(0, preferred)
            for target in targets:
                if target == current:
                    continue
                placement = dict(plan.placement)
                placement[service_id] = target
                if len(placement) == len(scenario.services):
                    yield self._build_plan(scenario, placement, plan)

    def _swap_candidates(
        self,
        scenario: ScenarioInstance,
        plan: DeploymentPlan,
        report: VerificationReport,
    ) -> Iterable[DeploymentPlan]:
        services = {service.service_id: service for service in scenario.services}
        involved = self._involved_services(scenario, report)
        if len(involved) < 2:
            involved = sorted(services)
        for left, right in combinations(involved, 2):
            if left not in plan.placement or right not in plan.placement:
                continue
            left_target = plan.placement[right]
            right_target = plan.placement[left]
            if (
                left_target not in services[left].eligible_nodes
                or right_target not in services[right].eligible_nodes
            ):
                continue
            placement = dict(plan.placement)
            placement[left] = left_target
            placement[right] = right_target
            yield self._build_plan(scenario, placement, plan)

    def _backtrack_candidates(
        self,
        scenario: ScenarioInstance,
        plan: DeploymentPlan,
    ) -> Iterable[DeploymentPlan]:
        services = {service.service_id: service for service in scenario.services}
        nodes = {node.node_id: node for node in scenario.nodes}
        order = sorted(
            services,
            key=lambda service_id: (
                len(services[service_id].eligible_nodes),
                -services[service_id].compute_demand,
                service_id,
            ),
        )
        residual_compute = {
            node_id: node.compute_capacity for node_id, node in nodes.items()
        }
        residual_memory = {
            node_id: node.memory_capacity for node_id, node in nodes.items()
        }
        placement: dict[str, str] = {}

        def search(index: int) -> Iterable[dict[str, str]]:
            if index == len(order):
                yield dict(placement)
                return
            service_id = order[index]
            service = services[service_id]
            preferred = [
                plan.placement.get(service_id),
                scenario.previous_placement.get(service_id),
            ]
            candidates = []
            for node_id in preferred + sorted(service.eligible_nodes):
                if node_id and node_id not in candidates:
                    candidates.append(node_id)
            for node_id in candidates:
                if (
                    residual_compute[node_id] < service.compute_demand
                    or residual_memory[node_id] < service.memory_demand
                ):
                    continue
                placement[service_id] = node_id
                residual_compute[node_id] -= service.compute_demand
                residual_memory[node_id] -= service.memory_demand
                yield from search(index + 1)
                residual_compute[node_id] += service.compute_demand
                residual_memory[node_id] += service.memory_demand
                del placement[service_id]

        for placement_candidate in search(0):
            yield self._build_plan(scenario, placement_candidate, plan)

    @staticmethod
    def _action_supported(
        action: RepairAction,
        plan: DeploymentPlan,
        report: VerificationReport,
    ) -> bool:
        violation_types = {item.violation_type for item in report.violations}
        if action == RepairAction.REROUTE:
            return bool(
                violation_types
                & {
                    ViolationType.ROUTE_CONNECTIVITY,
                    ViolationType.LINK_BANDWIDTH,
                    ViolationType.QOS_LATENCY,
                }
            )
        if action in {
            RepairAction.MOVE_BOTTLENECK_SERVICE,
            RepairAction.SWAP_SERVICES,
        }:
            return bool(
                violation_types
                & {
                    ViolationType.NODE_ELIGIBILITY,
                    ViolationType.NODE_CAPACITY,
                    ViolationType.QOS_LATENCY,
                    ViolationType.MIGRATION_BUDGET,
                }
            )
        return plan.status != PlanStatus.COMPLETE or bool(
            violation_types
            & {
                ViolationType.UNIQUE_PLACEMENT,
                ViolationType.NODE_ELIGIBILITY,
                ViolationType.NODE_CAPACITY,
            }
        )

    def _candidates(
        self,
        action: RepairAction,
        scenario: ScenarioInstance,
        plan: DeploymentPlan,
        report: VerificationReport,
    ) -> Iterable[DeploymentPlan]:
        if action == RepairAction.REROUTE:
            return self._reroute_candidates(scenario, plan)
        if action == RepairAction.MOVE_BOTTLENECK_SERVICE:
            return self._move_candidates(scenario, plan, report)
        if action == RepairAction.SWAP_SERVICES:
            return self._swap_candidates(scenario, plan, report)
        return self._backtrack_candidates(scenario, plan)

    def repair(
        self,
        *,
        scenario: ScenarioInstance,
        plan: DeploymentPlan,
        actions: list[RepairAction],
    ) -> RepairOutcome:
        current = plan
        current_report = self.verifier.verify(scenario, current)
        attempts = 0
        accepted_actions = 0
        seen = {self._plan_signature(plan)}
        trace: list[dict[str, Any]] = []
        budget_exhausted = False

        for action in actions:
            if current_report.feasible:
                break
            if not self._action_supported(action, current, current_report):
                trace.append(
                    {
                        "action": action.value,
                        "status": "not_applicable",
                        "before_profile": self._profile(current_report),
                        "attempts": [],
                    }
                )
                continue

            action_before = self._profile(current_report)
            rounds: list[dict[str, Any]] = []
            action_accepts = 0
            while self._action_supported(action, current, current_report):
                before_profile = self._profile(current_report)
                evaluated: list[tuple[DeploymentPlan, VerificationReport, str]] = []
                attempt_trace: list[dict[str, Any]] = []
                for candidate in self._candidates(
                    action,
                    scenario,
                    current,
                    current_report,
                ):
                    if attempts >= self.max_attempts:
                        budget_exhausted = True
                        break
                    signature = self._plan_signature(candidate)
                    if signature in seen:
                        continue
                    seen.add(signature)
                    candidate_report = self.verifier.verify(scenario, candidate)
                    attempts += 1
                    evaluated.append((candidate, candidate_report, signature))
                    attempt_trace.append(
                        {
                            "plan_signature": signature,
                            "profile": self._profile(candidate_report),
                        }
                    )

                best = min(
                    evaluated,
                    key=lambda item: (self._profile(item[1]), item[2]),
                    default=None,
                )
                accepted_signature = None
                if best is not None and self._profile(best[1]) < before_profile:
                    current, current_report, accepted_signature = best
                    accepted_actions += 1
                    action_accepts += 1
                for item in attempt_trace:
                    item["selected"] = item["plan_signature"] == accepted_signature
                rounds.append(
                    {
                        "before_profile": before_profile,
                        "after_profile": self._profile(current_report),
                        "accepted": accepted_signature is not None,
                        "attempts": attempt_trace,
                    }
                )
                if accepted_signature is None or current_report.feasible:
                    break
                if budget_exhausted:
                    break
            trace.append(
                {
                    "action": action.value,
                    "status": "accepted" if action_accepts else "no_improvement",
                    "before_profile": action_before,
                    "after_profile": self._profile(current_report),
                    "accepted_rounds": action_accepts,
                    "rounds": rounds,
                }
            )
            if budget_exhausted:
                break

        return RepairOutcome(
            plan=current,
            verification=current_report,
            trace=trace,
            attempts=attempts,
            accepted_actions=accepted_actions,
            budget_exhausted=budget_exhausted,
        )

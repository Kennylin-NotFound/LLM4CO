from __future__ import annotations

import random
import time
from itertools import product
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.deployment import build_deployment_plan
from cover_opt.domain.models import (
    DeploymentPlan,
    RouteAssignment,
    ScenarioInstance,
    VerificationReport,
)
from cover_opt.domain.satellite_graph import NoFeasiblePathError, SatelliteGraph
from cover_opt.hashing import sha256_json
from cover_opt.heuristics.executor import DeterministicExecutor
from cover_opt.heuristics.schema import HeuristicDSL
from cover_opt.objective.evaluator import ObjectiveEvaluator, ObjectiveReport
from cover_opt.simulator.link_state import link_latency, select_deterministic_routes
from cover_opt.verifier.plan_verifier import PlanVerifier


class SolverResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solver_name: str
    status: Literal["feasible", "infeasible", "budget_exhausted"]
    plan: DeploymentPlan | None = None
    verification: VerificationReport | None = None
    objective: ObjectiveReport | None = None
    candidates_evaluated: int = Field(ge=0)
    placement_assignments_considered: int = Field(ge=0)
    planning_time_ms: float = Field(ge=0.0)
    optimality_proven: bool = False
    scope: str
    best_signature: str | None = None
    trace: list[dict[str, Any]] = Field(default_factory=list)
    interface_version: str = "1.0.0"


def _plan_signature(plan: DeploymentPlan) -> str:
    return sha256_json(
        {
            "placement": plan.placement,
            "routes": [route.model_dump(mode="json") for route in plan.routes],
        }
    )


class ExactEnumerationOracle:
    def __init__(
        self,
        *,
        k_paths: int = 3,
        max_candidates: int = 100_000,
        max_wall_time_seconds: float = 30.0,
    ) -> None:
        if k_paths < 1 or max_candidates < 1 or max_wall_time_seconds <= 0:
            raise ValueError("oracle budgets and k_paths must be positive")
        self.k_paths = k_paths
        self.max_candidates = max_candidates
        self.max_wall_time_seconds = max_wall_time_seconds
        self.verifier = PlanVerifier()
        self.evaluator = ObjectiveEvaluator()

    @staticmethod
    def _capacity_feasible(
        scenario: ScenarioInstance,
        placement: dict[str, str],
    ) -> bool:
        nodes = {node.node_id: node for node in scenario.nodes}
        services = {service.service_id: service for service in scenario.services}
        compute = {node_id: 0.0 for node_id in nodes}
        memory = {node_id: 0.0 for node_id in nodes}
        for service_id, node_id in placement.items():
            compute[node_id] += services[service_id].compute_demand
            memory[node_id] += services[service_id].memory_demand
        return all(
            compute[node_id] <= nodes[node_id].compute_capacity
            and memory[node_id] <= nodes[node_id].memory_capacity
            for node_id in nodes
        )

    def _route_options(
        self,
        scenario: ScenarioInstance,
        placement: dict[str, str],
    ) -> list[tuple[RouteAssignment, ...]] | None:
        graph = SatelliteGraph(scenario)
        options: list[tuple[RouteAssignment, ...]] = []
        for edge in sorted(scenario.service_edges, key=lambda item: item.edge_id):
            try:
                paths = graph.k_shortest_paths(
                    placement[edge.source],
                    placement[edge.target],
                    k=self.k_paths,
                    link_weight=lambda link: link_latency(
                        link,
                        edge.data_volume_mbit,
                    ).total_ms,
                )
            except NoFeasiblePathError:
                return None
            options.append(
                tuple(
                    RouteAssignment(edge_id=edge.edge_id, path=list(path))
                    for path in paths
                )
            )
        return options

    def solve(self, scenario: ScenarioInstance) -> SolverResult:
        started = time.perf_counter()
        services = sorted(scenario.services, key=lambda item: item.service_id)
        placement_count = 0
        evaluated = 0
        truncated = False
        best: tuple[float, str, DeploymentPlan, VerificationReport, ObjectiveReport] | None = None

        eligible_products = product(
            *(tuple(sorted(service.eligible_nodes)) for service in services)
        )
        for assignment in eligible_products:
            if time.perf_counter() - started >= self.max_wall_time_seconds:
                truncated = True
                break
            placement_count += 1
            placement = {
                service.service_id: node_id
                for service, node_id in zip(services, assignment)
            }
            if not self._capacity_feasible(scenario, placement):
                continue
            route_options = self._route_options(scenario, placement)
            if route_options is None:
                continue
            for routes in product(*route_options):
                if evaluated >= self.max_candidates:
                    truncated = True
                    break
                if time.perf_counter() - started >= self.max_wall_time_seconds:
                    truncated = True
                    break
                plan = build_deployment_plan(
                    scenario=scenario,
                    placement=placement,
                    routes=list(routes),
                    method="exact_enumeration_oracle",
                    candidate_id=f"oracle_{evaluated:06d}",
                    run_id="exact_oracle",
                )
                verification = self.verifier.verify(scenario, plan)
                evaluated += 1
                if not verification.feasible:
                    continue
                objective = self.evaluator.evaluate(
                    scenario,
                    plan,
                    verification,
                )
                signature = _plan_signature(plan)
                candidate = (
                    objective.weighted_objective,
                    signature,
                    plan,
                    verification,
                    objective,
                )
                if best is None or candidate[:2] < best[:2]:
                    best = candidate
            if truncated:
                break

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if best is None:
            return SolverResult(
                solver_name="exact_enumeration_oracle",
                status="budget_exhausted" if truncated else "infeasible",
                candidates_evaluated=evaluated,
                placement_assignments_considered=placement_count,
                planning_time_ms=elapsed_ms,
                optimality_proven=not truncated,
                scope=f"all eligible placements x top-{self.k_paths} latency paths",
            )
        objective = best[4].model_copy(update={"planning_time_ms": elapsed_ms})
        return SolverResult(
            solver_name="exact_enumeration_oracle",
            status="budget_exhausted" if truncated else "feasible",
            plan=best[2],
            verification=best[3],
            objective=objective,
            candidates_evaluated=evaluated,
            placement_assignments_considered=placement_count,
            planning_time_ms=elapsed_ms,
            optimality_proven=not truncated,
            scope=f"all eligible placements x top-{self.k_paths} latency paths",
            best_signature=best[1],
        )


class HeuristicBaseline:
    def __init__(self, name: str, program: HeuristicDSL, *, k_paths: int = 3) -> None:
        self.name = name
        self.program = program
        self.executor = DeterministicExecutor(k_paths=k_paths)
        self.verifier = PlanVerifier()
        self.evaluator = ObjectiveEvaluator()

    def solve(self, scenario: ScenarioInstance) -> SolverResult:
        started = time.perf_counter()
        execution = self.executor.execute(
            scenario,
            self.program,
            method=self.name,
            candidate_id=self.name,
            run_id="baseline",
        )
        verification = self.verifier.verify(scenario, execution.plan)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        objective = (
            self.evaluator.evaluate(
                scenario,
                execution.plan,
                verification,
                planning_time_ms=elapsed_ms,
            )
            if verification.feasible
            else None
        )
        return SolverResult(
            solver_name=self.name,
            status="feasible" if verification.feasible else "infeasible",
            plan=execution.plan,
            verification=verification,
            objective=objective,
            candidates_evaluated=1,
            placement_assignments_considered=1,
            planning_time_ms=elapsed_ms,
            scope="one deterministic typed-heuristic execution without LLM search",
            best_signature=(
                _plan_signature(execution.plan) if verification.feasible else None
            ),
            trace=execution.trace,
        )


class RandomBaseline:
    def __init__(self, *, samples: int = 32, seed: int = 0, k_paths: int = 3) -> None:
        if samples < 1:
            raise ValueError("random baseline samples must be positive")
        self.samples = samples
        self.seed = seed
        self.k_paths = k_paths
        self.verifier = PlanVerifier()
        self.evaluator = ObjectiveEvaluator()

    def solve(self, scenario: ScenarioInstance) -> SolverResult:
        started = time.perf_counter()
        rng = random.Random(self.seed)
        services = sorted(scenario.services, key=lambda item: item.service_id)
        seen: set[str] = set()
        evaluated = 0
        attempts = 0
        best: tuple[float, str, DeploymentPlan, VerificationReport, ObjectiveReport] | None = None
        max_attempts = max(self.samples * 10, self.samples)

        while evaluated < self.samples and attempts < max_attempts:
            attempts += 1
            placement = {
                service.service_id: rng.choice(sorted(service.eligible_nodes))
                for service in services
            }
            placement_signature = sha256_json(placement)
            if placement_signature in seen:
                continue
            seen.add(placement_signature)
            try:
                routes = select_deterministic_routes(
                    scenario,
                    placement,
                    k_paths=self.k_paths,
                )
            except (NoFeasiblePathError, ValueError):
                routes = []
            plan = build_deployment_plan(
                scenario=scenario,
                placement=placement,
                routes=routes,
                method="random_baseline",
                candidate_id=f"random_{evaluated:04d}",
                run_id="baseline",
            )
            verification = self.verifier.verify(scenario, plan)
            evaluated += 1
            if not verification.feasible:
                continue
            objective = self.evaluator.evaluate(scenario, plan, verification)
            signature = _plan_signature(plan)
            candidate = (
                objective.weighted_objective,
                signature,
                plan,
                verification,
                objective,
            )
            if best is None or candidate[:2] < best[:2]:
                best = candidate

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if best is None:
            return SolverResult(
                solver_name="random_baseline",
                status="infeasible",
                candidates_evaluated=evaluated,
                placement_assignments_considered=len(seen),
                planning_time_ms=elapsed_ms,
                scope=f"best of up to {self.samples} seeded unique eligible placements",
            )
        objective = best[4].model_copy(update={"planning_time_ms": elapsed_ms})
        return SolverResult(
            solver_name="random_baseline",
            status="feasible",
            plan=best[2],
            verification=best[3],
            objective=objective,
            candidates_evaluated=evaluated,
            placement_assignments_considered=len(seen),
            planning_time_ms=elapsed_ms,
            scope=f"best of up to {self.samples} seeded unique eligible placements",
            best_signature=best[1],
        )

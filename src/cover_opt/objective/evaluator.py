from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.domain.models import DeploymentPlan, ScenarioInstance, VerificationReport
from cover_opt.simulator.latency import evaluate_dag_latency


class ObjectiveReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_version: str = "0.1.0"
    e2e_latency_ms: float = Field(ge=0)
    load_imbalance: float = Field(ge=0)
    migration_cost: float = Field(ge=0)
    energy_proxy: float = Field(ge=0, default=0.0)
    weighted_objective: float = Field(ge=0)
    planning_time_ms: float = Field(ge=0, default=0.0)


class ObjectiveEvaluator:
    def evaluate(
        self,
        scenario: ScenarioInstance,
        plan: DeploymentPlan,
        verification: VerificationReport,
        *,
        planning_time_ms: float = 0.0,
    ) -> ObjectiveReport:
        if not verification.feasible:
            raise ValueError("objective evaluation requires a verifier-approved plan")
        latency = evaluate_dag_latency(scenario, plan).e2e_latency_ms
        services = {service.service_id: service for service in scenario.services}
        nodes = {node.node_id: node for node in scenario.nodes}
        compute_usage = {node_id: 0.0 for node_id in nodes}
        for service_id, node_id in plan.placement.items():
            compute_usage[node_id] += services[service_id].compute_demand
        utilizations = [
            compute_usage[node_id] / node.compute_capacity
            for node_id, node in sorted(nodes.items())
        ]
        mean = sum(utilizations) / len(utilizations)
        if mean == 0:
            load_imbalance = 0.0
        else:
            variance = sum((value - mean) ** 2 for value in utilizations) / len(
                utilizations
            )
            load_imbalance = math.sqrt(variance) / mean
        migration_cost = float(
            sum(
                scenario.previous_placement.get(service_id) != node_id
                for service_id, node_id in plan.placement.items()
            )
        )
        weights = scenario.objective
        weighted = (
            weights.latency * latency
            + weights.load_imbalance * load_imbalance
            + weights.migration_cost * migration_cost
        )
        return ObjectiveReport(
            e2e_latency_ms=latency,
            load_imbalance=load_imbalance,
            migration_cost=migration_cost,
            weighted_objective=weighted,
            planning_time_ms=planning_time_ms,
        )


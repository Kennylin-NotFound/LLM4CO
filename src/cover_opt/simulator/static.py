from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from cover_opt.domain.deployment import build_deployment_plan
from cover_opt.domain.models import DeploymentPlan, ScenarioInstance
from cover_opt.simulator.latency import LatencyReport, evaluate_dag_latency
from cover_opt.simulator.link_state import select_deterministic_routes


class StaticSimulationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: DeploymentPlan
    latency: LatencyReport
    verification_status: str = "not_verified_phase_2"


class StaticSimulator:
    def __init__(self, scenario: ScenarioInstance, *, k_paths: int = 3) -> None:
        if k_paths < 1:
            raise ValueError("k_paths must be positive")
        self.scenario = scenario
        self.k_paths = k_paths

    def run(
        self,
        placement: dict[str, str],
        *,
        method: str = "deterministic_fixture",
        candidate_id: str = "manual",
        run_id: str = "local",
    ) -> StaticSimulationResult:
        routes = select_deterministic_routes(
            self.scenario, placement, k_paths=self.k_paths
        )
        plan = build_deployment_plan(
            scenario=self.scenario,
            placement=placement,
            routes=routes,
            method=method,
            candidate_id=candidate_id,
            run_id=run_id,
        )
        return StaticSimulationResult(
            plan=plan,
            latency=evaluate_dag_latency(self.scenario, plan),
        )


from __future__ import annotations

from cover_opt.domain.models import (
    DeploymentPlan,
    MigrationRecord,
    PlanStatus,
    RouteAssignment,
    ScenarioInstance,
)


def derive_migrations(
    scenario: ScenarioInstance, placement: dict[str, str]
) -> list[MigrationRecord]:
    migrations: list[MigrationRecord] = []
    for service_id, target_node in sorted(placement.items()):
        source_node = scenario.previous_placement.get(service_id)
        if source_node != target_node:
            migrations.append(
                MigrationRecord(
                    service_id=service_id,
                    source_node=source_node,
                    target_node=target_node,
                    cost=1.0,
                )
            )
    return migrations


def build_deployment_plan(
    *,
    scenario: ScenarioInstance,
    placement: dict[str, str],
    routes: list[RouteAssignment],
    method: str,
    candidate_id: str,
    run_id: str,
    status: PlanStatus = PlanStatus.COMPLETE,
) -> DeploymentPlan:
    return DeploymentPlan(
        placement=dict(sorted(placement.items())),
        routes=sorted(routes, key=lambda route: route.edge_id),
        migrations=derive_migrations(scenario, placement),
        status=status,
        method=method,
        candidate_id=candidate_id,
        run_id=run_id,
    )


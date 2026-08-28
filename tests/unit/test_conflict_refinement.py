from pathlib import Path

from cover_opt.domain.models import ScenarioInstance, VerificationReport, ViolationType
from cover_opt.heuristics.executor import DeterministicExecutor
from cover_opt.heuristics.handcrafted import latency_first
from cover_opt.heuristics.patch import HeuristicPatch
from cover_opt.search.refiner import TargetedRefiner
from cover_opt.simulator.scenario_factory import load_scenario
from cover_opt.verifier.conflict_graph import ConflictGraphBuilder
from cover_opt.verifier.plan_verifier import PlanVerifier
from cover_opt.verifier.violations import make_violation


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "configs/scenarios/small_static.yaml"


def migration_conflict_fixture():
    base = load_scenario(SCENARIO_PATH)
    payload = base.model_dump(mode="json")
    payload["migration_budget"] = 0
    scenario = ScenarioInstance.model_validate(payload)
    parent = latency_first()
    execution = DeterministicExecutor().execute(scenario, parent)
    report = PlanVerifier().verify(scenario, execution.plan)
    return scenario, parent, execution, report


def test_conflict_graph_is_stable_and_maps_decisions_to_components() -> None:
    _, _, _, report = migration_conflict_fixture()

    first = ConflictGraphBuilder().build(report)
    second = ConflictGraphBuilder().build(report.model_copy(deep=True))

    assert report.feasible is False
    assert {item.violation_type for item in report.violations} == {
        ViolationType.MIGRATION_BUDGET
    }
    assert first.graph_signature == second.graph_signature
    assert first.allowed_components == ["node_score", "repair_policy"]
    assert first.allowed_features == {"node_score": ["migration_penalty"]}
    assert first.allowed_repair_actions == [
        "move_bottleneck_service",
        "swap_services",
    ]
    assert len(first.constraint_nodes()) == 1
    assert len(first.decision_nodes()) > 0
    assert sum(edge.contribution for edge in first.edges) == 1.0
    assert (
        first.constraint_nodes()[0].metadata["attribution_method"]
        == "exact_event_share"
    )


def test_unauthorized_patch_is_rejected_without_partial_application() -> None:
    scenario, parent, _, report = migration_conflict_fixture()
    refiner = TargetedRefiner()
    context = refiner.build_context(
        parent=parent, scenario=scenario, verification=report
    )
    patch = HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "set_weight",
                    "component": "path_score",
                    "feature": "path_latency",
                    "weight": -10.0,
                }
            ]
        }
    )

    result = refiner.apply_patch(parent=parent, patch=patch, context=context)

    assert result.accepted is False
    assert "unauthorized components" in result.errors[0]
    assert parent.path_score.terms[0].weight == -0.8


def test_same_component_but_unrelated_feature_is_rejected() -> None:
    scenario, parent, _, report = migration_conflict_fixture()
    refiner = TargetedRefiner()
    context = refiner.build_context(
        parent=parent, scenario=scenario, verification=report
    )
    patch = HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "set_weight",
                    "component": "node_score",
                    "feature": "residual_compute_ratio",
                    "weight": 2.0,
                }
            ]
        }
    )

    result = refiner.apply_patch(parent=parent, patch=patch, context=context)

    assert result.accepted is False
    assert "unauthorized features" in result.errors[0]
    assert "node_score.residual_compute_ratio" in result.errors[0]


def test_conflict_graph_unions_multi_constraint_authorizations() -> None:
    capacity = make_violation(
        violation_type=ViolationType.NODE_CAPACITY,
        magnitude=0.5,
        entities=["sat-a", "compute"],
        decisions=["place:a@sat-a", "place:b@sat-a"],
        contributions={"place:a@sat-a": 0.25, "place:b@sat-a": 0.75},
        attribution_method="exact_resource_share",
        message="compute capacity exceeded",
    )
    qos = make_violation(
        violation_type=ViolationType.QOS_LATENCY,
        magnitude=0.2,
        entities=["scenario"],
        decisions=["place:a@sat-a", "route:e1"],
        contributions={"place:a@sat-a": 0.5, "route:e1": 0.5},
        attribution_method="proxy_uniform",
        message="latency exceeded",
    )
    report = VerificationReport(
        feasible=False,
        violations=[capacity, qos],
        verifier_version="fixture",
    )

    graph = ConflictGraphBuilder().build(report)

    assert graph.allowed_components == [
        "service_order",
        "node_score",
        "path_score",
        "repair_policy",
    ]
    assert graph.allowed_features["node_score"] == [
        "dependency_latency",
        "predicted_contact_duration",
        "residual_compute_ratio",
        "residual_memory_ratio",
    ]
    assert graph.allowed_features["path_score"] == [
        "contact_duration",
        "hop_count",
        "path_latency",
    ]
    assert graph.allowed_repair_actions == [
        "bounded_backtrack",
        "move_bottleneck_service",
        "reroute",
        "swap_services",
    ]
    methods = {
        node.label: node.metadata["attribution_method"]
        for node in graph.constraint_nodes()
    }
    assert methods == {
        "node_capacity": "exact_resource_share",
        "qos_latency": "proxy_uniform",
    }


def test_scripted_targeted_patch_repairs_migration_counterexample() -> None:
    scenario, parent, initial_execution, initial_report = migration_conflict_fixture()
    refiner = TargetedRefiner()
    context = refiner.build_context(
        parent=parent,
        scenario=scenario,
        verification=initial_report,
    )
    patch = HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "add_term",
                    "component": "node_score",
                    "feature": "migration_penalty",
                    "weight": -10.0,
                }
            ],
            "rationale": "Prefer the previous placement under a zero migration budget.",
        }
    )

    application = refiner.apply_patch(parent=parent, patch=patch, context=context)
    repaired_execution = DeterministicExecutor().execute(
        scenario, application.program, candidate_id="repaired"
    )
    repaired_report = PlanVerifier().verify(scenario, repaired_execution.plan)

    assert initial_report.feasible is False
    assert initial_execution.plan.placement != scenario.previous_placement
    assert application.accepted is True
    assert application.changed_components == ["node_score"]
    assert repaired_execution.plan.placement == scenario.previous_placement
    assert repaired_report.feasible is True


def test_patch_with_unknown_feature_fails_feature_authorization() -> None:
    scenario, parent, _, report = migration_conflict_fixture()
    refiner = TargetedRefiner()
    context = refiner.build_context(
        parent=parent, scenario=scenario, verification=report
    )
    patch = HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "add_term",
                    "component": "node_score",
                    "feature": "unknown_resource_magic",
                    "weight": 1.0,
                }
            ]
        }
    )

    result = refiner.apply_patch(parent=parent, patch=patch, context=context)

    assert result.accepted is False
    assert result.static_verification is None
    assert "unauthorized features" in result.errors[0]
    assert any("unknown_resource_magic" in error for error in result.errors)


def test_unrelated_repair_action_is_rejected() -> None:
    scenario, parent, _, report = migration_conflict_fixture()
    refiner = TargetedRefiner()
    context = refiner.build_context(
        parent=parent, scenario=scenario, verification=report
    )
    patch = HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "set_repair_policy",
                    "component": "repair_policy",
                    "actions": ["reroute"],
                }
            ]
        }
    )

    result = refiner.apply_patch(parent=parent, patch=patch, context=context)

    assert result.accepted is False
    assert result.errors == ["unauthorized repair actions: ['reroute']"]


def test_no_feedback_context_suppresses_violation_and_memory_details() -> None:
    scenario, parent, _, report = migration_conflict_fixture()
    refiner = TargetedRefiner(feedback_mode="none")

    context = refiner.build_context(
        parent=parent,
        scenario=scenario,
        verification=report,
        counterexample_summary={"leak": "violation details"},
    )

    assert context.feedback_mode == "none"
    assert context.feedback_payload == {"mode": "none"}
    assert context.counterexample_summary is None
    assert context.allowed_components == [
        "service_order",
        "node_score",
        "path_score",
        "repair_policy",
    ]
    migration_feature = context.operator_catalog["node_score"]["features"][
        "migration_penalty"
    ]
    assert "negative weight discourages migrations" in migration_feature
    assert "does not directly change" in context.operator_catalog[
        "repair_policy"
    ]["effect"]

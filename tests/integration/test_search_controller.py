from pathlib import Path

from cover_opt.domain.models import ScenarioInstance
from cover_opt.heuristics.handcrafted import latency_first
from cover_opt.heuristics.patch import HeuristicPatch
from cover_opt.heuristics.schema import HeuristicDSL
from cover_opt.search.budgets import SearchBudgets
from cover_opt.search.controller import SearchController, ScriptedPatchGenerator
from cover_opt.search.options import SearchFeatures
from cover_opt.search.refiner import RefinementContext
from cover_opt.simulator.scenario_factory import load_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "configs/scenarios/small_static.yaml"


def zero_migration_scenario() -> ScenarioInstance:
    base = load_scenario(SCENARIO_PATH)
    payload = base.model_dump(mode="json")
    payload["migration_budget"] = 0
    return ScenarioInstance.model_validate(payload)


def migration_patch() -> HeuristicPatch:
    return HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "add_term",
                    "component": "node_score",
                    "feature": "migration_penalty",
                    "weight": -10.0,
                }
            ],
            "rationale": "Respect the zero migration budget.",
        }
    )


def migration_aware_program() -> HeuristicDSL:
    payload = latency_first().model_dump(mode="json")
    payload["node_score"]["terms"].append(
        {"feature": "migration_penalty", "weight": -10.0}
    )
    return HeuristicDSL.model_validate(payload)


def invalid_migration_patch() -> HeuristicPatch:
    return HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "set_weight",
                    "component": "node_score",
                    "feature": "migration_penalty",
                    "weight": -10.0,
                }
            ],
            "rationale": "This term is absent in the parent DSL.",
        }
    )


def wrong_direction_migration_patch() -> HeuristicPatch:
    return HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "add_term",
                    "component": "node_score",
                    "feature": "migration_penalty",
                    "weight": 10.0,
                }
            ],
            "rationale": "Deliberately favor migrations to exercise replay.",
        }
    )


class RecordingSequenceGenerator:
    def __init__(self, patches: list[HeuristicPatch]) -> None:
        self.patches = patches
        self.contexts: list[RefinementContext] = []

    def propose(self, context: RefinementContext) -> HeuristicPatch | None:
        self.contexts.append(context)
        index = len(self.contexts) - 1
        return self.patches[index] if index < len(self.patches) else None


def test_controller_runs_bounded_counterexample_repair_loop() -> None:
    result = SearchController().run(
        scenario=zero_migration_scenario(),
        initial_program=latency_first(),
        generator=ScriptedPatchGenerator([migration_patch()]),
        budgets=SearchBudgets(
            max_patch_proposals=1,
            max_evaluator_calls=2,
            stop_on_first_feasible=True,
        ),
    )

    assert result.stop_reason == "first_feasible"
    assert result.best_candidate_id == "candidate_001"
    assert result.statistics.patch_proposals == 1
    assert result.statistics.accepted_patches == 1
    assert result.statistics.evaluator_calls == 2
    assert [record.category for record in result.records] == [
        "repairable",
        "feasible_elite",
    ]
    assert result.records[1].execution.plan.placement == (
        zero_migration_scenario().previous_placement
    )
    assert [event["event"] for event in result.trajectory] == [
        "candidate_evaluated",
        "patch_evaluated",
        "candidate_evaluated",
    ]
    patch_event = result.trajectory[1]
    assert patch_event["parent_signature"] == result.records[0].ast_signature
    assert patch_event["child_signature"] == result.records[1].ast_signature
    assert patch_event["changed_components"] == ["node_score"]
    assert len(patch_event["conflict_graph_signature"]) == 64


def test_controller_does_not_label_first_repair_attempt_as_replay() -> None:
    generator = RecordingSequenceGenerator([migration_patch()])
    result = SearchController(
        features=SearchFeatures(
            counterexample_memory_enabled=True,
            counterexample_replay_enabled=True,
        )
    ).run(
        scenario=zero_migration_scenario(),
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(
            max_patch_proposals=1,
            max_evaluator_calls=2,
            max_counterexample_replays=1,
            max_replays_per_counterexample=1,
            stop_on_first_feasible=True,
        ),
    )

    assert result.stop_reason == "first_feasible"
    assert result.statistics.counterexample_replays == 0
    assert [event["event"] for event in result.trajectory] == [
        "candidate_evaluated",
        "patch_evaluated",
        "candidate_evaluated",
    ]


def test_controller_replays_only_after_failed_repair_and_uses_eligible_parent() -> None:
    generator = RecordingSequenceGenerator(
        [wrong_direction_migration_patch(), migration_patch()]
    )
    result = SearchController(
        features=SearchFeatures(
            counterexample_memory_enabled=True,
            counterexample_replay_enabled=True,
        )
    ).run(
        scenario=zero_migration_scenario(),
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(
            max_patch_proposals=2,
            max_evaluator_calls=3,
            max_counterexample_replays=1,
            max_replays_per_counterexample=1,
            stop_on_first_feasible=True,
        ),
    )

    assert result.stop_reason == "first_feasible"
    assert result.best_candidate_id == "candidate_002"
    assert result.statistics.counterexample_replays == 1
    assert result.statistics.outcome_rejections == 1
    assert [event["event"] for event in result.trajectory] == [
        "candidate_evaluated",
        "patch_evaluated",
        "candidate_evaluated",
        "counterexample_replayed",
        "patch_evaluated",
        "candidate_evaluated",
    ]
    replay_event = result.trajectory[3]
    assert replay_event["counterexample_signature"]
    assert replay_event["parent_candidate_id"] == "candidate_000"
    assert replay_event["replay_count"] == 1
    assert generator.contexts[0].counterexample_summary is not None
    assert generator.contexts[0].counterexample_summary["replay_count"] == 0
    assert generator.contexts[1].counterexample_summary is not None
    assert generator.contexts[1].counterexample_summary["repair_failures"] == 1
    assert generator.contexts[1].counterexample_summary["replay_count"] == 1
    rejected = next(
        record for record in result.records if record.candidate_id == "candidate_001"
    )
    assert rejected.expansion_eligible is False
    assert rejected.expansion_block_reason == "outcome_rejected"


def test_controller_selects_generated_multistart_candidate_deterministically() -> None:
    result = SearchController().run(
        scenario=zero_migration_scenario(),
        initial_program=latency_first(),
        additional_initial_programs=[migration_aware_program()],
        generator=ScriptedPatchGenerator([]),
        budgets=SearchBudgets(
            max_patch_proposals=0,
            max_evaluator_calls=2,
            stop_on_first_feasible=True,
        ),
    )

    assert result.stop_reason == "initial_candidate_feasible"
    assert result.statistics.evaluator_calls == 2
    assert result.statistics.patch_proposals == 0
    assert result.best_candidate_id == "candidate_init_001"
    assert [record.candidate_id for record in result.records] == [
        "candidate_init_000",
        "candidate_init_001",
    ]
    assert [event["event"] for event in result.trajectory] == [
        "candidate_evaluated",
        "candidate_evaluated",
        "initial_candidate_selected",
    ]
    assert result.trajectory[-1]["selection"] == "best_feasible_objective"
    assert result.trajectory[-1]["source"] == "generated_initial"


def test_multistart_candidates_share_the_evaluator_budget() -> None:
    result = SearchController().run(
        scenario=zero_migration_scenario(),
        initial_program=latency_first(),
        additional_initial_programs=[migration_aware_program()],
        generator=ScriptedPatchGenerator([]),
        budgets=SearchBudgets(
            max_patch_proposals=0,
            max_evaluator_calls=1,
            stop_on_first_feasible=True,
        ),
    )

    assert result.stop_reason == "evaluator_budget"
    assert result.statistics.evaluator_calls == 1
    assert [record.candidate_id for record in result.records] == [
        "candidate_init_000"
    ]
    assert result.best_candidate_id is None
    selection = result.trajectory[-1]
    assert selection["event"] == "initial_candidate_selected"
    assert selection["evaluated_candidate_ids"] == ["candidate_init_000"]


def test_counterexample_replay_can_be_disabled_independently_of_memory() -> None:
    result = SearchController(
        features=SearchFeatures(
            counterexample_memory_enabled=True,
            counterexample_replay_enabled=False,
        )
    ).run(
        scenario=zero_migration_scenario(),
        initial_program=latency_first(),
        generator=ScriptedPatchGenerator([migration_patch()]),
        budgets=SearchBudgets(
            max_patch_proposals=1,
            max_evaluator_calls=2,
            stop_on_first_feasible=True,
        ),
    )

    assert result.statistics.counterexample_replays == 0
    assert not any(
        event["event"] == "counterexample_replayed"
        for event in result.trajectory
    )


def test_controller_stops_before_patch_when_evaluator_budget_is_spent() -> None:
    generator = ScriptedPatchGenerator([migration_patch()])

    result = SearchController().run(
        scenario=zero_migration_scenario(),
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(
            max_patch_proposals=4,
            max_evaluator_calls=1,
        ),
    )

    assert result.stop_reason == "evaluator_budget"
    assert result.statistics.patch_proposals == 0
    assert generator.call_count == 0
    assert result.best_candidate_id is None


def test_semantic_patch_rejection_is_fed_back_before_retry() -> None:
    generator = RecordingSequenceGenerator(
        [invalid_migration_patch(), migration_patch()]
    )

    result = SearchController().run(
        scenario=zero_migration_scenario(),
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(max_patch_proposals=2, max_evaluator_calls=2),
    )

    assert result.stop_reason == "first_feasible"
    assert result.statistics.rejected_patches == 1
    assert result.statistics.accepted_patches == 1
    assert len(generator.contexts) == 2
    assert generator.contexts[0].previous_patch_rejections == []
    rejection = generator.contexts[1].previous_patch_rejections[0]
    assert "set_weight requires exactly one existing term" in rejection.errors[0]
    assert rejection.patch["operations"][0]["op"] == "set_weight"
    assert result.semantic_patch_rejections == [rejection]


def test_duplicate_rejected_patch_is_not_applied_twice() -> None:
    invalid = invalid_migration_patch()
    same_operations = invalid.model_copy(
        update={"rationale": "Different prose must not bypass semantic deduplication."}
    )
    generator = RecordingSequenceGenerator([invalid, same_operations])

    result = SearchController().run(
        scenario=zero_migration_scenario(),
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(max_patch_proposals=2, max_evaluator_calls=2),
    )

    assert result.stop_reason == "patch_budget"
    assert result.statistics.rejected_patches == 2
    assert result.statistics.evaluator_calls == 1
    assert result.trajectory[-1]["event"] == "duplicate_patch_rejected"
    assert result.semantic_patch_rejections[0].occurrence_count == 2


def test_objective_refinement_continues_after_initial_feasibility() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    improvement_patch = HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "set_weight",
                    "component": "node_score",
                    "feature": "residual_compute_ratio",
                    "weight": -0.3,
                }
            ],
            "rationale": "Test a feasible node-score variant.",
        }
    )
    generator = RecordingSequenceGenerator([improvement_patch])

    result = SearchController(
        features=SearchFeatures(objective_refinement_enabled=True)
    ).run(
        scenario=scenario,
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(
            max_patch_proposals=2,
            max_evaluator_calls=3,
            stop_on_first_feasible=False,
        ),
    )

    assert result.stop_reason == "generator_exhausted"
    assert result.statistics.first_feasible_patch_proposal == 0
    assert result.statistics.accepted_patches == 1
    assert len(result.records) == 2
    assert generator.contexts[0].refinement_phase == "objective"
    assert generator.contexts[0].feedback_payload["mode"] == "objective_directed"
    assert generator.contexts[0].allowed_components == [
        "service_order",
        "node_score",
        "path_score",
    ]
    assert generator.contexts[0].patch_affordances["node_score"][
        "existing_terms_for_set_or_remove"
    ] == ["dependency_latency", "residual_compute_ratio"]
    assert "residual_memory_ratio" in generator.contexts[0].patch_affordances[
        "node_score"
    ]["absent_terms_for_add"]
    assert generator.contexts[0].execution_summary is not None
    assert generator.contexts[0].execution_summary["placement"] == (
        result.records[0].execution.plan.placement
    )
    initial = result.records[0].objective
    best = next(
        item.objective
        for item in result.records
        if item.candidate_id == result.best_candidate_id
    )
    assert initial is not None and best is not None
    assert best.weighted_objective < initial.weighted_objective


def test_non_improving_objective_patch_is_reported_before_next_mutation() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    no_effect_patch = HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "set_weight",
                    "component": "node_score",
                    "feature": "dependency_latency",
                    "weight": -0.8,
                }
            ]
        }
    )
    improvement_patch = HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "set_weight",
                    "component": "node_score",
                    "feature": "residual_compute_ratio",
                    "weight": -0.3,
                }
            ]
        }
    )
    generator = RecordingSequenceGenerator([no_effect_patch, improvement_patch])

    result = SearchController(
        features=SearchFeatures(objective_refinement_enabled=True)
    ).run(
        scenario=scenario,
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(
            max_patch_proposals=2,
            max_evaluator_calls=3,
            stop_on_first_feasible=False,
        ),
    )

    assert result.stop_reason == "evaluator_budget"
    assert len(result.objective_patch_evaluations) == 2
    first = result.objective_patch_evaluations[0]
    second = result.objective_patch_evaluations[1]
    assert first.improved is False
    assert first.improvement == 0.0
    assert first.patch["operations"][0]["feature"] == "dependency_latency"
    assert second.improved is True
    assert generator.contexts[1].previous_objective_evaluations == [first]
    assert generator.contexts[1].parent_dsl == generator.contexts[0].parent_dsl


def test_duplicate_non_improving_objective_patch_skips_evaluator() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    no_effect = HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "set_weight",
                    "component": "node_score",
                    "feature": "dependency_latency",
                    "weight": -0.8,
                }
            ],
            "rationale": "First wording.",
        }
    )
    same_operations = no_effect.model_copy(update={"rationale": "Second wording."})
    improvement = HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "set_weight",
                    "component": "node_score",
                    "feature": "residual_compute_ratio",
                    "weight": -0.3,
                }
            ]
        }
    )
    generator = RecordingSequenceGenerator(
        [no_effect, same_operations, improvement]
    )

    result = SearchController(
        features=SearchFeatures(objective_refinement_enabled=True)
    ).run(
        scenario=scenario,
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(
            max_patch_proposals=3,
            max_evaluator_calls=3,
            stop_on_first_feasible=False,
        ),
    )

    assert result.stop_reason == "evaluator_budget"
    assert result.statistics.patch_proposals == 3
    assert result.statistics.evaluator_calls == 3
    assert result.statistics.rejected_patches == 1
    assert result.objective_patch_evaluations[0].occurrence_count == 2
    assert result.objective_patch_evaluations[1].improved is True
    assert any(
        item["event"] == "duplicate_patch_rejected"
        and "non-improving" in item["errors"][0]
        for item in result.trajectory
    )


def test_stagnant_operator_target_is_blocked_before_feature_exploration() -> None:
    scenario = load_scenario(SCENARIO_PATH)

    def dependency_patch(weight: float) -> HeuristicPatch:
        return HeuristicPatch.model_validate(
            {
                "operations": [
                    {
                        "op": "set_weight",
                        "component": "node_score",
                        "feature": "dependency_latency",
                        "weight": weight,
                    }
                ]
            }
        )

    improvement = HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "set_weight",
                    "component": "node_score",
                    "feature": "residual_compute_ratio",
                    "weight": -0.3,
                }
            ]
        }
    )
    generator = RecordingSequenceGenerator(
        [
            dependency_patch(-0.5),
            dependency_patch(-0.9),
            dependency_patch(-0.3),
            improvement,
        ]
    )

    result = SearchController(
        features=SearchFeatures(objective_refinement_enabled=True)
    ).run(
        scenario=scenario,
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(
            max_patch_proposals=4,
            max_evaluator_calls=5,
            stop_on_first_feasible=False,
        ),
    )

    target = "set_weight:node_score.dependency_latency"
    assert generator.contexts[2].blocked_operator_targets == [target]
    assert generator.contexts[3].blocked_operator_targets == [target]
    assert result.statistics.accepted_patches == 3
    assert result.statistics.rejected_patches == 1
    assert result.statistics.evaluator_calls == 4
    assert result.objective_patch_evaluations[-1].improved is True
    assert any(
        target in error
        for item in result.trajectory
        for error in item.get("errors", [])
    )


def test_counterfactual_weight_probe_recovers_opposite_numeric_direction() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    llm_patch = HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "set_weight",
                    "component": "node_score",
                    "feature": "residual_compute_ratio",
                    "weight": 0.5,
                }
            ]
        }
    )
    generator = RecordingSequenceGenerator([llm_patch])

    result = SearchController(
        features=SearchFeatures(
            objective_refinement_enabled=True,
            counterfactual_weight_probe_enabled=True,
        )
    ).run(
        scenario=scenario,
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(
            max_patch_proposals=1,
            max_evaluator_calls=3,
            stop_on_first_feasible=False,
        ),
    )

    assert result.stop_reason == "evaluator_budget"
    assert result.statistics.patch_proposals == 1
    assert result.statistics.numeric_probes == 1
    assert result.statistics.evaluator_calls == 3
    assert len(result.objective_patch_evaluations) == 2
    assert result.objective_patch_evaluations[0].improved is False
    probe = result.objective_patch_evaluations[1]
    assert probe.source == "counterfactual_probe"
    assert probe.patch["operations"][0]["weight"] == -0.5
    assert probe.improved is True
    best = next(
        item for item in result.records if item.candidate_id == result.best_candidate_id
    )
    assert "_probe_" in best.candidate_id
    assert best.execution.plan.placement == {
        "ingest": "sat-b",
        "analyze": "sat-b",
        "respond": "sat-b",
    }

import json
from pathlib import Path

from cover_opt.cli import main
from cover_opt.domain.models import ScenarioInstance
from cover_opt.heuristics.handcrafted import latency_first
from cover_opt.heuristics.patch import HeuristicPatch
from cover_opt.search.budgets import SearchBudgets
from cover_opt.search.campaign import (
    CampaignSeedRun,
    CounterexampleReplayCampaignRunner,
)
from cover_opt.search.controller import ScriptedPatchGenerator
from cover_opt.search.options import SearchFeatures
from cover_opt.simulator.scenario_factory import load_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "configs/scenarios/small_static.yaml"
CAMPAIGN_CONFIG_PATH = (
    PROJECT_ROOT / "configs/experiments/counterexample_replay_campaign.yaml"
)


def zero_migration_scenario() -> ScenarioInstance:
    payload = load_scenario(SCENARIO_PATH).model_dump(mode="json")
    payload["migration_budget"] = 0
    return ScenarioInstance.model_validate(payload)


def migration_patch(weight: float) -> HeuristicPatch:
    return HeuristicPatch.model_validate(
        {
            "operations": [
                {
                    "op": "add_term",
                    "component": "node_score",
                    "feature": "migration_penalty",
                    "weight": weight,
                }
            ]
        }
    )


def test_campaign_replays_persisted_failed_scenario_with_eligible_parent() -> None:
    scenario = zero_migration_scenario()
    seed = CampaignSeedRun(
        run_id="seed_zero_migration",
        scenario=scenario,
        initial_program=latency_first(),
        generator=ScriptedPatchGenerator([migration_patch(10.0)]),
        budgets=SearchBudgets(
            max_patch_proposals=1,
            max_evaluator_calls=2,
            stop_on_first_feasible=True,
        ),
    )

    result = CounterexampleReplayCampaignRunner().run(
        seeds=[seed],
        replay_generator_factory=lambda _entry, _index: ScriptedPatchGenerator(
            [migration_patch(-10.0)]
        ),
        replay_budgets=SearchBudgets(
            max_patch_proposals=1,
            max_evaluator_calls=2,
            stop_on_first_feasible=True,
        ),
        features=SearchFeatures(
            counterexample_memory_enabled=True,
            counterexample_replay_enabled=False,
        ),
        max_scenario_replays=1,
        max_replays_per_counterexample=1,
    )

    assert result.stop_reason == "replay_budget"
    assert result.statistics.seed_runs == 1
    assert result.statistics.scenario_replays == 1
    assert result.statistics.resolved_counterexamples == 1
    assert result.statistics.total_llm_calls == 0
    assert len(result.runs) == 2
    seed_run, replay_run = result.runs
    assert seed_run.phase == "seed"
    assert seed_run.search_result.best_candidate_id is None
    rejected = next(
        record
        for record in seed_run.search_result.records
        if record.candidate_id == "candidate_001"
    )
    assert rejected.expansion_eligible is False

    assert replay_run.phase == "scenario_replay"
    assert replay_run.scenario_hash == scenario.stable_hash
    assert replay_run.source_run_id == "seed_zero_migration"
    assert replay_run.source_candidate_id == "candidate_000"
    assert replay_run.search_result.best_candidate_id == "candidate_001"
    replay_event = next(
        event
        for event in result.trajectory
        if event["event"] == "campaign_scenario_replayed"
    )
    assert replay_event["scenario_hash"] == scenario.stable_hash
    assert replay_event["source_candidate_id"] == "candidate_000"
    assert replay_event["replay_count"] == 1
    resolved = next(
        entry
        for entry in result.counterexample_store
        if entry.counterexample.signature
        == replay_run.search_result.counterexamples[0].signature
    )
    assert resolved.scenario.stable_hash == scenario.stable_hash
    assert resolved.resolved is True


def test_campaign_cli_persists_cross_run_replay_evidence(tmp_path: Path) -> None:
    output = tmp_path / "counterexample_replay_campaign.json"

    exit_code = main(
        [
            "run-counterexample-replay-campaign",
            "--config",
            str(CAMPAIGN_CONFIG_PATH),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["evidence_status"] == (
        "offline_cross_run_replay_control_evidence_not_llm_performance"
    )
    campaign = payload["campaign_result"]
    assert campaign["statistics"]["total_patch_generation_calls"] == 2
    assert campaign["statistics"]["total_llm_calls"] == 2
    assert [run["phase"] for run in campaign["runs"]] == [
        "seed",
        "scenario_replay",
    ]
    seed_run, replay_run = campaign["runs"]
    assert seed_run["scenario_hash"] == replay_run["scenario_hash"]
    assert replay_run["source_run_id"] == "seed_zero_migration"
    assert replay_run["source_candidate_id"] == "candidate_000"
    stored = campaign["counterexample_store"][0]
    assert stored["resolved"] is True
    assert stored["scenario"]["scenario_id"] == seed_run["scenario_id"]
    assert stored["parent_candidate_id"] == "candidate_000"

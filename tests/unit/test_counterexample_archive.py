from pathlib import Path

from cover_opt.domain.models import (
    ConstraintViolation,
    VerificationReport,
    ViolationType,
)
from cover_opt.search.counterexamples import CounterexampleArchive
from cover_opt.simulator.scenario_factory import load_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "configs/scenarios/small_static.yaml"


def report(
    violation_type: ViolationType,
    *,
    magnitude: float,
    entity: str,
    decision: str,
) -> VerificationReport:
    return VerificationReport(
        feasible=False,
        violations=[
            ConstraintViolation(
                violation_type=violation_type,
                magnitude=magnitude,
                entities=[entity],
                contributing_decisions=[decision],
                decision_contributions={decision: magnitude},
                dsl_components=["node_score"],
                message="fixture violation",
            )
        ],
        verifier_version="fixture",
    )


def test_counterexample_archive_aggregates_pattern_and_ranks_failed_repairs() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    archive = CounterexampleArchive()
    migration_report = report(
        ViolationType.MIGRATION_BUDGET,
        magnitude=2.0,
        entity="migration_budget",
        decision="placement:a",
    )

    first = archive.observe(
        scenario=scenario,
        verification=migration_report,
        candidate_id="candidate_000",
        ast_signature="a" * 64,
        iteration=0,
        conflict_graph_signature="c" * 64,
    )
    second = archive.observe(
        scenario=scenario,
        verification=migration_report,
        candidate_id="candidate_001",
        ast_signature="b" * 64,
        iteration=1,
        conflict_graph_signature="d" * 64,
    )
    archive.mark_repair_failure(first.signature)
    archive.observe(
        scenario=scenario,
        verification=report(
            ViolationType.QOS_LATENCY,
            magnitude=20.0,
            entity="qos_latency",
            decision="route:e1",
        ),
        candidate_id="candidate_002",
        ast_signature="e" * 64,
        iteration=2,
        conflict_graph_signature="f" * 64,
    )

    aggregated = next(
        record for record in archive.records if record.signature == first.signature
    )
    assert second.signature == first.signature
    assert aggregated.observation_count == 2
    assert aggregated.repair_failures == 1
    assert aggregated.candidate_ids == ["candidate_000", "candidate_001"]
    assert archive.ranked_for_replay(limit=1)[0].signature == first.signature

    replayed = archive.mark_replayed(first.signature, iteration=3)
    assert replayed is not None
    assert replayed.replay_count == 1
    assert replayed.last_replayed_iteration == 3
    assert replayed.prompt_summary()["replay_count"] == 1

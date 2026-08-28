from types import SimpleNamespace

import pytest

from cover_opt.heuristics.handcrafted import capacity_first, latency_first, migration_aware
from cover_opt.heuristics.static_verifier import dsl_signature
from cover_opt.search.archive import CandidateArchive
from cover_opt.search.diversity import dsl_structural_distance


def fake_feasible_record(program, candidate_id: str, objective: float):
    return SimpleNamespace(
        candidate_id=candidate_id,
        category="feasible_elite",
        iteration=0,
        program=program,
        ast_signature=dsl_signature(program),
        objective=SimpleNamespace(weighted_objective=objective),
        execution=SimpleNamespace(planning_time_ms=1.0),
    )


def test_structural_distance_is_normalized_symmetric_and_identity_preserving() -> None:
    latency = latency_first()
    capacity = capacity_first()

    identity = dsl_structural_distance(latency, latency)
    forward = dsl_structural_distance(latency, capacity)
    reverse = dsl_structural_distance(capacity, latency)

    assert identity.total == pytest.approx(0.0)
    assert 0.0 < forward.total <= 1.0
    assert forward.total == pytest.approx(reverse.total)
    assert forward.service_order > 0.0
    assert forward.repair_policy > 0.0


def test_archive_uses_deterministic_farthest_first_selection() -> None:
    archive = CandidateArchive()
    archive.records.extend(
        [
            fake_feasible_record(latency_first(), "latency", 1.0),
            fake_feasible_record(migration_aware(), "migration", 1.1),
            fake_feasible_record(capacity_first(), "capacity", 1.2),
        ]
    )

    selected = archive.diverse_feasible(limit=2)

    assert [record.candidate_id for record in selected] == ["latency", "capacity"]
    assert archive.diverse_feasible(limit=2) == selected

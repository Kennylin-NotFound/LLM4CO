from pathlib import Path

from cover_opt.evaluation.solvers import (
    ExactEnumerationOracle,
    HeuristicBaseline,
    RandomBaseline,
)
from cover_opt.heuristics.handcrafted import latency_no_repair
from cover_opt.simulator.scenario_factory import load_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "configs/scenarios/small_static.yaml"


def test_small_exact_oracle_is_deterministic_and_proves_candidate_set_optimality() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    first = ExactEnumerationOracle(k_paths=3).solve(scenario)
    second = ExactEnumerationOracle(k_paths=3).solve(scenario)

    assert first.status == "feasible"
    assert first.optimality_proven is True
    assert first.best_signature == second.best_signature
    assert first.objective is not None and second.objective is not None
    assert first.objective.weighted_objective == second.objective.weighted_objective
    assert first.candidates_evaluated > 1


def test_exact_oracle_is_no_worse_than_shared_interface_baselines() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    oracle = ExactEnumerationOracle(k_paths=3).solve(scenario)
    greedy = HeuristicBaseline(
        "latency_greedy",
        latency_no_repair(),
        k_paths=3,
    ).solve(scenario)
    random_result = RandomBaseline(samples=32, seed=7, k_paths=3).solve(scenario)

    assert oracle.objective is not None
    assert greedy.objective is not None
    assert random_result.objective is not None
    assert oracle.objective.weighted_objective <= greedy.objective.weighted_objective
    assert oracle.objective.weighted_objective <= random_result.objective.weighted_objective
    assert random_result.best_signature == RandomBaseline(
        samples=32,
        seed=7,
        k_paths=3,
    ).solve(scenario).best_signature

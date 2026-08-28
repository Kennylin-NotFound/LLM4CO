from pathlib import Path

from cover_opt.config import load_deepseek_live_pilot
from cover_opt.evaluation.pilot import StaticPilotScenarioFactory
from cover_opt.evaluation.protocol import load_formal_experiment_protocol
from cover_opt.simulator.scenario_factory import load_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs/experiments/deepseek_v4pro_live_pilot.yaml"


def test_pilot_scenarios_are_deterministic_distinct_and_previous_feasible() -> None:
    loaded = load_deepseek_live_pilot(CONFIG_PATH)
    protocol = load_formal_experiment_protocol(loaded.config.protocol_path)
    stage = next(item for item in protocol.stages if item.stage_id == "live_pilot")
    base = load_scenario(loaded.config.base_scenario_path)
    factory = StaticPilotScenarioFactory()

    first = [
        factory.build(base=base, seed=seed, ordinal=index)
        for index, seed in enumerate(stage.scenario_seeds)
    ]
    second = [
        factory.build(base=base, seed=seed, ordinal=index)
        for index, seed in enumerate(stage.scenario_seeds)
    ]

    assert [item.scenario.stable_hash for item in first] == [
        item.scenario.stable_hash for item in second
    ]
    assert len({item.scenario.stable_hash for item in first}) == 5
    assert len({tuple(sorted(item.scenario.previous_placement.items())) for item in first}) == 5
    assert all(item.scenario.migration_budget == 0 for item in first)
    assert all(item.scenario.seed in {100, 101, 102, 103, 104} for item in first)

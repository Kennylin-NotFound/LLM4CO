import math
from pathlib import Path

import pytest

from cover_opt.simulator.walker import (
    EARTH_RADIUS_KM,
    WalkerDeltaConstellation,
    generate_walker_scenario,
    load_walker_scenario_config,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WALKER_CONFIG = PROJECT_ROOT / "configs/scenarios/walker_dynamic.yaml"


def test_walker_snapshot_is_deterministic_and_time_varying() -> None:
    config = load_walker_scenario_config(WALKER_CONFIG)

    first = generate_walker_scenario(config, 0)
    repeated = generate_walker_scenario(config, 0)
    next_slot = generate_walker_scenario(config, 1)

    assert first.stable_hash == repeated.stable_hash
    assert first.stable_hash != next_slot.stable_hash
    assert len(first.nodes) == 24
    assert len(first.links) > 0
    assert [node.compute_rate_mips for node in first.nodes] == [
        node.compute_rate_mips for node in next_slot.nodes
    ]
    assert first.nodes[0].position_km != next_slot.nodes[0].position_km


def test_walker_positions_remain_on_circular_orbit() -> None:
    config = load_walker_scenario_config(WALKER_CONFIG)
    constellation = WalkerDeltaConstellation(config.topology)
    expected_radius = EARTH_RADIUS_KM + config.topology.altitude_km

    for position in (
        constellation.position_km(0, 0, 0),
        constellation.position_km(1, 3, 5),
        constellation.position_km(2, 7, 10),
    ):
        radius = math.sqrt(sum(value * value for value in position))
        assert radius == pytest.approx(expected_radius)


def test_walker_links_are_current_slot_and_have_valid_geometry() -> None:
    config = load_walker_scenario_config(WALKER_CONFIG)
    scenario = generate_walker_scenario(config, 2)

    assert {link.link_class for link in scenario.links} == {
        "intra_plane",
        "inter_plane",
    }
    assert all(link.available_from == link.available_until == 2 for link in scenario.links)
    assert all(link.distance_km > 0 for link in scenario.links)
    assert all(link.transmission_rate_mbps >= config.topology.rate_floor_mbps for link in scenario.links)


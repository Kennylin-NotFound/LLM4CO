from __future__ import annotations

import hashlib
import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.config import load_yaml
from cover_opt.domain.models import (
    ComputeNode,
    Microservice,
    NetworkLink,
    ObjectiveWeights,
    Provenance,
    ScenarioInstance,
    ServiceEdge,
)


EARTH_RADIUS_KM = 6_371.0
EARTH_GRAVITATIONAL_PARAMETER_KM3_S2 = 398_600.4418
WALKER_GENERATOR_VERSION = "walker-delta-0.1.0"


class WalkerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WalkerTopologyConfig(WalkerModel):
    constellation_id: str = Field(min_length=1)
    seed: int = Field(ge=0)
    orbital_planes: int = Field(ge=1)
    satellites_per_plane: int = Field(ge=2)
    phasing: int = Field(ge=0)
    altitude_km: float = Field(gt=0)
    inclination_deg: float = Field(ge=0, le=180)
    slot_duration_seconds: float = Field(gt=0)
    compute_capacity: float = Field(gt=0)
    memory_capacity: float = Field(gt=0)
    compute_rate_mips: float = Field(gt=0)
    resource_heterogeneity: float = Field(ge=0, le=0.5, default=0.0)
    base_rate_mbps: float = Field(gt=0)
    bandwidth_mbps: float = Field(gt=0)
    reference_distance_km: float = Field(gt=0)
    rate_floor_mbps: float = Field(gt=0)
    line_of_sight_clearance_km: float = Field(ge=0, default=0.0)
    inter_plane_links: bool = True


class WalkerScenarioConfig(WalkerModel):
    scenario_prefix: str = Field(min_length=1)
    topology: WalkerTopologyConfig
    services: list[Microservice] = Field(min_length=1)
    service_edges: list[ServiceEdge]
    previous_placement: dict[str, str]
    qos_latency_ms: float = Field(gt=0)
    migration_budget: int = Field(ge=0)
    objective: ObjectiveWeights
    provenance: Provenance


def load_walker_scenario_config(path: Path) -> WalkerScenarioConfig:
    return WalkerScenarioConfig.model_validate(load_yaml(path.resolve()))


class WalkerDeltaConstellation:
    def __init__(self, config: WalkerTopologyConfig) -> None:
        self.config = config
        self.orbit_radius_km = EARTH_RADIUS_KM + config.altitude_km
        self.orbital_period_seconds = 2.0 * math.pi * math.sqrt(
            self.orbit_radius_km**3 / EARTH_GRAVITATIONAL_PARAMETER_KM3_S2
        )

    @staticmethod
    def node_id(plane: int, satellite: int) -> str:
        return f"p{plane:02d}-s{satellite:02d}"

    def position_km(
        self, plane: int, satellite: int, time_slot: int
    ) -> tuple[float, float, float]:
        config = self.config
        total_satellites = config.orbital_planes * config.satellites_per_plane
        elapsed = time_slot * config.slot_duration_seconds
        mean_motion = 2.0 * math.pi / self.orbital_period_seconds
        raan = 2.0 * math.pi * plane / config.orbital_planes
        phase_offset = 2.0 * math.pi * config.phasing * plane / total_satellites
        argument = (
            2.0 * math.pi * satellite / config.satellites_per_plane
            + phase_offset
            + mean_motion * elapsed
        )
        inclination = math.radians(config.inclination_deg)
        cos_raan, sin_raan = math.cos(raan), math.sin(raan)
        cos_u, sin_u = math.cos(argument), math.sin(argument)
        cos_i, sin_i = math.cos(inclination), math.sin(inclination)
        radius = self.orbit_radius_km
        return (
            radius * (cos_raan * cos_u - sin_raan * sin_u * cos_i),
            radius * (sin_raan * cos_u + cos_raan * sin_u * cos_i),
            radius * (sin_u * sin_i),
        )

    def _resource_multiplier(self, node_id: str) -> float:
        spread = self.config.resource_heterogeneity
        if spread == 0:
            return 1.0
        payload = f"{self.config.seed}:{node_id}".encode("utf-8")
        integer = int(hashlib.sha256(payload).hexdigest()[:16], 16)
        unit = integer / float(0xFFFFFFFFFFFFFFFF)
        return 1.0 + spread * (2.0 * unit - 1.0)

    def nodes(self, time_slot: int) -> list[ComputeNode]:
        nodes: list[ComputeNode] = []
        for plane in range(self.config.orbital_planes):
            for satellite in range(self.config.satellites_per_plane):
                node_id = self.node_id(plane, satellite)
                multiplier = self._resource_multiplier(node_id)
                nodes.append(
                    ComputeNode(
                        node_id=node_id,
                        compute_capacity=self.config.compute_capacity * multiplier,
                        memory_capacity=self.config.memory_capacity * multiplier,
                        compute_rate_mips=self.config.compute_rate_mips * multiplier,
                        position_km=self.position_km(plane, satellite, time_slot),
                    )
                )
        return nodes

    @staticmethod
    def _distance(
        first: tuple[float, float, float], second: tuple[float, float, float]
    ) -> float:
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))

    def _has_line_of_sight(
        self,
        first: tuple[float, float, float],
        second: tuple[float, float, float],
    ) -> bool:
        direction = tuple(b - a for a, b in zip(first, second))
        length_squared = sum(value * value for value in direction)
        if length_squared == 0:
            return False
        projection = -sum(a * d for a, d in zip(first, direction)) / length_squared
        projection = min(1.0, max(0.0, projection))
        closest = tuple(a + projection * d for a, d in zip(first, direction))
        closest_radius = math.sqrt(sum(value * value for value in closest))
        return closest_radius > (
            EARTH_RADIUS_KM + self.config.line_of_sight_clearance_km
        )

    def _candidate_pairs(
        self, positions: dict[str, tuple[float, float, float]]
    ) -> dict[tuple[str, str], str]:
        config = self.config
        pairs: dict[tuple[str, str], str] = {}
        for plane in range(config.orbital_planes):
            for satellite in range(config.satellites_per_plane):
                first = self.node_id(plane, satellite)
                second = self.node_id(
                    plane, (satellite + 1) % config.satellites_per_plane
                )
                pair = tuple(sorted((first, second)))
                pairs[pair] = "intra_plane"

        if config.inter_plane_links and config.orbital_planes > 1:
            for plane in range(config.orbital_planes):
                next_plane = (plane + 1) % config.orbital_planes
                if plane == next_plane:
                    continue
                targets = [
                    self.node_id(next_plane, satellite)
                    for satellite in range(config.satellites_per_plane)
                ]
                for satellite in range(config.satellites_per_plane):
                    source = self.node_id(plane, satellite)
                    target = min(
                        targets,
                        key=lambda candidate: (
                            self._distance(positions[source], positions[candidate]),
                            candidate,
                        ),
                    )
                    pair = tuple(sorted((source, target)))
                    pairs.setdefault(pair, "inter_plane")
        return pairs

    def _link_rate_mbps(self, distance_km: float) -> float:
        config = self.config
        if distance_km <= config.reference_distance_km:
            return config.base_rate_mbps
        scaled = config.base_rate_mbps * (
            config.reference_distance_km / distance_km
        ) ** 2
        return max(config.rate_floor_mbps, scaled)

    def links(self, time_slot: int) -> list[NetworkLink]:
        positions = {
            node.node_id: node.position_km
            for node in self.nodes(time_slot)
            if node.position_km is not None
        }
        links: list[NetworkLink] = []
        for (first, second), link_class in sorted(self._candidate_pairs(positions).items()):
            if not self._has_line_of_sight(positions[first], positions[second]):
                continue
            distance_km = self._distance(positions[first], positions[second])
            links.append(
                NetworkLink(
                    link_id=f"isl_{first}__{second}",
                    source=first,
                    target=second,
                    distance_km=distance_km,
                    transmission_rate_mbps=self._link_rate_mbps(distance_km),
                    bandwidth_mbps=self.config.bandwidth_mbps,
                    available_from=time_slot,
                    available_until=time_slot,
                    bidirectional=True,
                    link_class=link_class,
                )
            )
        return links

    def scenario(
        self, config: WalkerScenarioConfig, time_slot: int
    ) -> ScenarioInstance:
        return ScenarioInstance(
            scenario_id=f"{config.scenario_prefix}_slot_{time_slot:04d}",
            seed=self.config.seed,
            time_slot=time_slot,
            generator_version=WALKER_GENERATOR_VERSION,
            slot_duration_seconds=self.config.slot_duration_seconds,
            nodes=self.nodes(time_slot),
            links=self.links(time_slot),
            services=config.services,
            service_edges=config.service_edges,
            previous_placement=config.previous_placement,
            qos_latency_ms=config.qos_latency_ms,
            migration_budget=config.migration_budget,
            objective=config.objective,
            provenance=config.provenance,
        )


def generate_walker_scenario(
    config: WalkerScenarioConfig, time_slot: int
) -> ScenarioInstance:
    return WalkerDeltaConstellation(config.topology).scenario(config, time_slot)

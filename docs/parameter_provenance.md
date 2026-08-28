# Parameter Provenance

Each scenario parameter must be assigned one of three source classes:

- `original_paper`: stated explicitly in the accepted paper or its released material.
- `public_reference`: taken from a cited public data source or standard.
- `synthetic_assumption`: chosen for controlled testing and not presented as measured reality.

## Phase 1 fixture

| Parameter group | Current value source | Source class | Usage boundary |
|---|---|---|---|
| Node compute and memory capacity | hand-authored small fixture | synthetic_assumption | schema and reproducibility tests only |
| Link delay, rate and bandwidth | hand-authored small fixture | synthetic_assumption | schema and reproducibility tests only |
| Service demand and workload | hand-authored small fixture | synthetic_assumption | schema and reproducibility tests only |
| QoS threshold | hand-authored small fixture | synthetic_assumption | schema test only |
| Migration budget | hand-authored small fixture | synthetic_assumption | schema test only |
| Objective weights | research contract defaults | synthetic_assumption | configuration test only |

These values are not calibrated Space-CPN measurements and must not be reused
as final experiment evidence. Later phases will add a machine-readable source
record for every final scenario family before results are generated.

## Phase 2 Walker fixture

The `walker_dynamic.yaml` topology uses a simplified circular-orbit Walker
Delta geometry. Altitude, inclination, link-rate parameters, resource
heterogeneity, workload, and QoS values are all `synthetic_assumption`. The
generator is intended to test deterministic time-slot state, line-of-sight
filtering, routing, and latency accounting. It is not an ns-3 result, an orbit
propagator validation, or a calibrated communication trace.

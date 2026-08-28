# Problem Formulation v0.1

## Scope

At time slot `t`, an instance is represented by

```text
I_t = (G_t, S, A, Q_t, X_previous)
```

where `G_t` is the active compute-network graph, `S` is the microservice set,
`A` is the service dependency DAG, `Q_t` contains the QoS threshold and
objective preference, and `X_previous` is the previous placement.

The first implementation makes two decisions:

1. A heuristic selects exactly one eligible compute node for each service.
2. A deterministic path selector chooses a route for each dependency after its endpoints are placed.

Joint placement-routing evolution is outside the first version. Natural
language parsing is evaluated separately and cannot affect the solver's main
performance metrics.

## Hard constraints

The canonical constraint identifiers are:

- `unique_placement`
- `node_eligibility`
- `node_capacity`
- `route_connectivity`
- `link_bandwidth`
- `qos_latency`
- `migration_budget`

Hard constraints are checked by one shared `PlanVerifier`. An infeasible plan
cannot enter the feasible candidate archive by receiving a favorable soft
penalty.

## Objective

For a feasible plan `Pi_t`, the planned scalar reporting objective is

```text
J(Pi_t) = w_l * latency(Pi_t)
        + w_b * load_imbalance(Pi_t)
        + w_m * migration_cost(Pi_t)
        + w_e * energy_proxy(Pi_t)
```

The selection contract remains lexicographic: feasibility is compared before
all soft metrics. Energy is disabled until its parameter provenance is
defensible. The initial main measurements are latency and migration cost, with
load imbalance as a secondary metric.

## Units and latency recurrence

The deterministic kernel uses explicit units: distance in km, data volume in
Mbit, link rate and bandwidth in Mbps, workload in million instructions,
compute rate in MIPS, and all reported latency in ms.

For service `m` placed on node `j`, processing latency is

```text
processing_ms(m, j) = workload_mi(m) / compute_rate_mips(j) * 1000
```

For one physical link, communication latency is transmission plus propagation:

```text
effective_rate_mbps = min(transmission_rate_mbps, bandwidth_mbps)
transmission_ms = data_volume_mbit / effective_rate_mbps * 1000
propagation_ms = distance_km / 299792.458 * 1000
```

Service completion follows the last-arriving predecessor semantics:

```text
finish(m) = processing(m)
          + max(finish(u) + communication(u, m)) for every predecessor u
```

An entry service starts at zero, and application end-to-end latency is the
maximum completion time among sink services. A microservice-latency sum may be
reported only as a separately named reconstructed-paper metric.

## LLM boundary

The LLM boundary generates one typed `HeuristicPatch` from a compact scenario,
conflict graph, parent DSL, authorized components, and operation budget. Strict
schema parsing and authorized application happen before deterministic
execution. The LLM does not certify feasibility, compute the objective, control
the experiment budget, edit a deployment plan directly, or execute arbitrary
generated Python. Current evidence uses Mock/Replay responses; online-model
quality remains untested.

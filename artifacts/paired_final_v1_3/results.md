# COVER-Opt paired-final results

Evidence status: `claim_eligible_paired_final_evidence`

## Quality gates

- manifest_complete: PASS
- run_counts_complete: PASS
- no_infrastructure_failures: PASS
- system_fingerprint_consistent: PASS
- minimum_paired_scenarios: PASS

## Method summary

| Method | Runs | Feasible | Majority scenarios | Objective | Gap % | LLM calls | Cost CNY |
|---|---:|---:|---:|---:|---:|---:|---:|
| capacity_greedy | 20 | 0.250 | 0.250 | 178.1629 | 85.27 | 0.00 | 0.0000 |
| cover_opt_conflict_feedback | 60 | 0.550 | 0.550 | 97.9140 | 5.18 | 2.22 | 1.1456 |
| cover_opt_full | 60 | 0.717 | 0.750 | 94.5750 | 0.00 | 2.70 | 1.6264 |
| cover_opt_generic_feedback | 60 | 0.750 | 0.750 | 98.1508 | 3.80 | 1.63 | 0.6771 |
| cover_opt_no_feedback | 60 | 0.300 | 0.300 | 104.9923 | 9.49 | 2.90 | 1.1654 |
| direct_llm_plan | 60 | 0.000 | 0.000 | NA | NA | 1.00 | 0.1636 |
| exact_enumeration_oracle | 20 | 1.000 | 1.000 | 93.7116 | 0.00 | 0.00 | 0.0000 |
| latency_greedy | 20 | 0.250 | 0.250 | 107.2220 | 11.39 | 0.00 | 0.0000 |
| random_baseline | 20 | 1.000 | 1.000 | 93.7116 | 0.00 | 0.00 | 0.0000 |
| structured_llm_plan | 60 | 0.233 | 0.250 | 156.6365 | 61.90 | 1.00 | 0.2485 |

## Preregistered comparisons

### C_SCHEMA: structured_llm_plan vs direct_llm_plan

Status: **not_supported**. primary feasible_rate: effect=0.25, Holm p=0.25, n=20

- `feasible_rate`: treatment=0.25, control=0.0, delta=0.25, 95% CI=(0.1, 0.45), raw p=0.0625, Holm p=0.25, n=20.
- `schema_failure_rate`: treatment=0.0, control=1.0, delta=-1.0, 95% CI=(-1.0, -1.0), raw p=7.74421643104407e-06, Holm p=None, n=20.

### C_FEEDBACK: cover_opt_conflict_feedback vs cover_opt_generic_feedback

Status: **not_supported**. primary feasible_rate: effect=-0.19999999999999996, Holm p=0.25, n=20

- `feasible_rate`: treatment=0.55, control=0.75, delta=-0.19999999999999996, 95% CI=(-0.4, -0.05), raw p=0.125, Holm p=0.25, n=20.
- `calls_to_first_feasible`: treatment=0.9166666666666666, control=0.6944444444444444, delta=0.2222222222222222, 95% CI=(0.0, 0.5555555555555555), raw p=0.5, Holm p=None, n=12.

### C_VERIFICATION: cover_opt_conflict_feedback vs cover_opt_no_feedback

Status: **not_supported**. primary violation_burden: effect=-0.25, Holm p=0.25, n=20

- `feasible_rate`: treatment=0.55, control=0.3, delta=0.25000000000000006, 95% CI=(0.0, 0.5), raw p=0.125, Holm p=None, n=20.
- `violation_burden`: treatment=0.65, control=0.9, delta=-0.25, 95% CI=(-0.5333333333333333, 0.08333333333333331), raw p=0.15102615479062906, Holm p=0.25, n=20.

### C_PIPELINE: cover_opt_full vs cover_opt_conflict_feedback

Status: **not_supported**. primary weighted_objective: effect=-4.51782197534034, Holm p=0.25, n=12

- `feasible_rate`: treatment=0.75, control=0.55, delta=0.19999999999999996, 95% CI=(0.05, 0.4), raw p=0.125, Holm p=None, n=20.
- `weighted_objective`: treatment=92.12395950625339, control=96.64178148159372, delta=-4.51782197534034, 95% CI=(-7.831489722948354, -1.4422709431694425), raw p=0.0625, Holm p=0.25, n=12.

## Evidence boundary

These results apply to the frozen controlled static benchmark and the enumerated top-k route candidate set. They do not establish production satellite-network performance or generalize to paper-scale instances.

from __future__ import annotations

import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from scipy.stats import wilcoxon

from cover_opt.evaluation.final import FinalRunRecord, PairedFinalManifest
from cover_opt.evaluation.protocol import FormalExperimentProtocol


class StatisticsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MethodSummary(StatisticsModel):
    method_id: str
    run_count: int
    scenario_count: int
    raw_feasible_rate: float
    majority_feasible_scenario_rate: float
    mean_weighted_objective_feasible_runs: float | None
    mean_candidate_set_gap_pct_feasible_runs: float | None
    mean_violation_burden: float
    schema_failure_rate: float
    mean_llm_calls: float
    mean_evaluator_calls: float
    total_billed_input_tokens: int
    total_billed_output_tokens: int
    total_estimated_cost_cny: float


class MetricComparison(StatisticsModel):
    metric_id: str
    direction: Literal["minimize", "maximize", "report_only"]
    scenario_count: int
    treatment_mean: float | None
    control_mean: float | None
    treatment_minus_control: float | None
    favorable_direction: bool | None
    confidence_interval_95: tuple[float, float] | None
    test_name: str
    p_value_raw: float | None
    p_value_holm: float | None = None
    discordant_treatment_only: int | None = None
    discordant_control_only: int | None = None


class ComparisonResult(StatisticsModel):
    comparison_id: str
    claim_id: str
    treatment: str
    control: str
    primary_metric_id: str
    metrics: list[MetricComparison]
    claim_status: Literal["supported", "not_supported"]
    claim_reason: str


class AnalysisReport(StatisticsModel):
    experiment_id: str
    protocol_hash: str
    config_hash: str
    code_tree_hash: str
    scenario_set_hash: str
    quality_gates: dict[str, bool]
    method_summaries: list[MethodSummary]
    comparisons: list[ComparisonResult]
    supported_claims: list[str]
    unsupported_claims: list[str]
    evidence_status: str
    analysis_version: str = "1.0.0"


def _mean_or_none(values: list[float]) -> float | None:
    return mean(values) if values else None


def _majority(records: list[FinalRunRecord]) -> float:
    return float(sum(item.final_feasible for item in records) >= (len(records) // 2 + 1))


def _exact_mcnemar(treatment: list[float], control: list[float]) -> tuple[float, int, int]:
    treatment_only = sum(t == 1.0 and c == 0.0 for t, c in zip(treatment, control))
    control_only = sum(t == 0.0 and c == 1.0 for t, c in zip(treatment, control))
    discordant = treatment_only + control_only
    if discordant == 0:
        return 1.0, treatment_only, control_only
    tail = sum(
        math.comb(discordant, value) for value in range(min(treatment_only, control_only) + 1)
    ) / (2**discordant)
    return min(1.0, 2.0 * tail), treatment_only, control_only


def _paired_bootstrap(
    treatment: list[float],
    control: list[float],
    *,
    seed: int,
    resamples: int = 10_000,
) -> tuple[float, float] | None:
    if not treatment or len(treatment) != len(control):
        return None
    rng = random.Random(seed)
    differences = [t - c for t, c in zip(treatment, control)]
    estimates = []
    for _ in range(resamples):
        estimates.append(
            mean(differences[rng.randrange(len(differences))] for _ in differences)
        )
    estimates.sort()
    low = estimates[int(0.025 * (resamples - 1))]
    high = estimates[int(0.975 * (resamples - 1))]
    return low, high


def _wilcoxon(treatment: list[float], control: list[float]) -> float:
    differences = [t - c for t, c in zip(treatment, control)]
    if not differences or all(abs(item) <= 1e-12 for item in differences):
        return 1.0
    return float(
        wilcoxon(
            treatment,
            control,
            zero_method="wilcox",
            alternative="two-sided",
            method="auto",
        ).pvalue
    )


def _holm_adjust(raw: dict[str, float]) -> dict[str, float]:
    ordered = sorted(raw.items(), key=lambda item: (item[1], item[0]))
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for rank, (key, value) in enumerate(ordered):
        running = max(running, min(1.0, (total - rank) * value))
        adjusted[key] = running
    return adjusted


class PairedFinalAnalyzer:
    version = "1.0.0"

    @staticmethod
    def _load_records(root: Path, manifest: PairedFinalManifest) -> list[FinalRunRecord]:
        records = []
        for relative in manifest.run_files:
            path = root / relative
            record = FinalRunRecord.model_validate_json(path.read_text(encoding="utf-8"))
            if (
                record.protocol_hash != manifest.protocol_hash
                or record.config_hash != manifest.config_hash
                or record.code_tree_hash != manifest.code_tree_hash
            ):
                raise ValueError(f"run artifact identity mismatch: {path}")
            records.append(record)
        return records

    @staticmethod
    def _group(
        records: list[FinalRunRecord],
    ) -> dict[str, dict[int, list[FinalRunRecord]]]:
        grouped: dict[str, dict[int, list[FinalRunRecord]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for record in records:
            grouped[record.method_id][record.scenario_seed].append(record)
        return {
            method: {
                seed: sorted(items, key=lambda item: item.llm_repetition)
                for seed, items in by_seed.items()
            }
            for method, by_seed in grouped.items()
        }

    @staticmethod
    def _scenario_metric(
        records: list[FinalRunRecord], metric_id: str
    ) -> float | None:
        if metric_id == "feasible_rate":
            return _majority(records)
        if metric_id == "weighted_objective":
            return _mean_or_none(
                [
                    item.weighted_objective
                    for item in records
                    if item.weighted_objective is not None
                ]
            )
        if metric_id == "candidate_set_gap_pct":
            return _mean_or_none(
                [
                    item.candidate_set_gap_pct
                    for item in records
                    if item.candidate_set_gap_pct is not None
                ]
            )
        if metric_id == "calls_to_first_feasible":
            return _mean_or_none(
                [
                    float(item.calls_to_first_feasible)
                    for item in records
                    if item.calls_to_first_feasible is not None
                ]
            )
        if metric_id == "violation_burden":
            return mean(item.violation_burden for item in records)
        if metric_id == "schema_failure_rate":
            return mean(float(item.schema_failures > 0) for item in records)
        raise ValueError(f"unsupported paired metric: {metric_id}")

    @staticmethod
    def _summary(
        method_id: str,
        by_seed: dict[int, list[FinalRunRecord]],
    ) -> MethodSummary:
        records = [item for seed in sorted(by_seed) for item in by_seed[seed]]
        objectives = [
            item.weighted_objective
            for item in records
            if item.weighted_objective is not None
        ]
        gaps = [
            item.candidate_set_gap_pct
            for item in records
            if item.candidate_set_gap_pct is not None
        ]
        return MethodSummary(
            method_id=method_id,
            run_count=len(records),
            scenario_count=len(by_seed),
            raw_feasible_rate=mean(float(item.final_feasible) for item in records),
            majority_feasible_scenario_rate=mean(
                _majority(by_seed[seed]) for seed in sorted(by_seed)
            ),
            mean_weighted_objective_feasible_runs=_mean_or_none(objectives),
            mean_candidate_set_gap_pct_feasible_runs=_mean_or_none(gaps),
            mean_violation_burden=mean(item.violation_burden for item in records),
            schema_failure_rate=mean(
                float(item.schema_failures > 0) for item in records
            ),
            mean_llm_calls=mean(float(item.llm_calls) for item in records),
            mean_evaluator_calls=mean(float(item.evaluator_calls) for item in records),
            total_billed_input_tokens=sum(item.billed_input_tokens for item in records),
            total_billed_output_tokens=sum(item.billed_output_tokens for item in records),
            total_estimated_cost_cny=sum(item.estimated_cost_cny for item in records),
        )

    def _compare_metric(
        self,
        *,
        metric_id: str,
        direction: Literal["minimize", "maximize", "report_only"],
        treatment: dict[int, list[FinalRunRecord]],
        control: dict[int, list[FinalRunRecord]],
        seed_salt: int,
    ) -> MetricComparison:
        common = sorted(set(treatment) & set(control))
        treatment_values: list[float] = []
        control_values: list[float] = []
        for seed in common:
            treatment_value = self._scenario_metric(treatment[seed], metric_id)
            control_value = self._scenario_metric(control[seed], metric_id)
            if treatment_value is None or control_value is None:
                continue
            treatment_values.append(treatment_value)
            control_values.append(control_value)
        if not treatment_values:
            return MetricComparison(
                metric_id=metric_id,
                direction=direction,
                scenario_count=0,
                treatment_mean=None,
                control_mean=None,
                treatment_minus_control=None,
                favorable_direction=None,
                confidence_interval_95=None,
                test_name="not_applicable",
                p_value_raw=None,
            )
        effect = mean(treatment_values) - mean(control_values)
        favorable = (
            effect > 0 if direction == "maximize" else effect < 0
            if direction == "minimize"
            else None
        )
        interval = _paired_bootstrap(
            treatment_values,
            control_values,
            seed=20250825 + seed_salt,
        )
        if metric_id == "feasible_rate":
            p_value, treatment_only, control_only = _exact_mcnemar(
                treatment_values,
                control_values,
            )
            test_name = "exact_mcnemar_majority_feasible"
        else:
            p_value = _wilcoxon(treatment_values, control_values)
            treatment_only = None
            control_only = None
            test_name = "paired_wilcoxon_scenario_aggregate"
        return MetricComparison(
            metric_id=metric_id,
            direction=direction,
            scenario_count=len(treatment_values),
            treatment_mean=mean(treatment_values),
            control_mean=mean(control_values),
            treatment_minus_control=effect,
            favorable_direction=favorable,
            confidence_interval_95=interval,
            test_name=test_name,
            p_value_raw=p_value,
            discordant_treatment_only=treatment_only,
            discordant_control_only=control_only,
        )

    def analyze(
        self,
        *,
        artifacts_root: Path,
        protocol: FormalExperimentProtocol,
    ) -> AnalysisReport:
        root = artifacts_root.resolve()
        manifest = PairedFinalManifest.model_validate_json(
            (root / "manifest.json").read_text(encoding="utf-8")
        )
        if manifest.protocol_hash != protocol.protocol_hash:
            raise ValueError("analysis protocol hash does not match manifest")
        records = self._load_records(root, manifest)
        grouped = self._group(records)
        stage = next(item for item in protocol.stages if item.stage_id == "paired_final")
        expected_seeds = set(stage.scenario_seeds)
        llm_methods = {
            item.method_id
            for item in protocol.methods
            if item.claim_eligible and item.live_comparable
        }
        run_count_gate = all(
            set(grouped.get(method_id, {})) == expected_seeds
            and all(
                len(grouped[method_id][seed]) == stage.llm_repetitions
                for seed in expected_seeds
            )
            for method_id in llm_methods
        )
        fingerprint_gate = all(
            record.llm_calls == 0
            or record.observed_system_fingerprints
            == [protocol.live_model_lock.system_fingerprint]
            for record in records
            if record.method_id in llm_methods
        )
        quality_gates = {
            "manifest_complete": manifest.complete,
            "run_counts_complete": run_count_gate,
            "no_infrastructure_failures": manifest.infrastructure_failure_count == 0,
            "system_fingerprint_consistent": fingerprint_gate,
            "minimum_paired_scenarios": len(expected_seeds)
            >= protocol.statistics.minimum_paired_scenarios,
        }
        metric_directions = {
            item.metric_id: item.direction for item in protocol.metrics
        }
        comparisons: list[ComparisonResult] = []
        primary_tests: dict[str, float] = {}
        pending: list[tuple[Any, list[MetricComparison], str]] = []
        for index, comparison in enumerate(protocol.comparisons):
            metrics = [
                self._compare_metric(
                    metric_id=metric_id,
                    direction=metric_directions[metric_id],
                    treatment=grouped[comparison.treatment],
                    control=grouped[comparison.control],
                    seed_salt=index * 101 + metric_index,
                )
                for metric_index, metric_id in enumerate(comparison.primary_metrics)
            ]
            primary_metric = protocol.statistics.primary_metric_by_comparison[
                comparison.comparison_id
            ]
            primary = next(item for item in metrics if item.metric_id == primary_metric)
            if primary.p_value_raw is not None:
                primary_tests[comparison.comparison_id] = primary.p_value_raw
            pending.append((comparison, metrics, primary_metric))
        adjusted = _holm_adjust(primary_tests)
        for comparison, metrics, primary_metric in pending:
            primary = next(item for item in metrics if item.metric_id == primary_metric)
            if comparison.comparison_id in adjusted:
                primary.p_value_holm = adjusted[comparison.comparison_id]
            enough = (
                primary.scenario_count >= protocol.statistics.minimum_paired_scenarios
            )
            supported = bool(
                all(quality_gates.values())
                and enough
                and primary.favorable_direction
                and primary.p_value_holm is not None
                and primary.p_value_holm < 0.05
            )
            reason = (
                f"primary {primary_metric}: effect={primary.treatment_minus_control}, "
                f"Holm p={primary.p_value_holm}, n={primary.scenario_count}"
            )
            comparisons.append(
                ComparisonResult(
                    comparison_id=comparison.comparison_id,
                    claim_id=comparison.claim_id,
                    treatment=comparison.treatment,
                    control=comparison.control,
                    primary_metric_id=primary_metric,
                    metrics=metrics,
                    claim_status="supported" if supported else "not_supported",
                    claim_reason=reason,
                )
            )
        supported_claims = [
            item.claim_id for item in comparisons if item.claim_status == "supported"
        ]
        unsupported_claims = [
            item.claim_id
            for item in comparisons
            if item.claim_status == "not_supported"
        ]
        return AnalysisReport(
            experiment_id=manifest.experiment_id,
            protocol_hash=manifest.protocol_hash,
            config_hash=manifest.config_hash,
            code_tree_hash=manifest.code_tree_hash,
            scenario_set_hash=manifest.scenario_set_hash,
            quality_gates=quality_gates,
            method_summaries=[
                self._summary(method_id, grouped[method_id])
                for method_id in sorted(grouped)
            ],
            comparisons=comparisons,
            supported_claims=supported_claims,
            unsupported_claims=unsupported_claims,
            evidence_status=(
                "claim_eligible_paired_final_evidence"
                if all(quality_gates.values())
                else "quality_gate_failed_not_claim_eligible"
            ),
        )


def render_markdown(report: AnalysisReport) -> str:
    lines = [
        "# COVER-Opt paired-final results",
        "",
        f"Evidence status: `{report.evidence_status}`",
        "",
        "## Quality gates",
        "",
    ]
    lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in report.quality_gates.items()
    )
    lines.extend(
        [
            "",
            "## Method summary",
            "",
            "| Method | Runs | Feasible | Majority scenarios | Objective | Gap % | LLM calls | Cost CNY |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in report.method_summaries:
        objective = (
            f"{item.mean_weighted_objective_feasible_runs:.4f}"
            if item.mean_weighted_objective_feasible_runs is not None
            else "NA"
        )
        gap = (
            f"{item.mean_candidate_set_gap_pct_feasible_runs:.2f}"
            if item.mean_candidate_set_gap_pct_feasible_runs is not None
            else "NA"
        )
        lines.append(
            f"| {item.method_id} | {item.run_count} | {item.raw_feasible_rate:.3f} | "
            f"{item.majority_feasible_scenario_rate:.3f} | {objective} | {gap} | "
            f"{item.mean_llm_calls:.2f} | {item.total_estimated_cost_cny:.4f} |"
        )
    lines.extend(["", "## Preregistered comparisons", ""])
    for item in report.comparisons:
        lines.append(
            f"### {item.claim_id}: {item.treatment} vs {item.control}"
        )
        lines.append("")
        lines.append(f"Status: **{item.claim_status}**. {item.claim_reason}")
        lines.append("")
        for metric in item.metrics:
            lines.append(
                f"- `{metric.metric_id}`: treatment={metric.treatment_mean}, "
                f"control={metric.control_mean}, delta={metric.treatment_minus_control}, "
                f"95% CI={metric.confidence_interval_95}, raw p={metric.p_value_raw}, "
                f"Holm p={metric.p_value_holm}, n={metric.scenario_count}."
            )
        lines.append("")
    lines.extend(
        [
            "## Evidence boundary",
            "",
            "These results apply to the frozen controlled static benchmark and the "
            "enumerated top-k route candidate set. They do not establish production "
            "satellite-network performance or generalize to paper-scale instances.",
            "",
        ]
    )
    return "\n".join(lines)

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cover_opt.config import ReplayRegressionSuiteConfig, load_yaml
from cover_opt.domain.models import ScenarioInstance
from cover_opt.heuristics.handcrafted import (
    capacity_first,
    latency_first,
    latency_no_repair,
    migration_aware,
)
from cover_opt.llm.patch_generator import LLMPatchGenerator, PatchGenerationTrace
from cover_opt.llm.replay import ReplayLLM
from cover_opt.search.controller import SearchController, SearchResult
from cover_opt.search.counterexamples import CounterexampleArchive, CounterexampleRecord


class RegressionCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    passed: bool
    checks: dict[str, bool]
    scenario_hash: str
    initial_violation_types: list[str]
    generation_trace: list[PatchGenerationTrace]
    search_result: SearchResult


class RegressionSuiteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_id: str
    passed: bool
    case_count: int = Field(ge=1)
    passed_case_count: int = Field(ge=0)
    violation_coverage: list[str]
    replay_queue: list[str]
    counterexamples: list[CounterexampleRecord]
    cases: list[RegressionCaseResult]
    runner_version: str = "1.0.0"


class RegressionReplayRunner:
    version = "1.0.0"

    @staticmethod
    def _scenario(path, overrides) -> ScenarioInstance:
        payload = load_yaml(path)
        payload.update(overrides.model_dump(mode="json", exclude_none=True))
        return ScenarioInstance.model_validate(payload)

    @staticmethod
    def _program(name: str):
        programs = {
            "latency_first": latency_first,
            "capacity_first": capacity_first,
            "migration_aware": migration_aware,
            "latency_no_repair": latency_no_repair,
        }
        return programs[name]()

    def run(self, config: ReplayRegressionSuiteConfig) -> RegressionSuiteResult:
        aggregate = CounterexampleArchive()
        case_results: list[RegressionCaseResult] = []
        coverage: set[str] = set()

        for case in config.cases:
            scenario = self._scenario(case.scenario_path, case.scenario_overrides)
            generator = LLMPatchGenerator.from_template_file(
                llm=ReplayLLM.from_file(case.replay_file),
                path=config.prompt_path,
            )
            result = SearchController().run(
                scenario=scenario,
                initial_program=self._program(case.initial_heuristic),
                generator=generator,
                budgets=case.budgets,
            )
            initial_types = sorted(
                {
                    violation.violation_type.value
                    for violation in result.records[0].verification.violations
                }
            )
            coverage.update(initial_types)
            final_feasible = bool(
                result.best_candidate_id
                and any(
                    record.candidate_id == result.best_candidate_id
                    and record.verification.feasible
                    for record in result.records
                )
            )
            generation_status = (
                generator.events[0].status if generator.events else "backend_error"
            )
            checks = {
                "stop_reason": result.stop_reason == case.expectation.stop_reason,
                "final_feasible": final_feasible == case.expectation.final_feasible,
                "initial_violation_coverage": set(
                    case.expectation.initial_violation_types
                ).issubset(initial_types),
                "generation_status": (
                    generation_status == case.expectation.generation_status
                ),
            }
            for record in result.counterexamples:
                aggregate.merge(record)
            case_results.append(
                RegressionCaseResult(
                    case_id=case.case_id,
                    passed=all(checks.values()),
                    checks=checks,
                    scenario_hash=scenario.stable_hash,
                    initial_violation_types=initial_types,
                    generation_trace=generator.events,
                    search_result=result,
                )
            )

        replay_queue = [
            record.counterexample_id for record in aggregate.ranked_for_replay()
        ]
        passed_count = sum(case.passed for case in case_results)
        return RegressionSuiteResult(
            suite_id=config.suite_id,
            passed=passed_count == len(case_results),
            case_count=len(case_results),
            passed_case_count=passed_count,
            violation_coverage=sorted(coverage),
            replay_queue=replay_queue,
            counterexamples=aggregate.records,
            cases=case_results,
        )

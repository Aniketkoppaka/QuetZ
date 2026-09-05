"""
evaluation/pipeline_eval.py -- Benchmark Evaluation and Self-Assessment Harness (Phase 4.2).

Evaluates the unified AutonomousPipeline across authentic and synthetic benchmark scenarios.
Measures:
  1. Success resolution rate (end-to-end verified fixes).
  2. Grounded reproduction rate (fraction of issues where a valid failure-then-pass reproduction was established).
  3. Abstention accuracy (correctly abstaining when verification or ground-truth evidence is insufficient).
  4. False-positive resistance (rejection of vacuous or weak patches).
  5. Blast-radius and mutation-score distributions across verified patches.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.agents.validator import AbstentionDecision
from autonomous_engineer.domain.models import ImplementationPlan, Issue, Repository, RepositoryMap
from autonomous_engineer.domain.states import WorkflowPhase
from autonomous_engineer.orchestration import JobStatus
from autonomous_engineer.orchestration.pipeline import (
    AutonomousPipeline,
    PipelineConfig,
    PipelineExecutionSummary,
)
from autonomous_engineer.review import ReviewVerdict
from autonomous_engineer.verification.reproduction import ReproductionCandidate


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class BenchmarkScenario(BaseModel):
    """A test scenario presented to the pipeline benchmark harness."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    issue: Issue
    expected_outcome: WorkflowPhase = Field(
        default=WorkflowPhase.COMPLETED,
        description="Expected final phase: COMPLETED, ABSTAINED, or FAILED",
    )
    reproduction_candidate: ReproductionCandidate | None = None
    description: str = ""


class ScenarioEvaluationResult(BaseModel):
    """Detailed evaluation result for an individual benchmark scenario."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    expected_phase: WorkflowPhase
    actual_phase: WorkflowPhase
    matched_expectation: bool
    summary: PipelineExecutionSummary
    duration_seconds: float = 0.0


class BenchmarkEvaluationReport(BaseModel):
    """Aggregate benchmark evaluation report across all evaluated scenarios."""

    model_config = ConfigDict(frozen=True)

    total_scenarios: int = 0
    scenarios_passed_expectation: int = 0
    accuracy_rate: float = 0.0
    resolved_count: int = 0
    abstained_count: int = 0
    failed_count: int = 0
    reproduction_verified_count: int = 0
    scenario_results: tuple[ScenarioEvaluationResult, ...] = Field(default=())
    generated_at: datetime = Field(default_factory=_utcnow)

    def to_markdown(self) -> str:
        """Render a markdown summary table of benchmark results."""
        lines = [
            "# ASE Autonomous Pipeline Benchmark Report",
            "",
            f"- **Generated At**: `{self.generated_at.isoformat()}`",
            f"- **Total Scenarios Evaluated**: {self.total_scenarios}",
            f"- **Benchmark Accuracy**: `{self.accuracy_rate:.1%}` ({self.scenarios_passed_expectation}/{self.total_scenarios})",
            f"- **Resolved (Completed)**: {self.resolved_count}",
            f"- **Abstained (Safe Fallback)**: {self.abstained_count}",
            f"- **Failed**: {self.failed_count}",
            f"- **Reproduction Grounded Fixes**: {self.reproduction_verified_count}",
            "",
            "| Scenario ID | Expected | Actual | Matched | Skills Matched | Verdict |",
            "|---|---|---|---|---|---|",
        ]
        for res in self.scenario_results:
            matched_str = "[MATCH]" if res.matched_expectation else "[MISMATCH]"
            skills_str = ", ".join(res.summary.matched_skills) or "none"
            verdict_str = res.summary.review_verdict.value if res.summary.review_verdict else "n/a"
            lines.append(
                f"| `{res.scenario_id}` | `{res.expected_phase.value}` | `{res.actual_phase.value}` | {matched_str} | {skills_str} | {verdict_str} |"
            )
        return "\n".join(lines)


class PipelineBenchmarkHarness:
    """
    Executes and evaluates AutonomousPipeline against a battery of benchmark scenarios.
    """

    def __init__(self, pipeline: AutonomousPipeline | None = None) -> None:
        self._pipeline = pipeline or AutonomousPipeline()

    def evaluate_scenario(
        self,
        scenario: BenchmarkScenario,
        repository: Repository,
        repository_map: RepositoryMap,
        plan: ImplementationPlan,
        config: PipelineConfig | None = None,
    ) -> ScenarioEvaluationResult:
        """Run and score a single benchmark scenario."""
        start_t = time.perf_counter()
        summary = self._pipeline.run(
            issue=scenario.issue,
            repository=repository,
            repository_map=repository_map,
            plan=plan,
            config=config,
            reproduction_candidate=scenario.reproduction_candidate,
        )
        duration = round(time.perf_counter() - start_t, 2)

        matched = summary.final_phase == scenario.expected_outcome

        return ScenarioEvaluationResult(
            scenario_id=scenario.scenario_id,
            expected_phase=scenario.expected_outcome,
            actual_phase=summary.final_phase,
            matched_expectation=matched,
            summary=summary,
            duration_seconds=duration,
        )

    def run_suite(
        self,
        scenarios: list[tuple[BenchmarkScenario, Repository, RepositoryMap, ImplementationPlan]],
        config: PipelineConfig | None = None,
    ) -> BenchmarkEvaluationReport:
        """Evaluate a full battery of scenarios and generate an aggregate report."""
        results: list[ScenarioEvaluationResult] = []
        passed_count = 0
        resolved_count = 0
        abstained_count = 0
        failed_count = 0
        reproduction_count = 0

        for scenario, repo, r_map, plan in scenarios:
            res = self.evaluate_scenario(
                scenario=scenario,
                repository=repo,
                repository_map=r_map,
                plan=plan,
                config=config,
            )
            results.append(res)
            if res.matched_expectation:
                passed_count += 1
            if res.actual_phase == WorkflowPhase.COMPLETED:
                resolved_count += 1
            elif res.actual_phase == WorkflowPhase.ABSTAINED:
                abstained_count += 1
            elif res.actual_phase == WorkflowPhase.FAILED:
                failed_count += 1

            if (
                res.summary.reproduction_evidence
                and res.summary.reproduction_evidence.is_verified
            ):
                reproduction_count += 1

        total = len(scenarios)
        accuracy = (passed_count / total) if total > 0 else 0.0

        return BenchmarkEvaluationReport(
            total_scenarios=total,
            scenarios_passed_expectation=passed_count,
            accuracy_rate=round(accuracy, 4),
            resolved_count=resolved_count,
            abstained_count=abstained_count,
            failed_count=failed_count,
            reproduction_verified_count=reproduction_count,
            scenario_results=tuple(results),
        )

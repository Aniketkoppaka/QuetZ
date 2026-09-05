"""
tests/unit/test_pipeline_eval.py -- Tests for Phase 4.2 Pipeline Benchmark Harness.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autonomous_engineer.domain.models import (
    ImplementationPlan,
    ImplementationStep,
    Issue,
    Repository,
    RepositoryMap,
    StepOperation,
)
from autonomous_engineer.domain.states import WorkflowPhase
from autonomous_engineer.evaluation.pipeline_eval import (
    BenchmarkEvaluationReport,
    BenchmarkScenario,
    PipelineBenchmarkHarness,
    ScenarioEvaluationResult,
)
from autonomous_engineer.orchestration import JobStatus
from autonomous_engineer.orchestration.pipeline import (
    AutonomousPipeline,
    PipelineExecutionSummary,
)
from autonomous_engineer.review import ReviewVerdict


def _make_scenario(scenario_id: str, expected: WorkflowPhase = WorkflowPhase.COMPLETED) -> BenchmarkScenario:
    issue = Issue(
        id=f"owner/repo#{scenario_id}",
        title=f"Bug fix task {scenario_id}",
        body="Details on the issue description.",
        repository_url="https://github.com/owner/repo",
    )
    return BenchmarkScenario(
        scenario_id=scenario_id,
        issue=issue,
        expected_outcome=expected,
    )


def _make_repo(tmp_path: Path) -> Repository:
    return Repository(
        url="https://github.com/owner/repo",
        workspace_path=tmp_path,
        commit_sha="123456abcdef",
    )


def _make_repo_map() -> RepositoryMap:
    return RepositoryMap(
        repository_url="https://github.com/owner/repo",
        commit_sha="123456abcdef",
        file_count=2,
        python_file_count=2,
    )


def _make_plan() -> ImplementationPlan:
    step = ImplementationStep(
        step_id="step-1",
        target_file="module.py",
        operation=StepOperation.MODIFY_SYMBOL,
        description="Fix logic",
    )
    return ImplementationPlan(
        plan_id="plan-1",
        summary="Fix calculation",
        rationale="Fix logic",
        steps=(step,),
    )


class TestPipelineBenchmarkHarness:
    def test_evaluate_scenario_matches_expected_outcome(self, tmp_path: Path):
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = PipelineExecutionSummary(
            run_id="run-1",
            issue_id="owner/repo#sc-1",
            final_phase=WorkflowPhase.COMPLETED,
            status=JobStatus.COMPLETED,
            review_verdict=ReviewVerdict.APPROVED,
            matched_skills=("python_bug_fix",),
        )

        harness = PipelineBenchmarkHarness(pipeline=mock_pipeline)
        scenario = _make_scenario("sc-1", expected=WorkflowPhase.COMPLETED)

        result = harness.evaluate_scenario(
            scenario=scenario,
            repository=_make_repo(tmp_path),
            repository_map=_make_repo_map(),
            plan=_make_plan(),
        )

        assert result.matched_expectation is True
        assert result.actual_phase == WorkflowPhase.COMPLETED
        assert result.expected_phase == WorkflowPhase.COMPLETED

    def test_run_suite_computes_accurate_aggregate_metrics(self, tmp_path: Path):
        mock_pipeline = MagicMock()
        # 1st scenario: Completed (expected Completed -> match)
        # 2nd scenario: Abstained (expected Abstained -> match)
        mock_pipeline.run.side_effect = [
            PipelineExecutionSummary(
                run_id="run-1",
                issue_id="owner/repo#sc-1",
                final_phase=WorkflowPhase.COMPLETED,
                status=JobStatus.COMPLETED,
                review_verdict=ReviewVerdict.APPROVED,
            ),
            PipelineExecutionSummary(
                run_id="run-2",
                issue_id="owner/repo#sc-2",
                final_phase=WorkflowPhase.ABSTAINED,
                status=JobStatus.ABSTAINED,
            ),
        ]

        harness = PipelineBenchmarkHarness(pipeline=mock_pipeline)

        scenarios = [
            (
                _make_scenario("sc-1", expected=WorkflowPhase.COMPLETED),
                _make_repo(tmp_path),
                _make_repo_map(),
                _make_plan(),
            ),
            (
                _make_scenario("sc-2", expected=WorkflowPhase.ABSTAINED),
                _make_repo(tmp_path),
                _make_repo_map(),
                _make_plan(),
            ),
        ]

        report = harness.run_suite(scenarios)

        assert report.total_scenarios == 2
        assert report.scenarios_passed_expectation == 2
        assert report.accuracy_rate == 1.0
        assert report.resolved_count == 1
        assert report.abstained_count == 1
        assert report.failed_count == 0

    def test_markdown_report_formatting(self):
        summary = PipelineExecutionSummary(
            run_id="run-1",
            issue_id="owner/repo#sc-1",
            final_phase=WorkflowPhase.COMPLETED,
            status=JobStatus.COMPLETED,
            matched_skills=("python_bug_fix",),
            review_verdict=ReviewVerdict.APPROVED,
        )
        res = ScenarioEvaluationResult(
            scenario_id="sc-1",
            expected_phase=WorkflowPhase.COMPLETED,
            actual_phase=WorkflowPhase.COMPLETED,
            matched_expectation=True,
            summary=summary,
        )
        report = BenchmarkEvaluationReport(
            total_scenarios=1,
            scenarios_passed_expectation=1,
            accuracy_rate=1.0,
            resolved_count=1,
            abstained_count=0,
            failed_count=0,
            scenario_results=(res,),
        )
        md = report.to_markdown()
        assert "ASE Autonomous Pipeline Benchmark Report" in md
        assert "100.0%" in md
        assert "| `sc-1` |" in md
        assert "[MATCH]" in md

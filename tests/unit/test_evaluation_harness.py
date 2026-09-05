"""
tests/unit/test_evaluation_harness.py

Comprehensive tests for Milestone 7: Real-world benchmark dataset models,
ground-truth separation, failure taxonomy precedence rules, metrics calculation,
ablation configuration, and end-to-end evaluation runner.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
import pytest

from autonomous_engineer.agents import (
    LLMMessage,
    MockLLMClient,
    PlannerInput,
)
from autonomous_engineer.domain.models import (
    ClassSymbol,
    FunctionSymbol,
    ImplementationPlan,
    ImplementationStep,
    Issue,
    PythonModuleMap,
    RepositoryMap,
    StepOperation,
)
from autonomous_engineer.evaluation import (
    BENCHMARK_REGISTRY,
    BenchmarkIssueStatus,
    BenchmarkRunResult,
    EndToEndReport,
    EvaluationAblationConfig,
    EvaluationFailureCategory,
    GroundTruthValidationStatus,
    LiveLLMStatus,
    RealBenchmarkIssue,
    RealBenchmarkRunner,
)
from autonomous_engineer.execution import (
    ExecutionEngine,
    ExecutionPolicy,
    ExecutionRequest,
    ExecutionStatus,
    PlanExecutionResult,
)
from autonomous_engineer.retrieval import ContextRetriever


# ---------------------------------------------------------------------------
# Fixtures for Evaluation Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_benchmark_issue() -> RealBenchmarkIssue:
    """Fixture representing a verified benchmark issue."""
    return RealBenchmarkIssue(
        case_id="REAL-SAMPLE-01",
        repository_name="pallets/click",
        repository_url="https://github.com/pallets/click",
        parent_commit_sha="1111111111111111111111111111111111111111",
        reference_commit_sha="2222222222222222222222222222222222222222",
        issue_title="Click Option default value validation bug",
        issue_body="Option parameter default value is not validated when prompt is active in click/core.py.",
        expected_affected_files=("src/click/core.py",),
        expected_test_command="pytest tests/test_options.py",
        category="exact_identifier",
        status=BenchmarkIssueStatus.GROUND_TRUTH_VERIFIED,
        ground_truth_status=GroundTruthValidationStatus.GROUND_TRUTH_VERIFIED,
        reference_patch_summary="Validate default value in Option.prompt.",
    )


@pytest.fixture
def sample_benchmark_workspace() -> Path:
    """Isolated temporary workspace for benchmark testing."""
    tmp = Path(tempfile.mkdtemp(prefix="agy_bench_ws_"))
    src_dir = tmp / "src" / "click"
    src_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = tmp / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    core_file = src_dir / "core.py"
    core_file.write_text(
        "class Option:\n    def prompt(self, value: str) -> str:\n        return value\n",
        encoding="utf-8",
    )

    test_file = tests_dir / "test_options.py"
    test_file.write_text("def test_prompt(): pass\n", encoding="utf-8")

    yield tmp

    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def sample_benchmark_repo_map(sample_benchmark_workspace: Path) -> RepositoryMap:
    """Structural map for the benchmark workspace."""
    mod = PythonModuleMap(
        file_path="src/click/core.py",
        module_name="src.click.core",
        line_count=10,
        classes=(
            ClassSymbol(
                name="Option",
                qualified_name="Option",
                line_number=1,
                end_line_number=5,
                methods=(
                    FunctionSymbol(
                        name="prompt",
                        qualified_name="Option.prompt",
                        line_number=2,
                        end_line_number=4,
                    ),
                ),
            ),
        ),
    )
    return RepositoryMap(
        repository_url="https://github.com/pallets/click",
        commit_sha="1111111111111111111111111111111111111111",
        file_count=2,
        python_file_count=2,
        python_modules=(mod,),
    )


# ---------------------------------------------------------------------------
# 1. Dataset Model & Ground-Truth Separation Tests
# ---------------------------------------------------------------------------


class TestBenchmarkDataset:
    def test_benchmark_registry_integrity(self) -> None:
        assert len(BENCHMARK_REGISTRY) >= 8
        verified = [i for i in BENCHMARK_REGISTRY if i.status in (BenchmarkIssueStatus.VERIFIED, BenchmarkIssueStatus.GROUND_TRUTH_VERIFIED)]
        excluded = [i for i in BENCHMARK_REGISTRY if i.status == BenchmarkIssueStatus.EXCLUDED]

        assert len(verified) >= 6
        assert len(excluded) >= 6

        # Verify all excluded entries have explicit reasons documented
        for exc in excluded:
            assert exc.exclusion_reason is not None
            assert len(exc.exclusion_reason) > 10

    def test_ground_truth_isolation_invariant(self, sample_benchmark_issue: RealBenchmarkIssue) -> None:
        """
        Verify that to_planner_issue() strips all evaluator ground-truth metadata.
        """
        planner_issue: Issue = sample_benchmark_issue.to_planner_issue()

        assert planner_issue.id == sample_benchmark_issue.case_id
        assert planner_issue.title == sample_benchmark_issue.issue_title
        assert planner_issue.body == sample_benchmark_issue.issue_body

        issue_dict = planner_issue.model_dump()
        assert "expected_affected_files" not in issue_dict
        assert "reference_commit_sha" not in issue_dict
        assert "reference_patch_summary" not in issue_dict
        assert "expected_test_command" not in issue_dict


# ---------------------------------------------------------------------------
# 2. Failure Taxonomy & Precedence Tests
# ---------------------------------------------------------------------------


class TestFailureTaxonomyPrecedence:
    def test_environment_failure_on_missing_workspace(
        self,
        sample_benchmark_issue: RealBenchmarkIssue,
        sample_benchmark_repo_map: RepositoryMap,
    ) -> None:
        runner = RealBenchmarkRunner()
        mock_llm = MockLLMClient(responses=['{"summary": "Test"}'])

        res = runner.run_case(
            issue=sample_benchmark_issue,
            workspace_path=Path("/non/existent/workspace/xyz"),
            repo_map=sample_benchmark_repo_map,
            llm_client=mock_llm,
        )

        assert res.failure_category == EvaluationFailureCategory.ENVIRONMENT_FAILURE
        assert res.is_resolved is False

    def test_retrieval_failure_when_target_file_not_retrieved(
        self,
        sample_benchmark_issue: RealBenchmarkIssue,
        sample_benchmark_workspace: Path,
    ) -> None:
        runner = RealBenchmarkRunner()
        mock_llm = MockLLMClient(responses=['{"summary": "Test"}'])

        # Empty repo map where core.py is not listed
        empty_map = RepositoryMap(
            repository_url="https://github.com/pallets/click",
            commit_sha="111",
            file_count=0,
            python_file_count=0,
        )

        res = runner.run_case(
            issue=sample_benchmark_issue,
            workspace_path=sample_benchmark_workspace,
            repo_map=empty_map,
            llm_client=mock_llm,
        )

        assert res.failure_category == EvaluationFailureCategory.RETRIEVAL_FAILURE
        assert res.is_resolved is False

    def test_planning_failure_when_planner_hallucinates(
        self,
        sample_benchmark_issue: RealBenchmarkIssue,
        sample_benchmark_workspace: Path,
        sample_benchmark_repo_map: RepositoryMap,
    ) -> None:
        runner = RealBenchmarkRunner()
        # Mock planner repeatedly emitting hallucinated target files
        bad_plan = json.dumps({
            "summary": "Bad",
            "rationale": "Bad",
            "steps": [{"step_id": "1", "target_file": "src/click/hallucinated.py", "description": "d"}],
        })
        mock_llm = MockLLMClient(responses=[bad_plan, bad_plan, bad_plan])

        res = runner.run_case(
            issue=sample_benchmark_issue,
            workspace_path=sample_benchmark_workspace,
            repo_map=sample_benchmark_repo_map,
            llm_client=mock_llm,
        )

        assert res.failure_category == EvaluationFailureCategory.PLANNING_FAILURE
        assert res.is_resolved is False

    def test_execution_representation_failure_when_search_content_mismatches(
        self,
        sample_benchmark_issue: RealBenchmarkIssue,
        sample_benchmark_workspace: Path,
        sample_benchmark_repo_map: RepositoryMap,
    ) -> None:
        runner = RealBenchmarkRunner()
        # Valid plan schema, but search_content is not found in file on disk
        mismatch_plan = json.dumps({
            "summary": "Mismatch",
            "rationale": "Mismatch",
            "steps": [
                {
                    "step_id": "step-1",
                    "operation": "modify_symbol",
                    "target_file": "src/click/core.py",
                    "target_symbol": "Option.prompt",
                    "description": "Edit",
                    "search_content": "NON_EXISTENT_STRING_TO_REPLACE",
                    "replace_content": "NEW_STRING",
                    "evidence": {"source": "repository_map", "reference_path": "src/click/core.py"},
                }
            ],
        })
        mock_llm = MockLLMClient(responses=[mismatch_plan])

        res = runner.run_case(
            issue=sample_benchmark_issue,
            workspace_path=sample_benchmark_workspace,
            repo_map=sample_benchmark_repo_map,
            llm_client=mock_llm,
        )

        assert res.failure_category == EvaluationFailureCategory.EXEC_REPRESENTATION_FAILURE
        assert res.is_resolved is False

    def test_issue_resolved_on_successful_execution_and_verification(
        self,
        sample_benchmark_issue: RealBenchmarkIssue,
        sample_benchmark_workspace: Path,
        sample_benchmark_repo_map: RepositoryMap,
    ) -> None:
        runner = RealBenchmarkRunner()
        valid_plan = json.dumps({
            "summary": "Valid plan",
            "rationale": "Valid plan",
            "steps": [
                {
                    "step_id": "step-1",
                    "operation": "modify_symbol",
                    "target_file": "src/click/core.py",
                    "target_symbol": "Option.prompt",
                    "description": "Edit",
                    "search_content": "return value",
                    "replace_content": "return value or 'default'",
                    "evidence": {"source": "repository_map", "reference_path": "src/click/core.py"},
                }
            ],
        })
        mock_llm = MockLLMClient(responses=[valid_plan])

        res = runner.run_case(
            issue=sample_benchmark_issue,
            workspace_path=sample_benchmark_workspace,
            repo_map=sample_benchmark_repo_map,
            llm_client=mock_llm,
        )

        assert res.failure_category == EvaluationFailureCategory.ISSUE_RESOLVED
        assert res.is_resolved is True
        assert res.retrieval_metrics["recall_at_3"] == 1.0


# ---------------------------------------------------------------------------
# 3. Benchmark Suite & Aggregate Report Tests
# ---------------------------------------------------------------------------


class TestBenchmarkSuiteEvaluation:
    def test_evaluate_suite_computes_aggregate_metrics(
        self,
        sample_benchmark_issue: RealBenchmarkIssue,
        sample_benchmark_workspace: Path,
        sample_benchmark_repo_map: RepositoryMap,
    ) -> None:
        runner = RealBenchmarkRunner()
        valid_plan = json.dumps({
            "summary": "Valid",
            "rationale": "Valid",
            "steps": [
                {
                    "step_id": "step-1",
                    "operation": "modify_symbol",
                    "target_file": "src/click/core.py",
                    "target_symbol": "Option.prompt",
                    "description": "Edit",
                    "search_content": "return value",
                    "replace_content": "return value or 'default'",
                    "evidence": {"source": "repository_map", "reference_path": "src/click/core.py"},
                }
            ],
        })
        mock_llm = MockLLMClient(responses=[valid_plan])

        report: EndToEndReport = runner.evaluate_suite(
            issues=(sample_benchmark_issue,),
            workspace_map={sample_benchmark_issue.case_id: sample_benchmark_workspace},
            repo_map_cache={sample_benchmark_issue.case_id: sample_benchmark_repo_map},
            llm_client=mock_llm,
        )

        assert report.verified_cases_evaluated == 1
        assert report.resolved_cases == 1
        assert report.resolved_rate == 1.0
        assert report.mean_target_file_recall_at_3 == 1.0
        assert report.mean_mrr == 1.0
        assert report.live_llm_status == LiveLLMStatus.MOCK_MODE

    def test_deterministic_dict_serialization(
        self,
        sample_benchmark_issue: RealBenchmarkIssue,
        sample_benchmark_workspace: Path,
        sample_benchmark_repo_map: RepositoryMap,
    ) -> None:
        runner = RealBenchmarkRunner()
        mock_llm = MockLLMClient(responses=['{"summary": "Test"}'])

        report = runner.evaluate_suite(
            issues=(sample_benchmark_issue,),
            workspace_map={sample_benchmark_issue.case_id: sample_benchmark_workspace},
            repo_map_cache={sample_benchmark_issue.case_id: sample_benchmark_repo_map},
            llm_client=mock_llm,
        )

        d = report.deterministic_dict()
        assert "verified_cases_evaluated" in d
        assert "resolved_rate" in d
        # Verify duration_seconds was stripped from all case results
        for cr in d["case_results"]:
            assert "duration_seconds" not in cr
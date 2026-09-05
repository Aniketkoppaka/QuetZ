"""
tests/unit/test_ground_truth_validation.py

Comprehensive tests for Milestone 9.5: Evaluator-side ground-truth dataset validation,
reproduction test verification, reference fix validation, and isolation invariants.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
import pytest

from autonomous_engineer.evaluation import (
    BENCHMARK_REGISTRY,
    BenchmarkIssueStatus,
    GroundTruthValidationReport,
    GroundTruthValidationResult,
    GroundTruthValidationStatus,
    GroundTruthValidator,
    RealBenchmarkIssue,
)


@pytest.fixture
def sample_gt_issue() -> RealBenchmarkIssue:
    """Fixture representing a benchmark issue for ground-truth validation."""
    return RealBenchmarkIssue(
        case_id="REAL-CLICK-01",
        repository_name="pallets/click",
        repository_url="https://github.com/pallets/click",
        parent_commit_sha="a2e482348b6f3c1a8d052d9b23b123456789abcd",
        reference_commit_sha="f8c123456789abcdef0123456789abcdef012345",
        issue_title="Option prompt parameter validation failure on empty string input",
        issue_body="When click.prompt is called with default='' and type=str, empty input raises BadParameter.",
        expected_affected_files=("src/click/core.py",),
        expected_test_command="pytest tests/test_options.py",
        category="exact_identifier",
        status=BenchmarkIssueStatus.VERIFIED,
        reference_patch_summary="Update Option.prompt to handle empty default value correctly.",
    )


@pytest.fixture
def temp_gt_workspace() -> Path:
    """Isolated temporary workspace."""
    tmp = Path(tempfile.mkdtemp(prefix="agy_gt_ws_"))
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 1. Metadata Consistency Tests
# ---------------------------------------------------------------------------


class TestMetadataConsistency:
    def test_detects_identical_parent_and_reference_sha(self) -> None:
        issue = RealBenchmarkIssue(
            case_id="BAD-SHA-01",
            repository_name="test/repo",
            repository_url="https://github.com/test/repo",
            parent_commit_sha="1111111111111111111111111111111111111111",
            reference_commit_sha="1111111111111111111111111111111111111111",
            issue_title="Bug title",
            issue_body="Bug body",
            expected_affected_files=("file.py",),
            category="test",
        )
        validator = GroundTruthValidator()
        res = validator.validate_case(issue)
        assert res.validation_status == GroundTruthValidationStatus.METADATA_INCONSISTENCY
        assert "identical" in res.notes

    def test_detects_missing_workspace(self, sample_gt_issue: RealBenchmarkIssue) -> None:
        validator = GroundTruthValidator()
        res = validator.validate_case(sample_gt_issue, workspace_path=Path("/non/existent/path/xyz"))
        assert res.validation_status == GroundTruthValidationStatus.REPOSITORY_ACQUISITION_FAILURE


# ---------------------------------------------------------------------------
# 2. Reproduction and Reference Fix Classification Tests
# ---------------------------------------------------------------------------


class TestReproductionAndFixClassification:
    def test_bug_not_reproduced_when_parent_test_passes(
        self, sample_gt_issue: RealBenchmarkIssue, temp_gt_workspace: Path
    ) -> None:
        validator = GroundTruthValidator()
        # Mock runner where test passes (returncode 0) on parent
        mock_runner = lambda ws, cmd: (0, "=== 1 passed in 0.01s ===")

        res = validator.validate_case(
            sample_gt_issue,
            workspace_path=temp_gt_workspace,
            test_runner_fn=mock_runner,
        )
        assert res.validation_status == GroundTruthValidationStatus.BUG_NOT_REPRODUCED
        assert res.expected_bug_reproduced is False
        assert res.parent_test_passed is True

    def test_dependency_environment_failure_detected(
        self, sample_gt_issue: RealBenchmarkIssue, temp_gt_workspace: Path
    ) -> None:
        validator = GroundTruthValidator()
        # Mock runner failing due to ModuleNotFoundError
        mock_runner = lambda ws, cmd: (1, "Traceback: ModuleNotFoundError: No module named 'click'")

        res = validator.validate_case(
            sample_gt_issue,
            workspace_path=temp_gt_workspace,
            test_runner_fn=mock_runner,
        )
        assert res.validation_status == GroundTruthValidationStatus.DEPENDENCY_ENVIRONMENT_FAILURE
        assert res.expected_bug_reproduced is False

    def test_reference_fix_failure_detected(
        self, sample_gt_issue: RealBenchmarkIssue, temp_gt_workspace: Path
    ) -> None:
        validator = GroundTruthValidator()
        # Parent fails as expected (assertion error)
        mock_runner = lambda ws, cmd: (1, "AssertionError: BadParameter not expected")
        # Reference fix applicator fails
        mock_fix = lambda ws: (False, "Patch failed to apply cleanly to src/click/core.py")

        res = validator.validate_case(
            sample_gt_issue,
            workspace_path=temp_gt_workspace,
            apply_reference_fn=mock_fix,
            test_runner_fn=mock_runner,
        )
        assert res.validation_status == GroundTruthValidationStatus.REFERENCE_FIX_FAILURE
        assert res.expected_bug_reproduced is True

    def test_reference_test_failure_detected(
        self, sample_gt_issue: RealBenchmarkIssue, temp_gt_workspace: Path
    ) -> None:
        validator = GroundTruthValidator()
        # Test always fails (exit code 1) even after reference fix
        mock_runner = lambda ws, cmd: (1, "AssertionError: Still broken")
        mock_fix = lambda ws: (True, None)

        res = validator.validate_case(
            sample_gt_issue,
            workspace_path=temp_gt_workspace,
            apply_reference_fn=mock_fix,
            test_runner_fn=mock_runner,
        )
        assert res.validation_status == GroundTruthValidationStatus.REFERENCE_TEST_FAILURE
        assert res.reference_test_passed is False

    def test_full_successful_validation(
        self, sample_gt_issue: RealBenchmarkIssue, temp_gt_workspace: Path
    ) -> None:
        validator = GroundTruthValidator()
        state = {"fixed": False}

        def mock_runner(ws: Path, cmd: str) -> tuple[int, str]:
            if state["fixed"]:
                return 0, "=== 1 passed in 0.02s ==="
            return 1, "AssertionError: Default empty string failed validation"

        def mock_fix(ws: Path) -> tuple[bool, str | None]:
            state["fixed"] = True
            return True, None

        res = validator.validate_case(
            sample_gt_issue,
            workspace_path=temp_gt_workspace,
            apply_reference_fn=mock_fix,
            test_runner_fn=mock_runner,
        )
        assert res.validation_status == GroundTruthValidationStatus.VALIDATED
        assert res.expected_bug_reproduced is True
        assert res.reference_test_passed is True
        assert res.expected_affected_files == ("src/click/core.py",)


# ---------------------------------------------------------------------------
# 3. Report & Serialization Invariants
# ---------------------------------------------------------------------------


class TestGroundTruthReportAndSerialization:
    def test_validate_suite_aggregates_results(
        self, sample_gt_issue: RealBenchmarkIssue, temp_gt_workspace: Path
    ) -> None:
        validator = GroundTruthValidator()
        mock_runner = lambda ws, cmd: (0, "passed")

        report: GroundTruthValidationReport = validator.validate_suite(
            issues=(sample_gt_issue,),
            workspace_map={sample_gt_issue.case_id: temp_gt_workspace},
            test_runner_map={sample_gt_issue.case_id: mock_runner},
        )
        assert report.total_cases == 1
        assert "bug_not_reproduced" in report.status_distribution

    def test_deterministic_dict_serialization(self, sample_gt_issue: RealBenchmarkIssue) -> None:
        validator = GroundTruthValidator()
        report = validator.validate_suite(issues=(sample_gt_issue,))
        d = report.deterministic_dict()

        assert "total_cases" in d
        assert "status_distribution" in d
        for cr in d["case_results"]:
            assert "duration_seconds" not in cr
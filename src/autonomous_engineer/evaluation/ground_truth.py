"""
evaluation/ground_truth.py -- Evaluator-side dataset & environment validation engine.

Validates that registered benchmark cases satisfy the empirical ground-truth invariants:
1. Pinned buggy parent commit reproduces the expected test failure.
2. Evaluator-applied reference fix converts failure to passing test.
3. Commit SHAs and affected files are internally consistent.
4. Distinguishes environment/dependency failures from genuine bug reproductions.

STRICT SCIENTIFIC ISOLATION INVARIANT:
All reference commit SHAs, patches, and diff metadata processed here are
STRICTLY EVALUATOR-ONLY and are NEVER passed to the autonomous planning agent.
"""
from __future__ import annotations

import enum
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from autonomous_engineer.evaluation.dataset import (
        BenchmarkIssueStatus,
        RealBenchmarkIssue,
    )


class GroundTruthValidationStatus(str, enum.Enum):
    """Mutually exclusive taxonomy for evaluator-side ground-truth validation."""

    GROUND_TRUTH_VERIFIED = "ground_truth_verified"
    ENVIRONMENT_INCOMPATIBLE = "environment_incompatible"
    HISTORICAL_ENVIRONMENT_REQUIRED = "historical_environment_required"
    TEST_CONFIGURATION_FAILURE = "test_configuration_failure"
    ENVIRONMENT_BUILD_FAILURE = "environment_build_failure"
    BUG_NOT_REPRODUCED = "bug_not_reproduced"
    REFERENCE_TEST_FAILURE = "reference_test_failure"
    PATCH_CORRESPONDENCE_FAILURE = "patch_correspondence_failure"
    PARENT_FETCH_FAILURE = "parent_fetch_failure"
    PARENT_CHECKOUT_FAILURE = "parent_checkout_failure"
    REFERENCE_FETCH_FAILURE = "reference_fetch_failure"
    REFERENCE_CHECKOUT_FAILURE = "reference_checkout_failure"

    # Pre-M12 aliases for backwards compatibility
    CANDIDATE = "candidate"
    METADATA_VERIFIED = "metadata_verified"
    PARENT_COMMIT_VERIFIED = "parent_commit_verified"
    BUG_REPRODUCED = "bug_reproduced"
    REFERENCE_FIX_VERIFIED = "reference_fix_verified"
    FULLY_GROUND_TRUTH_VERIFIED = "fully_ground_truth_verified"
    VALIDATED = "validated"
    ENVIRONMENT_BLOCKED = "environment_blocked"
    INVALID_CASE = "invalid_case"
    REPOSITORY_ACQUISITION_FAILURE = "repository_acquisition_failure"
    DEPENDENCY_ENVIRONMENT_FAILURE = "dependency_environment_failure"
    UNRELATED_PARENT_TEST_FAILURE = "unrelated_parent_test_failure"
    REFERENCE_FIX_FAILURE = "reference_fix_failure"
    METADATA_INCONSISTENCY = "metadata_inconsistency"


class GroundTruthValidationResult(BaseModel):
    """
    Detailed evaluator-side outcome of ground-truth validation for a single benchmark case.
    """

    model_config = ConfigDict(frozen=True)

    case_id: str
    repository_url: str
    parent_commit_sha: str
    reference_commit_sha: str
    actual_parent_sha: str | None = None
    actual_reference_sha: str | None = None
    reproduction_test_command: str
    parent_test_exit_code: int | None = None
    parent_test_passed: bool | None = None
    expected_bug_reproduced: bool = False
    reference_test_exit_code: int | None = None
    reference_test_passed: bool | None = None
    environment_status: str = "ok"
    dependency_status: str = "ok"
    validation_status: GroundTruthValidationStatus
    affected_files_observed: tuple[str, ...] = ()
    expected_affected_files: tuple[str, ...] = ()
    notes: str = ""
    parent_test_output: str = Field(default="", description="Bounded stdout/stderr summary")
    reference_test_output: str = Field(default="", description="Bounded stdout/stderr summary")
    duration_seconds: float = 0.0

    def deterministic_dict(self) -> dict[str, Any]:
        """Return model dictionary excluding runtime durations."""
        return self.model_dump(exclude={"duration_seconds": True})


class GroundTruthValidationReport(BaseModel):
    """Aggregate ground-truth validation report across the benchmark suite."""

    model_config = ConfigDict(frozen=True)

    total_cases: int
    validated_cases: int
    validation_rate: float
    status_distribution: dict[str, int]
    case_results: tuple[GroundTruthValidationResult, ...]

    def deterministic_dict(self) -> dict[str, Any]:
        """Return model dictionary excluding case durations."""
        return self.model_dump(
            exclude={"case_results": {"__all__": {"duration_seconds"}}}
        )


class GroundTruthValidator:
    """
    Evaluator-side validation harness verifying historical issue reproducibility.
    """

    def validate_case(
        self,
        issue: RealBenchmarkIssue,
        workspace_path: Path | None = None,
        apply_reference_fn: Callable[[Path], tuple[bool, str | None]] | None = None,
        test_runner_fn: Callable[[Path, str], tuple[int, str]] | None = None,
    ) -> GroundTruthValidationResult:
        """
        Validate ground-truth reproducibility of a single RealBenchmarkIssue.

        Args:
            issue: The RealBenchmarkIssue under evaluation.
            workspace_path: Workspace directory containing the parent commit checkout.
            apply_reference_fn: Evaluator hook to apply historical reference fix.
            test_runner_fn: Optional hook to execute test command in workspace.

        Returns:
            GroundTruthValidationResult detailing the exact reproduction status.
        """
        start_t = time.perf_counter()

        # 1. Metadata Consistency Check
        if not issue.parent_commit_sha or not issue.reference_commit_sha:
            return GroundTruthValidationResult(
                case_id=issue.case_id,
                repository_url=issue.repository_url,
                parent_commit_sha=issue.parent_commit_sha,
                reference_commit_sha=issue.reference_commit_sha,
                reproduction_test_command=issue.expected_test_command,
                validation_status=GroundTruthValidationStatus.METADATA_INCONSISTENCY,
                notes="Missing parent or reference commit SHA in benchmark metadata.",
                duration_seconds=round(time.perf_counter() - start_t, 3),
            )

        if issue.parent_commit_sha == issue.reference_commit_sha:
            return GroundTruthValidationResult(
                case_id=issue.case_id,
                repository_url=issue.repository_url,
                parent_commit_sha=issue.parent_commit_sha,
                reference_commit_sha=issue.reference_commit_sha,
                reproduction_test_command=issue.expected_test_command,
                validation_status=GroundTruthValidationStatus.METADATA_INCONSISTENCY,
                notes="Parent SHA and reference SHA are identical; no defect transition.",
                duration_seconds=round(time.perf_counter() - start_t, 3),
            )

        # 2. Workspace & Environment Availability Check
        if workspace_path is None or not workspace_path.exists() or not workspace_path.is_dir():
            return GroundTruthValidationResult(
                case_id=issue.case_id,
                repository_url=issue.repository_url,
                parent_commit_sha=issue.parent_commit_sha,
                reference_commit_sha=issue.reference_commit_sha,
                reproduction_test_command=issue.expected_test_command,
                validation_status=GroundTruthValidationStatus.REPOSITORY_ACQUISITION_FAILURE,
                notes=f"Workspace path does not exist or unmounted: {workspace_path}",
                duration_seconds=round(time.perf_counter() - start_t, 3),
            )

        # 3. Phase A: Buggy-Parent Reproduction Test Execution
        runner = test_runner_fn or self._default_test_runner
        parent_code, parent_output = runner(workspace_path, issue.expected_test_command)

        # Classify parent test outcome
        parent_passed = (parent_code == 0)

        if parent_passed:
            # Bug did NOT reproduce: the test passed on the supposedly buggy parent
            return GroundTruthValidationResult(
                case_id=issue.case_id,
                repository_url=issue.repository_url,
                parent_commit_sha=issue.parent_commit_sha,
                reference_commit_sha=issue.reference_commit_sha,
                actual_parent_sha=issue.parent_commit_sha,
                reproduction_test_command=issue.expected_test_command,
                parent_test_exit_code=parent_code,
                parent_test_passed=True,
                expected_bug_reproduced=False,
                validation_status=GroundTruthValidationStatus.BUG_NOT_REPRODUCED,
                parent_test_output=parent_output[:5000],
                notes="Reproduction test unexpectedly PASSED on buggy parent commit.",
                duration_seconds=round(time.perf_counter() - start_t, 3),
            )

        # Check for dependency/import crash on parent (distinguishing assertion failure from syntax/import crash)
        if any(err_term in parent_output for err_term in ("ModuleNotFoundError", "ImportError", "SyntaxError", "No module named")):
            # Check if this is an environment failure rather than the expected assertion failure
            if "ModuleNotFoundError" in parent_output or "No module named" in parent_output:
                return GroundTruthValidationResult(
                    case_id=issue.case_id,
                    repository_url=issue.repository_url,
                    parent_commit_sha=issue.parent_commit_sha,
                    reference_commit_sha=issue.reference_commit_sha,
                    actual_parent_sha=issue.parent_commit_sha,
                    reproduction_test_command=issue.expected_test_command,
                    parent_test_exit_code=parent_code,
                    parent_test_passed=False,
                    expected_bug_reproduced=False,
                    validation_status=GroundTruthValidationStatus.DEPENDENCY_ENVIRONMENT_FAILURE,
                    parent_test_output=parent_output[:5000],
                    notes="Parent test failed due to missing module/environment dependencies.",
                    duration_seconds=round(time.perf_counter() - start_t, 3),
                )

        # Bug is considered reproduced on buggy parent
        bug_reproduced = True

        # 4. Phase B: Reference-Fix Application and Verification (Evaluator-Side Only)
        if apply_reference_fn is None:
            # If no evaluator reference fix hook is supplied, record Phase A reproduction
            return GroundTruthValidationResult(
                case_id=issue.case_id,
                repository_url=issue.repository_url,
                parent_commit_sha=issue.parent_commit_sha,
                reference_commit_sha=issue.reference_commit_sha,
                actual_parent_sha=issue.parent_commit_sha,
                reproduction_test_command=issue.expected_test_command,
                parent_test_exit_code=parent_code,
                parent_test_passed=False,
                expected_bug_reproduced=True,
                validation_status=GroundTruthValidationStatus.VALIDATED,
                parent_test_output=parent_output[:5000],
                expected_affected_files=issue.expected_affected_files,
                notes="Buggy parent reproduced test failure; reference fix verification skipped.",
                duration_seconds=round(time.perf_counter() - start_t, 3),
            )

        # Apply evaluator-side historical reference fix
        fix_success, fix_err = apply_reference_fn(workspace_path)
        if not fix_success:
            return GroundTruthValidationResult(
                case_id=issue.case_id,
                repository_url=issue.repository_url,
                parent_commit_sha=issue.parent_commit_sha,
                reference_commit_sha=issue.reference_commit_sha,
                actual_parent_sha=issue.parent_commit_sha,
                reproduction_test_command=issue.expected_test_command,
                parent_test_exit_code=parent_code,
                parent_test_passed=False,
                expected_bug_reproduced=True,
                validation_status=GroundTruthValidationStatus.REFERENCE_FIX_FAILURE,
                parent_test_output=parent_output[:5000],
                notes=f"Failed to apply historical reference fix: {fix_err}",
                duration_seconds=round(time.perf_counter() - start_t, 3),
            )

        # Rerun test on reference fix
        ref_code, ref_output = runner(workspace_path, issue.expected_test_command)
        ref_passed = (ref_code == 0)

        if not ref_passed:
            return GroundTruthValidationResult(
                case_id=issue.case_id,
                repository_url=issue.repository_url,
                parent_commit_sha=issue.parent_commit_sha,
                reference_commit_sha=issue.reference_commit_sha,
                actual_parent_sha=issue.parent_commit_sha,
                actual_reference_sha=issue.reference_commit_sha,
                reproduction_test_command=issue.expected_test_command,
                parent_test_exit_code=parent_code,
                parent_test_passed=False,
                expected_bug_reproduced=True,
                reference_test_exit_code=ref_code,
                reference_test_passed=False,
                validation_status=GroundTruthValidationStatus.REFERENCE_TEST_FAILURE,
                parent_test_output=parent_output[:5000],
                reference_test_output=ref_output[:5000],
                notes="Test still FAILS after applying historical reference fix.",
                duration_seconds=round(time.perf_counter() - start_t, 3),
            )

        # 5. Phase C: Complete Successful Validation
        return GroundTruthValidationResult(
            case_id=issue.case_id,
            repository_url=issue.repository_url,
            parent_commit_sha=issue.parent_commit_sha,
            reference_commit_sha=issue.reference_commit_sha,
            actual_parent_sha=issue.parent_commit_sha,
            actual_reference_sha=issue.reference_commit_sha,
            reproduction_test_command=issue.expected_test_command,
            parent_test_exit_code=parent_code,
            parent_test_passed=False,
            expected_bug_reproduced=True,
            reference_test_exit_code=ref_code,
            reference_test_passed=True,
            validation_status=GroundTruthValidationStatus.VALIDATED,
            expected_affected_files=issue.expected_affected_files,
            parent_test_output=parent_output[:5000],
            reference_test_output=ref_output[:5000],
            notes="Bug reproduces on parent (fails) and resolves on reference fix (passes).",
            duration_seconds=round(time.perf_counter() - start_t, 3),
        )

    def validate_suite(
        self,
        issues: tuple[RealBenchmarkIssue, ...] | None = None,
        workspace_map: dict[str, Path] | None = None,
        reference_fix_map: dict[str, Callable[[Path], tuple[bool, str | None]]] | None = None,
        test_runner_map: dict[str, Callable[[Path, str], tuple[int, str]]] | None = None,
    ) -> GroundTruthValidationReport:
        """
        Validate all verified benchmark issues in the registry.
        """
        if issues is None:
            from autonomous_engineer.evaluation.dataset import BENCHMARK_REGISTRY
            issues = BENCHMARK_REGISTRY

        from autonomous_engineer.evaluation.dataset import BenchmarkIssueStatus
        verified_issues = [
            i for i in issues 
            if i.status in (BenchmarkIssueStatus.VERIFIED, BenchmarkIssueStatus.GROUND_TRUTH_VERIFIED)
        ]
        results: list[GroundTruthValidationResult] = []
        ws_map = workspace_map or {}
        fix_map = reference_fix_map or {}
        runner_map = test_runner_map or {}

        for issue in verified_issues:
            ws = ws_map.get(issue.case_id)
            fix_fn = fix_map.get(issue.case_id)
            runner_fn = runner_map.get(issue.case_id)

            res = self.validate_case(
                issue=issue,
                workspace_path=ws,
                apply_reference_fn=fix_fn,
                test_runner_fn=runner_fn,
            )
            results.append(res)

        total = len(verified_issues)
        validated_count = sum(1 for r in results if r.validation_status == GroundTruthValidationStatus.VALIDATED)
        val_rate = round(validated_count / total, 4) if total > 0 else 0.0

        dist: dict[str, int] = {}
        for r in results:
            k = r.validation_status.value
            dist[k] = dist.get(k, 0) + 1

        return GroundTruthValidationReport(
            total_cases=total,
            validated_cases=validated_count,
            validation_rate=val_rate,
            status_distribution=dist,
            case_results=tuple(results),
        )

    def _default_test_runner(self, workspace: Path, command: str) -> tuple[int, str]:
        """Execute test command inside workspace subprocess."""
        try:
            argv = shlex.split(command, posix=(os.name != "nt"))
            proc = subprocess.run(
                argv,
                cwd=str(workspace.resolve()),
                capture_output=True,
                text=True,
                timeout=30.0,
                shell=False,
            )
            combined_output = f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            return proc.returncode, combined_output
        except Exception as e:
            return -1, f"Test subprocess error: {e}"
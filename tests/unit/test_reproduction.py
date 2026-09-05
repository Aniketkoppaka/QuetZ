"""
tests/unit/test_reproduction.py -- Tests for Phase 3.2 Reproduction-Before-Fix Engine.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autonomous_engineer.execution.models import (
    ExecutionPolicy,
    VerificationResult,
    VerificationType,
)
from autonomous_engineer.verification.reproduction import (
    ReproductionCandidate,
    ReproductionEvidence,
    ReproductionStatus,
    ReproductionVerifier,
)


def _make_result(
    passed: bool,
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    target: str = "pytest",
) -> VerificationResult:
    return VerificationResult(
        verification_type=VerificationType.SUBPROCESS_TEST,
        target=target,
        passed=passed,
        exit_code=exit_code if not passed and exit_code == 0 else exit_code,
        stdout=stdout,
        stderr=stderr,
        error_message=None if passed else f"Process exited with {exit_code}",
    )


class TestReproductionCandidate:
    def test_build_command_line_default(self):
        candidate = ReproductionCandidate(test_command="pytest")
        assert candidate.build_command_line() == "pytest"

    def test_build_command_line_with_file_and_filter(self):
        candidate = ReproductionCandidate(
            test_command="pytest",
            target_test_file="tests/test_calculator.py",
            target_filter="test_division_by_zero",
        )
        assert candidate.build_command_line() == "pytest tests/test_calculator.py -k test_division_by_zero"

    def test_candidate_frozen(self):
        candidate = ReproductionCandidate(test_command="pytest")
        with pytest.raises(Exception):
            candidate.test_command = "python"  # type: ignore[misc]


class TestReproductionVerifier:
    def test_confirmed_reproduction_flow(self):
        """Failed pre-patch, passed post-patch -> CONFIRMED_REPRODUCED."""
        verifier = ReproductionVerifier()
        candidate = ReproductionCandidate(
            test_command="pytest",
            target_filter="test_crash",
            expected_failure_pattern=r"ZeroDivisionError",
        )

        pre_res = _make_result(
            passed=False,
            exit_code=1,
            stdout="FAILED test_crash - ZeroDivisionError: division by zero",
        )
        post_res = _make_result(passed=True, exit_code=0, stdout="PASSED")

        evidence = verifier.evaluate_reproduction(pre_res, post_res, candidate)

        assert evidence.status == ReproductionStatus.CONFIRMED_REPRODUCED
        assert evidence.is_verified is True
        assert evidence.pre_patch_failed_as_expected is True
        assert evidence.post_patch_passed_cleanly is True
        assert evidence.failure_pattern_matched is True
        assert "Confirmed Fail-Then-Pass" in evidence.diagnostics

    def test_vacuous_pre_patch_fails_reproduction(self):
        """Passed pre-patch -> VACUOUS_PRE_PATCH (cannot prove bug existed)."""
        verifier = ReproductionVerifier()
        candidate = ReproductionCandidate(test_command="pytest")

        pre_res = _make_result(passed=True, exit_code=0, stdout="1 passed")
        post_res = _make_result(passed=True, exit_code=0, stdout="1 passed")

        evidence = verifier.evaluate_reproduction(pre_res, post_res, candidate)

        assert evidence.status == ReproductionStatus.VACUOUS_PRE_PATCH
        assert evidence.is_verified is False
        assert evidence.pre_patch_failed_as_expected is False
        assert "does not reproduce the issue" in evidence.diagnostics

    def test_still_failing_post_patch(self):
        """Failed pre-patch and still failed post-patch -> STILL_FAILING_POST_PATCH."""
        verifier = ReproductionVerifier()
        candidate = ReproductionCandidate(test_command="pytest")

        pre_res = _make_result(passed=False, exit_code=1, stderr="AssertionError")
        post_res = _make_result(passed=False, exit_code=1, stderr="AssertionError")

        evidence = verifier.evaluate_reproduction(pre_res, post_res, candidate)

        assert evidence.status == ReproductionStatus.STILL_FAILING_POST_PATCH
        assert evidence.is_verified is False
        assert evidence.pre_patch_failed_as_expected is True
        assert evidence.post_patch_passed_cleanly is False
        assert "Test FAILED after patch applied" in evidence.diagnostics

    def test_failure_pattern_regex_mismatch(self):
        """Pre-patch fails with wrong error -> pattern_matched is False."""
        verifier = ReproductionVerifier()
        candidate = ReproductionCandidate(
            test_command="pytest",
            expected_failure_pattern=r"CustomValidationError",
        )

        pre_res = _make_result(
            passed=False,
            exit_code=1,
            stderr="ImportError: No module named foo",
        )
        post_res = _make_result(passed=True, exit_code=0)

        evidence = verifier.evaluate_reproduction(pre_res, post_res, candidate)

        assert evidence.status == ReproductionStatus.CONFIRMED_REPRODUCED
        assert evidence.failure_pattern_matched is False

    def test_run_pre_and_post_patch_invokes_underlying_verifier(self, tmp_path: Path):
        mock_exec_verifier = MagicMock()
        mock_exec_verifier.verify_tests.side_effect = [
            _make_result(passed=False, exit_code=1),
            _make_result(passed=True, exit_code=0),
        ]

        verifier = ReproductionVerifier(verifier=mock_exec_verifier)
        candidate = ReproductionCandidate(
            test_command="pytest",
            target_test_file="tests/test_foo.py",
        )
        policy = ExecutionPolicy()

        pre_res = verifier.run_pre_patch(tmp_path, candidate, policy)
        post_res = verifier.run_post_patch(tmp_path, candidate, policy)

        assert pre_res.passed is False
        assert post_res.passed is True
        assert mock_exec_verifier.verify_tests.call_count == 2
        mock_exec_verifier.verify_tests.assert_called_with(
            workspace=tmp_path,
            policy=policy,
            command_override="pytest tests/test_foo.py",
        )

    def test_to_markdown_renders_cleanly(self):
        candidate = ReproductionCandidate(test_command="pytest -k test_foo")
        evidence = ReproductionEvidence(
            candidate=candidate,
            status=ReproductionStatus.CONFIRMED_REPRODUCED,
            pre_patch_failed_as_expected=True,
            post_patch_passed_cleanly=True,
            failure_pattern_matched=True,
            diagnostics="All good",
        )
        md = evidence.to_markdown()
        assert "Reproduction-Before-Fix Evidence" in md
        assert "CONFIRMED_REPRODUCED" in md
        assert "All good" in md

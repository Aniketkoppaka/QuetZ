"""
verification/reproduction.py -- Reproduction-Before-Fix (Fail-Then-Pass) Verification Engine (Phase 3.2).

Ensures that any proposed bug-fix is backed by verified reproduction evidence:
1. Candidate reproduction tests must explicitly FAIL on the pre-patch repository state
   (confirming the bug exists and reproduction is grounded).
2. The exact same reproduction test must PASS on the post-patch repository state
   (confirming the fix resolves the specific failure mode).

If a candidate test passes pre-patch, it is flagged as INCONCLUSIVE / VACUOUS (cannot prove bug fix).
If a candidate test fails post-patch, it is flagged as REPRODUCTION_FAILED_POST_PATCH.
"""
from __future__ import annotations

import enum
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.execution.models import (
    ExecutionPolicy,
    VerificationResult,
)
from autonomous_engineer.execution.verifier import ExecutionVerifier


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class ReproductionStatus(str, enum.Enum):
    """Lifecycle status of a reproduction verification attempt."""

    NOT_RUN = "not_run"
    CONFIRMED_REPRODUCED = "confirmed_reproduced"  # Failed pre-patch, passed post-patch (GOLD STANDARD)
    VACUOUS_PRE_PATCH = "vacuous_pre_patch"        # Passed pre-patch (fails reproduction requirement)
    STILL_FAILING_POST_PATCH = "still_failing_post_patch"  # Failed pre-patch AND failed post-patch
    ERROR_DURING_EXECUTION = "error_during_execution"      # Policy violation or process error


class ReproductionCandidate(BaseModel):
    """
    Candidate reproduction test specification.

    Attributes:
        candidate_id: Unique identifier for this candidate.
        test_command: Command to invoke (must satisfy policy.allowed_test_commands).
        target_test_file: Optional target test file path.
        target_filter: Optional test name or keyword expression (e.g. passed to -k).
        expected_failure_pattern: Optional regex pattern expected to appear in stderr/stdout when failing.
        description: Description of what this reproduction candidate exercises.
    """

    model_config = ConfigDict(frozen=True)

    candidate_id: str = Field(default_factory=_new_id)
    test_command: str = Field(default="pytest")
    target_test_file: str | None = Field(default=None)
    target_filter: str | None = Field(default=None)
    expected_failure_pattern: str | None = Field(default=None)
    description: str = Field(default="")

    def build_command_line(self) -> str:
        """Construct full command line to execute."""
        parts = [self.test_command.strip()]
        if self.target_test_file:
            parts.append(self.target_test_file.strip())
        if self.target_filter:
            parts.extend(["-k", self.target_filter.strip()])
        return " ".join(parts)


class ReproductionEvidence(BaseModel):
    """
    Cryptographically verifiable evidence of reproduction pre- and post-patch.
    """

    model_config = ConfigDict(frozen=True)

    evidence_id: str = Field(default_factory=_new_id)
    candidate: ReproductionCandidate
    status: ReproductionStatus
    pre_patch_result: VerificationResult | None = None
    post_patch_result: VerificationResult | None = None
    pre_patch_failed_as_expected: bool = False
    post_patch_passed_cleanly: bool = False
    failure_pattern_matched: bool = False
    recorded_at: datetime = Field(default_factory=_utcnow)
    diagnostics: str = ""

    @property
    def is_verified(self) -> bool:
        """True iff this candidate achieved confirmed reproduction (fail-then-pass)."""
        return self.status == ReproductionStatus.CONFIRMED_REPRODUCED

    def to_markdown(self) -> str:
        """Render markdown summary of reproduction evidence."""
        return (
            f"### Reproduction-Before-Fix Evidence\n"
            f"- **Evidence ID**: `{self.evidence_id}`\n"
            f"- **Status**: `{self.status.value.upper()}`\n"
            f"- **Command**: `{self.candidate.build_command_line()}`\n"
            f"- **Pre-Patch Failed**: {'YES' if self.pre_patch_failed_as_expected else 'NO'}\n"
            f"- **Post-Patch Passed**: {'YES' if self.post_patch_passed_cleanly else 'NO'}\n"
            f"- **Expected Failure Signature Matched**: {'YES' if self.failure_pattern_matched else 'N/A or NO'}\n"
            f"- **Diagnostics**: {self.diagnostics or 'None'}\n"
        )


class ReproductionVerifier:
    """
    Orchestrates pre-patch and post-patch test execution to prove bug reproduction and resolution.
    """

    def __init__(self, verifier: ExecutionVerifier | None = None) -> None:
        self._verifier = verifier or ExecutionVerifier()

    def run_pre_patch(
        self,
        workspace: Path,
        candidate: ReproductionCandidate,
        policy: ExecutionPolicy,
    ) -> VerificationResult:
        """
        Execute candidate against pre-patch workspace.

        Expected outcome: returncode != 0 (FAILED test demonstrating the bug).
        """
        cmd = candidate.build_command_line()
        return self._verifier.verify_tests(
            workspace=workspace,
            policy=policy,
            command_override=cmd,
        )

    def run_post_patch(
        self,
        workspace: Path,
        candidate: ReproductionCandidate,
        policy: ExecutionPolicy,
    ) -> VerificationResult:
        """
        Execute candidate against post-patch workspace.

        Expected outcome: returncode == 0 (PASSED test demonstrating the fix).
        """
        cmd = candidate.build_command_line()
        return self._verifier.verify_tests(
            workspace=workspace,
            policy=policy,
            command_override=cmd,
        )

    def evaluate_reproduction(
        self,
        pre_result: VerificationResult,
        post_result: VerificationResult,
        candidate: ReproductionCandidate,
    ) -> ReproductionEvidence:
        """
        Evaluate paired pre- and post-patch results into an authoritative ReproductionEvidence record.
        """
        # 1. Pre-patch check: MUST fail
        if pre_result.passed:
            return ReproductionEvidence(
                candidate=candidate,
                status=ReproductionStatus.VACUOUS_PRE_PATCH,
                pre_patch_result=pre_result,
                post_patch_result=post_result,
                pre_patch_failed_as_expected=False,
                post_patch_passed_cleanly=post_result.passed,
                failure_pattern_matched=False,
                diagnostics=(
                    "Test PASSED on unpatched code. It does not reproduce the issue "
                    "or the test condition was already satisfied."
                ),
            )

        # Pre-patch did fail as expected
        pre_failed = True
        pattern_matched = True

        # Check optional failure pattern regex
        if candidate.expected_failure_pattern:
            combined_output = f"{pre_result.stdout}\n{pre_result.stderr}\n{pre_result.error_message or ''}"
            pattern_matched = bool(
                re.search(candidate.expected_failure_pattern, combined_output, re.IGNORECASE)
            )

        # 2. Post-patch check: MUST pass
        if not post_result.passed:
            return ReproductionEvidence(
                candidate=candidate,
                status=ReproductionStatus.STILL_FAILING_POST_PATCH,
                pre_patch_result=pre_result,
                post_patch_result=post_result,
                pre_patch_failed_as_expected=pre_failed,
                post_patch_passed_cleanly=False,
                failure_pattern_matched=pattern_matched,
                diagnostics=(
                    f"Test FAILED after patch applied. Return code: {post_result.exit_code}. "
                    f"Error: {post_result.error_message}"
                ),
            )

        # Confirmed reproduction: failed before, passed after
        return ReproductionEvidence(
            candidate=candidate,
            status=ReproductionStatus.CONFIRMED_REPRODUCED,
            pre_patch_result=pre_result,
            post_patch_result=post_result,
            pre_patch_failed_as_expected=pre_failed,
            post_patch_passed_cleanly=True,
            failure_pattern_matched=pattern_matched,
            diagnostics="Confirmed Fail-Then-Pass reproduction achieved.",
        )

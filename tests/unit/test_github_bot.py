"""
tests/unit/test_github_bot.py -- Tests for GitHub PR Bot & Automated Delivery.
"""
from __future__ import annotations

import pytest

from autonomous_engineer.domain.models import Issue, PatchSummary, FinalResult
from autonomous_engineer.domain.states import WorkflowPhase
from autonomous_engineer.execution.models import (
    Capability,
    ExecutionPolicy,
    ExecutionStatus,
    VerificationCertificate,
)
from autonomous_engineer.github import GitHubPRBot, PullRequestPayload
from autonomous_engineer.orchestration import JobStatus
from autonomous_engineer.orchestration.pipeline import PipelineExecutionSummary
from autonomous_engineer.review import ReviewVerdict


def _make_issue() -> Issue:
    return Issue(
        id="owner/repo#42",
        title="Fix NullPointerException in processor",
        body="Crashes with TypeError on None inputs.",
        repository_url="https://github.com/owner/repo",
        base_branch="main",
    )


def _make_certificate() -> VerificationCertificate:
    return VerificationCertificate(
        plan_id="plan-42",
        issue_id="owner/repo#42",
        status=ExecutionStatus.COMPLETED,
        static_ast_passed=True,
        test_verification_passed=True,
        rolled_back=False,
        evidence_hash="0123456789abcdef",
        confidence_score=0.98,
    )


def _make_summary(phase: WorkflowPhase = WorkflowPhase.COMPLETED) -> PipelineExecutionSummary:
    patch_summary = PatchSummary(files_modified=("src/processor.py",))
    final_res = FinalResult(
        task_id="task-42",
        issue_id="owner/repo#42",
        resolved=True,
        total_repair_attempts=0,
        patch_summary=patch_summary,
    )
    return PipelineExecutionSummary(
        run_id="run-42",
        issue_id="owner/repo#42",
        final_phase=phase,
        status=JobStatus.COMPLETED if phase == WorkflowPhase.COMPLETED else JobStatus.FAILED,
        certificate=_make_certificate() if phase == WorkflowPhase.COMPLETED else None,
        final_result=final_res if phase == WorkflowPhase.COMPLETED else None,
        review_verdict=ReviewVerdict.APPROVED,
        matched_skills=("python_bug_fix",),
        duration_seconds=12.5,
    )


class TestGitHubPRBot:
    def test_generates_authorized_pr_payload(self):
        bot = GitHubPRBot()
        issue = _make_issue()
        summary = _make_summary()
        policy = ExecutionPolicy(
            granted_capabilities=(
                Capability.CAP_READ_REPO,
                Capability.CAP_WRITE_SOURCE,
                Capability.CAP_OPEN_PR,
            )
        )

        payload = bot.generate_pr_payload(issue, summary, policy)

        assert payload.issue_id == "owner/repo#42"
        assert payload.base_branch == "main"
        assert "ase/fix-owner-repo-42" in payload.branch_name
        assert "[ASE] Fix: Fix NullPointerException in processor" in payload.title
        assert "Verification Certificate" in payload.commit_message
        assert "0123456789abcdef" in payload.body
        assert "src/processor.py" in payload.files_changed

    def test_rejects_when_cap_open_pr_not_granted(self):
        bot = GitHubPRBot()
        issue = _make_issue()
        summary = _make_summary()
        # Default policy does NOT grant CAP_OPEN_PR (fail closed)
        policy = ExecutionPolicy()

        with pytest.raises(PermissionError, match="cap_open_pr"):
            bot.generate_pr_payload(issue, summary, policy)

    def test_rejects_when_run_is_not_completed(self):
        bot = GitHubPRBot()
        issue = _make_issue()
        summary = _make_summary(phase=WorkflowPhase.FAILED)
        policy = ExecutionPolicy(
            granted_capabilities=(Capability.CAP_OPEN_PR,)
        )

        with pytest.raises(ValueError, match="Cannot generate PR for uncompleted run"):
            bot.generate_pr_payload(issue, summary, policy)

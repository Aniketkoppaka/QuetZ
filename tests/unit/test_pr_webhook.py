"""
Unit tests for PR bot enhancements & webhook dispatcher in github/pr_bot.py.
"""
from unittest.mock import MagicMock, patch

from autonomous_engineer.config.policy_engine import PolicyCheckResult
from autonomous_engineer.domain.models import Issue, ReviewVerdict
from autonomous_engineer.domain.states import WorkflowPhase
from autonomous_engineer.execution.models import (
    Capability,
    ExecutionPolicy,
    ExecutionStatus,
    VerificationCertificate,
)
from autonomous_engineer.github.pr_bot import GitHubPRBot, WebhookDispatcher, WebhookNotification
from autonomous_engineer.orchestration import JobStatus
from autonomous_engineer.orchestration.pipeline import PipelineExecutionSummary
from autonomous_engineer.verification.security_scan import SecurityFinding, SecurityScanReport, SecuritySeverity


def test_webhook_dispatcher_dispatch():
    dispatcher = WebhookDispatcher(webhook_url="https://hooks.slack.com/services/test/123")
    notif = WebhookNotification(
        event_type="PR_CREATED",
        issue_id="ISSUE-42",
        title="Fix division by zero",
        status="COMPLETED",
        certificate_id="cert-1234",
        confidence_score=0.95,
    )
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        success = dispatcher.dispatch(notif)
        assert success is True
        mock_urlopen.assert_called_once()


def test_pr_bot_includes_sast_and_policy_reports():
    issue = Issue(
        id="ISSUE-99",
        title="Fix memory leak",
        body="leaks in loop",
        repository_url="https://github.com/org/repo",
        base_branch="main",
    )
    cert = VerificationCertificate(
        certificate_id="cert-9999",
        plan_id="plan-123",
        issue_id="ISSUE-99",
        status=ExecutionStatus.COMPLETED,
        confidence_score=0.95,
        static_ast_passed=True,
        test_verification_passed=True,
        rolled_back=False,
        evidence_hash="sha256:abc1234",
    )
    summary = PipelineExecutionSummary(
        run_id="run-99",
        issue_id="ISSUE-99",
        final_phase=WorkflowPhase.COMPLETED,
        status=JobStatus.COMPLETED,
        certificate=cert,
        review_verdict=ReviewVerdict.APPROVED,
    )
    policy = ExecutionPolicy(
        granted_capabilities=(
            Capability.CAP_READ_REPO,
            Capability.CAP_WRITE_SOURCE,
            Capability.CAP_OPEN_PR,
        )
    )

    sast_report = SecurityScanReport(
        scanned_files=("src/leak.py",),
        findings=(),
        passed=True,
    )
    policy_report = PolicyCheckResult(passed=True, violations=())

    bot = GitHubPRBot()
    payload = bot.generate_pr_payload(
        issue=issue,
        summary=summary,
        policy=policy,
        sast_report=sast_report,
        policy_report=policy_report,
    )

    assert "SAST Security Audit: PASS" in payload.body
    assert "Enterprise Policy & Governance: PASS" in payload.body
    assert "cert-9999" in payload.commit_message


def test_submit_pull_request_success():
    bot = GitHubPRBot()
    payload = MagicMock(
        title="Fix issue 99",
        body="PR body",
        branch_name="ase/fix-99",
        base_branch="main",
    )
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 201
        mock_resp.read.return_value = b'{"html_url": "https://github.com/org/repo/pull/1", "number": 1, "node_id": "PR_kwDO"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = bot.submit_pull_request(
            repo_owner="org",
            repo_name="repo",
            payload=payload,
            github_token="ghp_testtoken12345",
        )
        assert res["success"] is True
        assert res["html_url"] == "https://github.com/org/repo/pull/1"
        assert res["number"] == 1


def test_submit_pull_request_missing_token():
    import pytest
    bot = GitHubPRBot()
    payload = MagicMock()
    with pytest.raises(ValueError, match="GITHUB_TOKEN is required"):
        bot.submit_pull_request(repo_owner="org", repo_name="repo", payload=payload, github_token="")
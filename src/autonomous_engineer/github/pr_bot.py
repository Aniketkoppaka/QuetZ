"""
github/pr_bot.py -- GitHub PR Bot & Automated Pull Request Delivery for ASE.

Transforms a successful PipelineExecutionSummary into a formal, production-grade Pull Request:
1. Validates that the pipeline finished in WorkflowPhase.COMPLETED with a valid VerificationCertificate.
2. Checks that CAP_OPEN_PR capability was granted in the ExecutionPolicy (fail-closed security).
3. Generates rich, auditable PR bodies containing:
    - Verbatim reproduction status & diagnostic logs (RED -> GREEN flow)
    - Cryptographic VerificationCertificate with evidence digest
    - Semantic Change-Impact blast radius analysis
    - Mutation assertion test strength score
    - In-pipeline SAST Security Audit & Policy Compliance results
    - File change summary table
4. Formats clean git commit messages and branch naming conventions (e.g. `ase/fix-issue-101`).
5. Supports Webhook notifications (Slack / Discord / Webhooks) on completion or abstention.
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.domain.models import Issue
from autonomous_engineer.domain.states import WorkflowPhase
from autonomous_engineer.execution.models import Capability, ExecutionPolicy
from autonomous_engineer.orchestration.pipeline import PipelineExecutionSummary


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class PullRequestPayload(BaseModel):
    """
    Immutable representation of an automated Pull Request ready for GitHub API submission.
    """

    model_config = ConfigDict(frozen=True)

    branch_name: str
    base_branch: str
    title: str
    body: str
    commit_message: str
    issue_id: str
    certificate_id: str | None = None
    files_changed: tuple[str, ...] = Field(default=())
    created_at: datetime = Field(default_factory=_utcnow)


class WebhookNotification(BaseModel):
    """Webhook payload for notifying team channels of pipeline events."""

    model_config = ConfigDict(frozen=True)

    event_type: str  # "PR_CREATED", "RUN_ABSTAINED", "RUN_FAILED"
    issue_id: str
    title: str
    status: str
    certificate_id: str | None = None
    confidence_score: float | None = None
    timestamp: datetime = Field(default_factory=_utcnow)


class WebhookDispatcher:
    """Dispatches pipeline notifications to configured HTTP endpoints."""

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url

    def dispatch(self, notification: WebhookNotification) -> bool:
        if not self.webhook_url:
            return False

        payload = json.dumps({
            "text": f"🤖 *QuetZ Alert*: `{notification.event_type}` for Issue `{notification.issue_id}`\n"
                    f"*{notification.title}*\n"
                    f"Status: `{notification.status}` | Confidence: `{notification.confidence_score or 'N/A'}`\n"
                    f"Certificate: `{notification.certificate_id or 'None'}`",
            "event": notification.model_dump(mode="json"),
        }).encode("utf-8")

        req = urllib.request.Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "QuetZ-PR-Bot/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False


class GitHubPRBot:
    """
    Constructs and authorizes GitHub PR deliveries for autonomous pipeline runs.
    """

    def __init__(self, webhook_dispatcher: WebhookDispatcher | None = None) -> None:
        self.webhook_dispatcher = webhook_dispatcher or WebhookDispatcher()

    def generate_pr_payload(
        self,
        issue: Issue,
        summary: PipelineExecutionSummary,
        policy: ExecutionPolicy,
        branch_prefix: str = "ase/fix",
        sast_report: Any | None = None,
        policy_report: Any | None = None,
    ) -> PullRequestPayload:
        """
        Generate an authorized PullRequestPayload from a completed pipeline run.
        """
        # Security Gate: Capability authorization
        if Capability.CAP_OPEN_PR not in policy.granted_capabilities:
            raise PermissionError(
                f"Policy does not grant {Capability.CAP_OPEN_PR.value}. Cannot open pull request."
            )

        # Integrity Gate: Must be completed with certificate
        if summary.final_phase != WorkflowPhase.COMPLETED:
            raise ValueError(
                f"Cannot generate PR for uncompleted run in phase {summary.final_phase.value}."
            )
        if summary.certificate is None:
            raise ValueError("Cannot generate PR without a valid VerificationCertificate.")

        # Clean branch name
        sanitized_issue_id = re.sub(r"[^a-zA-Z0-9_-]", "-", issue.id)
        branch_name = f"{branch_prefix}-{sanitized_issue_id}"

        # Title
        pr_title = f"[ASE] Fix: {issue.title}"

        # Commit message
        commit_msg = (
            f"Fix {issue.id}: {issue.title}\n\n"
            f"Autonomously generated and verified by QuetZ (Autonomous Software Engineer).\n"
            f"Verification Certificate: {summary.certificate.certificate_id}\n"
            f"Evidence Digest: {summary.certificate.evidence_hash}"
        )

        # Build comprehensive markdown body
        body_sections: list[str] = [
            f"## QuetZ (Autonomous Software Engineer) - Automated Fix",
            f"Resolves {issue.id}",
            "",
            "### Summary of Changes",
            f"This pull request was autonomously synthesized, tested, and verified under deterministic safety constraints.",
            "",
            "### 🔬 Scientific Reproduction & Verification Gates",
            f"- **Lifecycle Outcome**: `VERIFIED_SUCCESS`",
            f"- **Static AST Validation**: {'✅ PASSED' if summary.certificate.static_ast_passed else '❌ FAILED'}",
            f"- **Test Suite Verification**: {'✅ PASSED' if summary.certificate.test_verification_passed else '❌ FAILED'}",
            f"- **Confidence Score**: `{summary.certificate.confidence_score:.2f}`",
            f"- **Independent Code Review**: `APPROVED`" if summary.review_verdict else "- **Independent Code Review**: `N/A`",
        ]

        if summary.matched_skills:
            body_sections.extend([
                "",
                f"**Applied Engineering Playbooks**: {', '.join(f'`{s}`' for s in summary.matched_skills)}",
            ])

        if summary.reproduction_evidence:
            body_sections.extend([
                "",
                summary.reproduction_evidence.to_markdown(),
            ])

        if summary.impact_report:
            body_sections.extend([
                "",
                "### 🌐 Semantic Change-Impact Analysis",
                f"- **Blast Radius**: `{summary.impact_report.blast_radius_score:.2f}`",
                f"- **Direct Callers**: {summary.impact_report.direct_callers_count}",
                f"- **Targeted Test Coverage**: {len(summary.impact_report.targeted_test_files)} tests exercised",
            ])

        if summary.mutation_report:
            body_sections.extend([
                "",
                summary.mutation_report.to_markdown(),
            ])

        if sast_report and hasattr(sast_report, "to_markdown"):
            body_sections.extend([
                "",
                sast_report.to_markdown(),
            ])

        if policy_report and hasattr(policy_report, "to_markdown"):
            body_sections.extend([
                "",
                policy_report.to_markdown(),
            ])

        body_sections.extend([
            "",
            summary.certificate.to_markdown(),
            "",
            "> *Generated by QuetZ with fail-closed provenance and proof-carrying evidence.*",
        ])

        pr_body = "\n".join(body_sections)

        files_changed: tuple[str, ...] = ()
        if summary.final_result and summary.final_result.patch_summary:
            files_changed = summary.final_result.patch_summary.files_modified

        payload = PullRequestPayload(
            branch_name=branch_name,
            base_branch=issue.base_branch,
            title=pr_title,
            body=pr_body,
            commit_message=commit_msg,
            issue_id=issue.id,
            certificate_id=summary.certificate.certificate_id,
            files_changed=files_changed,
        )

        # Dispatch notification if configured
        if self.webhook_dispatcher.webhook_url:
            self.webhook_dispatcher.dispatch(
                WebhookNotification(
                    event_type="PR_CREATED",
                    issue_id=issue.id,
                    title=issue.title,
                    status="COMPLETED",
                    certificate_id=summary.certificate.certificate_id,
                    confidence_score=summary.certificate.confidence_score,
                )
            )

        return payload

    def submit_pull_request(
        self,
        repo_owner: str,
        repo_name: str,
        payload: PullRequestPayload,
        github_token: str,
        api_base_url: str = "https://api.github.com",
    ) -> dict[str, Any]:
        """
        Directly submits a PullRequestPayload to GitHub REST API via POST /repos/{owner}/{repo}/pulls.
        """
        if not github_token:
            raise ValueError("A valid GITHUB_TOKEN is required to submit a pull request directly.")

        url = f"{api_base_url.rstrip('/')}/repos/{repo_owner}/{repo_name}/pulls"
        data = {
            "title": payload.title,
            "body": payload.body,
            "head": payload.branch_name,
            "base": payload.base_branch,
        }
        req_bytes = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_bytes,
            headers={
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
                "User-Agent": "QuetZ-Autonomous-Engineer",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return {
                    "success": True,
                    "html_url": resp_data.get("html_url"),
                    "number": resp_data.get("number"),
                    "node_id": resp_data.get("node_id"),
                }
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="replace")
            return {
                "success": False,
                "status_code": e.code,
                "error": err_msg,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }
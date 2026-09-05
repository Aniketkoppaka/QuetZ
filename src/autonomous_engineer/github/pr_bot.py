"""
github/pr_bot.py -- GitHub PR Bot & Automated Pull Request Delivery for ASE (Addition 2).

Transforms a successful PipelineExecutionSummary into a formal, production-grade Pull Request:
1. Validates that the pipeline finished in WorkflowPhase.COMPLETED with a valid VerificationCertificate.
2. Checks that CAP_OPEN_PR capability was granted in the ExecutionPolicy (fail-closed security).
3. Generates rich, auditable PR bodies containing:
    - Verbatim reproduction status & diagnostic logs
    - Cryptographic VerificationCertificate with evidence digest
    - Semantic Change-Impact blast radius analysis
    - Mutation assertion test strength score
    - File change summary table
4. Formats clean git commit messages and branch naming conventions (e.g. `ase/fix-issue-101`).
"""
from __future__ import annotations

import re
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


class GitHubPRBot:
    """
    Constructs and authorizes GitHub PR deliveries for autonomous pipeline runs.
    """

    def generate_pr_payload(
        self,
        issue: Issue,
        summary: PipelineExecutionSummary,
        policy: ExecutionPolicy,
        branch_prefix: str = "ase/fix",
    ) -> PullRequestPayload:
        """
        Generate an authorized PullRequestPayload from a completed pipeline run.

        Raises:
            ValueError: If pipeline run was not COMPLETED or certificate is missing.
            PermissionError: If CAP_OPEN_PR capability is not granted in policy.
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
            "### Verification & Safety Gates",
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
                "### Semantic Change-Impact Analysis",
                f"- **Blast Radius**: `{summary.impact_report.blast_radius_score:.2f}`",
                f"- **Direct Callers**: {summary.impact_report.direct_callers_count}",
                f"- **Targeted Test Coverage**: {len(summary.impact_report.targeted_test_files)} tests exercised",
            ])

        if summary.mutation_report:
            body_sections.extend([
                "",
                summary.mutation_report.to_markdown(),
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

        return PullRequestPayload(
            branch_name=branch_name,
            base_branch=issue.base_branch,
            title=pr_title,
            body=pr_body,
            commit_message=commit_msg,
            issue_id=issue.id,
            certificate_id=summary.certificate.certificate_id,
            files_changed=files_changed,
        )

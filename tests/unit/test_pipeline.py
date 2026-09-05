"""
tests/unit/test_pipeline.py -- Tests for Phase 4.1 Unified End-to-End Pipeline.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autonomous_engineer.agents.validator import AbstentionAssessment, AbstentionDecision
from autonomous_engineer.domain.models import (
    ImplementationPlan,
    ImplementationStep,
    Issue,
    Repository,
    RepositoryMap,
    StepOperation,
)
from autonomous_engineer.domain.states import WorkflowPhase
from autonomous_engineer.execution.models import (
    ExecutionPolicy,
    ExecutionStatus,
    FileChangeRecord,
    PlanExecutionResult,
    VerificationCertificate,
    VerificationResult,
    VerificationType,
)
from autonomous_engineer.orchestration import JobStatus
from autonomous_engineer.orchestration.pipeline import (
    AutonomousPipeline,
    PipelineConfig,
    PipelineExecutionSummary,
)
from autonomous_engineer.review import ReviewResult, ReviewVerdict
from autonomous_engineer.verification.reproduction import (
    ReproductionCandidate,
    ReproductionEvidence,
    ReproductionStatus,
)


def _make_issue() -> Issue:
    return Issue(
        id="owner/repo#101",
        title="Fix bug in calculation",
        body="There is a TypeError bug crashing the service when None is passed.",
        repository_url="https://github.com/owner/repo",
    )


def _make_repo(tmp_path: Path) -> Repository:
    return Repository(
        url="https://github.com/owner/repo",
        workspace_path=tmp_path,
        commit_sha="abcdef123456",
    )


def _make_repo_map() -> RepositoryMap:
    return RepositoryMap(
        repository_url="https://github.com/owner/repo",
        commit_sha="abcdef123456",
        file_count=1,
        python_file_count=1,
    )


def _make_plan() -> ImplementationPlan:
    step = ImplementationStep(
        step_id="step-1",
        target_file="app.py",
        target_symbol="calc",
        operation=StepOperation.MODIFY_SYMBOL,
        description="Fix calculation logic",
        search_content="return a + b",
        replace_content="return (a or 0) + (b or 0)",
        dependencies=(),
    )
    return ImplementationPlan(
        plan_id="plan-1",
        issue_id="owner/repo#101",
        summary="Sanitize calculation arguments",
        rationale="Prevents NoneType crashes",
        steps=(step,),
    )


def _make_certificate(passed: bool = True) -> VerificationCertificate:
    return VerificationCertificate(
        plan_id="plan-1",
        issue_id="owner/repo#101",
        status=ExecutionStatus.COMPLETED if passed else ExecutionStatus.FAILED,
        static_ast_passed=passed,
        test_verification_passed=passed,
        rolled_back=not passed,
        evidence_hash="abcdef0123456789",
        confidence_score=0.95 if passed else 0.30,
    )


class TestAutonomousPipeline:
    def test_successful_end_to_end_run(self, tmp_path: Path):
        """Pipeline successfully navigates all gates to WorkflowPhase.COMPLETED."""
        mock_exec_engine = MagicMock()
        mock_exec_engine.execute.return_value = PlanExecutionResult(
            plan_id="plan-1",
            status=ExecutionStatus.COMPLETED,
            changes=(
                FileChangeRecord(
                    file_path="app.py",
                    operation=StepOperation.MODIFY_SYMBOL,
                ),
            ),
        )
        mock_exec_engine.generate_certificate.return_value = _make_certificate(passed=True)

        mock_abstention_engine = MagicMock()
        mock_abstention_engine.assess_evidence.return_value = AbstentionAssessment(
            decision=AbstentionDecision.VERIFIED_SUCCESS,
            should_abstain=False,
            confidence_score=0.95,
            rationale="All proofs verified",
        )

        mock_review_agent = MagicMock()
        mock_review_agent.review_patch.return_value = ReviewResult(
            verdict=ReviewVerdict.APPROVED,
            summary="Review approved patch",
            feedback=("Patch looks solid.",),
        )

        pipeline = AutonomousPipeline(
            execution_engine=mock_exec_engine,
            abstention_engine=mock_abstention_engine,
            review_agent=mock_review_agent,
        )

        summary = pipeline.run(
            issue=_make_issue(),
            repository=_make_repo(tmp_path),
            repository_map=_make_repo_map(),
            plan=_make_plan(),
        )

        assert summary.final_phase == WorkflowPhase.COMPLETED
        assert summary.status == JobStatus.COMPLETED
        assert "python_bug_fix" in summary.matched_skills
        assert summary.final_result is not None
        assert summary.final_result.resolved is True

    def test_abstains_when_reproduction_is_vacuous(self, tmp_path: Path):
        """When require_reproduction is True and pre-patch test passes -> ABSTAIN."""
        mock_repro_verifier = MagicMock()
        # Pre-patch passes (vacuous reproduction)
        mock_repro_verifier.run_pre_patch.return_value = VerificationResult(
            verification_type=VerificationType.SUBPROCESS_TEST,
            target="pytest",
            passed=True,
            exit_code=0,
        )
        mock_repro_verifier.evaluate_reproduction.return_value = ReproductionEvidence(
            candidate=ReproductionCandidate(test_command="pytest"),
            status=ReproductionStatus.VACUOUS_PRE_PATCH,
            diagnostics="Test already passed on unpatched code",
        )

        pipeline = AutonomousPipeline(
            reproduction_verifier=mock_repro_verifier,
        )

        candidate = ReproductionCandidate(
            test_command="pytest",
            target_filter="test_something",
        )
        config = PipelineConfig(require_reproduction=True)

        summary = pipeline.run(
            issue=_make_issue(),
            repository=_make_repo(tmp_path),
            repository_map=_make_repo_map(),
            plan=_make_plan(),
            config=config,
            reproduction_candidate=candidate,
        )

        assert summary.final_phase == WorkflowPhase.ABSTAINED
        assert summary.status == JobStatus.ABSTAINED
        assert summary.reproduction_evidence is not None
        assert summary.reproduction_evidence.status == ReproductionStatus.VACUOUS_PRE_PATCH

    def test_fails_when_execution_fails(self, tmp_path: Path):
        """When execution engine fails/rolls back -> FAILED."""
        mock_exec_engine = MagicMock()
        mock_exec_engine.execute.return_value = PlanExecutionResult(
            plan_id="plan-1",
            status=ExecutionStatus.FAILED,
            rolled_back=True,
            error_message="Syntax check failed",
        )

        pipeline = AutonomousPipeline(
            execution_engine=mock_exec_engine,
        )

        summary = pipeline.run(
            issue=_make_issue(),
            repository=_make_repo(tmp_path),
            repository_map=_make_repo_map(),
            plan=_make_plan(),
        )

        assert summary.final_phase == WorkflowPhase.FAILED
        assert summary.status == JobStatus.FAILED

    def test_abstains_when_independent_reviewer_rejects(self, tmp_path: Path):
        """When independent code review rejects patch -> ABSTAINED."""
        mock_exec_engine = MagicMock()
        mock_exec_engine.execute.return_value = PlanExecutionResult(
            plan_id="plan-1",
            status=ExecutionStatus.COMPLETED,
            changes=(
                FileChangeRecord(
                    file_path="app.py",
                    operation=StepOperation.MODIFY_SYMBOL,
                ),
            ),
        )
        mock_exec_engine.generate_certificate.return_value = _make_certificate(passed=True)

        mock_abstention_engine = MagicMock()
        mock_abstention_engine.assess_evidence.return_value = AbstentionAssessment(
            decision=AbstentionDecision.VERIFIED_SUCCESS,
            should_abstain=False,
            confidence_score=0.95,
        )

        mock_review_agent = MagicMock()
        mock_review_agent.review_patch.return_value = ReviewResult(
            verdict=ReviewVerdict.REJECTED,
            summary="Review rejected patch",
            feedback=("Detected potential side effect in untouched caller.",),
        )

        pipeline = AutonomousPipeline(
            execution_engine=mock_exec_engine,
            abstention_engine=mock_abstention_engine,
            review_agent=mock_review_agent,
        )

        summary = pipeline.run(
            issue=_make_issue(),
            repository=_make_repo(tmp_path),
            repository_map=_make_repo_map(),
            plan=_make_plan(),
        )

        assert summary.final_phase == WorkflowPhase.ABSTAINED
        assert summary.review_verdict == ReviewVerdict.REJECTED

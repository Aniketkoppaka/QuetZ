"""
tests/unit/test_state_machine.py

Tests for the WorkflowRun finite state machine.

Invariants verified:
- Valid forward transitions (normal happy path)
- Valid failure transitions from each active phase
- Invalid transitions are rejected with InvalidTransitionError
- Backward transitions are rejected
- Skipping phases is rejected
- Terminal states raise TerminalStateError on further transitions
- Transition log grows accurately with each hop
- Original WorkflowRun is unchanged after transition (immutability)
- Repair loop semantics (3-attempt trace)
- Failure detail is carried through to terminal state
- Serialization round-trip of WorkflowRun with full history
- VALID_TRANSITIONS table structural invariants
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from autonomous_engineer.domain import (
    FailureCategory,
    FailureDetail,
    ImplementationPlan,
    InvalidTransitionError,
    Issue,
    RepairAttempt,
    Repository,
    RepositoryMap,
    TERMINAL_PHASES,
    TerminalStateError,
    # Aliased: TestSuiteResult would be mistaken for a test class by pytest
    # when it appears in a test module's global namespace under its original name.
    TestSuiteResult as SuiteResult,
    VALID_TRANSITIONS,
)
from autonomous_engineer.domain.states import WorkflowPhase, WorkflowRun


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def issue() -> Issue:
    return Issue(
        id="owner/repo#99",
        title="NullPointerException in DataProcessor",
        body="When input is None the processor crashes.",
        repository_url="https://github.com/owner/repo",
    )


@pytest.fixture
def fresh_run(issue: Issue) -> WorkflowRun:
    return WorkflowRun(run_id="run-001", task_id="task-001", issue=issue)


@pytest.fixture
def plan() -> ImplementationPlan:
    return ImplementationPlan(
        summary="Guard against None input",
        rationale="Add an early-return guard at the top of process().",
        steps=("Add None check to process()", "Add regression test"),
    )


@pytest.fixture
def repository() -> Repository:
    return Repository(
        url="https://github.com/owner/repo",
        workspace_path=Path("/tmp/workspace/owner-repo-run-001"),
        commit_sha="abc123def456",
        branch="main",
    )


@pytest.fixture
def repo_map() -> RepositoryMap:
    return RepositoryMap(
        repository_url="https://github.com/owner/repo",
        file_count=42,
        python_file_count=30,
        test_file_paths=("tests/test_processor.py",),
        has_pyproject_toml=True,
    )


@pytest.fixture
def passing_suite() -> SuiteResult:
    return SuiteResult(total=5, passed=5, failed=0, errors=0, skipped=0)


@pytest.fixture
def failing_suite() -> SuiteResult:
    return SuiteResult(total=5, passed=4, failed=1, errors=0, skipped=0)


# ---------------------------------------------------------------------------
# Helper: advance run through standard phases up to a given target
# ---------------------------------------------------------------------------

def _advance_to(run: WorkflowRun, *phases: WorkflowPhase) -> WorkflowRun:
    """Apply a sequence of transitions in order."""
    for phase in phases:
        run = run.transition(phase, triggered_by="test-helper")
    return run


# ---------------------------------------------------------------------------
# Valid forward transitions -- normal happy path
# ---------------------------------------------------------------------------


class TestValidForwardTransitions:
    def test_initialised_to_acquiring(self, fresh_run: WorkflowRun) -> None:
        run = fresh_run.transition(WorkflowPhase.ACQUIRING, "orchestrator", "Starting")
        assert run.phase == WorkflowPhase.ACQUIRING

    def test_complete_happy_path(
        self,
        fresh_run: WorkflowRun,
        repository: Repository,
        repo_map: RepositoryMap,
        plan: ImplementationPlan,
        passing_suite: SuiteResult,
    ) -> None:
        """Exercise every phase in the normal successful path."""
        run = fresh_run
        run = run.transition(WorkflowPhase.ACQUIRING, "test", repository=repository)
        assert run.repository == repository

        run = run.transition(WorkflowPhase.MAPPING, "test", repository_map=repo_map)
        assert run.repository_map == repo_map

        run = run.transition(WorkflowPhase.RETRIEVING, "test")
        run = run.transition(WorkflowPhase.PLANNING, "test", current_plan=plan)
        assert run.current_plan == plan

        run = run.transition(WorkflowPhase.IMPLEMENTING, "test")
        run = run.transition(WorkflowPhase.EXECUTING, "test")
        run = run.transition(
            WorkflowPhase.EVALUATING, "test", last_test_suite_result=passing_suite
        )
        assert run.last_test_suite_result == passing_suite

        run = run.transition(WorkflowPhase.REVIEWING, "test")
        run = run.transition(WorkflowPhase.VERIFYING, "test")
        run = run.transition(WorkflowPhase.SUBMITTING, "test")
        run = run.transition(WorkflowPhase.COMPLETED, "test")

        assert run.phase == WorkflowPhase.COMPLETED
        assert run.is_terminal

    def test_original_unchanged_after_transition(self, fresh_run: WorkflowRun) -> None:
        """Transitions must produce a new object; the original is immutable."""
        after = fresh_run.transition(WorkflowPhase.ACQUIRING, "test")
        assert fresh_run.phase == WorkflowPhase.INITIALISED  # original untouched
        assert after.phase == WorkflowPhase.ACQUIRING
        assert fresh_run is not after

    def test_transition_log_grows(self, fresh_run: WorkflowRun) -> None:
        assert len(fresh_run.transition_log) == 0

        run = fresh_run.transition(WorkflowPhase.ACQUIRING, "component-A", "Step 1")
        assert len(run.transition_log) == 1
        assert run.transition_log[0].from_phase == WorkflowPhase.INITIALISED
        assert run.transition_log[0].to_phase == WorkflowPhase.ACQUIRING
        assert run.transition_log[0].triggered_by == "component-A"
        assert run.transition_log[0].reason == "Step 1"

        run = run.transition(WorkflowPhase.MAPPING, "component-B")
        assert len(run.transition_log) == 2
        assert run.transition_log[1].from_phase == WorkflowPhase.ACQUIRING

    def test_transition_log_order_preserved(self, fresh_run: WorkflowRun) -> None:
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING,
            WorkflowPhase.MAPPING,
            WorkflowPhase.RETRIEVING,
        )
        log = run.transition_log
        assert log[0].to_phase == WorkflowPhase.ACQUIRING
        assert log[1].to_phase == WorkflowPhase.MAPPING
        assert log[2].to_phase == WorkflowPhase.RETRIEVING

    def test_phase_serializes_as_string(self, fresh_run: WorkflowRun) -> None:
        data = json.loads(fresh_run.model_dump_json())
        assert data["phase"] == "initialised"


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------


class TestInvalidTransitions:
    def test_planning_to_completed_rejected(
        self, fresh_run: WorkflowRun, plan: ImplementationPlan
    ) -> None:
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING, WorkflowPhase.MAPPING,
            WorkflowPhase.RETRIEVING, WorkflowPhase.PLANNING,
        )
        with pytest.raises(InvalidTransitionError):
            run.transition(WorkflowPhase.COMPLETED, "test")

    def test_initialised_to_completed_rejected(self, fresh_run: WorkflowRun) -> None:
        with pytest.raises(InvalidTransitionError):
            fresh_run.transition(WorkflowPhase.COMPLETED, "test")

    def test_implementing_to_reviewing_rejected(
        self, fresh_run: WorkflowRun
    ) -> None:
        """Cannot skip EXECUTING + EVALUATING to go straight to REVIEWING."""
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING, WorkflowPhase.MAPPING,
            WorkflowPhase.RETRIEVING, WorkflowPhase.PLANNING,
            WorkflowPhase.IMPLEMENTING,
        )
        with pytest.raises(InvalidTransitionError):
            run.transition(WorkflowPhase.REVIEWING, "test")

    def test_backward_transition_rejected(
        self, fresh_run: WorkflowRun, repository: Repository
    ) -> None:
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING,
            WorkflowPhase.MAPPING,
        )
        with pytest.raises(InvalidTransitionError):
            run.transition(WorkflowPhase.INITIALISED, "test")  # backward

    @pytest.mark.parametrize(
        "bad_target",
        [
            WorkflowPhase.RETRIEVING,
            WorkflowPhase.IMPLEMENTING,
            WorkflowPhase.EXECUTING,
            WorkflowPhase.VERIFYING,
            WorkflowPhase.SUBMITTING,
            WorkflowPhase.REVIEWING,
        ],
    )
    def test_initialised_only_allows_acquiring_failed_abandoned(
        self, fresh_run: WorkflowRun, bad_target: WorkflowPhase
    ) -> None:
        with pytest.raises(InvalidTransitionError):
            fresh_run.transition(bad_target, "test")

    def test_error_message_contains_phase_names(self, fresh_run: WorkflowRun) -> None:
        with pytest.raises(InvalidTransitionError) as exc_info:
            fresh_run.transition(WorkflowPhase.COMPLETED, "test")
        msg = str(exc_info.value)
        assert "initialised" in msg
        assert "completed" in msg


# ---------------------------------------------------------------------------
# Terminal state enforcement
# ---------------------------------------------------------------------------


class TestTerminalStates:
    @pytest.mark.parametrize("terminal", list(TERMINAL_PHASES))
    def test_all_terminal_phases_defined(self, terminal: WorkflowPhase) -> None:
        assert terminal in WorkflowPhase

    def test_completed_is_terminal(self, fresh_run: WorkflowRun) -> None:
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING, WorkflowPhase.MAPPING,
            WorkflowPhase.RETRIEVING, WorkflowPhase.PLANNING,
            WorkflowPhase.IMPLEMENTING, WorkflowPhase.EXECUTING,
            WorkflowPhase.EVALUATING, WorkflowPhase.REVIEWING,
            WorkflowPhase.VERIFYING, WorkflowPhase.SUBMITTING,
            WorkflowPhase.COMPLETED,
        )
        assert run.is_terminal
        with pytest.raises(TerminalStateError):
            run.transition(WorkflowPhase.ACQUIRING, "test")

    def test_failed_is_terminal(self, fresh_run: WorkflowRun) -> None:
        run = _advance_to(fresh_run, WorkflowPhase.ACQUIRING, WorkflowPhase.FAILED)
        assert run.is_terminal
        with pytest.raises(TerminalStateError):
            run.transition(WorkflowPhase.PLANNING, "test")

    def test_abandoned_is_terminal(self, fresh_run: WorkflowRun) -> None:
        run = fresh_run.transition(WorkflowPhase.ABANDONED, "test")
        assert run.is_terminal
        with pytest.raises(TerminalStateError):
            run.transition(WorkflowPhase.ACQUIRING, "test")

    def test_abstained_is_terminal(self, fresh_run: WorkflowRun) -> None:
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING,
            WorkflowPhase.MAPPING,
            WorkflowPhase.RETRIEVING,
        )
        run = run.transition(WorkflowPhase.ABSTAINED, "abstention_engine")
        assert run.is_terminal
        assert run.phase == WorkflowPhase.ABSTAINED
        with pytest.raises(TerminalStateError):
            run.transition(WorkflowPhase.PLANNING, "test")

    def test_terminal_error_message_names_state(self, fresh_run: WorkflowRun) -> None:
        run = fresh_run.transition(WorkflowPhase.FAILED, "test")
        with pytest.raises(TerminalStateError) as exc_info:
            run.transition(WorkflowPhase.ACQUIRING, "test")
        assert "failed" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Failure semantics
# ---------------------------------------------------------------------------


class TestFailureSemantics:
    def test_failure_detail_attached_on_failed_transition(
        self, fresh_run: WorkflowRun
    ) -> None:
        failure = FailureDetail(
            category=FailureCategory.REPOSITORY_ACQUISITION,
            message="Connection refused",
            detail="git clone exited with code 128",
            retriable=True,
        )
        run = _advance_to(fresh_run, WorkflowPhase.ACQUIRING)
        run = run.transition(WorkflowPhase.FAILED, "acquisition", failure=failure)
        assert run.phase == WorkflowPhase.FAILED
        assert run.failure is not None
        assert run.failure.category == FailureCategory.REPOSITORY_ACQUISITION
        assert run.failure.retriable is True

    def test_timeout_failure_category(self, fresh_run: WorkflowRun) -> None:
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING, WorkflowPhase.MAPPING,
            WorkflowPhase.RETRIEVING, WorkflowPhase.PLANNING,
            WorkflowPhase.IMPLEMENTING, WorkflowPhase.EXECUTING,
        )
        failure = FailureDetail(
            category=FailureCategory.TIMEOUT,
            message="Exceeded 300s wall-clock limit",
        )
        run = run.transition(WorkflowPhase.FAILED, "executor", failure=failure)
        assert run.failure.category == FailureCategory.TIMEOUT

    def test_repair_exhausted_goes_to_abandoned(
        self, fresh_run: WorkflowRun, plan: ImplementationPlan, failing_suite: SuiteResult
    ) -> None:
        """REPAIRING -> ABANDONED represents repair limit exhaustion."""
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING, WorkflowPhase.MAPPING,
            WorkflowPhase.RETRIEVING, WorkflowPhase.PLANNING,
            WorkflowPhase.IMPLEMENTING, WorkflowPhase.EXECUTING,
        )
        run = run.transition(
            WorkflowPhase.EVALUATING, "test", last_test_suite_result=failing_suite
        )
        run = run.transition(WorkflowPhase.REPAIRING, "test")
        failure = FailureDetail(
            category=FailureCategory.REPAIR_EXHAUSTED,
            message="Max 3 iterations reached",
            retriable=False,
        )
        run = run.transition(WorkflowPhase.ABANDONED, "orchestrator", failure=failure)
        assert run.phase == WorkflowPhase.ABANDONED
        assert run.is_terminal
        assert run.failure.category == FailureCategory.REPAIR_EXHAUSTED

    def test_planning_failure_leads_to_failed(self, fresh_run: WorkflowRun) -> None:
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING, WorkflowPhase.MAPPING,
            WorkflowPhase.RETRIEVING, WorkflowPhase.PLANNING,
        )
        run = run.transition(
            WorkflowPhase.FAILED, "planner",
            failure=FailureDetail(category=FailureCategory.PLANNING, message="No plan"),
        )
        assert run.phase == WorkflowPhase.FAILED
        assert run.failure.category == FailureCategory.PLANNING


# ---------------------------------------------------------------------------
# Repair iteration semantics
# ---------------------------------------------------------------------------


class TestRepairIterationSemantics:
    def test_repair_loop_three_attempts(
        self,
        fresh_run: WorkflowRun,
        plan: ImplementationPlan,
        failing_suite: SuiteResult,
        passing_suite: SuiteResult,
    ) -> None:
        """
        Simulate: attempt 1 fails, attempt 2 fails, attempt 3 succeeds.
        Verify repair_attempts accumulates and all prior data is preserved.
        """
        # --- Attempt 1 ---
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING, WorkflowPhase.MAPPING,
            WorkflowPhase.RETRIEVING, WorkflowPhase.PLANNING,
            WorkflowPhase.IMPLEMENTING, WorkflowPhase.EXECUTING,
        )
        run = run.transition(
            WorkflowPhase.EVALUATING, "test", last_test_suite_result=failing_suite
        )
        attempt1 = RepairAttempt(
            attempt_number=1,
            plan=plan,
            test_suite_result=failing_suite,
            failure=FailureDetail(category=FailureCategory.TEST_FAILURE, message="1 failed"),
        )
        run = run.transition(
            WorkflowPhase.REPAIRING, "test", repair_attempts=(attempt1,)
        )
        assert len(run.repair_attempts) == 1

        # --- Attempt 2 ---
        plan2 = ImplementationPlan(
            summary="Attempt 2", rationale="Revised", steps=("Step C",), attempt_number=2
        )
        run = _advance_to(
            run,
            WorkflowPhase.PLANNING, WorkflowPhase.IMPLEMENTING,
            WorkflowPhase.EXECUTING,
        )
        run = run.transition(
            WorkflowPhase.EVALUATING, "test", last_test_suite_result=failing_suite
        )
        attempt2 = RepairAttempt(
            attempt_number=2,
            plan=plan2,
            test_suite_result=failing_suite,
            failure=FailureDetail(category=FailureCategory.TEST_FAILURE, message="still 1"),
        )
        run = run.transition(
            WorkflowPhase.REPAIRING, "test", repair_attempts=(attempt1, attempt2)
        )
        assert len(run.repair_attempts) == 2

        # --- Attempt 3 succeeds ---
        plan3 = ImplementationPlan(
            summary="Attempt 3", rationale="Final fix", steps=("Step D",), attempt_number=3
        )
        run = _advance_to(
            run,
            WorkflowPhase.PLANNING, WorkflowPhase.IMPLEMENTING,
            WorkflowPhase.EXECUTING,
        )
        run = run.transition(
            WorkflowPhase.EVALUATING, "test", last_test_suite_result=passing_suite,
            current_plan=plan3,
        )
        run = _advance_to(
            run,
            WorkflowPhase.REVIEWING, WorkflowPhase.VERIFYING,
            WorkflowPhase.SUBMITTING, WorkflowPhase.COMPLETED,
        )

        assert run.phase == WorkflowPhase.COMPLETED
        assert len(run.repair_attempts) == 2           # preserved
        assert run.last_test_suite_result.all_passed   # latest result
        assert run.current_plan.attempt_number == 3    # latest plan

    def test_current_attempt_number_increments(
        self,
        fresh_run: WorkflowRun,
        plan: ImplementationPlan,
        failing_suite: SuiteResult,
    ) -> None:
        assert fresh_run.current_attempt_number == 1

        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING, WorkflowPhase.MAPPING,
            WorkflowPhase.RETRIEVING, WorkflowPhase.PLANNING,
            WorkflowPhase.IMPLEMENTING, WorkflowPhase.EXECUTING,
        )
        run = run.transition(
            WorkflowPhase.EVALUATING, "test", last_test_suite_result=failing_suite
        )
        attempt1 = RepairAttempt(attempt_number=1, plan=plan, test_suite_result=failing_suite)
        run = run.transition(WorkflowPhase.REPAIRING, "test", repair_attempts=(attempt1,))
        assert run.current_attempt_number == 2


# ---------------------------------------------------------------------------
# Verification / review distinguishability
# ---------------------------------------------------------------------------


class TestVerificationAndReviewSemantics:
    def test_reviewing_and_verifying_are_distinct_phases(self) -> None:
        assert WorkflowPhase.REVIEWING != WorkflowPhase.VERIFYING

    def test_review_rejection_can_trigger_repair(self, fresh_run: WorkflowRun) -> None:
        """REVIEWING -> REPAIRING is valid (reviewer needs changes)."""
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING, WorkflowPhase.MAPPING,
            WorkflowPhase.RETRIEVING, WorkflowPhase.PLANNING,
            WorkflowPhase.IMPLEMENTING, WorkflowPhase.EXECUTING,
            WorkflowPhase.EVALUATING, WorkflowPhase.REVIEWING,
        )
        # Reviewer says "needs changes" -> go back to repair
        run = run.transition(WorkflowPhase.REPAIRING, "reviewer", reason="Needs changes")
        assert run.phase == WorkflowPhase.REPAIRING

    def test_verifying_is_separate_from_evaluating(
        self, fresh_run: WorkflowRun, passing_suite: SuiteResult
    ) -> None:
        """
        EVALUATING is the in-loop test parse step.
        VERIFYING is the final clean-room verification -- they are distinct.
        """
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING, WorkflowPhase.MAPPING,
            WorkflowPhase.RETRIEVING, WorkflowPhase.PLANNING,
            WorkflowPhase.IMPLEMENTING, WorkflowPhase.EXECUTING,
        )
        run = run.transition(
            WorkflowPhase.EVALUATING, "evaluator", last_test_suite_result=passing_suite
        )
        run = run.transition(WorkflowPhase.REVIEWING, "reviewer")
        run = run.transition(WorkflowPhase.VERIFYING, "verifier")
        # Verifying can also fail
        run = run.transition(
            WorkflowPhase.FAILED, "verifier",
            failure=FailureDetail(
                category=FailureCategory.TEST_FAILURE,
                message="Regression detected on clean checkout",
            ),
        )
        assert run.phase == WorkflowPhase.FAILED


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    def test_fresh_run_round_trip(self, fresh_run: WorkflowRun) -> None:
        restored = WorkflowRun.model_validate_json(fresh_run.model_dump_json())
        assert restored.run_id == fresh_run.run_id
        assert restored.phase == fresh_run.phase
        assert restored.issue == fresh_run.issue

    def test_run_with_repository_round_trip(
        self, fresh_run: WorkflowRun, repository: Repository
    ) -> None:
        run = _advance_to(fresh_run, WorkflowPhase.ACQUIRING)
        run = run.transition(WorkflowPhase.MAPPING, "test", repository=repository)
        restored = WorkflowRun.model_validate_json(run.model_dump_json())
        assert restored.phase == WorkflowPhase.MAPPING
        assert restored.repository is not None
        assert restored.repository.commit_sha == repository.commit_sha
        assert len(restored.transition_log) == 2

    def test_transition_log_survives_round_trip(self, fresh_run: WorkflowRun) -> None:
        run = _advance_to(
            fresh_run,
            WorkflowPhase.ACQUIRING, WorkflowPhase.MAPPING, WorkflowPhase.RETRIEVING,
        )
        restored = WorkflowRun.model_validate_json(run.model_dump_json())
        assert len(restored.transition_log) == 3
        assert restored.transition_log[0].triggered_by == "test-helper"
        assert restored.transition_log[2].to_phase == WorkflowPhase.RETRIEVING

    def test_failure_detail_survives_round_trip(self, fresh_run: WorkflowRun) -> None:
        run = _advance_to(fresh_run, WorkflowPhase.ACQUIRING)
        failure = FailureDetail(
            category=FailureCategory.TIMEOUT,
            message="Clock ran out",
            retriable=True,
        )
        run = run.transition(WorkflowPhase.FAILED, "executor", failure=failure)
        restored = WorkflowRun.model_validate_json(run.model_dump_json())
        assert restored.failure is not None
        assert restored.failure.category == FailureCategory.TIMEOUT
        assert restored.failure.retriable is True


# ---------------------------------------------------------------------------
# Transition table structural invariants
# ---------------------------------------------------------------------------


class TestTransitionTableInvariants:
    def test_terminal_phases_have_no_outgoing_transitions(self) -> None:
        """Terminal phases must never appear as a 'from' in VALID_TRANSITIONS."""
        from_phases = {from_p for from_p, _ in VALID_TRANSITIONS}
        for terminal in TERMINAL_PHASES:
            assert terminal not in from_phases, (
                f"Terminal phase {terminal!r} appears as source in VALID_TRANSITIONS -- "
                "this is a design invariant violation."
            )

    def test_every_non_terminal_phase_has_outgoing_transitions(self) -> None:
        """Every non-terminal phase must have at least one outgoing transition."""
        from_phases = {from_p for from_p, _ in VALID_TRANSITIONS}
        for phase in WorkflowPhase:
            if phase not in TERMINAL_PHASES:
                assert phase in from_phases, (
                    f"Non-terminal phase {phase!r} has no outgoing transitions."
                )

    def test_transition_table_has_expected_minimum_size(self) -> None:
        """Sanity check: the table should have a meaningful number of transitions."""
        assert len(VALID_TRANSITIONS) >= 30, (
            f"VALID_TRANSITIONS has only {len(VALID_TRANSITIONS)} entries -- "
            "seems suspiciously small."
        )

    def test_all_transitions_reference_valid_phases(self) -> None:
        valid_phases = set(WorkflowPhase)
        for from_p, to_p in VALID_TRANSITIONS:
            assert from_p in valid_phases
            assert to_p in valid_phases

    def test_ase_job_session_lifecycle(self, issue: Issue, tmp_path: Path) -> None:
        """Verify ASEJob pause, resume, checkpointing, and disk persistence."""
        from autonomous_engineer.orchestration import (
            ASEJob,
            ASEJobManager,
            JobBudget,
            JobStatus,
        )

        storage = tmp_path / "job_storage"
        mgr = ASEJobManager(storage_dir=storage)
        budget = JobBudget(max_total_tokens=5000, max_repair_iterations=3)
        job = mgr.create_job(task_id="task-job-1", issue=issue, budget=budget, job_id="job-uuid-1")

        assert job.status == JobStatus.PENDING
        assert job.job_id == "job-uuid-1"

        # Advance workflow through job
        job.transition_workflow(WorkflowPhase.ACQUIRING, "job_runner", tokens_used=500)
        assert job.status == JobStatus.RUNNING
        assert job.run.phase == WorkflowPhase.ACQUIRING
        assert job.budget.tokens_consumed == 500

        # Pause and checkpoint
        ckpt = job.pause()
        assert job.status == JobStatus.PAUSED
        assert ckpt.phase == WorkflowPhase.ACQUIRING

        # Persist to disk and restore
        ckpt_path = mgr.persist_checkpoint(job.job_id)
        assert ckpt_path.exists()

        restored_job = mgr.load_checkpoint(ckpt_path)
        assert restored_job.job_id == "job-uuid-1"
        assert restored_job.status == JobStatus.PAUSED
        assert restored_job.run.phase == WorkflowPhase.ACQUIRING
        assert restored_job.budget.tokens_consumed == 500

        # Resume restored job
        restored_job.resume()
        assert restored_job.status == JobStatus.RUNNING

    def test_independent_review_agent(self, issue: Issue) -> None:
        """Verify IndependentReviewAgent reviews patch with zero access to planner reasoning."""
        from autonomous_engineer.domain.models import (
            ImplementationStep,
            ReviewVerdict,
            StepOperation,
        )
        from autonomous_engineer.execution.models import (
            ExecutionStatus,
            FileChangeRecord,
            VerificationCertificate,
        )
        from autonomous_engineer.review import IndependentReviewAgent

        agent = IndependentReviewAgent()
        plan = ImplementationPlan(
            summary="Fix bug",
            rationale="Rationale",
            affected_files=("src/pkg/service.py",),
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.MODIFY_SYMBOL,
                    target_file="src/pkg/service.py",
                    description="Edit",
                ),
            ),
        )

        valid_change = (
            FileChangeRecord(
                file_path="src/pkg/service.py",
                operation=StepOperation.MODIFY_SYMBOL,
            ),
        )

        cert = VerificationCertificate(
            plan_id=plan.plan_id,
            issue_id=issue.id,
            status=ExecutionStatus.COMPLETED,
            static_ast_passed=True,
            test_verification_passed=True,
            rolled_back=False,
            unauthorized_modifications_detected=False,
            evidence_hash="0" * 64,
            confidence_score=0.9,
        )

        # 1. Approved case
        res_approved = agent.review_patch(issue, plan, valid_change, cert)
        assert res_approved.verdict == ReviewVerdict.APPROVED
        assert res_approved.correctness_score >= 0.9

        # 2. Scope creep case
        unauth_change = (
            FileChangeRecord(
                file_path="src/pkg/unauthorized.py",
                operation=StepOperation.MODIFY_SYMBOL,
            ),
        )
        res_rejected = agent.review_patch(issue, plan, unauth_change, cert)
        assert res_rejected.verdict == ReviewVerdict.REJECTED
        assert "Scope creep" in res_rejected.feedback[0]

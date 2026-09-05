"""
tests/unit/test_domain_models.py

Tests for core domain model construction, validation, and serialization.
All tests are pure Python -- no external infrastructure dependencies.

Coverage:
- Field validation (blank strings, empty tuples, negative counts)
- Immutability (frozen models reject assignment)
- Computed properties (succeeded, all_passed, failure_count)
- JSON round-trip (model_dump_json / model_validate_json)
- FailureCategory taxonomy (distinct values, JSON serialization)
- RepairAttempt sequence representation
- Infrastructure independence (no Docker, GitHub, or LLM modules)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from autonomous_engineer.domain import (
    CodeContext,
    ExecutionResult,
    FailureCategory,
    FailureDetail,
    FinalResult,
    ImplementationPlan,
    Issue,
    PatchSummary,
    RepairAttempt,
    Repository,
    RepositoryMap,
    ReviewResult,
    ReviewVerdict,
    # Aliased: domain classes named Test* are mistaken for test classes by pytest
    # when they appear in a test module's global namespace under their original names.
    # Aliasing them here eliminates the PytestCollectionWarning at its root cause
    # without renaming the domain API or suppressing warnings globally.
    TestCaseResult as CaseResult,
    TestOutcome as CaseOutcome,
    TestSuiteResult as SuiteResult,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_issue() -> Issue:
    return Issue(
        id="owner/repo#42",
        title="Fix the thing",
        body="When I do X, Y happens instead of Z.",
        repository_url="https://github.com/owner/repo",
    )


@pytest.fixture
def minimal_plan() -> ImplementationPlan:
    return ImplementationPlan(
        summary="Fix the off-by-one error in process_batch",
        rationale="The loop index starts at 1 but the list is 0-indexed.",
        steps=("Edit src/batch.py line 42", "Add regression test"),
    )


@pytest.fixture
def passing_suite() -> SuiteResult:
    return SuiteResult(total=3, passed=3, failed=0, errors=0, skipped=0)


@pytest.fixture
def failing_suite() -> SuiteResult:
    return SuiteResult(
        total=3,
        passed=2,
        failed=1,
        errors=0,
        skipped=0,
        test_cases=(
            CaseResult(
                test_id="tests/test_batch.py::test_edge",
                outcome=CaseOutcome.FAILED,
                message="AssertionError: expected 0, got 1",
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------


class TestIssue:
    def test_valid_construction(self, minimal_issue: Issue) -> None:
        assert minimal_issue.id == "owner/repo#42"
        assert minimal_issue.base_branch == "main"  # default
        assert minimal_issue.labels == ()

    def test_blank_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Issue(id="   ", title="T", body="B", repository_url="https://github.com/x/y")

    def test_blank_title_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Issue(id="x/y#1", title="", body="B", repository_url="https://github.com/x/y")

    def test_blank_body_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Issue(id="x/y#1", title="T", body="", repository_url="https://github.com/x/y")

    def test_blank_repo_url_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Issue(id="x/y#1", title="T", body="B", repository_url="  ")

    def test_immutable(self, minimal_issue: Issue) -> None:
        with pytest.raises((ValidationError, TypeError)):
            minimal_issue.title = "mutated"  # type: ignore[misc]

    def test_json_round_trip(self, minimal_issue: Issue) -> None:
        restored = Issue.model_validate_json(minimal_issue.model_dump_json())
        assert restored == minimal_issue

    def test_created_at_defaults_to_none(self, minimal_issue: Issue) -> None:
        assert minimal_issue.created_at is None

    def test_created_at_preserved_in_round_trip(self) -> None:
        ts = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        issue = Issue(
            id="x/y#1", title="T", body="B",
            repository_url="https://github.com/x/y",
            created_at=ts,
        )
        restored = Issue.model_validate_json(issue.model_dump_json())
        assert restored.created_at == ts


# ---------------------------------------------------------------------------
# ImplementationPlan
# ---------------------------------------------------------------------------


class TestImplementationPlan:
    def test_valid_construction(self, minimal_plan: ImplementationPlan) -> None:
        assert len(minimal_plan.steps) == 2
        assert minimal_plan.attempt_number == 1

    def test_empty_steps_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ImplementationPlan(
                summary="Do nothing",
                rationale="Because.",
                steps=(),
            )

    def test_plan_id_auto_generated(self) -> None:
        p1 = ImplementationPlan(summary="S", rationale="R", steps=("step",))
        p2 = ImplementationPlan(summary="S", rationale="R", steps=("step",))
        assert p1.plan_id != p2.plan_id  # UUIDs are unique

    def test_json_round_trip(self, minimal_plan: ImplementationPlan) -> None:
        restored = ImplementationPlan.model_validate_json(minimal_plan.model_dump_json())
        assert restored.summary == minimal_plan.summary
        assert restored.steps == minimal_plan.steps
        assert restored.plan_id == minimal_plan.plan_id


# ---------------------------------------------------------------------------
# ExecutionResult
# ---------------------------------------------------------------------------


class TestExecutionResult:
    def test_succeeded_on_exit_zero(self) -> None:
        r = ExecutionResult(exit_code=0, duration_seconds=1.5)
        assert r.succeeded is True

    def test_not_succeeded_on_nonzero_exit(self) -> None:
        r = ExecutionResult(exit_code=1, duration_seconds=0.3)
        assert r.succeeded is False

    def test_timeout_overrides_zero_exit_code(self) -> None:
        r = ExecutionResult(exit_code=0, duration_seconds=60.0, timed_out=True)
        assert r.succeeded is False

    def test_resource_limit_overrides_zero_exit_code(self) -> None:
        r = ExecutionResult(exit_code=0, duration_seconds=5.0, resource_limit_hit=True)
        assert r.succeeded is False

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionResult(exit_code=0, duration_seconds=-1.0)


# ---------------------------------------------------------------------------
# TestSuiteResult
# ---------------------------------------------------------------------------


class TestTestSuiteResult:
    def test_all_passed_on_clean_suite(self, passing_suite: SuiteResult) -> None:
        assert passing_suite.all_passed is True
        assert passing_suite.failure_count == 0

    def test_all_passed_false_on_failure(self, failing_suite: SuiteResult) -> None:
        assert failing_suite.all_passed is False
        assert failing_suite.failure_count == 1

    def test_parse_error_marks_not_passed(self) -> None:
        r = SuiteResult(
            total=0, passed=0, failed=0, errors=0, skipped=0,
            parse_error="output truncated at 64KB",
        )
        assert r.all_passed is False

    def test_error_count_contributes_to_failure_count(self) -> None:
        r = SuiteResult(total=2, passed=0, failed=1, errors=1, skipped=0)
        assert r.failure_count == 2

    def test_test_cases_preserved_in_round_trip(self, failing_suite: SuiteResult) -> None:
        restored = SuiteResult.model_validate_json(failing_suite.model_dump_json())
        assert len(restored.test_cases) == 1
        assert restored.test_cases[0].outcome == CaseOutcome.FAILED


# ---------------------------------------------------------------------------
# RepairAttempt
# ---------------------------------------------------------------------------


class TestRepairAttempt:
    def test_not_succeeded_without_test_result(
        self, minimal_plan: ImplementationPlan
    ) -> None:
        a = RepairAttempt(attempt_number=1, plan=minimal_plan)
        assert a.succeeded is False

    def test_succeeded_with_passing_suite(
        self, minimal_plan: ImplementationPlan, passing_suite: SuiteResult
    ) -> None:
        a = RepairAttempt(attempt_number=1, plan=minimal_plan, test_suite_result=passing_suite)
        assert a.succeeded is True

    def test_not_succeeded_when_failure_present(
        self, minimal_plan: ImplementationPlan, passing_suite: SuiteResult
    ) -> None:
        a = RepairAttempt(
            attempt_number=1,
            plan=minimal_plan,
            test_suite_result=passing_suite,
            failure=FailureDetail(category=FailureCategory.TEST_FAILURE, message="x"),
        )
        assert a.succeeded is False

    def test_sequence_of_three_attempts(
        self,
        minimal_plan: ImplementationPlan,
        failing_suite: SuiteResult,
        passing_suite: SuiteResult,
    ) -> None:
        """Three attempts can be constructed and queried without losing data."""
        plan2 = ImplementationPlan(
            summary="Attempt 2", rationale="Revised", steps=("Step B",), attempt_number=2
        )
        plan3 = ImplementationPlan(
            summary="Attempt 3", rationale="Final", steps=("Step C",), attempt_number=3
        )
        attempts = (
            RepairAttempt(
                attempt_number=1,
                plan=minimal_plan,
                test_suite_result=failing_suite,
                failure=FailureDetail(
                    category=FailureCategory.TEST_FAILURE, message="1 failed", retriable=True
                ),
            ),
            RepairAttempt(attempt_number=2, plan=plan2, test_suite_result=failing_suite),
            RepairAttempt(attempt_number=3, plan=plan3, test_suite_result=passing_suite),
        )
        assert len(attempts) == 3
        assert attempts[0].succeeded is False
        assert attempts[1].succeeded is False
        assert attempts[2].succeeded is True
        # Previous attempt data is preserved unchanged
        assert attempts[0].failure.category == FailureCategory.TEST_FAILURE
        assert attempts[0].plan.attempt_number == 1
        assert attempts[2].plan.attempt_number == 3


# ---------------------------------------------------------------------------
# ReviewResult
# ---------------------------------------------------------------------------


class TestReviewResult:
    def test_approved_verdict(self) -> None:
        r = ReviewResult(verdict=ReviewVerdict.APPROVED, summary="LGTM")
        assert r.verdict == ReviewVerdict.APPROVED
        assert r.feedback == ()

    def test_rejected_with_feedback(self) -> None:
        r = ReviewResult(
            verdict=ReviewVerdict.REJECTED,
            summary="Does not address the issue",
            feedback=("Missing edge case for empty input", "No test for None"),
        )
        assert len(r.feedback) == 2

    def test_correctness_score_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ReviewResult(verdict=ReviewVerdict.APPROVED, summary="S", correctness_score=1.5)


# ---------------------------------------------------------------------------
# FailureDetail taxonomy
# ---------------------------------------------------------------------------


class TestFailureDetail:
    def test_all_categories_are_distinct(self) -> None:
        values = [c.value for c in FailureCategory]
        assert len(values) == len(set(values))

    def test_retriable_semantics(self) -> None:
        permanent = FailureDetail(
            category=FailureCategory.INVALID_INPUT,
            message="Repository URL is invalid",
            retriable=False,
        )
        transient = FailureDetail(
            category=FailureCategory.INFRASTRUCTURE,
            message="Docker daemon unavailable",
            retriable=True,
        )
        assert permanent.retriable is False
        assert transient.retriable is True

    def test_category_serializes_as_string(self) -> None:
        fd = FailureDetail(category=FailureCategory.TEST_FAILURE, message="Tests failed")
        data = json.loads(fd.model_dump_json())
        assert data["category"] == "test_failure"
        assert isinstance(data["category"], str)

    def test_detail_field_defaults_empty(self) -> None:
        fd = FailureDetail(category=FailureCategory.TIMEOUT, message="Timed out")
        assert fd.detail == ""

    def test_all_expected_categories_exist(self) -> None:
        expected = {
            "invalid_input", "configuration",
            "repository_acquisition", "repository_understanding",
            "retrieval", "planning", "implementation", "patch_application",
            "dependency_installation", "test_failure", "execution_error",
            "timeout", "resource_limit",
            "repair_exhausted", "review_rejected",
            "security_violation", "infrastructure", "unknown",
        }
        actual = {c.value for c in FailureCategory}
        assert expected == actual, f"Category mismatch.\nExpected: {expected}\nActual: {actual}"


# ---------------------------------------------------------------------------
# Infrastructure independence
# ---------------------------------------------------------------------------


class TestDomainInfrastructureIndependence:
    """Verify the domain layer does not silently pull in external infrastructure."""

    def test_no_docker_module_imported(self) -> None:
        assert "docker" not in sys.modules, "domain layer must not import Docker"

    def test_no_github_sdk_imported(self) -> None:
        for mod in ("github", "pygithub", "PyGithub"):
            assert mod not in sys.modules, f"domain layer must not import {mod}"

    def test_no_llm_sdk_imported(self) -> None:
        llm_modules = ["openai", "anthropic", "langchain", "langgraph", "litellm"]
        for mod in llm_modules:
            assert mod not in sys.modules, f"LLM module unexpectedly imported: {mod}"

    def test_domain_has_no_database_import(self) -> None:
        db_modules = ["sqlalchemy", "sqlite3", "psycopg2", "pymongo", "redis"]
        # sqlite3 is stdlib and might appear, but SQLAlchemy etc. should not
        for mod in ["sqlalchemy", "psycopg2", "pymongo", "redis"]:
            assert mod not in sys.modules


# ---------------------------------------------------------------------------
# TransitionRecord.metadata immutability (regression tests)
# ---------------------------------------------------------------------------

from types import MappingProxyType  # noqa: E402

from autonomous_engineer.domain.states import TransitionRecord, WorkflowPhase, WorkflowRun


class TestTransitionRecordImmutability:
    """
    Regression tests for the MappingProxyType-backed ``metadata`` field on
    ``TransitionRecord``.

    Immutability contract:
      * Attribute reassignment: blocked by frozen=True on the model.
      * Item-level key assignment: blocked by MappingProxyType.
      * Item-level key deletion: blocked by MappingProxyType.
      * Preserved after JSON round-trip (model_dump_json / model_validate_json).
      * Preserved after model_dump(mode='python') + model_validate() -- the
        code path used inside WorkflowRun.transition().
      * Mutation attempts on log records inside WorkflowRun are blocked.

    Shallow contract (documented limitation):
      * Only the mapping itself is frozen. Values that are themselves mutable
        (e.g. lists, dicts) remain mutable. Callers should store primitive
        values (str, int, bool, float, None) in metadata.
    """

    def _make_record(self, meta: dict | None = None) -> TransitionRecord:
        return TransitionRecord(
            from_phase=WorkflowPhase.INITIALISED,
            to_phase=WorkflowPhase.ACQUIRING,
            triggered_by="test",
            metadata=meta or {},
        )

    def test_metadata_is_mappingproxy_type(self) -> None:
        rec = self._make_record({"key": "value"})
        assert isinstance(rec.metadata, MappingProxyType)

    def test_metadata_empty_default_is_mappingproxy(self) -> None:
        rec = TransitionRecord(
            from_phase=WorkflowPhase.INITIALISED,
            to_phase=WorkflowPhase.ACQUIRING,
            triggered_by="test",
        )
        assert isinstance(rec.metadata, MappingProxyType)
        assert len(rec.metadata) == 0

    def test_metadata_attribute_reassignment_blocked(self) -> None:
        from pydantic import ValidationError
        rec = self._make_record({"a": 1})
        with pytest.raises((ValidationError, TypeError)):
            rec.metadata = {"new": "value"}  # type: ignore[misc]

    def test_metadata_item_assignment_blocked(self) -> None:
        rec = self._make_record({"key": "original"})
        with pytest.raises(TypeError, match="does not support item assignment"):
            rec.metadata["key"] = "mutated"

    def test_metadata_item_deletion_blocked(self) -> None:
        rec = self._make_record({"key": "value"})
        with pytest.raises(TypeError):
            del rec.metadata["key"]

    def test_value_unchanged_after_failed_mutation(self) -> None:
        rec = self._make_record({"key": "original"})
        try:
            rec.metadata["key"] = "mutated"
        except TypeError:
            pass
        assert rec.metadata["key"] == "original"

    def test_source_dict_mutation_does_not_affect_record(self) -> None:
        """Mutating the dict passed at construction must not affect the stored proxy."""
        source = {"x": 1}
        rec = self._make_record(source)
        source["x"] = 999
        assert rec.metadata["x"] == 1

    def test_metadata_survives_json_round_trip_as_mappingproxy(self) -> None:
        rec = self._make_record({"count": 3, "label": "retry"})
        restored = TransitionRecord.model_validate_json(rec.model_dump_json())
        assert isinstance(restored.metadata, MappingProxyType)
        assert restored.metadata["count"] == 3
        assert restored.metadata["label"] == "retry"

    def test_restored_metadata_is_immutable_after_json_round_trip(self) -> None:
        rec = self._make_record({"k": "v"})
        restored = TransitionRecord.model_validate_json(rec.model_dump_json())
        with pytest.raises(TypeError):
            restored.metadata["k"] = "modified"

    def test_metadata_survives_model_dump_python_round_trip(self) -> None:
        """model_dump(mode='python') is the code path inside WorkflowRun.transition()."""
        rec = self._make_record({"step": "acquire"})
        dumped = rec.model_dump(mode="python")
        # model_dump(mode='python') returns a plain dict for MappingProxyType
        assert isinstance(dumped["metadata"], dict)
        # model_validate() re-coerces it to MappingProxyType via field_validator
        restored = TransitionRecord.model_validate(dumped)
        assert isinstance(restored.metadata, MappingProxyType)
        with pytest.raises(TypeError):
            restored.metadata["step"] = "tampered"

    def test_mutation_on_workflow_run_log_record_is_blocked(self) -> None:
        """TransitionRecord objects inside WorkflowRun.transition_log are immutable."""
        issue = Issue(
            id="owner/repo#1", title="T", body="B",
            repository_url="https://github.com/owner/repo",
        )
        run = WorkflowRun(run_id="r1", task_id="t1", issue=issue)
        run2 = run.transition(WorkflowPhase.ACQUIRING, "comp-A")
        run3 = run2.transition(WorkflowPhase.MAPPING, "comp-B")

        log_rec = run3.transition_log[0]
        assert isinstance(log_rec.metadata, MappingProxyType)
        with pytest.raises(TypeError):
            log_rec.metadata["injected"] = "evil"

    def test_failed_mutation_does_not_appear_in_next_transition(self) -> None:
        """Confirms mutation is truly blocked, not just silently rejected."""
        issue = Issue(
            id="owner/repo#2", title="T2", body="B2",
            repository_url="https://github.com/owner/repo",
        )
        run = WorkflowRun(run_id="r2", task_id="t2", issue=issue)
        run2 = run.transition(WorkflowPhase.ACQUIRING, "comp-A")

        with pytest.raises(TypeError):
            run2.transition_log[0].metadata["tampered"] = True

        run3 = run2.transition(WorkflowPhase.MAPPING, "comp-B")
        assert "tampered" not in run3.transition_log[0].metadata

    def test_field_description_documents_shallow_contract(self) -> None:
        """The field description must mention the shallow-immutability limitation."""
        field_info = TransitionRecord.model_fields["metadata"]
        desc = (field_info.description or "").lower()
        assert "nested" in desc or "shallow" in desc or "caller" in desc, (
            "metadata field description should document the shallow-immutability contract"
        )
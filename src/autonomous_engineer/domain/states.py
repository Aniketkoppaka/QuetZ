"""
domain/states.py -- Explicit finite-state machine for the autonomous workflow.

Design:
  WorkflowPhase       -- enum of all valid phases (states).
  TERMINAL_PHASES     -- frozenset of phases with no outgoing transitions.
  VALID_TRANSITIONS   -- frozenset of permitted (from, to) phase pairs.
  TransitionRecord    -- immutable audit log entry for one transition.
  WorkflowRun         -- immutable snapshot of the full run state.

Mutation contract:
    WorkflowRun objects are NEVER mutated in place.
    All state changes go through WorkflowRun.transition(), which:
      1. Validates (current_phase, to_phase) against VALID_TRANSITIONS.
      2. Builds an updated field dict via model_dump().
      3. Returns a NEW WorkflowRun with the updated state.
      4. Appends a TransitionRecord to the audit log.

Serialization:
    WorkflowRun.model_dump_json() -- complete, lossless snapshot.
    WorkflowRun.model_validate_json(s) -- reconstruction from snapshot.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from autonomous_engineer.domain.errors import (
    InvalidTransitionError,
    TerminalStateError,
)
from autonomous_engineer.domain.models import (
    CodeContext,
    ExecutionResult,
    FailureDetail,
    FinalResult,
    ImplementationPlan,
    Issue,
    PatchSummary,
    RepairAttempt,
    Repository,
    RepositoryMap,
    ReviewResult,
    TestSuiteResult,
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Workflow phases (states)
# ---------------------------------------------------------------------------


class WorkflowPhase(str, enum.Enum):
    """
    All valid phases of an autonomous engineering run.

    States are named for the phase the system is *entering*, not the action
    being performed. The str-mixin means they serialize as plain strings
    (e.g. "planning") in JSON output rather than as enum repr.
    """

    # Lifecycle start
    INITIALISED = "initialised"      # Task created, not yet started

    # Repository phase
    ACQUIRING = "acquiring"          # Cloning / fetching the repository
    MAPPING = "mapping"              # Building RepositoryMap (understanding)

    # Context retrieval
    RETRIEVING = "retrieving"        # Locating relevant code context

    # Planning & implementation
    PLANNING = "planning"            # Producing an ImplementationPlan
    IMPLEMENTING = "implementing"    # Applying code changes via tools

    # Execution & evaluation
    EXECUTING = "executing"          # Running tests in sandbox
    EVALUATING = "evaluating"        # Parsing / interpreting test results

    # Repair
    REPAIRING = "repairing"          # Diagnosing failure, preparing next attempt

    # Final stages
    REVIEWING = "reviewing"          # Independent review of the patch
    VERIFYING = "verifying"          # Final clean-room verification run
    SUBMITTING = "submitting"        # Creating PR / patch file

    # Terminal states -- no transitions out
    COMPLETED = "completed"          # Successfully resolved and accepted
    FAILED = "failed"                # Irrecoverably failed
    ABANDONED = "abandoned"          # Exceeded limits or operator-cancelled
    ABSTAINED = "abstained"          # Formally abstained due to insufficient evidence/confidence


# Terminal phases -- no further transitions are permitted out of these.
TERMINAL_PHASES: frozenset[WorkflowPhase] = frozenset({
    WorkflowPhase.COMPLETED,
    WorkflowPhase.FAILED,
    WorkflowPhase.ABANDONED,
    WorkflowPhase.ABSTAINED,
})


# ---------------------------------------------------------------------------
# Valid transition table
# ---------------------------------------------------------------------------
# The complete, authoritative specification of what transitions are allowed.
# Any (from, to) pair NOT in this set raises InvalidTransitionError.

VALID_TRANSITIONS: frozenset[tuple[WorkflowPhase, WorkflowPhase]] = frozenset({
    # --- Normal forward path ---
    (WorkflowPhase.INITIALISED,  WorkflowPhase.ACQUIRING),
    (WorkflowPhase.ACQUIRING,    WorkflowPhase.MAPPING),
    (WorkflowPhase.MAPPING,      WorkflowPhase.RETRIEVING),
    (WorkflowPhase.RETRIEVING,   WorkflowPhase.PLANNING),
    (WorkflowPhase.PLANNING,     WorkflowPhase.IMPLEMENTING),
    (WorkflowPhase.IMPLEMENTING, WorkflowPhase.EXECUTING),
    (WorkflowPhase.EXECUTING,    WorkflowPhase.EVALUATING),

    # --- After evaluation: success path to review ---
    (WorkflowPhase.EVALUATING,   WorkflowPhase.REVIEWING),

    # --- After evaluation: repair path ---
    (WorkflowPhase.EVALUATING,   WorkflowPhase.REPAIRING),
    (WorkflowPhase.REPAIRING,    WorkflowPhase.PLANNING),   # re-plan next attempt

    # --- After review ---
    (WorkflowPhase.REVIEWING,    WorkflowPhase.VERIFYING),  # reviewer approved
    (WorkflowPhase.REVIEWING,    WorkflowPhase.REPAIRING),  # reviewer needs changes

    # --- Final stages ---
    (WorkflowPhase.VERIFYING,    WorkflowPhase.SUBMITTING),
    (WorkflowPhase.SUBMITTING,   WorkflowPhase.COMPLETED),

    # --- Failure paths ---
    # Any non-terminal phase can transition to FAILED on an unrecoverable error.
    (WorkflowPhase.INITIALISED,  WorkflowPhase.FAILED),    # pre-start validation
    (WorkflowPhase.ACQUIRING,    WorkflowPhase.FAILED),
    (WorkflowPhase.MAPPING,      WorkflowPhase.FAILED),
    (WorkflowPhase.RETRIEVING,   WorkflowPhase.FAILED),
    (WorkflowPhase.PLANNING,     WorkflowPhase.FAILED),
    (WorkflowPhase.IMPLEMENTING, WorkflowPhase.FAILED),
    (WorkflowPhase.EXECUTING,    WorkflowPhase.FAILED),
    (WorkflowPhase.EVALUATING,   WorkflowPhase.FAILED),
    (WorkflowPhase.REVIEWING,    WorkflowPhase.FAILED),     # hard-rejection
    (WorkflowPhase.VERIFYING,    WorkflowPhase.FAILED),
    (WorkflowPhase.SUBMITTING,   WorkflowPhase.FAILED),

    # REPAIRING -> ABANDONED means repair limit was exhausted (not a hard error)
    (WorkflowPhase.REPAIRING,    WorkflowPhase.ABANDONED),

    # --- Abandonment (operator cancel from any active phase) ---
    (WorkflowPhase.INITIALISED,  WorkflowPhase.ABANDONED),
    (WorkflowPhase.ACQUIRING,    WorkflowPhase.ABANDONED),
    (WorkflowPhase.MAPPING,      WorkflowPhase.ABANDONED),
    (WorkflowPhase.RETRIEVING,   WorkflowPhase.ABANDONED),
    (WorkflowPhase.PLANNING,     WorkflowPhase.ABANDONED),
    (WorkflowPhase.IMPLEMENTING, WorkflowPhase.ABANDONED),
    (WorkflowPhase.EXECUTING,    WorkflowPhase.ABANDONED),
    (WorkflowPhase.EVALUATING,   WorkflowPhase.ABANDONED),
    (WorkflowPhase.REPAIRING,    WorkflowPhase.FAILED),     # repair can also hard-fail
    (WorkflowPhase.REVIEWING,    WorkflowPhase.ABANDONED),
    (WorkflowPhase.VERIFYING,    WorkflowPhase.ABANDONED),
    (WorkflowPhase.SUBMITTING,   WorkflowPhase.ABANDONED),

    # --- Formal Abstention paths (insufficient evidence / low confidence) ---
    (WorkflowPhase.RETRIEVING,   WorkflowPhase.ABSTAINED),   # Insufficient grounded context to formulate plan
    (WorkflowPhase.PLANNING,     WorkflowPhase.ABSTAINED),   # Unresolved uncertainties exceed threshold
    (WorkflowPhase.EVALUATING,   WorkflowPhase.ABSTAINED),   # Inconclusive evaluation / unverified behavior
    (WorkflowPhase.REPAIRING,    WorkflowPhase.ABSTAINED),   # Repair cannot establish verification proof
    (WorkflowPhase.REVIEWING,    WorkflowPhase.ABSTAINED),   # Independent reviewer rejects with abstention
    (WorkflowPhase.VERIFYING,    WorkflowPhase.ABSTAINED),   # Final clean-room verification fails proof
})


# ---------------------------------------------------------------------------
# Transition record -- audit log entry
# ---------------------------------------------------------------------------


class TransitionRecord(BaseModel):
    """
    An immutable record of one state transition.

    The complete sequence of TransitionRecords constitutes an audit log from
    which the full history of a run can be reconstructed.

    Captures answers to: What state? To what state? Why? When? Who triggered?

    Immutability note:
        ``metadata`` is stored as a ``MappingProxyType``.  This prevents both
        attribute reassignment (blocked by ``frozen=True`` on the model) and
        item-level mutation (blocked by the proxy).  Values stored *inside*
        metadata should themselves be immutable (str, int, bool, float, None)
        to maintain the shallow-immutability contract.  Nested mutable objects
        (lists, dicts) passed as metadata values are the caller's
        responsibility and are NOT frozen by the proxy.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    from_phase: WorkflowPhase
    to_phase: WorkflowPhase
    triggered_by: str = Field(
        description="What caused this transition (component name, event name, etc.)",
    )
    reason: str = Field(default="", description="Human-readable explanation")
    occurred_at: datetime = Field(default_factory=_utcnow)
    metadata: MappingProxyType = Field(
        default_factory=lambda: MappingProxyType({}),
        description=(
            "Arbitrary structured data attached to this transition. "
            "Stored as MappingProxyType to prevent in-place key mutation. "
            "Primitive values (str, int, bool, float, None) are recommended; "
            "nested mutable objects are caller-controlled."
        ),
    )

    @field_validator("metadata", mode="before")
    @classmethod
    def coerce_to_proxy(cls, v: Any) -> MappingProxyType:
        """
        Accept dict or MappingProxyType; coerce to MappingProxyType.

        The input dict is *copied* (via dict()) before being wrapped so that the
        resulting proxy is independent from the caller's source dict.  Without
        this copy, a caller retaining a reference to the original dict could
        observe mutations through the proxy.

        The copy is shallow: values that are themselves mutable objects remain
        mutable.  Callers should store only primitive values in metadata.
        """
        if isinstance(v, MappingProxyType):
            # Already a proxy: re-wrap a copy so the proxy is independent of
            # whatever underlying dict the original proxy referenced.
            return MappingProxyType(dict(v))
        if isinstance(v, dict):
            return MappingProxyType(dict(v))
        raise ValueError(
            f"metadata must be a dict or MappingProxyType, got {type(v).__name__!r}"
        )

    @field_serializer("metadata")
    def serialize_metadata(self, v: MappingProxyType, _info: Any) -> dict[str, Any]:
        """Serialize MappingProxyType as a plain dict for JSON output."""
        return dict(v)


# ---------------------------------------------------------------------------
# WorkflowRun -- the complete runtime state of one task
# ---------------------------------------------------------------------------


class WorkflowRun(BaseModel):
    """
    Immutable snapshot of the complete state of one autonomous engineering run.

    WorkflowRun is the single authoritative record of:
      - what task is being worked on (issue)
      - what phase the run is currently in
      - all data produced so far (repository, map, context, plans, results)
      - every state transition that has occurred (the transition_log)

    Mutation contract:
        Never mutate a WorkflowRun directly.
        All changes go through WorkflowRun.transition(), which validates the
        transition and returns a NEW WorkflowRun with updated state.

    Serialization:
        .model_dump_json() produces a complete, lossless snapshot.
        WorkflowRun.model_validate_json(s) reconstructs from that snapshot.
    """

    model_config = ConfigDict(frozen=True)

    # Identity
    run_id: str = Field(description="Unique identifier for this run")
    task_id: str = Field(description="Identifier for the overall task")

    # Input
    issue: Issue

    # Current phase
    phase: WorkflowPhase = WorkflowPhase.INITIALISED

    # Data produced during the run (all optional -- populated as phases complete)
    repository: Repository | None = None
    repository_map: RepositoryMap | None = None
    context: tuple[CodeContext, ...] = Field(default=())
    current_plan: ImplementationPlan | None = None
    repair_attempts: tuple[RepairAttempt, ...] = Field(default=())
    last_execution_result: ExecutionResult | None = None
    last_test_suite_result: TestSuiteResult | None = None
    patch_summary: PatchSummary | None = None
    review_result: ReviewResult | None = None
    final_result: FinalResult | None = None
    failure: FailureDetail | None = None

    # Audit log -- grows with each transition
    transition_log: tuple[TransitionRecord, ...] = Field(default=())

    # Timestamps
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    # -----------------------------------------------------------------------
    # State machine
    # -----------------------------------------------------------------------

    def transition(
        self,
        to_phase: WorkflowPhase,
        triggered_by: str,
        reason: str = "",
        **updates: Any,
    ) -> "WorkflowRun":
        """
        Validate and perform a state transition, returning a new WorkflowRun.

        Args:
            to_phase:     The target phase to transition to.
            triggered_by: The component/event that triggered this transition.
            reason:       Optional human-readable explanation.
            **updates:    Field values to set on the new WorkflowRun.
                          Only fields declared on WorkflowRun are accepted;
                          pydantic will raise ValidationError on unknown fields.

        Returns:
            A new WorkflowRun in the target phase with the provided updates applied.

        Raises:
            TerminalStateError:     If the current phase is terminal.
            InvalidTransitionError: If (current, to_phase) is not in VALID_TRANSITIONS.
            pydantic.ValidationError: If any **updates value fails field validation.
        """
        # Guard 1: terminal state
        if self.phase in TERMINAL_PHASES:
            raise TerminalStateError(self.phase.value)

        # Guard 2: transition validity
        if (self.phase, to_phase) not in VALID_TRANSITIONS:
            raise InvalidTransitionError(self.phase.value, to_phase.value)

        now = _utcnow()
        record = TransitionRecord(
            from_phase=self.phase,
            to_phase=to_phase,
            triggered_by=triggered_by,
            reason=reason,
            occurred_at=now,
        )

        # Build the updated field dict.
        # model_dump() serializes nested models to dicts; model_validate()
        # will reconstruct them. The 'mode="python"' keeps Python objects
        # (datetime, Path, Enum) as-is for round-trip fidelity.
        current_data = self.model_dump(mode="python")
        current_data.update(updates)
        current_data["phase"] = to_phase
        current_data["updated_at"] = now
        # Append the new TransitionRecord (as a dict so pydantic can validate it)
        current_data["transition_log"] = list(self.transition_log) + [record]

        return WorkflowRun.model_validate(current_data)

    # -----------------------------------------------------------------------
    # Convenience queries
    # -----------------------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        """True iff this run is in a terminal state (no further transitions)."""
        return self.phase in TERMINAL_PHASES

    @property
    def current_attempt_number(self) -> int:
        """The 1-based number of the next repair attempt (1 = first attempt)."""
        return len(self.repair_attempts) + 1

    @property
    def elapsed_seconds(self) -> float:
        """Wall-clock seconds since this run was created."""
        return (datetime.now(tz=timezone.utc) - self.created_at).total_seconds()
"""
domain/errors.py -- Failure taxonomy for the autonomous workflow.

Provides a structured hierarchy of failure categories so the system can answer
"Why did this run fail?" with precision rather than a boolean.

Design notes:
- FailureCategory uses str-mixin so values serialize naturally to JSON strings.
- Categories are intentionally coarse -- enough to route diagnosis and populate
  evaluation metrics without requiring exhaustive sub-classification up front.
- WorkflowError and its subclasses are *programmatic* errors (bugs), not domain
  failure representations. Domain failures are FailureDetail objects carried
  inside WorkflowRun, not Python exceptions raised to the caller.
"""
from __future__ import annotations

import enum


class FailureCategory(str, enum.Enum):
    """
    Broad categories of failure that the autonomous workflow can encounter.

    Using str-mixin so the value serializes naturally to JSON as a string
    (e.g. "test_failure") rather than as an enum repr.

    These categories are intentionally coarse -- enough to route diagnosis
    without requiring exhaustive sub-classification up front.
    """

    # Input / configuration problems
    INVALID_INPUT = "invalid_input"            # Bad issue, repo URL, or config
    CONFIGURATION = "configuration"            # Missing or invalid env/config

    # Repository problems
    REPOSITORY_ACQUISITION = "repository_acquisition"  # Clone/fetch failed
    REPOSITORY_UNDERSTANDING = "repository_understanding"  # Map/scan failed

    # Planning and implementation
    RETRIEVAL = "retrieval"                    # Context retrieval failed
    PLANNING = "planning"                      # LLM couldn't produce valid plan
    IMPLEMENTATION = "implementation"          # Code modification failed
    PATCH_APPLICATION = "patch_application"   # Patch couldn't be applied cleanly

    # Execution
    DEPENDENCY_INSTALLATION = "dependency_installation"  # pip/poetry failed
    TEST_FAILURE = "test_failure"              # Tests ran but did not pass
    EXECUTION_ERROR = "execution_error"        # Test runner crashed / unhandled
    TIMEOUT = "timeout"                        # Wall-clock time limit exceeded
    RESOURCE_LIMIT = "resource_limit"          # Memory/CPU limit exceeded

    # Control flow
    REPAIR_EXHAUSTED = "repair_exhausted"      # Max repair iterations reached
    REVIEW_REJECTED = "review_rejected"        # Independent reviewer rejected

    # Safety / security
    SECURITY_VIOLATION = "security_violation"  # Sandbox escape or policy breach

    # Infrastructure
    INFRASTRUCTURE = "infrastructure"          # Docker unavailable, network, etc.

    # Unknown -- should be minimized but cannot be eliminated
    UNKNOWN = "unknown"


class WorkflowError(Exception):
    """
    Base exception for workflow-level *programmatic* errors.

    Distinguishes bugs (WorkflowError subclasses raised as exceptions) from
    expected domain failures (represented as FailureDetail in WorkflowRun).
    """


class InvalidTransitionError(WorkflowError):
    """
    Raised when a caller attempts a state transition that is not in
    VALID_TRANSITIONS.
    """

    def __init__(self, from_state: str, to_state: str, reason: str = "") -> None:
        self.from_state = from_state
        self.to_state = to_state
        msg = f"Invalid transition: {from_state!r} -> {to_state!r}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


class TerminalStateError(WorkflowError):
    """
    Raised when a caller attempts to transition out of a terminal state
    (COMPLETED, FAILED, or ABANDONED).
    """

    def __init__(self, state: str) -> None:
        self.state = state
        super().__init__(f"Cannot transition out of terminal state: {state!r}")
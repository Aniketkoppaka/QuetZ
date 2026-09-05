"""
autonomous_engineer.domain -- Core domain models and workflow state machine.

Public API surface:

    # Errors & failure taxonomy
    from autonomous_engineer.domain import FailureCategory, FailureDetail
    from autonomous_engineer.domain import WorkflowError, InvalidTransitionError, TerminalStateError

    # Domain models
    from autonomous_engineer.domain import Issue, Repository, RepositoryMap
    from autonomous_engineer.domain import CodeContext, ImplementationPlan
    from autonomous_engineer.domain import ExecutionResult, TestSuiteResult, TestCaseResult, TestOutcome
    from autonomous_engineer.domain import RepairAttempt, ReviewResult, ReviewVerdict
    from autonomous_engineer.domain import PatchSummary, FinalResult

    # Workflow state machine
    from autonomous_engineer.domain import WorkflowPhase, WorkflowRun, TransitionRecord
    from autonomous_engineer.domain import VALID_TRANSITIONS, TERMINAL_PHASES

Status: Milestone 1.
"""
from autonomous_engineer.domain.errors import (
    FailureCategory,
    InvalidTransitionError,
    TerminalStateError,
    WorkflowError,
)
from autonomous_engineer.domain.models import (
    ClassSymbol,
    CodeContext,
    ContextBudget,
    EvidenceSource,
    ExecutionResult,
    FailureDetail,
    FinalResult,
    FunctionSymbol,
    ImplementationPlan,
    ImplementationStep,
    ImportStatement,
    Issue,
    ParseFailure,
    PatchSummary,
    PythonModuleMap,
    RepairAttempt,
    Repository,
    RepositoryMap,
    RetrievalItem,
    RetrievalReason,
    RetrievalResult,
    ReviewResult,
    ReviewVerdict,
    StepEvidence,
    StepOperation,
    TestCaseResult,
    TestOutcome,
    TestSuiteResult,
)
from autonomous_engineer.domain.states import (
    TERMINAL_PHASES,
    VALID_TRANSITIONS,
    TransitionRecord,
    WorkflowPhase,
    WorkflowRun,
)

__all__ = [
    # errors
    "FailureCategory",
    "InvalidTransitionError",
    "TerminalStateError",
    "WorkflowError",
    # models
    "ClassSymbol",
    "CodeContext",
    "ContextBudget",
    "EvidenceSource",
    "ExecutionResult",
    "FailureDetail",
    "FinalResult",
    "FunctionSymbol",
    "ImplementationPlan",
    "ImplementationStep",
    "ImportStatement",
    "Issue",
    "ParseFailure",
    "PatchSummary",
    "PythonModuleMap",
    "RepairAttempt",
    "Repository",
    "RepositoryMap",
    "RetrievalItem",
    "RetrievalReason",
    "RetrievalResult",
    "ReviewResult",
    "ReviewVerdict",
    "StepEvidence",
    "StepOperation",
    "TestCaseResult",
    "TestOutcome",
    "TestSuiteResult",
    # states
    "TERMINAL_PHASES",
    "VALID_TRANSITIONS",
    "TransitionRecord",
    "WorkflowPhase",
    "WorkflowRun",
]
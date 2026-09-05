"""
domain/models.py -- Core domain models for the autonomous workflow.

All models are immutable (frozen=True). The domain layer has no external
dependencies beyond pydantic -- no LLM SDKs, GitHub clients, Docker, or
retrieval databases.

Design principles:
- Explicit fields with narrow types rather than open dicts.
- Optional values use Optional[T] = None, never a sentinel string.
- Timestamps are always UTC datetime objects, serialized to ISO 8601.
- Identifiers are plain strings (UUIDs or similar) -- no DB rows yet.
- Every model can be round-tripped through JSON without data loss.
- tuple[T, ...] is used for ordered collections to enforce immutability.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utcnow() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(tz=timezone.utc)


def _new_id() -> str:
    """Generate a new random identifier."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Input domain objects
# ---------------------------------------------------------------------------


class Issue(BaseModel):
    """
    Represents a GitHub issue or software-engineering task to be resolved.

    This is the primary input to the autonomous workflow. It carries enough
    information to begin work without requiring a live GitHub connection at
    the domain layer.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Opaque identifier, e.g. 'owner/repo#42'")
    title: str = Field(description="Short issue title")
    body: str = Field(description="Full issue description / problem statement")
    repository_url: str = Field(description="HTTPS or SSH URL of the target repository")
    base_branch: str = Field(default="main", description="Branch to resolve the issue against")
    labels: tuple[str, ...] = Field(default=(), description="Issue labels")
    created_at: datetime | None = Field(default=None, description="When the issue was filed")

    @field_validator("id", "title", "body", "repository_url")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Field must not be blank")
        return v


class Repository(BaseModel):
    """
    Represents a locally acquired copy of the target repository.

    Produced by the repository-acquisition component. The workspace_path
    is where modifications will be made -- it must be an isolated copy so
    that the original clone is never altered.
    """

    model_config = ConfigDict(frozen=True)

    url: str = Field(description="Remote URL the repo was cloned from")
    workspace_path: Path = Field(description="Absolute path to the isolated workspace copy")
    commit_sha: str = Field(description="The exact commit SHA checked out")
    branch: str = Field(default="", description="The branch name that was checked out if applicable")
    requested_revision: str = Field(
        default="",
        description="The revision requested (e.g. branch, tag, or commit SHA)",
    )
    acquired_at: datetime = Field(default_factory=_utcnow)


class ImportStatement(BaseModel):
    """
    Represents an imported module or symbol in a Python file.

    Captures syntactic import structure without attempting cross-file semantic resolution.
    """

    model_config = ConfigDict(frozen=True)

    module: str | None = Field(
        default=None,
        description="Source module name (e.g. 'os.path' or 'math')",
    )
    names: tuple[str, ...] = Field(
        default=(),
        description="Names imported (e.g. ('sqrt', 'ceil') or ('os',))",
    )
    alias: str | None = Field(
        default=None,
        description="Import alias if specified (e.g. 'np' for 'import numpy as np')",
    )
    is_from: bool = Field(
        default=False,
        description="True for 'from ... import ...', False for 'import ...'",
    )
    level: int = Field(
        default=0,
        ge=0,
        description="Relative import dot level (e.g. 1 for 'from .utils import x')",
    )
    line_number: int = Field(ge=1, description="1-based source line number")


class FunctionSymbol(BaseModel):
    """
    Represents a function or method defined in a Python module.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Simple function name (e.g. 'process_data')")
    qualified_name: str = Field(
        description="Dotted qualified name (e.g. 'DataProcessor.process_data' or 'helper')",
    )
    line_number: int = Field(ge=1, description="1-based starting line number")
    end_line_number: int | None = Field(
        default=None,
        ge=1,
        description="1-based ending line number if available",
    )
    is_async: bool = Field(default=False, description="True for 'async def'")
    is_method: bool = Field(default=False, description="True if defined inside a class")
    decorators: tuple[str, ...] = Field(
        default=(),
        description="Syntactic string representation of decorators (e.g. '@property')",
    )
    parameters: tuple[str, ...] = Field(
        default=(),
        description="Parameter names in signature",
    )
    docstring: str | None = Field(
        default=None,
        description="Extracted docstring if present",
    )


class ClassSymbol(BaseModel):
    """
    Represents a class definition in a Python module.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Simple class name (e.g. 'RepositoryAnalyzer')")
    qualified_name: str = Field(
        description="Dotted qualified name (e.g. 'OuterClass.NestedClass')",
    )
    line_number: int = Field(ge=1, description="1-based starting line number")
    end_line_number: int | None = Field(
        default=None,
        ge=1,
        description="1-based ending line number if available",
    )
    base_classes: tuple[str, ...] = Field(
        default=(),
        description="Syntactic names of base classes (e.g. ('BaseModel', 'Generic[T]'))",
    )
    decorators: tuple[str, ...] = Field(
        default=(),
        description="Syntactic string representation of class decorators",
    )
    methods: tuple[FunctionSymbol, ...] = Field(
        default=(),
        description="Methods defined directly on this class",
    )
    nested_classes: tuple[ClassSymbol, ...] = Field(
        default=(),
        description="Classes defined within this class",
    )
    docstring: str | None = Field(
        default=None,
        description="Extracted class docstring if present",
    )


class ParseFailure(BaseModel):
    """
    Records a structured parsing or decoding failure for a specific file.

    Ensures that a single malformed file does not fail entire repository analysis.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str = Field(description="Repo-relative file path")
    error_type: str = Field(description="Error class name (e.g. 'SyntaxError', 'UnicodeDecodeError')")
    message: str = Field(description="Human-readable error description")
    line_number: int | None = Field(default=None, description="Line number where error occurred")
    offset: int | None = Field(default=None, description="Column offset where error occurred")


class PythonModuleMap(BaseModel):
    """
    Structural map of a single Python source file.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str = Field(description="Repo-relative path using forward slashes")
    module_name: str = Field(description="Dotted module name inferred from path")
    is_test_file: bool = Field(default=False, description="True if filename/path matches test conventions")
    line_count: int = Field(default=0, ge=0, description="Total lines in file")
    docstring: str | None = Field(default=None, description="Module-level docstring")
    imports: tuple[ImportStatement, ...] = Field(default=(), description="Extracted import statements")
    classes: tuple[ClassSymbol, ...] = Field(default=(), description="Top-level class definitions")
    functions: tuple[FunctionSymbol, ...] = Field(default=(), description="Top-level function definitions")


class RepositoryMap(BaseModel):
    """
    Deterministic structural summary of the target repository produced during the
    repository-understanding phase (Milestone 2.2).
    """

    model_config = ConfigDict(frozen=True)

    repository_url: str
    commit_sha: str = Field(default="", description="The exact commit SHA mapped")
    file_count: int = Field(ge=0, description="Total inventoried files in repository")
    python_file_count: int = Field(ge=0, description="Total Python source files discovered")
    non_python_file_paths: tuple[str, ...] = Field(
        default=(),
        description="Sorted repo-relative paths to non-Python files",
    )
    python_modules: tuple[PythonModuleMap, ...] = Field(
        default=(),
        description="Structured AST analysis maps for all parsed Python modules",
    )
    test_file_paths: tuple[str, ...] = Field(
        default=(),
        description="Sorted repo-relative paths identified as candidate test files",
    )
    configuration_file_paths: tuple[str, ...] = Field(
        default=(),
        description="Sorted repo-relative paths to project configuration files",
    )
    parse_failures: tuple[ParseFailure, ...] = Field(
        default=(),
        description="Isolated parse and decoding failures encountered during scanning",
    )
    entry_points: tuple[str, ...] = Field(default=())
    has_pyproject_toml: bool = False
    has_setup_py: bool = False
    has_requirements_txt: bool = False
    scanned_at: datetime = Field(default_factory=_utcnow)
    partial: bool = Field(
        default=False,
        description="True if the scan was incomplete (e.g. hit resource limits)",
    )


class CodeContext(BaseModel):
    """
    A single piece of retrieved context: a file excerpt or symbol definition
    that is relevant to the issue being resolved.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str = Field(description="Repo-relative path to the source file")
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    content: str = Field(description="The actual source text")
    relevance_score: float | None = Field(
        default=None,
        description="Retrieval confidence score, if applicable",
    )
    symbol_name: str | None = Field(
        default=None,
        description="Function/class name if this context was retrieved by symbol",
    )


class RetrievalReason(BaseModel):
    """
    Structured explanation for why a specific code item was retrieved.
    """

    model_config = ConfigDict(frozen=True)

    strategy: str = Field(description="Strategy name (e.g. 'lexical', 'structural_import', 'structural_test')")
    signal: str = Field(description="Specific signal (e.g. 'filename_match', 'symbol_match', 'docstring_match')")
    score_contribution: float = Field(ge=0.0, description="Score contributed by this signal")
    description: str = Field(default="", description="Human-readable explanation of the match")


class RetrievalItem(BaseModel):
    """
    A single retrieved code artifact (file, class, method, or function).
    """

    model_config = ConfigDict(frozen=True)

    file_path: str = Field(description="Repo-relative path using forward slashes")
    symbol_name: str | None = Field(default=None, description="Qualified symbol name if symbol-level")
    symbol_type: str = Field(
        default="file",
        description="Type of item: 'file', 'module', 'class', 'method', 'function', 'test', 'config'",
    )
    start_line: int | None = Field(default=None, ge=1, description="Starting line in source file")
    end_line: int | None = Field(default=None, ge=1, description="Ending line in source file")
    score: float = Field(ge=0.0, description="Total aggregated relevance score")
    reasons: tuple[RetrievalReason, ...] = Field(
        default=(),
        description="Structured list of reasons explaining why this item was retrieved",
    )
    content: str | None = Field(
        default=None,
        description="Optional source excerpt text for this item",
    )


class ContextBudget(BaseModel):
    """
    Resource budget bounding the maximum amount of retrieved context.
    """

    model_config = ConfigDict(frozen=True)

    max_files: int = Field(default=10, ge=1, description="Maximum number of distinct files to retrieve")
    max_symbols: int = Field(default=25, ge=1, description="Maximum total symbols to retrieve")
    max_characters: int = Field(default=40_000, ge=100, description="Maximum total source characters")


class RetrievalResult(BaseModel):
    """
    Complete output of a context retrieval operation.
    """

    model_config = ConfigDict(frozen=True)

    query: str = Field(description="Issue text or search query evaluated")
    items: tuple[RetrievalItem, ...] = Field(
        default=(),
        description="Ranked list of retrieved code items within budget",
    )
    total_candidates_evaluated: int = Field(ge=0, description="Total items considered before budgeting")
    excluded_by_budget_count: int = Field(default=0, ge=0, description="Candidates dropped due to budget")
    strategy_used: str = Field(description="Retrieval strategy name ('lexical', 'structural', 'combined')")
    budget_applied: ContextBudget = Field(default_factory=ContextBudget)
    retrieved_at: datetime = Field(default_factory=_utcnow)

    def deterministic_dict(self) -> dict[str, Any]:
        """Return model dictionary excluding non-deterministic runtime timestamps."""
        return self.model_dump(exclude={"retrieved_at"})


class StepOperation(str, enum.Enum):
    """Types of code modification operations supported in planning steps."""

    MODIFY_SYMBOL = "modify_symbol"
    ADD_SYMBOL = "add_symbol"
    DELETE_SYMBOL = "delete_symbol"
    ADD_FILE = "add_file"
    DELETE_FILE = "delete_file"
    REFACTOR_FILE = "refactor_file"
    UPDATE_CONFIGURATION = "update_configuration"
    ADD_TEST = "add_test"
    UPDATE_TEST = "update_test"


class EvidenceSource(str, enum.Enum):
    """Hierarchy of evidence grounding a plan step."""

    RETRIEVED_CONTEXT = "retrieved_context"
    REPOSITORY_MAP = "repository_map"
    NEW_FILE = "new_file"
    EXPLICIT_ASSUMPTION = "explicit_assumption"
    UNSUPPORTED = "unsupported"


class StepEvidence(BaseModel):
    """
    Evidence grounding an implementation step to verified repository artifacts.
    """

    model_config = ConfigDict(frozen=True)

    source: EvidenceSource = Field(description="Evidence tier grounding this step")
    reference_path: str = Field(description="Repo-relative file path supporting the step")
    reference_symbol: str | None = Field(default=None, description="Symbol name if supported by symbol")
    relevance_reason: str = Field(default="", description="Why this evidence justifies the step")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Evidence confidence score")


class ImplementationStep(BaseModel):
    """
    An atomic, unambiguous implementation step in an ImplementationPlan.
    """

    model_config = ConfigDict(frozen=True)

    step_id: str = Field(description="Unique step identifier, e.g. 'step-1'")
    operation: StepOperation = Field(
        default=StepOperation.MODIFY_SYMBOL,
        description="Type of operation to perform",
    )
    target_file: str = Field(description="Repo-relative target file path")
    target_symbol: str | None = Field(
        default=None,
        description="Target class, method, or function name if symbol-level",
    )
    description: str = Field(description="Concise description of the change to be made")
    rationale: str = Field(default="", description="Why this step is necessary")
    expected_behavior: str = Field(default="", description="Expected outcome after applying step")
    dependencies: tuple[str, ...] = Field(
        default=(),
        description="Step IDs that must be completed prior to executing this step",
    )
    evidence: StepEvidence | None = Field(
        default=None,
        description="Grounding evidence for this step",
    )
    verification_requirement: str = Field(
        default="",
        description="How this step's completion should be tested/verified",
    )
    content: str | None = Field(
        default=None,
        description="Full file content for ADD_FILE or full-file replacement",
    )
    search_content: str | None = Field(
        default=None,
        description="Exact text or symbol block to locate and replace",
    )
    replace_content: str | None = Field(
        default=None,
        description="Exact replacement text to substitute for search_content",
    )


class ImplementationPlan(BaseModel):
    """
    A structured, grounded, validated plan produced by the planning layer.
    """

    model_config = ConfigDict(frozen=True)

    plan_id: str = Field(default_factory=_new_id)
    issue_id: str = Field(default="", description="The issue identifier this plan addresses")
    summary: str = Field(description="Concise objective of the intended change")
    rationale: str = Field(description="Why this change resolves the issue")
    steps: tuple[ImplementationStep, ...] = Field(
        description="Ordered list of atomic implementation steps",
    )
    affected_files: tuple[str, ...] = Field(
        default=(),
        description="Repo-relative paths to all files affected by the plan",
    )
    assumptions: tuple[str, ...] = Field(
        default=(),
        description="Explicit assumptions made by the planner that require validation",
    )
    unresolved_uncertainties: tuple[str, ...] = Field(
        default=(),
        description="Known uncertainties or edge cases requiring runtime verification",
    )
    created_at: datetime = Field(default_factory=_utcnow)
    attempt_number: int = Field(
        default=1,
        ge=1,
        description="Which repair iteration produced this plan",
    )
    planner_version: str = Field(default="1.0", description="Version of the planner contract")

    @field_validator("steps", mode="before")
    @classmethod
    def _coerce_steps(cls, v: Any) -> tuple[ImplementationStep, ...]:
        if not v:
            raise ValueError("ImplementationPlan must have at least one step")
        if isinstance(v, (list, tuple)):
            coerced: list[ImplementationStep] = []
            for idx, item in enumerate(v):
                if isinstance(item, str):
                    coerced.append(
                        ImplementationStep(
                            step_id=f"step-{idx + 1}",
                            operation=StepOperation.MODIFY_SYMBOL,
                            target_file="",
                            description=item,
                            rationale=item,
                        )
                    )
                elif isinstance(item, dict):
                    coerced.append(ImplementationStep.model_validate(item))
                elif isinstance(item, ImplementationStep):
                    coerced.append(item)
                else:
                    raise ValueError(f"Invalid step item: {item}")
            return tuple(coerced)
        return v

    @model_validator(mode="after")
    def _populate_affected_files(self) -> ImplementationPlan:
        if not self.affected_files and self.steps:
            files = tuple(dict.fromkeys(s.target_file for s in self.steps if s.target_file))
            object.__setattr__(self, "affected_files", files)
        return self

    def deterministic_dict(self) -> dict[str, Any]:
        """Return model dictionary excluding non-deterministic runtime timestamps and plan_id."""
        return self.model_dump(exclude={"created_at", "plan_id"})


# ---------------------------------------------------------------------------
# Execution domain objects
# ---------------------------------------------------------------------------


class ExecutionResult(BaseModel):
    """
    The raw output from one sandboxed execution (e.g. running pytest).
    Produced by the execution component and consumed by the test-parsing logic.
    """

    model_config = ConfigDict(frozen=True)

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = Field(ge=0.0)
    timed_out: bool = False
    resource_limit_hit: bool = False
    executed_at: datetime = Field(default_factory=_utcnow)
    command: str = Field(default="", description="The command that was run")

    @property
    def succeeded(self) -> bool:
        """True iff the process exited with code 0 and no resource violations."""
        return self.exit_code == 0 and not self.timed_out and not self.resource_limit_hit


class TestOutcome(str, enum.Enum):
    """Possible outcome of a single test case."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    XFAILED = "xfailed"  # expected failure that did fail (expected)
    XPASSED = "xpassed"  # expected failure that unexpectedly passed


class TestCaseResult(BaseModel):
    """Result of a single test case."""

    model_config = ConfigDict(frozen=True)

    test_id: str = Field(
        description="Unique test identifier, e.g. 'tests/test_foo.py::test_bar'",
    )
    outcome: TestOutcome
    duration_seconds: float | None = None
    message: str | None = Field(
        default=None,
        description="Failure/error message or assertion text",
    )


class TestSuiteResult(BaseModel):
    """
    Structured summary of a full test suite execution.
    Produced by parsing the raw ExecutionResult output.
    """

    model_config = ConfigDict(frozen=True)

    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0)
    skipped: int = Field(ge=0)
    test_cases: tuple[TestCaseResult, ...] = Field(default=())
    parsed_at: datetime = Field(default_factory=_utcnow)
    parse_error: str | None = Field(
        default=None,
        description="Set if the output could not be fully parsed",
    )

    @property
    def all_passed(self) -> bool:
        """True iff no failures, no errors, and output was parseable."""
        return self.failed == 0 and self.errors == 0 and self.parse_error is None

    @property
    def failure_count(self) -> int:
        return self.failed + self.errors


# ---------------------------------------------------------------------------
# Repair / iteration domain objects
# ---------------------------------------------------------------------------

from autonomous_engineer.domain.errors import FailureCategory  # noqa: E402


class FailureDetail(BaseModel):
    """
    Structured representation of why a step failed.

    Combined with FailureCategory, this allows the system (and operators) to
    answer 'Why did this run fail?' with enough precision to route post-mortem
    analysis and inform repair strategy.
    """

    model_config = ConfigDict(frozen=True)

    category: FailureCategory
    message: str = Field(description="Human-readable failure description")
    detail: str = Field(default="", description="Raw error text or traceback excerpt")
    retriable: bool = Field(
        default=False,
        description="Whether a retry/repair attempt is semantically meaningful",
    )


class RepairAttempt(BaseModel):
    """
    Records one iteration of the bounded repair loop.

    The repair loop (implemented in a later milestone) will produce a sequence
    of RepairAttempts. This model preserves enough information to later
    calculate: iteration count, failure progression, time cost, and whether
    the eventual success was achieved.
    """

    model_config = ConfigDict(frozen=True)

    attempt_number: int = Field(ge=1)
    plan: ImplementationPlan
    execution_result: ExecutionResult | None = None
    test_suite_result: TestSuiteResult | None = None
    failure: FailureDetail | None = None
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None

    @property
    def succeeded(self) -> bool:
        """True iff the attempt produced a passing test suite with no failure."""
        return (
            self.test_suite_result is not None
            and self.test_suite_result.all_passed
            and self.failure is None
        )

    @property
    def duration_seconds(self) -> float | None:
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()


# ---------------------------------------------------------------------------
# Review / verification domain objects
# ---------------------------------------------------------------------------


class ReviewVerdict(str, enum.Enum):
    """Possible verdicts from the independent review agent."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"


class ReviewResult(BaseModel):
    """
    The result of the independent review agent's evaluation of the patch.

    Deliberately separated from the implementation agent's view -- the reviewer
    must not see internal reasoning, only the final diff and issue description.
    """

    model_config = ConfigDict(frozen=True)

    verdict: ReviewVerdict
    summary: str = Field(description="One-sentence verdict summary")
    feedback: tuple[str, ...] = Field(
        default=(),
        description="Specific review comments",
    )
    correctness_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional 0-1 confidence that the patch is correct",
    )
    reviewed_at: datetime = Field(default_factory=_utcnow)


class PatchSummary(BaseModel):
    """
    A lightweight summary of the generated patch/diff.

    The actual diff content is stored separately (not in the domain model)
    to avoid bloating the workflow state object with large text payloads.
    """

    model_config = ConfigDict(frozen=True)

    files_modified: tuple[str, ...] = Field(default=())
    files_added: tuple[str, ...] = Field(default=())
    files_deleted: tuple[str, ...] = Field(default=())
    lines_added: int = Field(default=0, ge=0)
    lines_removed: int = Field(default=0, ge=0)
    diff_path: str | None = Field(
        default=None,
        description="Path to the serialized unified diff file",
    )


class FinalResult(BaseModel):
    """
    The terminal outcome of a complete autonomous engineering run.

    Contains enough information to reconstruct what happened, measure
    performance (iteration count, time), and submit to an evaluation harness.
    """

    model_config = ConfigDict(frozen=True)

    task_id: str
    issue_id: str
    resolved: bool = Field(description="True iff the issue was resolved and accepted")
    total_repair_attempts: int = Field(ge=0)
    total_duration_seconds: float | None = None
    patch_summary: PatchSummary | None = None
    pull_request_url: str | None = None
    failure: FailureDetail | None = None
    completed_at: datetime = Field(default_factory=_utcnow)
"""
execution/models.py -- Immutable domain models for safe implementation execution.

Defines execution requests, policies, change records, verification results,
and execution results with deterministic dictionary serialization.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.domain.models import (
    ImplementationPlan,
    ImplementationStep,
    StepOperation,
)


def _utcnow() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(tz=timezone.utc)


def _new_id() -> str:
    """Generate a new random UUID."""
    return str(uuid.uuid4())


class ExecutionStatus(str, enum.Enum):
    """Lifecycle states of implementation execution."""

    PREFLIGHT_FAILED = "preflight_failed"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFICATION_FAILED = "verification_failed"
    ROLLED_BACK = "rolled_back"
    ROLLBACK_FAILED = "rollback_failed"
    FAILED = "failed"


class VerificationType(str, enum.Enum):
    """Categories of post-execution verification checks."""

    SYNTAX_AST = "syntax_ast"
    FILE_EXISTENCE = "file_existence"
    SYMBOL_EXISTENCE = "symbol_existence"
    SUBPROCESS_TEST = "subprocess_test"


class Capability(str, enum.Enum):
    """
    Granular security capabilities governing agent execution.
    """

    CAP_READ_REPO = "cap_read_repo"
    CAP_WRITE_SOURCE = "cap_write_source"
    CAP_CREATE_FILE = "cap_create_file"
    CAP_DELETE_FILE = "cap_delete_file"
    CAP_RUN_TEST = "cap_run_test"
    CAP_NETWORK_READ = "cap_network_read"
    CAP_NETWORK_WRITE = "cap_network_write"
    CAP_GIT_COMMIT = "cap_git_commit"
    CAP_OPEN_PR = "cap_open_pr"
    CAP_COMMENT_PR = "cap_comment_pr"


class RiskLevel(str, enum.Enum):
    """
    Risk stratification levels for autonomous operations.
    """

    R0_READ_ONLY = "r0_read_only"
    R1_LOCAL_MUTATION = "r1_local_mutation"
    R2_TEST_EXECUTION = "r2_test_execution"
    R3_GIT_MUTATION = "r3_git_mutation"
    R4_EXTERNAL_COMMUNICATION = "r4_external_communication"
    R5_PRODUCTION_IMPACT = "r5_production_impact"


class ExecutionPolicy(BaseModel):
    """
    Security and resource boundaries governing plan execution.
    """

    model_config = ConfigDict(frozen=True)

    granted_capabilities: tuple[Capability, ...] = Field(
        default=(
            Capability.CAP_READ_REPO,
            Capability.CAP_WRITE_SOURCE,
            Capability.CAP_CREATE_FILE,
            Capability.CAP_RUN_TEST,
        ),
        description="Explicit capability set granted to the executor",
    )
    max_risk_level: RiskLevel = Field(
        default=RiskLevel.R2_TEST_EXECUTION,
        description="Maximum risk level permitted for autonomous execution",
    )

    allowed_operations: tuple[StepOperation, ...] = Field(
        default=tuple(StepOperation),
        description="Permitted StepOperation values",
    )
    allow_file_deletion: bool = Field(
        default=False,
        description="Whether DELETE_FILE operation is permitted",
    )
    allow_test_execution: bool = Field(
        default=True,
        description="Whether test commands are allowed to run",
    )
    auto_rollback_on_failure: bool = Field(
        default=True,
        description="Whether workspace is automatically restored if any step or verification fails",
    )
    max_changed_files: int = Field(
        default=20,
        ge=1,
        description="Maximum number of files allowed to be modified",
    )
    max_changed_bytes: int = Field(
        default=1_000_000,
        ge=1,
        description="Maximum total bytes allowed to be written across all changes",
    )
    max_execution_time_seconds: float = Field(
        default=60.0,
        ge=1.0,
        description="Maximum wall-clock execution timeout in seconds",
    )
    allowed_test_commands: tuple[str, ...] = Field(
        default=("pytest", "python -m pytest", "unittest", "python -m unittest"),
        description="Allowlisted verification command prefixes",
    )


class EditMatchTelemetry(BaseModel):
    """
    Telemetry recording details of how an edit's search_content was matched in M15.
    """

    model_config = ConfigDict(frozen=True)

    tier_used: int = Field(description="Matching tier used: 1 (exact), 2 (normalized), 3 (symbol-scoped), 4 (fuzzy token)")
    normalization_applied: bool = Field(default=False, description="Whether whitespace/indentation normalization occurred")
    symbol_scoped: bool = Field(default=False, description="Whether search was scoped to target_symbol")
    target_symbol: str | None = Field(default=None, description="Target symbol name if symbol-scoped")
    original_anchor_length: int = Field(default=0, ge=0, description="Character length of search_content")
    matched_span_lines: tuple[int, int] | None = Field(default=None, description="1-based (start_line, end_line) of matched text")
    candidate_matches_count: int = Field(default=1, ge=0, description="Number of candidate matches found")
    ambiguity_rejected: bool = Field(default=False, description="True if edit was rejected due to ambiguity")
    outcome: str = Field(default="applied", description="Outcome: 'applied' or 'rejected'")


class FileChangeRecord(BaseModel):
    """
    Immutable audit record of a single file modification, creation, or deletion.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str = Field(description="Repo-relative file path")
    operation: StepOperation = Field(description="Applied operation")
    original_content: str | None = Field(default=None, description="Pre-change content if file existed")
    new_content: str | None = Field(default=None, description="Post-change content if file exists")
    original_hash: str | None = Field(default=None, description="SHA256 hash before change")
    new_hash: str | None = Field(default=None, description="SHA256 hash after change")
    applied_at: datetime = Field(default_factory=_utcnow)
    match_telemetry: EditMatchTelemetry | None = Field(
        default=None,
        description="M15 edit matching telemetry",
    )


class VerificationResult(BaseModel):
    """
    Outcome of an individual static or dynamic verification check.
    """

    model_config = ConfigDict(frozen=True)

    verification_type: VerificationType = Field(description="Type of verification performed")
    target: str = Field(description="Target file, symbol, or command verified")
    passed: bool = Field(description="True if check succeeded")
    exit_code: int | None = Field(default=None, description="Exit code if subprocess command")
    stdout: str = Field(default="", description="Captured bounded stdout")
    stderr: str = Field(default="", description="Captured bounded stderr")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Check duration in ms")
    error_message: str | None = Field(default=None, description="Failure diagnostics if failed")


class ExecutionRequest(BaseModel):
    """
    Formal input contract for executing an ImplementationPlan in a workspace.
    """

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(default_factory=_new_id)
    workspace_path: Path = Field(description="Root path of the acquired workspace")
    plan: ImplementationPlan = Field(description="Validated ImplementationPlan")
    policy: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    expected_commit_sha: str | None = Field(default=None, description="Expected repository commit SHA")
    initial_file_hashes: dict[str, str] = Field(
        default_factory=dict,
        description="Expected SHA256 hashes of target files for stale-plan detection",
    )


class PlanExecutionResult(BaseModel):
    """
    Complete audit-safe outcome of an implementation execution run.
    """

    model_config = ConfigDict(frozen=True)

    execution_id: str = Field(default_factory=_new_id)
    plan_id: str = Field(description="Identifier of executed plan")
    status: ExecutionStatus = Field(description="Final execution lifecycle status")
    changes: tuple[FileChangeRecord, ...] = Field(default=(), description="All file changes performed")
    verifications: tuple[VerificationResult, ...] = Field(default=(), description="All verification checks run")
    rolled_back: bool = Field(default=False, description="True if changes were rolled back")
    error_message: str | None = Field(default=None, description="Failure diagnostic message if execution failed")
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime = Field(default_factory=_utcnow)

    @property
    def succeeded(self) -> bool:
        """True iff execution completed successfully and all verifications passed."""
        return self.status == ExecutionStatus.COMPLETED and not self.rolled_back

    def deterministic_dict(self) -> dict[str, Any]:
        """Return model dictionary excluding non-deterministic runtime timestamps and UUIDs."""
        return self.model_dump(
            exclude={
                "execution_id": True,
                "started_at": True,
                "completed_at": True,
                "changes": {"__all__": {"applied_at"}},
                "verifications": {"__all__": {"duration_ms"}},
            }
        )


class VerificationCertificate(BaseModel):
    """
    Cryptographically verifiable proof artifact documenting execution, verification, and safety.
    """

    model_config = ConfigDict(frozen=True)

    certificate_id: str = Field(default_factory=_new_id)
    plan_id: str = Field(description="Identifier of executed plan")
    issue_id: str = Field(description="Identifier of target issue")
    status: ExecutionStatus = Field(description="Execution lifecycle status")
    files_modified: tuple[str, ...] = Field(default=(), description="Files modified during execution")
    files_created: tuple[str, ...] = Field(default=(), description="Files created during execution")
    files_deleted: tuple[str, ...] = Field(default=(), description="Files deleted during execution")
    static_ast_passed: bool = Field(description="True iff all modified Python files passed AST syntax checks")
    test_verification_passed: bool = Field(description="True iff test suite verification succeeded")
    rolled_back: bool = Field(description="True if workspace was rolled back")
    unauthorized_modifications_detected: bool = Field(
        default=False,
        description="True if modifications outside plan authority occurred",
    )
    anchor_tiers_used: tuple[int, ...] = Field(
        default=(),
        description="List of anchor tiers utilized across all steps (1=exact, 2=normalized, 3=symbol, 4=fuzzy)",
    )
    evidence_hash: str = Field(description="SHA256 digest of deterministic plan execution results and changes")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Overall verification confidence score")
    certified_at: datetime = Field(default_factory=_utcnow)

    def to_markdown(self) -> str:
        """Render a clean human-readable verification certificate."""
        return (
            f"# ASE Verification Certificate\n\n"
            f"- **Certificate ID**: `{self.certificate_id}`\n"
            f"- **Issue**: `{self.issue_id}`\n"
            f"- **Plan ID**: `{self.plan_id}`\n"
            f"- **Status**: `{self.status.value.upper()}`\n"
            f"- **Confidence Score**: `{self.confidence_score:.2f}`\n\n"
            f"### Safety & Verification Gates\n"
            f"- **Static AST Validation**: {'PASS' if self.static_ast_passed else 'FAIL'}\n"
            f"- **Dynamic Test Verification**: {'PASS' if self.test_verification_passed else 'FAIL'}\n"
            f"- **Unauthorized Modifications**: {'DETECTED (VIOLATION)' if self.unauthorized_modifications_detected else 'NONE'}\n"
            f"- **Rollback State**: {'ROLLED BACK' if self.rolled_back else 'RETAINED'}\n"
            f"- **Anchor Tiers Used**: {list(self.anchor_tiers_used)}\n\n"
            f"### Cryptographic Evidence\n"
            f"- **Evidence Digest**: `{self.evidence_hash}`\n"
            f"- **Timestamp**: `{self.certified_at.isoformat()}`\n"
        )
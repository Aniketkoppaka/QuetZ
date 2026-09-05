"""
execution -- Safe, deterministic implementation execution and verification engine.

Public API:
  - ExecutionEngine: Primary orchestrator executing validated plans in a workspace.
  - ExecutionRequest: Contract specifying workspace, plan, policy, and stale-check hashes.
  - ExecutionPolicy: Security, resource, and test execution boundaries.
  - PlanExecutionResult: Audit-safe execution result with deterministic serialization.
  - FileChangeRecord: Immutable change record per modified/created/deleted file.
  - ExecutionStatus: Execution lifecycle state enum.
  - VerificationType, VerificationResult: Multi-tier static and dynamic verification.
  - ExecutionPreflight, PreflightResult: Pre-flight validator and DAG ordering.
  - SafeFileEditor: Atomic file modification and snapshot rollback engine.
  - ExecutionVerifier: Static AST/symbol checks and secure subprocess test runner.
  - ExecutionBenchmarkScenario, ExecutionBenchmarkReport, ExecutionBenchmarkHarness: Benchmark harness.
"""
from __future__ import annotations

from autonomous_engineer.execution.benchmark import (
    ExecutionBenchmarkHarness,
    ExecutionBenchmarkReport,
    ExecutionBenchmarkScenario,
)
from autonomous_engineer.execution.engine import ExecutionEngine
from autonomous_engineer.execution.file_editor import SafeFileEditor
from autonomous_engineer.execution.models import (
    Capability,
    ExecutionPolicy,
    ExecutionRequest,
    ExecutionStatus,
    FileChangeRecord,
    PlanExecutionResult,
    RiskLevel,
    VerificationCertificate,
    VerificationResult,
    VerificationType,
)
from autonomous_engineer.execution.preflight import (
    ExecutionPreflight,
    PreflightResult,
)
from autonomous_engineer.execution.verifier import ExecutionVerifier

__all__ = [
    "Capability",
    "ExecutionBenchmarkHarness",
    "ExecutionBenchmarkReport",
    "ExecutionBenchmarkScenario",
    "ExecutionEngine",
    "ExecutionPolicy",
    "ExecutionPreflight",
    "ExecutionRequest",
    "ExecutionStatus",
    "ExecutionVerifier",
    "FileChangeRecord",
    "PlanExecutionResult",
    "PreflightResult",
    "RiskLevel",
    "SafeFileEditor",
    "VerificationCertificate",
    "VerificationResult",
    "VerificationType",
]

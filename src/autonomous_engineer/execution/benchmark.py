"""
execution/benchmark.py -- Deterministic execution and verification benchmark harness.

Evaluates ExecutionEngine across 13 required scenarios covering happy paths,
preflight rejections, stale hash detection, verification failures, security violations, and rollbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.execution.engine import ExecutionEngine
from autonomous_engineer.execution.models import (
    ExecutionRequest,
    ExecutionStatus,
    PlanExecutionResult,
)


class ExecutionBenchmarkScenario(BaseModel):
    """Specification of an execution benchmark scenario."""

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(description="Unique scenario ID (e.g. 'EXEC-VALID-01')")
    name: str = Field(description="Human readable name")
    category: str = Field(description="Scenario category")
    expected_status: ExecutionStatus = Field(description="Expected final ExecutionStatus")
    expected_rolled_back: bool = Field(default=False, description="Expected rollback boolean state")
    description: str = Field(default="")


@dataclass(frozen=True)
class ExecutionBenchmarkReport:
    """Aggregated evaluation metrics for execution benchmark scenarios."""

    total_scenarios: int
    passed_scenarios: int
    accuracy: float
    preflight_rejection_correctness: float
    rollback_success_rate: float
    verification_classification_correctness: float
    case_results: tuple[dict[str, Any], ...]


class ExecutionBenchmarkHarness:
    """Executes and reports on execution benchmark test cases."""

    def evaluate_case(
        self,
        engine: ExecutionEngine,
        request: ExecutionRequest,
        scenario: ExecutionBenchmarkScenario,
        test_command: str | None = None,
    ) -> dict[str, Any]:
        """Execute a single scenario and compare result against expected invariants."""
        res: PlanExecutionResult = engine.execute(request, test_command=test_command)

        matched_status = (res.status == scenario.expected_status)
        matched_rollback = (res.rolled_back == scenario.expected_rolled_back)
        passed = matched_status and matched_rollback

        return {
            "case_id": scenario.case_id,
            "name": scenario.name,
            "category": scenario.category,
            "expected_status": scenario.expected_status.value,
            "actual_status": res.status.value,
            "expected_rolled_back": scenario.expected_rolled_back,
            "actual_rolled_back": res.rolled_back,
            "passed": passed,
            "error_message": res.error_message,
        }
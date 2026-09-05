"""
execution/engine.py -- Primary implementation execution engine.

Coordinates:
1. Pre-flight validation & plan authority enforcement.
2. Topological step-by-step file execution.
3. Multi-tier static (AST syntax, symbols) and dynamic (subprocess test) verification.
4. Automatic rollback upon failure.
5. Deterministic execution result generation.
"""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from autonomous_engineer.domain.models import StepOperation
from autonomous_engineer.execution.file_editor import SafeFileEditor
from autonomous_engineer.execution.models import (
    ExecutionPolicy,
    ExecutionRequest,
    ExecutionStatus,
    PlanExecutionResult,
    VerificationCertificate,
    VerificationResult,
    _utcnow,
)
from autonomous_engineer.execution.preflight import ExecutionPreflight, PreflightResult
from autonomous_engineer.execution.verifier import ExecutionVerifier


class ExecutionEngine:
    """Orchestrates safe, atomic, auditable plan execution inside a workspace."""

    def __init__(
        self,
        preflight: ExecutionPreflight | None = None,
        verifier: ExecutionVerifier | None = None,
    ) -> None:
        self._preflight = preflight or ExecutionPreflight()
        self._verifier = verifier or ExecutionVerifier()

    def execute(
        self,
        request: ExecutionRequest,
        test_command: str | None = None,
    ) -> PlanExecutionResult:
        """
        Execute an ImplementationPlan against the workspace specified in ExecutionRequest.

        Args:
            request: Formal ExecutionRequest contract.
            test_command: Optional test command override (e.g. 'pytest tests/test_auth.py').

        Returns:
            PlanExecutionResult documenting execution status, changes, verifications, and rollback.
        """
        start_time = _utcnow()
        plan_id = request.plan.plan_id
        workspace = request.workspace_path.resolve()
        policy = request.policy

        # 1. Pre-Flight Validation
        preflight_res: PreflightResult = self._preflight.run_preflight(request)
        if not preflight_res.is_valid:
            return PlanExecutionResult(
                plan_id=plan_id,
                status=ExecutionStatus.PREFLIGHT_FAILED,
                error_message="; ".join(preflight_res.errors),
                started_at=start_time,
                completed_at=_utcnow(),
            )

        editor = SafeFileEditor()
        step_exec_error: str | None = None

        # 2. Sequential Step Execution in Topological Order
        for step in preflight_res.ordered_steps:
            try:
                editor.apply_step(workspace, step)
            except Exception as e:
                step_exec_error = f"Step {step.step_id!r} failed during execution: {e}"
                break

        # If any step failed execution, trigger rollback
        if step_exec_error is not None:
            if policy.auto_rollback_on_failure:
                rb_success, rb_err = editor.rollback(workspace)
                status = ExecutionStatus.ROLLED_BACK if rb_success else ExecutionStatus.ROLLBACK_FAILED
                rb_msg = f" (Rollback failed: {rb_err})" if not rb_success else ""
                return PlanExecutionResult(
                    plan_id=plan_id,
                    status=status,
                    changes=editor.applied_changes,
                    rolled_back=rb_success,
                    error_message=f"{step_exec_error}{rb_msg}",
                    started_at=start_time,
                    completed_at=_utcnow(),
                )
            else:
                return PlanExecutionResult(
                    plan_id=plan_id,
                    status=ExecutionStatus.FAILED,
                    changes=editor.applied_changes,
                    rolled_back=False,
                    error_message=step_exec_error,
                    started_at=start_time,
                    completed_at=_utcnow(),
                )

        # 3. Post-Execution Multi-Tier Verification
        verifications: list[VerificationResult] = []

        # Tier 1: Static AST and symbol verification
        static_results = self._verifier.verify_static(
            workspace=workspace,
            changes=editor.applied_changes,
            steps=preflight_res.ordered_steps,
        )
        verifications.extend(static_results)

        static_passed = all(r.passed for r in static_results)

        # Tier 2: Dynamic test runner subprocess
        if static_passed and policy.allow_test_execution:
            test_result = self._verifier.verify_tests(
                workspace=workspace,
                policy=policy,
                command_override=test_command,
            )
            verifications.append(test_result)

        all_verifications_passed = all(v.passed for v in verifications)

        if all_verifications_passed:
            return PlanExecutionResult(
                plan_id=plan_id,
                status=ExecutionStatus.COMPLETED,
                changes=editor.applied_changes,
                verifications=tuple(verifications),
                rolled_back=False,
                started_at=start_time,
                completed_at=_utcnow(),
            )

        # 4. Handle Verification Failure & Auto-Rollback
        failed_checks = [f"[{v.verification_type.value}] {v.target}: {v.error_message}" for v in verifications if not v.passed]
        failure_diag = "; ".join(failed_checks) or "Verification checks failed."

        if policy.auto_rollback_on_failure:
            rb_success, rb_err = editor.rollback(workspace)
            status = ExecutionStatus.ROLLED_BACK if rb_success else ExecutionStatus.ROLLBACK_FAILED
            rb_msg = f" (Rollback failed: {rb_err})" if not rb_success else ""
            return PlanExecutionResult(
                plan_id=plan_id,
                status=status,
                changes=editor.applied_changes,
                verifications=tuple(verifications),
                rolled_back=rb_success,
                error_message=f"{failure_diag}{rb_msg}",
                started_at=start_time,
                completed_at=_utcnow(),
            )
        else:
            return PlanExecutionResult(
                plan_id=plan_id,
                status=ExecutionStatus.VERIFICATION_FAILED,
                changes=editor.applied_changes,
                verifications=tuple(verifications),
                rolled_back=False,
                error_message=failure_diag,
                started_at=start_time,
                completed_at=_utcnow(),
            )

    def generate_certificate(
        self,
        request: ExecutionRequest,
        result: PlanExecutionResult,
        issue_id: str = "unknown",
    ) -> VerificationCertificate:
        """
        Generate an immutable cryptographic VerificationCertificate from an ExecutionRequest and PlanExecutionResult.
        """
        files_modified = tuple(
            c.file_path for c in result.changes if c.operation not in (StepOperation.ADD_FILE, StepOperation.ADD_TEST, StepOperation.DELETE_FILE)
        )
        files_created = tuple(
            c.file_path for c in result.changes if c.operation in (StepOperation.ADD_FILE, StepOperation.ADD_TEST)
        )
        files_deleted = tuple(
            c.file_path for c in result.changes if c.operation == StepOperation.DELETE_FILE
        )

        static_passed = all(
            v.passed for v in result.verifications if v.verification_type.value.startswith("syntax")
        ) if result.verifications else False

        test_passed = any(
            v.passed for v in result.verifications if v.verification_type.value == "subprocess_test"
        )

        anchor_tiers: list[int] = []
        for c in result.changes:
            if c.match_telemetry is not None:
                anchor_tiers.append(c.match_telemetry.tier_used)

        # Unauthorized modifications check: were any modified files outside plan.affected_files?
        unauth = False
        if request.plan.affected_files:
            for c in result.changes:
                if c.file_path not in request.plan.affected_files:
                    unauth = True
                    break

        # Compute deterministic evidence hash over execution result dict
        result_dict = result.deterministic_dict()
        evidence_json = json.dumps(result_dict, sort_keys=True)
        evidence_hash = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()

        # Confidence score computation based on verification rigor
        confidence = 0.0
        if result.succeeded:
            confidence = 0.6  # Base pass
            if static_passed:
                confidence += 0.2
            if test_passed:
                confidence += 0.2
        elif result.rolled_back:
            confidence = 0.0

        return VerificationCertificate(
            plan_id=result.plan_id,
            issue_id=issue_id,
            status=result.status,
            files_modified=files_modified,
            files_created=files_created,
            files_deleted=files_deleted,
            static_ast_passed=static_passed,
            test_verification_passed=test_passed,
            rolled_back=result.rolled_back,
            unauthorized_modifications_detected=unauth,
            anchor_tiers_used=tuple(anchor_tiers),
            evidence_hash=evidence_hash,
            confidence_score=min(1.0, confidence),
        )
"""
execution/preflight.py -- Deterministic pre-flight validation and plan authority verification.

Enforces that:
1. Workspace root exists and is confined.
2. Target paths are inside the workspace (no directory traversal or symlink escapes).
3. Plan authority: only declared affected files may be operated on.
4. Concurrency/stale protection: initial file hashes match expectations.
5. Target files and symbols exist on disk for modify/delete operations.
6. Step dependencies form a valid DAG and are topologically sorted for execution.
7. Execution policy rules (allowed operations, file deletion, file limits) are respected.
"""
from __future__ import annotations

import ast
import hashlib
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.domain.models import ImplementationStep, StepOperation
from autonomous_engineer.execution.models import Capability, ExecutionPolicy, ExecutionRequest


class PreflightResult(BaseModel):
    """Result of an ExecutionPreflight inspection."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool = Field(description="True iff all preflight invariants hold")
    errors: tuple[str, ...] = Field(default=(), description="Preflight errors preventing execution")
    warnings: tuple[str, ...] = Field(default=(), description="Non-fatal warnings")
    ordered_steps: tuple[ImplementationStep, ...] = Field(
        default=(),
        description="Topologically sorted implementation steps for execution",
    )


class ExecutionPreflight:
    """Pre-flight validator for execution requests."""

    def run_preflight(self, request: ExecutionRequest) -> PreflightResult:
        """
        Execute deterministic pre-flight validation on the given ExecutionRequest.

        Returns:
            PreflightResult containing validation status and topologically ordered steps.
        """
        errors: list[str] = []
        warnings: list[str] = []
        workspace = request.workspace_path.resolve()
        plan = request.plan
        policy = request.policy

        # 1. Workspace Validity
        if not workspace.exists():
            errors.append(f"Workspace path does not exist: {workspace}")
            return PreflightResult(is_valid=False, errors=tuple(errors))
        if not workspace.is_dir():
            errors.append(f"Workspace path is not a directory: {workspace}")
            return PreflightResult(is_valid=False, errors=tuple(errors))

        # 2. Plan Non-Emptiness & Step Count Limit
        if not plan.steps:
            errors.append("ImplementationPlan has no steps to execute.")
            return PreflightResult(is_valid=False, errors=tuple(errors))

        unique_target_files = {s.target_file for s in plan.steps if s.target_file}
        if len(unique_target_files) > policy.max_changed_files:
            errors.append(
                f"Plan targets {len(unique_target_files)} files, exceeding policy limit of {policy.max_changed_files}."
            )

        # 3. Step Path Boundary & Plan Authority Verification
        for step in plan.steps:
            target = step.target_file.strip()
            if not target:
                errors.append(f"Step {step.step_id!r} has an empty target_file path.")
                continue

            if "\\" in target:
                errors.append(f"Step {step.step_id!r} path {target!r} contains backslashes; must use forward slashes.")
                continue

            if Path(target).is_absolute():
                errors.append(f"Step {step.step_id!r} specifies an absolute path: {target!r}.")
                continue

            # Confinement check
            target_full_path = (workspace / target).resolve()
            try:
                target_full_path.relative_to(workspace)
            except ValueError:
                errors.append(f"Step {step.step_id!r} path {target!r} escapes workspace boundary.")
                continue

            # Plan authority check
            if plan.affected_files and target not in plan.affected_files:
                errors.append(
                    f"Step {step.step_id!r} targets file {target!r} which is not authorized in plan.affected_files."
                )

            # Policy operation check
            if step.operation not in policy.allowed_operations:
                errors.append(
                    f"Step {step.step_id!r} operation {step.operation.value!r} is disabled by execution policy."
                )

            # Granular Capability checks
            if step.operation in (StepOperation.ADD_FILE, StepOperation.ADD_TEST):
                if Capability.CAP_CREATE_FILE not in policy.granted_capabilities:
                    errors.append(
                        f"Step {step.step_id!r} requires CAP_CREATE_FILE, which is not granted by execution policy."
                    )
            elif step.operation == StepOperation.DELETE_FILE:
                if Capability.CAP_DELETE_FILE not in policy.granted_capabilities or not policy.allow_file_deletion:
                    errors.append(
                        f"Step {step.step_id!r} requires CAP_DELETE_FILE, but file deletion is disabled by policy."
                    )
            else:
                # Any modification operation (MODIFY_SYMBOL, REFACTOR_FILE, etc.)
                if Capability.CAP_WRITE_SOURCE not in policy.granted_capabilities:
                    errors.append(
                        f"Step {step.step_id!r} requires CAP_WRITE_SOURCE, which is not granted by execution policy."
                    )

            # Stale file hash checks
            if target in request.initial_file_hashes:
                expected_hash = request.initial_file_hashes[target]
                if not target_full_path.exists():
                    errors.append(
                        f"Step {step.step_id!r}: expected file {target!r} with hash {expected_hash!r}, but file does not exist."
                    )
                else:
                    actual_hash = hashlib.sha256(target_full_path.read_bytes()).hexdigest()
                    if actual_hash != expected_hash:
                        errors.append(
                            f"Step {step.step_id!r}: stale file detected for {target!r}. "
                            f"Expected hash {expected_hash[:8]}..., found {actual_hash[:8]}..."
                        )

            # Target existence and symbol checks for modification operations
            if step.operation in (
                StepOperation.MODIFY_SYMBOL,
                StepOperation.DELETE_SYMBOL,
                StepOperation.DELETE_FILE,
                StepOperation.REFACTOR_FILE,
                StepOperation.UPDATE_CONFIGURATION,
                StepOperation.UPDATE_TEST,
            ):
                if not target_full_path.exists():
                    errors.append(
                        f"Step {step.step_id!r} targets non-existent file {target!r} for operation {step.operation.value!r}."
                    )
                elif step.target_symbol and target.endswith(".py"):
                    # Check if symbol actually exists in the Python file on disk
                    if not self._check_symbol_exists_on_disk(target_full_path, step.target_symbol):
                        errors.append(
                            f"Step {step.step_id!r} specifies target_symbol {step.target_symbol!r}, "
                            f"which was not found in {target!r} on disk."
                        )

            elif step.operation in (StepOperation.ADD_FILE, StepOperation.ADD_TEST):
                if target_full_path.exists():
                    warnings.append(f"Step {step.step_id!r} requests {step.operation.value!r} for existing file {target!r}.")

        # 4. Topological Sort & Dependency Cycle Check
        ordered_steps = self._topological_sort_steps(plan.steps, errors)

        is_valid = len(errors) == 0
        return PreflightResult(
            is_valid=is_valid,
            errors=tuple(errors),
            warnings=tuple(warnings),
            ordered_steps=tuple(ordered_steps) if is_valid else (),
        )

    def _check_symbol_exists_on_disk(self, file_path: Path, symbol_name: str) -> bool:
        """Check if target symbol name exists in AST of file on disk."""
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="replace"), filename=str(file_path))
        except Exception:
            return False

        target_base = symbol_name.split(".")[-1]
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == symbol_name or node.name == target_base:
                    return True
        return False

    def _topological_sort_steps(
        self, steps: tuple[ImplementationStep, ...], errors: list[str]
    ) -> list[ImplementationStep]:
        """Sort steps in dependency order using Kahn's algorithm."""
        step_map = {s.step_id: s for s in steps}
        in_degree: dict[str, int] = {s.step_id: 0 for s in steps}
        graph: dict[str, list[str]] = {s.step_id: [] for s in steps}

        for s in steps:
            for dep in s.dependencies:
                if dep in step_map:
                    graph[dep].append(s.step_id)
                    in_degree[s.step_id] += 1
                else:
                    errors.append(f"Step {s.step_id!r} references unknown dependency {dep!r}.")

        queue = deque([sid for sid, deg in in_degree.items() if deg == 0])
        sorted_ids: list[str] = []

        while queue:
            curr = queue.popleft()
            sorted_ids.append(curr)
            for neighbor in graph[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_ids) != len(steps):
            errors.append("Circular dependency detected among plan steps.")
            return list(steps)

        return [step_map[sid] for sid in sorted_ids]
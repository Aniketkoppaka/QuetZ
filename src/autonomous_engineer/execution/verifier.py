"""
execution/verifier.py -- Multi-tier static analysis and sandboxed test verification engine.

Provides:
1. Static Python AST syntax verification on modified/created files.
2. Symbol presence verification on modified modules.
3. Secure subprocess test execution with allowlisted commands, sanitized environments, and bounded outputs.
"""
from __future__ import annotations

import ast
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from autonomous_engineer.domain.models import ImplementationStep, StepOperation
from autonomous_engineer.execution.models import (
    ExecutionPolicy,
    FileChangeRecord,
    VerificationResult,
    VerificationType,
)


def _sanitize_env() -> dict[str, str]:
    """Create a minimal sanitized environment copy stripping potential secrets."""
    clean_env: dict[str, str] = {}
    for k, v in os.environ.items():
        k_upper = k.upper()
        if any(secret_term in k_upper for secret_term in ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH")):
            continue
        clean_env[k] = v
    return clean_env


class ExecutionVerifier:
    """Performs static and dynamic post-execution verifications."""

    def verify_static(
        self,
        workspace: Path,
        changes: tuple[FileChangeRecord, ...],
        steps: tuple[ImplementationStep, ...],
    ) -> list[VerificationResult]:
        """
        Execute static syntax and symbol checks on all changed files.

        Returns:
            List of VerificationResult records.
        """
        results: list[VerificationResult] = []
        workspace_resolved = workspace.resolve()
        step_by_file = {s.target_file: s for s in steps}
        verified_ast_files: set[str] = set()

        for change in changes:
            target_path = (workspace_resolved / change.file_path).resolve()
            step = step_by_file.get(change.file_path)

            if change.operation == StepOperation.DELETE_FILE:
                # Verify file no longer exists
                passed = not target_path.exists()
                results.append(
                    VerificationResult(
                        verification_type=VerificationType.FILE_EXISTENCE,
                        target=change.file_path,
                        passed=passed,
                        error_message=None if passed else f"Deleted file {change.file_path!r} still exists.",
                    )
                )
                continue

            # Verify file exists
            if not target_path.exists():
                results.append(
                    VerificationResult(
                        verification_type=VerificationType.FILE_EXISTENCE,
                        target=change.file_path,
                        passed=False,
                        error_message=f"Expected modified/created file {change.file_path!r} does not exist on disk.",
                    )
                )
                continue

            # Python AST syntax check
            if change.file_path.endswith(".py"):
                start_t = time.perf_counter()
                try:
                    tree = ast.parse(
                        target_path.read_text(encoding="utf-8", errors="replace"),
                        filename=str(target_path),
                    )
                    latency = round((time.perf_counter() - start_t) * 1000, 2)
                    results.append(
                        VerificationResult(
                            verification_type=VerificationType.SYNTAX_AST,
                            target=change.file_path,
                            passed=True,
                            duration_ms=latency,
                        )
                    )

                    # Symbol presence check if step specifies target_symbol
                    if step and step.target_symbol:
                        sym_found = self._check_symbol_present(tree, step.target_symbol)
                        if step.operation in (StepOperation.MODIFY_SYMBOL, StepOperation.ADD_SYMBOL):
                            results.append(
                                VerificationResult(
                                    verification_type=VerificationType.SYMBOL_EXISTENCE,
                                    target=f"{change.file_path}::{step.target_symbol}",
                                    passed=sym_found,
                                    error_message=None
                                    if sym_found
                                    else f"Symbol {step.target_symbol!r} not found in {change.file_path!r} after edits.",
                                )
                            )

                except SyntaxError as e:
                    latency = round((time.perf_counter() - start_t) * 1000, 2)
                    results.append(
                        VerificationResult(
                            verification_type=VerificationType.SYNTAX_AST,
                            target=change.file_path,
                            passed=False,
                            duration_ms=latency,
                            error_message=f"SyntaxError in {change.file_path}: {e}",
                        )
                    )

        return results

    def verify_tests(
        self,
        workspace: Path,
        policy: ExecutionPolicy,
        command_override: str | None = None,
    ) -> VerificationResult:
        """
        Execute secure test runner subprocess confined within the workspace.

        Returns:
            VerificationResult record.
        """
        if not policy.allow_test_execution:
            return VerificationResult(
                verification_type=VerificationType.SUBPROCESS_TEST,
                target="tests_disabled",
                passed=True,
                stdout="Test execution skipped (disabled by policy).",
            )

        cmd_str = command_override or "pytest"
        clean_cmd = cmd_str.strip()

        # Command allowlist verification
        is_allowed = any(clean_cmd.startswith(prefix) for prefix in policy.allowed_test_commands)
        if not is_allowed:
            return VerificationResult(
                verification_type=VerificationType.SUBPROCESS_TEST,
                target=clean_cmd,
                passed=False,
                exit_code=-1,
                error_message=f"Unauthorized test command: {clean_cmd!r}. Allowed prefixes: {policy.allowed_test_commands}",
            )

        # Parse command into argv list (shell=False)
        try:
            argv = shlex.split(clean_cmd, posix=(os.name != "nt"))
        except Exception as e:
            return VerificationResult(
                verification_type=VerificationType.SUBPROCESS_TEST,
                target=clean_cmd,
                passed=False,
                exit_code=-1,
                error_message=f"Failed to parse test command: {e}",
            )

        start_t = time.perf_counter()
        try:
            proc = subprocess.run(
                argv,
                cwd=str(workspace.resolve()),
                env=_sanitize_env(),
                capture_output=True,
                text=True,
                timeout=policy.max_execution_time_seconds,
                shell=False,
            )
            duration_ms = round((time.perf_counter() - start_t) * 1000, 2)
            passed = (proc.returncode == 0)

            # Bound output sizes to 50KB
            stdout_bounded = proc.stdout[:50000] if proc.stdout else ""
            stderr_bounded = proc.stderr[:50000] if proc.stderr else ""

            return VerificationResult(
                verification_type=VerificationType.SUBPROCESS_TEST,
                target=clean_cmd,
                passed=passed,
                exit_code=proc.returncode,
                stdout=stdout_bounded,
                stderr=stderr_bounded,
                duration_ms=duration_ms,
                error_message=None if passed else f"Test process exited with non-zero code {proc.returncode}.",
            )

        except subprocess.TimeoutExpired as e:
            duration_ms = round((time.perf_counter() - start_t) * 1000, 2)
            return VerificationResult(
                verification_type=VerificationType.SUBPROCESS_TEST,
                target=clean_cmd,
                passed=False,
                exit_code=-1,
                duration_ms=duration_ms,
                error_message=f"Test process timed out after {policy.max_execution_time_seconds}s.",
            )
        except Exception as e:
            duration_ms = round((time.perf_counter() - start_t) * 1000, 2)
            return VerificationResult(
                verification_type=VerificationType.SUBPROCESS_TEST,
                target=clean_cmd,
                passed=False,
                exit_code=-1,
                duration_ms=duration_ms,
                error_message=f"Test execution subprocess error: {e}",
            )

    # Alias for single test execution
    verify_test = verify_tests

    def _check_symbol_present(self, tree: ast.AST, symbol_name: str) -> bool:
        """Check if symbol name appears in parsed AST."""
        target_base = symbol_name.split(".")[-1]
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == symbol_name or node.name == target_base:
                    return True
        return False
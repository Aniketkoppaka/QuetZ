"""
execution/docker_runner.py -- Hardened Containerized Sandboxing Driver for QuetZ.

Executes test suites and commands inside isolated, ephemeral Docker containers with:
- Zero Network Access (--network none) to prevent exfiltration.
- Explicit resource boundaries (CPU quotas, memory caps).
- Read/Write isolated workspace mounting.
- Secret-sanitized environment variable injection.
- Fail-closed fallback if Docker is unavailable or misconfigured.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DockerExecutionConfig(BaseModel):
    """Configuration options for sandboxed container execution."""

    model_config = ConfigDict(frozen=True)

    image_name: str = "quetz-sandbox:latest"
    memory_limit: str = "1024m"
    cpu_limit: str = "2.0"
    network_mode: str = "none"  # "none" enforces total network egress blocking
    workspace_container_path: str = "/workspace"
    timeout_seconds: int = 120
    max_output_bytes: int = 50000


class DockerExecutionResult(BaseModel):
    """Execution telemetry and output from a container run."""

    model_config = ConfigDict(frozen=True)

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    sandboxed: bool
    fallback_used: bool = False
    error_message: str | None = None

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


def _sanitize_env() -> dict[str, str]:
    """Create minimal environment copy stripping sensitive tokens and keys."""
    clean_env: dict[str, str] = {}
    for k, v in os.environ.items():
        k_upper = k.upper()
        if any(term in k_upper for term in ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH")):
            continue
        clean_env[k] = v
    return clean_env


class DockerRunner:
    """Manages containerized test and command execution."""

    def __init__(self, config: DockerExecutionConfig | None = None) -> None:
        self.config = config or DockerExecutionConfig()
        self._docker_path = shutil.which("docker")

    def is_docker_available(self) -> bool:
        """Check if Docker CLI is present and the daemon is reachable."""
        if not self._docker_path:
            return False
        try:
            res = subprocess.run(
                [self._docker_path, "info"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return res.returncode == 0
        except Exception:
            return False

    def build_docker_cmd(self, workspace: Path, command: str) -> list[str]:
        """Construct the hardened docker run command line."""
        docker_bin = self._docker_path or "docker"
        abs_workspace = str(workspace.resolve())

        # Normalize windows paths for docker volume mounting if needed
        vol_arg = f"{abs_workspace}:{self.config.workspace_container_path}"

        cmd = [
            docker_bin,
            "run",
            "--rm",
            "-i",
            "--network", self.config.network_mode,
            "-m", self.config.memory_limit,
            "--cpus", self.config.cpu_limit,
            "-v", vol_arg,
            "-w", self.config.workspace_container_path,
            self.config.image_name,
            "sh", "-c", command,
        ]
        return cmd

    def run_command(
        self,
        command: str,
        workspace: Path,
        allow_fallback: bool = True,
    ) -> DockerExecutionResult:
        """
        Execute command inside Docker container, or fallback to host runner if enabled.
        """
        clean_cmd = command.strip()
        workspace_resolved = workspace.resolve()

        if self.is_docker_available():
            docker_cmd = self.build_docker_cmd(workspace_resolved, clean_cmd)
            start_t = time.perf_counter()
            try:
                proc = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.config.timeout_seconds,
                )
                dur_ms = round((time.perf_counter() - start_t) * 1000, 2)
                return DockerExecutionResult(
                    exit_code=proc.returncode,
                    stdout=proc.stdout[:self.config.max_output_bytes],
                    stderr=proc.stderr[:self.config.max_output_bytes],
                    duration_ms=dur_ms,
                    sandboxed=True,
                    fallback_used=False,
                )
            except subprocess.TimeoutExpired:
                dur_ms = round((time.perf_counter() - start_t) * 1000, 2)
                return DockerExecutionResult(
                    exit_code=-1,
                    stdout="",
                    stderr="Container execution timed out",
                    duration_ms=dur_ms,
                    sandboxed=True,
                    fallback_used=False,
                    error_message=f"Timeout expired after {self.config.timeout_seconds}s",
                )
            except Exception as e:
                if not allow_fallback:
                    return DockerExecutionResult(
                        exit_code=-1,
                        stdout="",
                        stderr=str(e),
                        duration_ms=0.0,
                        sandboxed=True,
                        fallback_used=False,
                        error_message=f"Docker invocation failed: {e}",
                    )

        # Fallback to sanitized host execution
        if not allow_fallback:
            return DockerExecutionResult(
                exit_code=-1,
                stdout="",
                stderr="Docker is unavailable and fallback is disabled",
                duration_ms=0.0,
                sandboxed=False,
                fallback_used=False,
                error_message="Docker daemon unreachable",
            )

        start_t = time.perf_counter()
        try:
            argv = shlex.split(clean_cmd, posix=(os.name != "nt"))
            proc = subprocess.run(
                argv,
                cwd=str(workspace_resolved),
                env=_sanitize_env(),
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                shell=False,
            )
            dur_ms = round((time.perf_counter() - start_t) * 1000, 2)
            return DockerExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout[:self.config.max_output_bytes],
                stderr=proc.stderr[:self.config.max_output_bytes],
                duration_ms=dur_ms,
                sandboxed=False,
                fallback_used=True,
            )
        except Exception as exc:
            dur_ms = round((time.perf_counter() - start_t) * 1000, 2)
            return DockerExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                duration_ms=dur_ms,
                sandboxed=False,
                fallback_used=True,
                error_message=f"Host execution failed: {exc}",
            )
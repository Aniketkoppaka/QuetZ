"""
repository/git_cli.py -- Controlled subprocess wrapper for Git CLI.

Executes Git commands safely:
- shell=False is strictly enforced.
- Environment variables isolate execution (no interactive prompts, no global config).
- Output is captured and typed as GitCommandResult.
- Timeouts and executable lookups are translated into domain repository errors.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from autonomous_engineer.repository.errors import (
    AcquisitionTimeoutError,
    GitUnavailableError,
    RepositoryError,
)


@dataclass(frozen=True)
class GitCommandResult:
    """Immutable result of a Git command execution."""

    returncode: int
    stdout: str
    stderr: str
    command: tuple[str, ...]

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


class GitCli:
    """Controlled interface to the system Git executable."""

    def __init__(self, git_binary: str | None = None) -> None:
        self._git_binary = git_binary

    def get_binary_path(self) -> str:
        """Return the resolved path to the git executable or raise GitUnavailableError."""
        binary = self._git_binary or shutil.which("git")
        if not binary:
            raise GitUnavailableError(
                "Git executable ('git') was not found in system PATH. "
                "Git CLI is required for repository acquisition."
            )
        return binary

    def check_available(self) -> None:
        """Verify that Git is available and can execute."""
        self.get_binary_path()

    def run(
        self,
        args: list[str],
        cwd: Path | None = None,
        timeout: float | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> GitCommandResult:
        """
        Execute a Git command with strict subprocess parameters.

        Args:
            args: Command arguments (excluding the 'git' binary).
            cwd: Working directory for command execution.
            timeout: Maximum execution time in seconds.
            extra_env: Additional environment variables to merge.

        Returns:
            GitCommandResult containing returncode, stdout, stderr.

        Raises:
            GitUnavailableError: If the Git binary cannot be located or executed.
            AcquisitionTimeoutError: If execution exceeds the specified timeout.
            RepositoryError: For unhandled execution errors.
        """
        git_bin = self.get_binary_path()
        full_cmd = [git_bin] + args

        # Build isolated environment
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = ""
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        env["LC_ALL"] = "C"
        if extra_env:
            env.update(extra_env)

        try:
            proc = subprocess.run(
                full_cmd,
                cwd=str(cwd) if cwd else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                shell=False,
                check=False,
            )
            return GitCommandResult(
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                command=tuple(full_cmd),
            )
        except subprocess.TimeoutExpired as exc:
            raise AcquisitionTimeoutError(
                f"Git command timed out after {timeout} seconds: {' '.join(full_cmd)}"
            ) from exc
        except FileNotFoundError as exc:
            raise GitUnavailableError(f"Git executable not found: {git_bin}") from exc
        except Exception as exc:
            raise RepositoryError(
                f"Unexpected error executing git command {' '.join(full_cmd)}: {exc}"
            ) from exc
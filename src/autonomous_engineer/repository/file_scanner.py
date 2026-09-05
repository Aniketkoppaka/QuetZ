"""
repository/file_scanner.py -- Deterministic repository filesystem scanner.

Scans a repository workspace directory and classifies files into:
- Python source files (.py, .pyi)
- Non-Python files
- Candidate test files
- Project configuration files

Applies deterministic sorting and ignores build/cache/vcs directories.
"""
from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

# Standard directory exclusions for repository scanning
DEFAULT_EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "env",
    ".env",
    "build",
    "dist",
    "node_modules",
    ".coverage",
    "htmlcov",
})

# Patterns for identifying project configuration files
CONFIG_PATTERNS: tuple[str, ...] = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements/*.txt",
    "tox.ini",
    "pytest.ini",
    "mypy.ini",
    "ruff.toml",
    ".ruff.toml",
    ".pre-commit-config.yaml",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "environment.yml",
    ".python-version",
)


@dataclass(frozen=True)
class DiscoveredFiles:
    """Deterministic inventory of repository files."""

    python_files: tuple[str, ...]
    non_python_files: tuple[str, ...]
    test_files: tuple[str, ...]
    configuration_files: tuple[str, ...]
    total_count: int


class FileScanner:
    """Scans repository workspaces deterministically."""

    def __init__(
        self,
        excluded_dirs: frozenset[str] | None = None,
    ) -> None:
        self._excluded_dirs = excluded_dirs or DEFAULT_EXCLUDED_DIRS

    def is_test_file(self, relative_path: str) -> bool:
        """
        Check if a file path matches standard Python test conventions.

        Matches:
          - tests/**/*.py or test/**/*.py
          - test_*.py or *_test.py
          - test.py or tests.py
        """
        norm_path = relative_path.replace("\\", "/").lower()
        filename = norm_path.split("/")[-1]

        if not (filename.endswith(".py") or filename.endswith(".pyi")):
            return False

        if (
            filename.startswith("test_")
            or filename.endswith("_test.py")
            or filename.endswith("_test.pyi")
            or filename in ("test.py", "tests.py", "test.pyi", "tests.pyi")
        ):
            return True

        parts = norm_path.split("/")
        if "tests" in parts or "test" in parts:
            return True

        return False

    def is_config_file(self, relative_path: str) -> bool:
        """Check if a file path matches standard Python project configuration files."""
        norm_path = relative_path.replace("\\", "/")
        filename = norm_path.split("/")[-1]

        for pattern in CONFIG_PATTERNS:
            if "/" in pattern:
                if fnmatch.fnmatch(norm_path, pattern):
                    return True
            else:
                if fnmatch.fnmatch(filename, pattern):
                    return True
        return False

    def scan(
        self,
        workspace_path: Path,
        max_file_count: int | None = None,
    ) -> DiscoveredFiles:
        """
        Scan workspace directory and return sorted inventory of files.

        Args:
            workspace_path: Root path of the repository workspace.
            max_file_count: Optional limit on total files to discover.

        Returns:
            DiscoveredFiles with deterministically sorted repository-relative paths.
        """
        python_files: list[str] = []
        non_python_files: list[str] = []
        test_files: list[str] = []
        config_files: list[str] = []

        workspace_resolved = workspace_path.resolve()

        for root, dirs, files in os.walk(workspace_resolved, topdown=True):
            # Prune excluded directories in-place (case-insensitive check)
            dirs[:] = [
                d for d in dirs
                if d.lower() not in self._excluded_dirs
                and not d.endswith(".egg-info")
            ]
            dirs.sort()  # Deterministic directory traversal

            files.sort()  # Deterministic file traversal
            for file in files:
                full_path = Path(root) / file
                try:
                    rel_path = full_path.relative_to(workspace_resolved).as_posix()
                except ValueError:
                    continue

                if rel_path.endswith(".py") or rel_path.endswith(".pyi"):
                    python_files.append(rel_path)
                    if self.is_test_file(rel_path):
                        test_files.append(rel_path)
                else:
                    non_python_files.append(rel_path)

                if self.is_config_file(rel_path):
                    config_files.append(rel_path)

                if max_file_count is not None:
                    current_total = len(python_files) + len(non_python_files)
                    if current_total >= max_file_count:
                        break
            if max_file_count is not None:
                current_total = len(python_files) + len(non_python_files)
                if current_total >= max_file_count:
                    break

        python_files.sort()
        non_python_files.sort()
        test_files.sort()
        config_files.sort()

        total = len(python_files) + len(non_python_files)

        return DiscoveredFiles(
            python_files=tuple(python_files),
            non_python_files=tuple(non_python_files),
            test_files=tuple(test_files),
            configuration_files=tuple(config_files),
            total_count=total,
        )
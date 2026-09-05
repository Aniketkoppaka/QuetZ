"""
repository/analyzer.py -- High-level RepositoryAnalyzer service.

Coordinates deterministic filesystem scanning and Python AST analysis to produce
an immutable, serializable RepositoryMap.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.domain.models import (
    ParseFailure,
    PythonModuleMap,
    Repository,
    RepositoryMap,
)
from autonomous_engineer.repository.ast_analyzer import PythonAstAnalyzer
from autonomous_engineer.repository.file_scanner import FileScanner


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class AnalysisOptions(BaseModel):
    """Configuration options and resource limits for repository analysis."""

    model_config = ConfigDict(frozen=True)

    max_file_count: int | None = Field(
        default=50_000,
        ge=1,
        description="Maximum total files to inventory",
    )
    max_file_size_bytes: int | None = Field(
        default=5 * 1024 * 1024,  # 5 MB
        ge=1,
        description="Maximum size of an individual Python file to parse",
    )
    max_total_bytes_read: int | None = Field(
        default=100 * 1024 * 1024,  # 100 MB
        ge=1,
        description="Maximum cumulative bytes of Python source to parse",
    )
    excluded_dirs: tuple[str, ...] = Field(
        default=(),
        description="Additional directory names to ignore during scanning",
    )


class RepositoryAnalyzer:
    """Analyzes an acquired repository workspace into a structural RepositoryMap."""

    def __init__(
        self,
        scanner: FileScanner | None = None,
        ast_analyzer: PythonAstAnalyzer | None = None,
    ) -> None:
        self._scanner = scanner or FileScanner()
        self._ast = ast_analyzer or PythonAstAnalyzer()

    def analyze(
        self,
        repository: Repository,
        options: AnalysisOptions | None = None,
    ) -> RepositoryMap:
        """
        Produce a deterministic RepositoryMap for the given repository workspace.

        Args:
            repository: Acquired Repository domain model.
            options: Optional analysis limits and configuration.

        Returns:
            Immutable RepositoryMap containing file inventory and AST symbol maps.
        """
        opts = options or AnalysisOptions()
        ws_path = repository.workspace_path

        if not ws_path.exists():
            raise FileNotFoundError(
                f"Repository workspace path does not exist: {ws_path}"
            )

        # 1. Deterministic file inventory
        discovered = self._scanner.scan(
            ws_path,
            max_file_count=opts.max_file_count,
        )

        # 2. Parse Python modules and isolate failures
        python_modules: list[PythonModuleMap] = []
        parse_failures: list[ParseFailure] = []
        total_bytes_read = 0
        partial = False

        for rel_path in discovered.python_files:
            # Check cumulative bytes limit
            if opts.max_total_bytes_read is not None and total_bytes_read >= opts.max_total_bytes_read:
                parse_failures.append(
                    ParseFailure(
                        file_path=rel_path,
                        error_type="TotalBytesLimitExceeded",
                        message=f"Cumulative read limit ({opts.max_total_bytes_read} bytes) reached during analysis",
                    )
                )
                partial = True
                continue

            try:
                file_size = (ws_path / rel_path).stat().st_size
                total_bytes_read += file_size
            except OSError:
                pass

            is_test = self._scanner.is_test_file(rel_path)
            res = self._ast.analyze_file(
                workspace_path=ws_path,
                relative_path=rel_path,
                is_test_file=is_test,
                max_file_size_bytes=opts.max_file_size_bytes,
            )

            if isinstance(res, PythonModuleMap):
                python_modules.append(res)
            elif isinstance(res, ParseFailure):
                parse_failures.append(res)

        # Check for standard project config files
        has_pyproject = any(
            p.lower() == "pyproject.toml" for p in discovered.configuration_files
        )
        has_setup = any(
            p.lower() == "setup.py" for p in discovered.configuration_files
        )
        has_reqs = any(
            p.lower() == "requirements.txt" or p.lower().startswith("requirements/")
            for p in discovered.configuration_files
        )

        return RepositoryMap(
            repository_url=repository.url,
            commit_sha=repository.commit_sha,
            file_count=discovered.total_count,
            python_file_count=len(discovered.python_files),
            non_python_file_paths=discovered.non_python_files,
            python_modules=tuple(python_modules),
            test_file_paths=discovered.test_files,
            configuration_file_paths=discovered.configuration_files,
            parse_failures=tuple(parse_failures),
            entry_points=(),
            has_pyproject_toml=has_pyproject,
            has_setup_py=has_setup,
            has_requirements_txt=has_reqs,
            scanned_at=_utcnow(),
            partial=partial,
        )
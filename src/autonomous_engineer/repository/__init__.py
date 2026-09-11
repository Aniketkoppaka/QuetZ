"""
repository -- Repository acquisition, workspace isolation, and AST structural analysis.

Public API:
  - GitAcquisitionService: Service to acquire Git repositories into isolated workspaces.
  - RepositoryAnalyzer: Service to analyze repository workspaces into structural RepositoryMaps.
  - AnalysisOptions: Configuration options and limits for AST analysis.
  - FileScanner: Deterministic filesystem scanner and file classifier.
  - DiscoveredFiles: Inventory dataclass for discovered repository files.
  - PythonAstAnalyzer: Pure syntactic AST symbol and import extractor.
  - RepositoryReference: Validated repository reference and revision specification.
  - AcquisitionOptions: Configuration options and resource limits for acquisition.
  - WorkspaceManager: Directory lifecycle and cleanup manager.
  - RepositoryError and subclasses: Structured acquisition exceptions.
"""
from __future__ import annotations

from autonomous_engineer.repository.acquisition import GitAcquisitionService
from autonomous_engineer.repository.analyzer import AnalysisOptions, RepositoryAnalyzer
from autonomous_engineer.repository.ast_analyzer import PythonAstAnalyzer
from autonomous_engineer.repository.errors import (
    AcquisitionTimeoutError,
    AuthenticationFailedError,
    GitUnavailableError,
    InvalidRepositoryReferenceError,
    NetworkFailedError,
    RepositoryError,
    RepositoryNotFoundError,
    ResourceLimitExceededError,
    RevisionNotFoundError,
    RevisionVerificationError,
    SubmoduleUnsupportedError,
    WorkspaceCreationError,
)
from autonomous_engineer.repository.file_scanner import DiscoveredFiles, FileScanner
from autonomous_engineer.repository.git_cli import GitCli, GitCommandResult
from autonomous_engineer.repository.models import AcquisitionOptions, RepositoryReference
from autonomous_engineer.repository.workspace import WorkspaceManager
from autonomous_engineer.repository.impact_analyzer import (
    AffectedModule,
    CallerReference,
    ChangeImpactAnalyzer,
    ChangedSymbol,
    ImpactReport,
)
from autonomous_engineer.repository.js_ts_analyzer import (
    JsTsAnalyzer,
    JsTsClassSymbol,
    JsTsFunctionSymbol,
    JsTsModuleMap,
)
from autonomous_engineer.repository.go_rust_analyzer import (
    PolyglotCodeAnalyzer,
    PolyglotModuleMap,
    PolyglotSymbol,
)

__all__ = [
    "AcquisitionOptions",
    "AcquisitionTimeoutError",
    "AffectedModule",
    "AnalysisOptions",
    "AuthenticationFailedError",
    "CallerReference",
    "ChangeImpactAnalyzer",
    "ChangedSymbol",
    "DiscoveredFiles",
    "FileScanner",
    "GitAcquisitionService",
    "GitCli",
    "GitCommandResult",
    "GitUnavailableError",
    "ImpactReport",
    "InvalidRepositoryReferenceError",
    "JsTsAnalyzer",
    "JsTsClassSymbol",
    "JsTsFunctionSymbol",
    "JsTsModuleMap",
    "NetworkFailedError",
    "PythonAstAnalyzer",
    "RepositoryAnalyzer",
    "RepositoryError",
    "RepositoryNotFoundError",
    "RepositoryReference",
    "ResourceLimitExceededError",
    "RevisionNotFoundError",
    "RevisionVerificationError",
    "SubmoduleUnsupportedError",
    "WorkspaceCreationError",
    "WorkspaceManager",
]
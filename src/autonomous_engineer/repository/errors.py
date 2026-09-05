"""
repository/errors.py -- Structured exceptions for repository acquisition.

Every exception inherits from RepositoryError and maps to a FailureCategory
in the domain failure taxonomy, allowing the orchestration layer to record
precise failure reasons in WorkflowRun.failure.
"""
from __future__ import annotations

from autonomous_engineer.domain.errors import FailureCategory


class RepositoryError(Exception):
    """Base exception for all repository acquisition and workspace errors."""

    failure_category: FailureCategory = FailureCategory.REPOSITORY_ACQUISITION

    def __init__(
        self,
        message: str,
        failure_category: FailureCategory | None = None,
    ) -> None:
        super().__init__(message)
        if failure_category is not None:
            self.failure_category = failure_category


class InvalidRepositoryReferenceError(RepositoryError):
    """Raised when repository URL or revision format is invalid or prohibited."""

    failure_category = FailureCategory.INVALID_INPUT


class RepositoryNotFoundError(RepositoryError):
    """Raised when the remote/local repository cannot be found or does not exist."""

    failure_category = FailureCategory.REPOSITORY_ACQUISITION


class AuthenticationFailedError(RepositoryError):
    """Raised when access to the repository is denied due to authentication failure."""

    failure_category = FailureCategory.REPOSITORY_ACQUISITION


class NetworkFailedError(RepositoryError):
    """Raised when network connectivity or DNS resolution fails during acquisition."""

    failure_category = FailureCategory.INFRASTRUCTURE


class RevisionNotFoundError(RepositoryError):
    """Raised when the requested branch, tag, or commit SHA does not exist in the repository."""

    failure_category = FailureCategory.REPOSITORY_ACQUISITION


class RevisionVerificationError(RepositoryError):
    """Raised when the checked-out commit SHA does not match the requested immutable revision."""

    failure_category = FailureCategory.REPOSITORY_ACQUISITION


class GitUnavailableError(RepositoryError):
    """Raised when the Git binary is not found on PATH or cannot be executed."""

    failure_category = FailureCategory.INFRASTRUCTURE


class AcquisitionTimeoutError(RepositoryError):
    """Raised when repository acquisition exceeds the configured wall-clock timeout."""

    failure_category = FailureCategory.TIMEOUT


class ResourceLimitExceededError(RepositoryError):
    """Raised when the acquired repository exceeds maximum disk size or file count limits."""

    failure_category = FailureCategory.RESOURCE_LIMIT


class SubmoduleUnsupportedError(RepositoryError):
    """Raised when a repository contains submodules and submodule support is disabled."""

    failure_category = FailureCategory.REPOSITORY_ACQUISITION


class WorkspaceCreationError(RepositoryError):
    """Raised when creating or preparing the local workspace directory fails."""

    failure_category = FailureCategory.INFRASTRUCTURE
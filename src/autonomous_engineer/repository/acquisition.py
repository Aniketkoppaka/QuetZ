"""
repository/acquisition.py -- Repository acquisition service and revision verification.

Orchestrates:
1. Validating repository reference and options.
2. Allocating isolated workspace directories.
3. Secure Git clone and checkout with hooks disabled.
4. Independent revision resolution and verification.
5. Submodule detection and resource limit enforcement.
6. Automatic workspace cleanup on any failure.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from autonomous_engineer.domain.models import Repository
from autonomous_engineer.repository.errors import (
    AuthenticationFailedError,
    NetworkFailedError,
    RepositoryError,
    RepositoryNotFoundError,
    ResourceLimitExceededError,
    RevisionNotFoundError,
    RevisionVerificationError,
    SubmoduleUnsupportedError,
)
from autonomous_engineer.repository.git_cli import GitCli
from autonomous_engineer.repository.models import AcquisitionOptions, RepositoryReference
from autonomous_engineer.repository.workspace import WorkspaceManager


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _classify_clone_error(url: str, stderr: str) -> RepositoryError:
    """Classify Git clone stderr output into specific RepositoryError subclasses."""
    lower_err = stderr.lower()

    if (
        "authentication failed" in lower_err
        or "could not read username" in lower_err
        or "terminal prompts disabled" in lower_err
        or "permission denied (publickey)" in lower_err
    ):
        return AuthenticationFailedError(
            f"Authentication failed accessing repository {url!r}: {stderr.strip()}"
        )

    if (
        "repository not found" in lower_err
        or "does not exist" in lower_err
        or "remote: not found" in lower_err
        or "does not appear to be a git repository" in lower_err
        or "could not read from remote repository" in lower_err
        or ("fatal: repository" in lower_err and "not found" in lower_err)
    ):
        return RepositoryNotFoundError(
            f"Repository not found at {url!r}: {stderr.strip()}"
        )

    if (
        "could not resolve host" in lower_err
        or "failed to connect" in lower_err
        or "connection refused" in lower_err
        or "network is unreachable" in lower_err
        or "operation timed out" in lower_err
    ):
        return NetworkFailedError(
            f"Network failure connecting to {url!r}: {stderr.strip()}"
        )

    return RepositoryError(f"Failed to clone repository from {url!r}: {stderr.strip()}")


class GitAcquisitionService:
    """Service for acquiring remote/local Git repositories into isolated workspaces."""

    def __init__(
        self,
        git_cli: GitCli | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        self._git = git_cli or GitCli()
        self._workspaces = workspace_manager or WorkspaceManager()

    def acquire(
        self,
        reference: RepositoryReference,
        options: AcquisitionOptions | None = None,
        workspace_id: str | None = None,
    ) -> Repository:
        """
        Acquire a repository at the requested revision into an isolated workspace.

        Args:
            reference: Validated RepositoryReference containing URL and revision.
            options: Configuration options (timeouts, size limits, submodule policy).
            workspace_id: Optional unique identifier for directory naming.

        Returns:
            Immutable Repository domain model representing the acquired snapshot.

        Raises:
            RepositoryNotFoundError: If the repository does not exist.
            AuthenticationFailedError: If authentication fails.
            NetworkFailedError: If network connectivity fails.
            RevisionNotFoundError: If requested revision does not exist.
            RevisionVerificationError: If checked-out commit does not match requested SHA.
            SubmoduleUnsupportedError: If repo contains .gitmodules and allow_submodules is False.
            ResourceLimitExceededError: If repo exceeds disk size or file count limits.
            AcquisitionTimeoutError: If acquisition exceeds timeout_seconds.
        """
        opts = options or AcquisitionOptions()
        self._git.check_available()

        ws_mgr = (
            self._workspaces
            if opts.base_workspace_dir is None
            else WorkspaceManager(base_dir=opts.base_workspace_dir)
        )
        ws_path = ws_mgr.create_workspace(prefix="repo_", workspace_id=workspace_id)

        try:
            # 1. Clone repository without checkout (disabling hooks)
            clone_args = [
                "-c", "core.hooksPath=",
                "clone",
                "--no-checkout",
                "--",
                reference.url,
                str(ws_path),
            ]
            clone_res = self._git.run(
                clone_args,
                timeout=opts.timeout_seconds,
            )
            if not clone_res.succeeded:
                raise _classify_clone_error(reference.url, clone_res.stderr)

            # 2. Checkout requested revision
            rev = reference.requested_revision
            checkout_args = [
                "-c", "core.hooksPath=",
                "-C", str(ws_path),
                "checkout",
                rev,
                "--",
            ]
            checkout_res = self._git.run(
                checkout_args,
                timeout=opts.timeout_seconds,
            )

            if not checkout_res.succeeded:
                # If direct checkout failed, attempt explicit fetch from origin
                fetch_args = [
                    "-c", "core.hooksPath=",
                    "-C", str(ws_path),
                    "fetch",
                    "origin",
                    rev,
                    "--",
                ]
                fetch_res = self._git.run(fetch_args, timeout=opts.timeout_seconds)
                if fetch_res.succeeded:
                    # Retry checkout of FETCH_HEAD
                    checkout_res = self._git.run(
                        [
                            "-c", "core.hooksPath=",
                            "-C", str(ws_path),
                            "checkout",
                            "FETCH_HEAD",
                            "--",
                        ],
                        timeout=opts.timeout_seconds,
                    )

                if not checkout_res.succeeded:
                    raise RevisionNotFoundError(
                        f"Requested revision {rev!r} was not found in repository {reference.url!r}: "
                        f"{checkout_res.stderr.strip()}"
                    )

            # 3. Resolve and verify checked-out commit SHA
            rev_res = self._git.run(
                ["-C", str(ws_path), "rev-parse", "HEAD"],
                timeout=opts.timeout_seconds,
            )
            if not rev_res.succeeded or not rev_res.stdout.strip():
                raise RevisionVerificationError(
                    f"Failed to resolve HEAD commit SHA: {rev_res.stderr.strip()}"
                )
            resolved_sha = rev_res.stdout.strip()

            # If an exact hex commit SHA was requested, verify the match
            if re.match(r"^[0-9a-fA-F]{7,40}$", rev):
                if not resolved_sha.lower().startswith(rev.lower()):
                    raise RevisionVerificationError(
                        f"Verified commit SHA {resolved_sha!r} does not match "
                        f"requested SHA {rev!r}"
                    )

            # 4. Check for submodules
            if not opts.allow_submodules and (ws_path / ".gitmodules").exists():
                raise SubmoduleUnsupportedError(
                    f"Repository at {reference.url!r} contains submodules (.gitmodules), "
                    "which are unsupported in Milestone 2.1."
                )

            # 5. Enforce resource limits
            if opts.max_size_bytes is not None:
                usage = ws_mgr.get_disk_usage_bytes(ws_path)
                if usage > opts.max_size_bytes:
                    raise ResourceLimitExceededError(
                        f"Acquired repository size ({usage} bytes) exceeds configured "
                        f"maximum limit ({opts.max_size_bytes} bytes)."
                    )

            if opts.max_file_count is not None:
                file_count = ws_mgr.count_files(ws_path)
                if file_count > opts.max_file_count:
                    raise ResourceLimitExceededError(
                        f"Acquired repository file count ({file_count}) exceeds configured "
                        f"maximum limit ({opts.max_file_count})."
                    )

            # 6. Detect branch name (if not detached HEAD)
            branch_res = self._git.run(
                ["-C", str(ws_path), "rev-parse", "--abbrev-ref", "HEAD"],
                timeout=opts.timeout_seconds,
            )
            branch_name = branch_res.stdout.strip() if branch_res.succeeded else ""
            if branch_name == "HEAD":
                branch_name = ""

            return Repository(
                url=reference.url,
                workspace_path=ws_path,
                commit_sha=resolved_sha,
                branch=branch_name,
                requested_revision=reference.requested_revision,
                acquired_at=_utcnow(),
            )

        except Exception:
            # Clean up on any failure
            ws_mgr.cleanup_workspace(ws_path)
            raise

    def cleanup(self, workspace_path: Path) -> None:
        """Clean up an acquired workspace directory."""
        self._workspaces.cleanup_workspace(workspace_path)
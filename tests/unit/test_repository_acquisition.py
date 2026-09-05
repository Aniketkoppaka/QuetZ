"""
tests/unit/test_repository_acquisition.py

Unit and integration tests for repository acquisition and workspace isolation.
All tests use local Git repositories created in temporary directories (no internet).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from autonomous_engineer.domain.errors import FailureCategory
from autonomous_engineer.domain.models import Repository
from autonomous_engineer.repository import (
    AcquisitionOptions,
    AcquisitionTimeoutError,
    AuthenticationFailedError,
    GitAcquisitionService,
    GitCli,
    GitCommandResult,
    GitUnavailableError,
    InvalidRepositoryReferenceError,
    NetworkFailedError,
    RepositoryError,
    RepositoryNotFoundError,
    RepositoryReference,
    ResourceLimitExceededError,
    RevisionNotFoundError,
    RevisionVerificationError,
    SubmoduleUnsupportedError,
    WorkspaceManager,
)


# ---------------------------------------------------------------------------
# Fixture: Local Git Repository
# ---------------------------------------------------------------------------


@pytest.fixture
def local_git_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """
    Create a local Git repository with known commits, branches, and tags.

    Returns:
        (repo_path, {"initial_sha": ..., "feature_sha": ..., "v1_sha": ...})
    """
    repo_dir = tmp_path / "source_repo"
    repo_dir.mkdir()

    # Configure local git user for reproducible commits
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "Test Author"
    env["GIT_AUTHOR_EMAIL"] = "author@example.com"
    env["GIT_COMMITTER_NAME"] = "Test Committer"
    env["GIT_COMMITTER_EMAIL"] = "committer@example.com"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull

    def run_git(*args: str) -> str:
        res = subprocess.run(
            ["git", "-C", str(repo_dir)] + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            env=env,
        )
        return res.stdout.strip()

    subprocess.run(["git", "init", "-b", "main", str(repo_dir)], check=True, env=env)

    # Initial commit on main
    (repo_dir / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    (repo_dir / "app.py").write_text("def hello(): return 'world'\n", encoding="utf-8")
    run_git("add", ".")
    run_git("commit", "-m", "Initial commit")
    initial_sha = run_git("rev-parse", "HEAD")

    # Tag v1.0.0
    run_git("tag", "v1.0.0")

    # Feature branch with a second commit
    run_git("checkout", "-b", "feature-fix")
    (repo_dir / "app.py").write_text("def hello(): return 'fixed world'\n", encoding="utf-8")
    run_git("add", "app.py")
    run_git("commit", "-m", "Fix bug in app.py")
    feature_sha = run_git("rev-parse", "HEAD")

    # Switch back to main
    run_git("checkout", "main")

    return repo_dir, {
        "initial_sha": initial_sha,
        "feature_sha": feature_sha,
        "v1_tag": "v1.0.0",
    }


# ---------------------------------------------------------------------------
# Successful Acquisition Tests
# ---------------------------------------------------------------------------


class TestSuccessfulAcquisition:
    def test_acquire_default_branch(
        self, local_git_repo: tuple[Path, dict[str, str]], tmp_path: Path
    ) -> None:
        repo_dir, shas = local_git_repo
        service = GitAcquisitionService(
            workspace_manager=WorkspaceManager(base_dir=tmp_path / "ws")
        )
        ref = RepositoryReference(url=str(repo_dir), requested_revision="main")

        acquired = service.acquire(ref)

        assert isinstance(acquired, Repository)
        assert acquired.url == str(repo_dir)
        assert acquired.commit_sha == shas["initial_sha"]
        assert acquired.requested_revision == "main"
        assert acquired.branch == "main"
        assert (acquired.workspace_path / "README.md").exists()
        assert (acquired.workspace_path / "app.py").read_text(encoding="utf-8") == "def hello(): return 'world'\n"

        # Cleanup
        service.cleanup(acquired.workspace_path)
        assert not acquired.workspace_path.exists()

    def test_acquire_pinned_commit_sha(
        self, local_git_repo: tuple[Path, dict[str, str]], tmp_path: Path
    ) -> None:
        repo_dir, shas = local_git_repo
        service = GitAcquisitionService(
            workspace_manager=WorkspaceManager(base_dir=tmp_path / "ws")
        )
        ref = RepositoryReference(url=str(repo_dir), requested_revision=shas["feature_sha"])

        acquired = service.acquire(ref)

        assert acquired.commit_sha == shas["feature_sha"]
        assert acquired.requested_revision == shas["feature_sha"]
        assert (acquired.workspace_path / "app.py").read_text(encoding="utf-8") == "def hello(): return 'fixed world'\n"
        service.cleanup(acquired.workspace_path)

    def test_acquire_specific_branch(
        self, local_git_repo: tuple[Path, dict[str, str]], tmp_path: Path
    ) -> None:
        repo_dir, shas = local_git_repo
        service = GitAcquisitionService(
            workspace_manager=WorkspaceManager(base_dir=tmp_path / "ws")
        )
        ref = RepositoryReference(url=str(repo_dir), requested_revision="feature-fix")

        acquired = service.acquire(ref)

        assert acquired.commit_sha == shas["feature_sha"]
        assert (acquired.workspace_path / "app.py").read_text(encoding="utf-8") == "def hello(): return 'fixed world'\n"
        service.cleanup(acquired.workspace_path)

    def test_acquire_tag(
        self, local_git_repo: tuple[Path, dict[str, str]], tmp_path: Path
    ) -> None:
        repo_dir, shas = local_git_repo
        service = GitAcquisitionService(
            workspace_manager=WorkspaceManager(base_dir=tmp_path / "ws")
        )
        ref = RepositoryReference(url=str(repo_dir), requested_revision="v1.0.0")

        acquired = service.acquire(ref)

        assert acquired.commit_sha == shas["initial_sha"]
        service.cleanup(acquired.workspace_path)


# ---------------------------------------------------------------------------
# Workspace Isolation & Lifecycle Tests
# ---------------------------------------------------------------------------


class TestWorkspaceIsolation:
    def test_workspaces_are_isolated(
        self, local_git_repo: tuple[Path, dict[str, str]], tmp_path: Path
    ) -> None:
        repo_dir, _ = local_git_repo
        service = GitAcquisitionService(
            workspace_manager=WorkspaceManager(base_dir=tmp_path / "ws")
        )
        ref = RepositoryReference(url=str(repo_dir), requested_revision="main")

        ws1 = service.acquire(ref)
        ws2 = service.acquire(ref)

        assert ws1.workspace_path != ws2.workspace_path
        assert ws1.workspace_path.exists()
        assert ws2.workspace_path.exists()

        # Mutate file in ws1, verify ws2 is unchanged
        (ws1.workspace_path / "README.md").write_text("Modified in ws1", encoding="utf-8")
        assert (ws2.workspace_path / "README.md").read_text(encoding="utf-8") == "# Test Repo\n"

        service.cleanup(ws1.workspace_path)
        service.cleanup(ws2.workspace_path)

    def test_cleanup_handles_nonexistent_path(self, tmp_path: Path) -> None:
        wm = WorkspaceManager(base_dir=tmp_path)
        # Should not raise
        wm.cleanup_workspace(tmp_path / "nonexistent_dir_123")


# ---------------------------------------------------------------------------
# Validation & Security Tests
# ---------------------------------------------------------------------------


class TestRepositoryReferenceValidation:
    def test_blank_url_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RepositoryReference(url="")

    def test_blank_revision_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RepositoryReference(url="https://github.com/owner/repo", requested_revision="")

    def test_leading_dash_in_url_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not start with a dash"):
            RepositoryReference(url="--upload-pack=exploit")

    def test_leading_dash_in_revision_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not start with a dash"):
            RepositoryReference(
                url="https://github.com/owner/repo",
                requested_revision="--upload-pack=exploit",
            )

    def test_embedded_credentials_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Embedded credentials"):
            RepositoryReference(url="https://user:password@github.com/owner/repo.git")

    def test_ssh_references_rejected(self) -> None:
        with pytest.raises(ValidationError, match="SSH repository references are currently unsupported"):
            RepositoryReference(url="git@github.com:owner/repo.git")

        with pytest.raises(ValidationError, match="SSH repository references are currently unsupported"):
            RepositoryReference(url="ssh://git@github.com/owner/repo.git")

    def test_control_characters_in_revision_rejected(self) -> None:
        with pytest.raises(ValidationError, match="illegal control characters"):
            RepositoryReference(url="https://github.com/owner/repo", requested_revision="main\nrm -rf /")


# ---------------------------------------------------------------------------
# Failure & Error Classification Tests
# ---------------------------------------------------------------------------


class TestAcquisitionFailures:
    def test_nonexistent_repository_fails_with_repository_not_found(
        self, tmp_path: Path
    ) -> None:
        service = GitAcquisitionService(
            workspace_manager=WorkspaceManager(base_dir=tmp_path / "ws")
        )
        nonexistent = tmp_path / "does_not_exist_repo"
        ref = RepositoryReference(url=str(nonexistent), requested_revision="main")

        with pytest.raises(RepositoryNotFoundError) as exc_info:
            service.acquire(ref)

        assert exc_info.value.failure_category == FailureCategory.REPOSITORY_ACQUISITION

        # Verify no orphaned workspace left behind
        ws_dirs = list((tmp_path / "ws").glob("*"))
        assert len(ws_dirs) == 0

    def test_nonexistent_revision_fails_with_revision_not_found(
        self, local_git_repo: tuple[Path, dict[str, str]], tmp_path: Path
    ) -> None:
        repo_dir, _ = local_git_repo
        service = GitAcquisitionService(
            workspace_manager=WorkspaceManager(base_dir=tmp_path / "ws")
        )
        ref = RepositoryReference(
            url=str(repo_dir),
            requested_revision="nonexistent-branch-9999",
        )

        with pytest.raises(RevisionNotFoundError) as exc_info:
            service.acquire(ref)

        assert exc_info.value.failure_category == FailureCategory.REPOSITORY_ACQUISITION

        # Verify workspace cleaned up on failure
        ws_dirs = list((tmp_path / "ws").glob("*"))
        assert len(ws_dirs) == 0

    def test_submodule_detection_fails_when_unsupported(
        self, local_git_repo: tuple[Path, dict[str, str]], tmp_path: Path
    ) -> None:
        repo_dir, _ = local_git_repo
        # Add a .gitmodules file to source repo
        (repo_dir / ".gitmodules").write_text("[submodule \"lib\"]\n\tpath = lib\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_dir), "add", ".gitmodules"], check=True)
        subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "Add submodule file"], check=True)

        service = GitAcquisitionService(
            workspace_manager=WorkspaceManager(base_dir=tmp_path / "ws")
        )
        ref = RepositoryReference(url=str(repo_dir), requested_revision="main")

        with pytest.raises(SubmoduleUnsupportedError) as exc_info:
            service.acquire(ref, options=AcquisitionOptions(allow_submodules=False))

        assert exc_info.value.failure_category == FailureCategory.REPOSITORY_ACQUISITION

        # Verify workspace cleaned up
        ws_dirs = list((tmp_path / "ws").glob("*"))
        assert len(ws_dirs) == 0

    def test_resource_limit_size_exceeded(
        self, local_git_repo: tuple[Path, dict[str, str]], tmp_path: Path
    ) -> None:
        repo_dir, _ = local_git_repo
        service = GitAcquisitionService(
            workspace_manager=WorkspaceManager(base_dir=tmp_path / "ws")
        )
        ref = RepositoryReference(url=str(repo_dir), requested_revision="main")

        # Set artificially tiny max size (1024 bytes)
        with pytest.raises(ResourceLimitExceededError) as exc_info:
            service.acquire(ref, options=AcquisitionOptions(max_size_bytes=1024))

        assert exc_info.value.failure_category == FailureCategory.RESOURCE_LIMIT

        # Verify workspace cleaned up
        ws_dirs = list((tmp_path / "ws").glob("*"))
        assert len(ws_dirs) == 0

    def test_git_unavailable_raises_git_unavailable_error(self, tmp_path: Path) -> None:
        git_cli = GitCli(git_binary="/nonexistent/path/to/git_bin_12345")
        service = GitAcquisitionService(
            git_cli=git_cli,
            workspace_manager=WorkspaceManager(base_dir=tmp_path / "ws"),
        )
        ref = RepositoryReference(url="https://github.com/owner/repo", requested_revision="main")

        with pytest.raises(GitUnavailableError) as exc_info:
            service.acquire(ref)

        assert exc_info.value.failure_category == FailureCategory.INFRASTRUCTURE

    def test_revision_verification_failure_on_sha_mismatch(
        self, local_git_repo: tuple[Path, dict[str, str]], tmp_path: Path
    ) -> None:
        repo_dir, shas = local_git_repo
        service = GitAcquisitionService(
            workspace_manager=WorkspaceManager(base_dir=tmp_path / "ws")
        )
        # Construct a fake 40-character SHA that doesn't match initial_sha
        fake_sha = "0123456789abcdef0123456789abcdef01234567"
        ref = RepositoryReference(url=str(repo_dir), requested_revision=fake_sha)

        with pytest.raises((RevisionNotFoundError, RevisionVerificationError)):
            service.acquire(ref)

    def test_error_category_mapping(self) -> None:
        """Verify that every repository exception maps to the correct FailureCategory."""
        assert InvalidRepositoryReferenceError("x").failure_category == FailureCategory.INVALID_INPUT
        assert RepositoryNotFoundError("x").failure_category == FailureCategory.REPOSITORY_ACQUISITION
        assert AuthenticationFailedError("x").failure_category == FailureCategory.REPOSITORY_ACQUISITION
        assert NetworkFailedError("x").failure_category == FailureCategory.INFRASTRUCTURE
        assert RevisionNotFoundError("x").failure_category == FailureCategory.REPOSITORY_ACQUISITION
        assert RevisionVerificationError("x").failure_category == FailureCategory.REPOSITORY_ACQUISITION
        assert GitUnavailableError("x").failure_category == FailureCategory.INFRASTRUCTURE
        assert AcquisitionTimeoutError("x").failure_category == FailureCategory.TIMEOUT
        assert ResourceLimitExceededError("x").failure_category == FailureCategory.RESOURCE_LIMIT
        assert SubmoduleUnsupportedError("x").failure_category == FailureCategory.REPOSITORY_ACQUISITION


# ---------------------------------------------------------------------------
# Git CLI Subprocess Safety Tests
# ---------------------------------------------------------------------------


class TestGitCliSafety:
    def test_run_passes_command_as_list_no_shell(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="out", stderr="")
            git = GitCli(git_binary="git")
            res = git.run(["status"], cwd=tmp_path)

            mock_run.assert_called_once()
            _, kwargs = mock_run.call_args
            assert kwargs.get("shell") is False
            assert res.stdout == "out"

    def test_run_translates_timeout_expired(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=5.0)
            git = GitCli(git_binary="git")

            with pytest.raises(AcquisitionTimeoutError):
                git.run(["clone", "foo"], timeout=5.0)
"""
repository/workspace.py -- Workspace directory lifecycle and isolation management.

Responsible for:
- Allocating unique, isolated workspace directories.
- Robust cross-platform deletion (handling Windows read-only file attributes in .git).
- Inspecting workspace disk usage and file counts for resource limit enforcement.
"""
from __future__ import annotations

import os
import shutil
import stat
import tempfile
import uuid
from pathlib import Path

from autonomous_engineer.repository.errors import WorkspaceCreationError


def _remove_readonly(func, path, exc_info):
    """Error handler for shutil.rmtree to clear read-only flag on Windows."""
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)
    except Exception:
        pass


class WorkspaceManager:
    """Manages creation, inspection, and cleanup of isolated workspaces."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path:
        """Return the effective base directory for workspaces."""
        if self._base_dir is not None:
            return self._base_dir
        return Path(tempfile.gettempdir()) / "autonomous_engineer_workspaces"

    def create_workspace(self, prefix: str = "ws_", workspace_id: str | None = None) -> Path:
        """
        Create a new, isolated directory for repository acquisition.

        Args:
            prefix: Prefix for directory naming.
            workspace_id: Optional explicit identifier. If None, generates random UUID.

        Returns:
            Absolute Path to the newly created directory.

        Raises:
            WorkspaceCreationError: If directory creation fails.
        """
        uid = workspace_id or uuid.uuid4().hex[:12]
        target_dir = self.base_dir / f"{prefix}{uid}"

        try:
            target_dir.mkdir(parents=True, exist_ok=False)
            return target_dir.resolve()
        except Exception as exc:
            raise WorkspaceCreationError(
                f"Failed to create workspace directory at {target_dir}: {exc}"
            ) from exc

    def cleanup_workspace(self, workspace_path: Path) -> None:
        """
        Safely remove an isolated workspace directory.

        If the directory does not exist, this is a no-op.
        """
        if not workspace_path.exists():
            return

        try:
            shutil.rmtree(workspace_path, onerror=_remove_readonly)
        except Exception:
            # Fallback for Python 3.12+ on_exc signature or edge cases
            try:
                shutil.rmtree(workspace_path, ignore_errors=True)
            except Exception:
                pass

    def get_disk_usage_bytes(self, workspace_path: Path) -> int:
        """Calculate total disk usage of the workspace directory in bytes."""
        total = 0
        if not workspace_path.exists():
            return 0

        for root, _, files in os.walk(workspace_path):
            for file in files:
                p = Path(root) / file
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        return total

    def count_files(self, workspace_path: Path) -> int:
        """Count total number of files in the workspace directory."""
        count = 0
        if not workspace_path.exists():
            return 0

        for _, _, files in os.walk(workspace_path):
            count += len(files)
        return count
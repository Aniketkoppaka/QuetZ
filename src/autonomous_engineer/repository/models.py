"""
repository/models.py -- Value objects and configuration for repository acquisition.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RepositoryReference(BaseModel):
    """
    Reference to a Git repository and requested revision to acquire.

    Safety validations:
      - Embedded credentials (user:password@host) are rejected.
      - Option injection (leading dash) is rejected.
      - Control characters and newlines are rejected.
      - SSH references are explicitly rejected in this milestone.
    """

    model_config = ConfigDict(frozen=True)

    url: str = Field(
        description="HTTPS URL, file:// URL, or local path to the Git repository",
    )
    requested_revision: str = Field(
        default="HEAD",
        description="Requested branch name, tag, or commit SHA",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Repository URL must not be blank")

        if clean.startswith("-"):
            raise ValueError("Repository URL must not start with a dash ('-')")

        # Reject embedded credentials in URLs (e.g. https://user:pass@host/repo)
        if re.search(r"^[a-zA-Z]+://[^/@:]+:[^/@:]+@", clean):
            raise ValueError("Embedded credentials in repository URL are prohibited")

        # Disallow SSH URLs as per scope
        if clean.startswith("git@") or clean.startswith("ssh://"):
            raise ValueError("SSH repository references are currently unsupported")

        return clean

    @field_validator("requested_revision")
    @classmethod
    def validate_revision(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Requested revision must not be blank")

        if clean.startswith("-"):
            raise ValueError("Requested revision must not start with a dash ('-')")

        if any(c in clean for c in "\x00\r\n\t"):
            raise ValueError("Requested revision contains illegal control characters")

        return clean


class AcquisitionOptions(BaseModel):
    """Configuration options and resource limits for repository acquisition."""

    model_config = ConfigDict(frozen=True)

    timeout_seconds: float = Field(
        default=120.0,
        ge=1.0,
        description="Maximum seconds allowed for the acquisition process",
    )
    max_size_bytes: int | None = Field(
        default=500 * 1024 * 1024,  # 500 MB
        ge=1024,
        description="Maximum allowed workspace disk usage in bytes",
    )
    max_file_count: int | None = Field(
        default=50_000,
        ge=1,
        description="Maximum allowed file count in the acquired workspace",
    )
    allow_submodules: bool = Field(
        default=False,
        description="Whether submodules are permitted (False raises SubmoduleUnsupportedError)",
    )
    base_workspace_dir: Path | None = Field(
        default=None,
        description="Base directory for workspaces (defaults to system temp if None)",
    )
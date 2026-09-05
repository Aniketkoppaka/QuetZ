"""
tests/unit/test_package_import.py

Smoke tests that verify the autonomous_engineer package can be imported
successfully and that the package version is correctly declared.

These tests prove the Python project is correctly configured and the source
layout is importable — the minimum bar for Milestone 0.
"""

import importlib
import sys

import pytest


class TestPackageImport:
    """Verify the top-level package and all sub-packages are importable."""

    def test_top_level_package_imports(self) -> None:
        """autonomous_engineer must import without error."""
        mod = importlib.import_module("autonomous_engineer")
        assert mod is not None

    def test_version_is_declared(self) -> None:
        """__version__ must be present and a non-empty string."""
        import autonomous_engineer

        assert hasattr(autonomous_engineer, "__version__"), (
            "autonomous_engineer.__version__ is not defined"
        )
        version: object = autonomous_engineer.__version__
        assert isinstance(version, str), f"__version__ must be str, got {type(version)}"
        assert version.strip() != "", "__version__ must not be empty"

    def test_version_format(self) -> None:
        """__version__ should follow a basic MAJOR.MINOR.PATCH pattern."""
        import autonomous_engineer

        parts = autonomous_engineer.__version__.split(".")
        assert len(parts) == 3, (
            f"Expected 3-part version (MAJOR.MINOR.PATCH), got: {autonomous_engineer.__version__!r}"
        )
        for part in parts:
            assert part.isdigit(), f"Version part {part!r} is not numeric"

    @pytest.mark.parametrize(
        "subpackage",
        [
            "autonomous_engineer.config",
            "autonomous_engineer.domain",
            "autonomous_engineer.orchestration",
            "autonomous_engineer.repository",
            "autonomous_engineer.retrieval",
            "autonomous_engineer.tools",
            "autonomous_engineer.execution",
            "autonomous_engineer.agents",
            "autonomous_engineer.github",
            "autonomous_engineer.review",
            "autonomous_engineer.evaluation",
            "autonomous_engineer.observability",
        ],
    )
    def test_subpackage_imports(self, subpackage: str) -> None:
        """Every declared sub-package must be importable."""
        mod = importlib.import_module(subpackage)
        assert mod is not None, f"Failed to import {subpackage}"

    def test_package_in_sys_modules_after_import(self) -> None:
        """After import, autonomous_engineer must appear in sys.modules."""
        import autonomous_engineer  # noqa: F401

        assert "autonomous_engineer" in sys.modules

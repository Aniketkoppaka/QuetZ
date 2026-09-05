"""
tests/unit/test_repository_analysis.py

Comprehensive tests for deterministic repository mapping and Python AST analysis.
All tests run offline against temporary repository workspace fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from autonomous_engineer.domain.models import (
    ClassSymbol,
    FunctionSymbol,
    ImportStatement,
    ParseFailure,
    PythonModuleMap,
    Repository,
    RepositoryMap,
)
from autonomous_engineer.repository import (
    AnalysisOptions,
    FileScanner,
    PythonAstAnalyzer,
    RepositoryAnalyzer,
)


# ---------------------------------------------------------------------------
# Fixture: Sample Multi-file Python Repository Workspace
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_repo_workspace(tmp_path: Path) -> tuple[Repository, Path]:
    """Create a structured multi-module Python repository workspace on disk."""
    ws = tmp_path / "test_workspace"
    ws.mkdir()

    # 1. Config files
    (ws / "pyproject.toml").write_text("[project]\nname = 'sample-pkg'\n", encoding="utf-8")
    (ws / "requirements.txt").write_text("pytest>=8.0\npydantic>=2.0\n", encoding="utf-8")
    (ws / "README.md").write_text("# Sample Package\n", encoding="utf-8")
    (ws / "LICENSE").write_text("MIT License\n", encoding="utf-8")

    # 2. Source package
    src_dir = ws / "src" / "sample_pkg"
    src_dir.mkdir(parents=True)

    (src_dir / "__init__.py").write_text(
        '"""Sample package root."""\n__version__ = "1.0.0"\n',
        encoding="utf-8",
    )

    models_code = '''"""Data models for sample package."""
from __future__ import annotations

import sys
from typing import Any, Generic, TypeVar
from dataclasses import dataclass
from .utils import helper_func

T = TypeVar("T")

@dataclass
class BaseModel:
    """Base class for models."""
    id: str

class DataProcessor(BaseModel, Generic[T]):
    """Processes incoming generic data."""

    def __init__(self, name: str, timeout: float = 30.0) -> None:
        self.name = name
        self.timeout = timeout

    @property
    def is_ready(self) -> bool:
        """Check if processor is ready."""
        return bool(self.name)

    async def process_async(self, data: T, *args, retries: int = 3, **kwargs) -> Any:
        """Asynchronously process data items."""
        return helper_func(data)

    class InternalHelper:
        """Nested class helper."""
        def run(self) -> bool:
            return True


def standalone_worker(count: int = 1) -> None:
    """A top-level standalone function."""
    pass
'''
    (src_dir / "models.py").write_text(models_code, encoding="utf-8")

    utils_code = '''"""Utility functions."""
import os.path
from math import sqrt, ceil

def helper_func(val):
    return val
'''
    (src_dir / "utils.py").write_text(utils_code, encoding="utf-8")

    # 3. Tests directory
    tests_dir = ws / "tests"
    tests_dir.mkdir()

    test_models_code = '''"""Unit tests for models."""
import pytest
from sample_pkg.models import DataProcessor

def test_processor_init():
    p = DataProcessor("test")
    assert p.is_ready is True

@pytest.mark.asyncio
async def test_processor_async():
    p = DataProcessor("test")
    res = await p.process_async("data")
    assert res == "data"
'''
    (tests_dir / "test_models.py").write_text(test_models_code, encoding="utf-8")

    # 4. Ignored directories (must not appear in inventory)
    git_dir = ws / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("git config", encoding="utf-8")

    pycache_dir = src_dir / "__pycache__"
    pycache_dir.mkdir()
    (pycache_dir / "models.cpython-311.pyc").write_bytes(b"\x00\x01\x02")

    repo = Repository(
        url="https://github.com/example/sample-pkg",
        workspace_path=ws,
        commit_sha="1234567890abcdef1234567890abcdef12345678",
        branch="main",
        requested_revision="main",
    )

    return repo, ws


# ---------------------------------------------------------------------------
# FileScanner Tests
# ---------------------------------------------------------------------------


class TestFileScanner:
    def test_scanner_discovers_files_and_ignores_git(
        self, sample_repo_workspace: tuple[Repository, Path]
    ) -> None:
        _, ws = sample_repo_workspace
        scanner = FileScanner()
        disc = scanner.scan(ws)

        # Check Python files
        assert "src/sample_pkg/__init__.py" in disc.python_files
        assert "src/sample_pkg/models.py" in disc.python_files
        assert "src/sample_pkg/utils.py" in disc.python_files
        assert "tests/test_models.py" in disc.python_files

        # Verify .git and __pycache__ are excluded
        for p in disc.python_files + disc.non_python_files:
            assert not p.startswith(".git")
            assert "__pycache__" not in p
            assert not p.endswith(".pyc")

        # Check non-Python files
        assert "pyproject.toml" in disc.non_python_files
        assert "requirements.txt" in disc.non_python_files
        assert "README.md" in disc.non_python_files
        assert "LICENSE" in disc.non_python_files

        # Check test files classification
        assert "tests/test_models.py" in disc.test_files
        assert "src/sample_pkg/models.py" not in disc.test_files

        # Check configuration files classification
        assert "pyproject.toml" in disc.configuration_files
        assert "requirements.txt" in disc.configuration_files

    def test_scanner_ordering_is_deterministic(
        self, sample_repo_workspace: tuple[Repository, Path]
    ) -> None:
        _, ws = sample_repo_workspace
        scanner = FileScanner()
        disc1 = scanner.scan(ws)
        disc2 = scanner.scan(ws)

        assert disc1.python_files == disc2.python_files
        assert disc1.non_python_files == disc2.non_python_files
        assert list(disc1.python_files) == sorted(disc1.python_files)

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("tests/test_foo.py", True),
            ("tests/unit/test_bar.py", True),
            ("src/test_utils.py", True),
            ("src/pkg/models_test.py", True),
            ("test/test_basic.py", True),
            ("src/pkg/test.py", True),
            ("src/pkg/models.py", False),
            ("src/pkg/utils.py", False),
            ("README.md", False),
        ],
    )
    def test_is_test_file_heuristics(self, path: str, expected: bool) -> None:
        scanner = FileScanner()
        assert scanner.is_test_file(path) == expected


# ---------------------------------------------------------------------------
# PythonAstAnalyzer Tests
# ---------------------------------------------------------------------------


class TestPythonAstAnalyzer:
    def test_analyze_module_with_classes_functions_imports(
        self, sample_repo_workspace: tuple[Repository, Path]
    ) -> None:
        _, ws = sample_repo_workspace
        analyzer = PythonAstAnalyzer()

        res = analyzer.analyze_file(ws, "src/sample_pkg/models.py")
        assert isinstance(res, PythonModuleMap)

        # Module properties
        assert res.file_path == "src/sample_pkg/models.py"
        assert res.module_name == "src.sample_pkg.models"
        assert res.is_test_file is False
        assert res.docstring == "Data models for sample package."
        assert res.line_count > 20

        # Imports
        imp_modules = {imp.module for imp in res.imports}
        assert "__future__" in imp_modules
        assert "sys" in imp_modules
        assert "typing" in imp_modules
        assert "dataclasses" in imp_modules
        assert "utils" in imp_modules

        # Verify relative import level
        rel_imp = next(imp for imp in res.imports if imp.module == "utils")
        assert rel_imp.level == 1
        assert rel_imp.is_from is True
        assert "helper_func" in rel_imp.names

        # Top-level classes
        class_names = [c.name for c in res.classes]
        assert "BaseModel" in class_names
        assert "DataProcessor" in class_names

        # Inspect DataProcessor class
        dp_class = next(c for c in res.classes if c.name == "DataProcessor")
        assert dp_class.qualified_name == "DataProcessor"
        assert "BaseModel" in dp_class.base_classes
        assert any("Generic" in b for b in dp_class.base_classes)
        assert dp_class.docstring == "Processes incoming generic data."

        # Methods on DataProcessor
        method_names = [m.name for m in dp_class.methods]
        assert "__init__" in method_names
        assert "is_ready" in method_names
        assert "process_async" in method_names

        # Check async method
        async_method = next(m for m in dp_class.methods if m.name == "process_async")
        assert async_method.is_async is True
        assert async_method.is_method is True
        assert async_method.qualified_name == "DataProcessor.process_async"
        assert "data" in async_method.parameters
        assert "*args" in async_method.parameters
        assert "retries" in async_method.parameters
        assert "**kwargs" in async_method.parameters

        # Check decorated property
        prop_method = next(m for m in dp_class.methods if m.name == "is_ready")
        assert "@property" in prop_method.decorators
        assert prop_method.is_async is False

        # Check nested class
        assert len(dp_class.nested_classes) == 1
        nested = dp_class.nested_classes[0]
        assert nested.name == "InternalHelper"
        assert nested.qualified_name == "DataProcessor.InternalHelper"
        assert len(nested.methods) == 1
        assert nested.methods[0].name == "run"
        assert nested.methods[0].qualified_name == "DataProcessor.InternalHelper.run"

        # Top-level functions
        func_names = [f.name for f in res.functions]
        assert "standalone_worker" in func_names
        worker = next(f for f in res.functions if f.name == "standalone_worker")
        assert worker.qualified_name == "standalone_worker"
        assert worker.is_method is False
        assert worker.parameters == ("count",)

    def test_empty_python_file(self, tmp_path: Path) -> None:
        (tmp_path / "empty.py").write_text("", encoding="utf-8")
        analyzer = PythonAstAnalyzer()

        res = analyzer.analyze_file(tmp_path, "empty.py")
        assert isinstance(res, PythonModuleMap)
        assert res.classes == ()
        assert res.functions == ()
        assert res.imports == ()
        assert res.line_count == 0


# ---------------------------------------------------------------------------
# Parse Failure & Error Isolation Tests
# ---------------------------------------------------------------------------


class TestParseFailureIsolation:
    def test_syntax_error_is_isolated_as_parse_failure(self, tmp_path: Path) -> None:
        (tmp_path / "valid.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "broken.py").write_text("def broken_syntax(:\n    pass\n", encoding="utf-8")

        analyzer = PythonAstAnalyzer()

        valid_res = analyzer.analyze_file(tmp_path, "valid.py")
        broken_res = analyzer.analyze_file(tmp_path, "broken.py")

        assert isinstance(valid_res, PythonModuleMap)
        assert isinstance(broken_res, ParseFailure)
        assert broken_res.file_path == "broken.py"
        assert broken_res.error_type == "SyntaxError"
        assert broken_res.line_number == 1

    def test_non_utf8_decoding_failure_is_isolated(self, tmp_path: Path) -> None:
        # Write invalid raw bytes that cannot be decoded as UTF-8 or ASCII
        broken_file = tmp_path / "bad_encoding.py"
        broken_file.write_bytes(b"# -*- coding: utf-8 -*-\n\xff\xfe\x00\x00invalid")

        analyzer = PythonAstAnalyzer()
        res = analyzer.analyze_file(tmp_path, "bad_encoding.py")

        assert isinstance(res, ParseFailure)
        assert res.file_path == "bad_encoding.py"
        assert "Decode" in res.error_type or "Syntax" in res.error_type

    def test_repository_analyzer_preserves_valid_files_when_one_file_is_broken(
        self, tmp_path: Path
    ) -> None:
        ws = tmp_path / "mixed_ws"
        ws.mkdir()

        (ws / "good1.py").write_text("def fn1(): pass\n", encoding="utf-8")
        (ws / "good2.py").write_text("def fn2(): pass\n", encoding="utf-8")
        (ws / "bad.py").write_text("def (invalid syntax:\n", encoding="utf-8")

        repo = Repository(
            url="https://github.com/example/mixed",
            workspace_path=ws,
            commit_sha="abcdef123456",
        )

        service = RepositoryAnalyzer()
        repo_map = service.analyze(repo)

        assert repo_map.file_count == 3
        assert repo_map.python_file_count == 3
        assert len(repo_map.python_modules) == 2  # good1 and good2
        assert len(repo_map.parse_failures) == 1  # bad
        assert repo_map.parse_failures[0].file_path == "bad.py"


# ---------------------------------------------------------------------------
# Security Boundary Tests (Pure Syntactic AST)
# ---------------------------------------------------------------------------


class TestSecurityBoundary:
    def test_malicious_code_is_never_executed_during_ast_analysis(
        self, tmp_path: Path
    ) -> None:
        """
        Create a file that would raise RuntimeError or create side-effect files
        if imported or executed. Verify analysis succeeds purely syntactically.
        """
        flag_file = tmp_path / "should_not_exist.txt"
        malicious_code = f"""
import os
# If executed, this file would be created:
os.system("echo hacked > {flag_file.as_posix()}")
raise RuntimeError("Code execution violation!")

class ExploitClass:
    def method(self):
        pass
"""
        (tmp_path / "exploit.py").write_text(malicious_code, encoding="utf-8")

        analyzer = PythonAstAnalyzer()
        res = analyzer.analyze_file(tmp_path, "exploit.py")

        # Must parse successfully without executing
        assert isinstance(res, PythonModuleMap)
        assert len(res.classes) == 1
        assert res.classes[0].name == "ExploitClass"

        # Verify side effect did not happen
        assert not flag_file.exists(), "Repository code was executed during AST analysis!"


# ---------------------------------------------------------------------------
# High-Level RepositoryAnalyzer & Determinism Tests
# ---------------------------------------------------------------------------


class TestRepositoryAnalyzer:
    def test_full_repository_analysis(
        self, sample_repo_workspace: tuple[Repository, Path]
    ) -> None:
        repo, _ = sample_repo_workspace
        analyzer = RepositoryAnalyzer()
        repo_map = analyzer.analyze(repo)

        assert isinstance(repo_map, RepositoryMap)
        assert repo_map.repository_url == repo.url
        assert repo_map.commit_sha == repo.commit_sha
        assert repo_map.file_count == 8  # 4 python + 4 non-python
        assert repo_map.python_file_count == 4
        assert repo_map.has_pyproject_toml is True
        assert repo_map.has_requirements_txt is True
        assert repo_map.has_setup_py is False
        assert len(repo_map.python_modules) == 4
        assert len(repo_map.parse_failures) == 0

    def test_determinism_identical_runs_produce_identical_maps(
        self, sample_repo_workspace: tuple[Repository, Path]
    ) -> None:
        """Running analyzer twice on same repository produces identical results."""
        repo, _ = sample_repo_workspace
        analyzer = RepositoryAnalyzer()

        map1 = analyzer.analyze(repo)
        map2 = analyzer.analyze(repo)

        # Compare model dump dicts (ignoring timestamp)
        d1 = map1.model_dump(exclude={"scanned_at"})
        d2 = map2.model_dump(exclude={"scanned_at"})

        assert d1 == d2

        # Verify exact JSON equivalence
        j1 = json.loads(map1.model_dump_json(exclude={"scanned_at"}))
        j2 = json.loads(map2.model_dump_json(exclude={"scanned_at"}))
        assert j1 == j2

    def test_resource_limit_max_file_size_exceeded(self, tmp_path: Path) -> None:
        ws = tmp_path / "limit_ws"
        ws.mkdir()

        # Create a 2KB file
        (ws / "large.py").write_text("#" * 2048, encoding="utf-8")
        repo = Repository(
            url="https://github.com/example/limit",
            workspace_path=ws,
            commit_sha="abc123",
        )

        analyzer = RepositoryAnalyzer()
        # Set max file size limit to 1KB (1024 bytes)
        repo_map = analyzer.analyze(
            repo, options=AnalysisOptions(max_file_size_bytes=1024)
        )

        assert len(repo_map.parse_failures) == 1
        assert repo_map.parse_failures[0].error_type == "FileSizeLimitExceeded"
        assert len(repo_map.python_modules) == 0

    def test_resource_limit_max_total_bytes_marks_partial(self, tmp_path: Path) -> None:
        ws = tmp_path / "partial_ws"
        ws.mkdir()

        (ws / "f1.py").write_text("a = 1\n" * 100, encoding="utf-8")
        (ws / "f2.py").write_text("b = 2\n" * 100, encoding="utf-8")
        repo = Repository(
            url="https://github.com/example/partial",
            workspace_path=ws,
            commit_sha="abc123",
        )

        analyzer = RepositoryAnalyzer()
        # Set tiny total read limit (100 bytes)
        repo_map = analyzer.analyze(
            repo, options=AnalysisOptions(max_total_bytes_read=100)
        )

        assert repo_map.partial is True
        assert len(repo_map.parse_failures) >= 1
        assert any(
            pf.error_type == "TotalBytesLimitExceeded" for pf in repo_map.parse_failures
        )


# ---------------------------------------------------------------------------
# JSON Serialization Lossless Round-Trip Tests
# ---------------------------------------------------------------------------


class TestRepositoryMapSerialization:
    def test_lossless_json_round_trip(
        self, sample_repo_workspace: tuple[Repository, Path]
    ) -> None:
        repo, _ = sample_repo_workspace
        analyzer = RepositoryAnalyzer()
        original_map = analyzer.analyze(repo)

        # Serialize to JSON
        json_str = original_map.model_dump_json()

        # Deserialize from JSON
        restored_map = RepositoryMap.model_validate_json(json_str)

        # Verify all fields
        assert restored_map.repository_url == original_map.repository_url
        assert restored_map.commit_sha == original_map.commit_sha
        assert restored_map.file_count == original_map.file_count
        assert restored_map.python_file_count == original_map.python_file_count
        assert restored_map.test_file_paths == original_map.test_file_paths
        assert restored_map.configuration_file_paths == original_map.configuration_file_paths
        assert len(restored_map.python_modules) == len(original_map.python_modules)

        # Check deep structural equality of first module
        orig_mod = next(m for m in original_map.python_modules if m.file_path == "src/sample_pkg/models.py")
        rest_mod = next(m for m in restored_map.python_modules if m.file_path == "src/sample_pkg/models.py")

        assert rest_mod.module_name == orig_mod.module_name
        assert rest_mod.docstring == orig_mod.docstring
        assert len(rest_mod.classes) == len(orig_mod.classes)
        assert len(rest_mod.functions) == len(orig_mod.functions)
        assert len(rest_mod.imports) == len(orig_mod.imports)
"""
tests/unit/test_impact_analyzer.py -- Tests for Phase 3.1 ChangeImpactAnalyzer.

Uses lightweight synthetic RepositoryMap fixtures to exercise:
  - Symbol extraction from changed files
  - Import graph construction (absolute and relative imports)
  - BFS blast-radius computation (direct and transitive callers)
  - Targeted test-file selection (all four priority tiers)
  - Edge cases: empty repo, no callers, non-Python paths, isolated changes
  - ImpactReport model invariants
"""
from __future__ import annotations

import pytest

from autonomous_engineer.domain.models import (
    ClassSymbol,
    FunctionSymbol,
    ImportStatement,
    PythonModuleMap,
    RepositoryMap,
)
from autonomous_engineer.repository.impact_analyzer import (
    AffectedModule,
    CallerReference,
    ChangeImpactAnalyzer,
    ChangedSymbol,
    ImpactReport,
    _path_stem,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _func(name: str, line: int = 1) -> FunctionSymbol:
    return FunctionSymbol(name=name, qualified_name=name, line_number=line)


def _method(name: str, cls: str, line: int = 5) -> FunctionSymbol:
    return FunctionSymbol(
        name=name,
        qualified_name=f"{cls}.{name}",
        line_number=line,
        is_method=True,
    )


def _cls(name: str, methods: list[FunctionSymbol] | None = None, line: int = 1) -> ClassSymbol:
    return ClassSymbol(
        name=name,
        qualified_name=name,
        line_number=line,
        methods=tuple(methods or []),
    )


def _abs_import(module: str, names: tuple[str, ...] = (), line: int = 1) -> ImportStatement:
    """Absolute `from module import names` statement."""
    return ImportStatement(module=module, names=names, is_from=bool(names), level=0, line_number=line)


def _rel_import(module: str | None, names: tuple[str, ...], level: int, line: int = 1) -> ImportStatement:
    """Relative import: `from .module import names` (level=1) or `from ..sub import x` (level=2)."""
    return ImportStatement(module=module, names=names, is_from=True, level=level, line_number=line)


def _mod(
    file_path: str,
    module_name: str,
    *,
    imports: list[ImportStatement] | None = None,
    functions: list[FunctionSymbol] | None = None,
    classes: list[ClassSymbol] | None = None,
    is_test: bool = False,
) -> PythonModuleMap:
    return PythonModuleMap(
        file_path=file_path,
        module_name=module_name,
        is_test_file=is_test,
        line_count=10,
        imports=tuple(imports or []),
        functions=tuple(functions or []),
        classes=tuple(classes or []),
    )


def _repo(*modules: PythonModuleMap, test_paths: tuple[str, ...] = ()) -> RepositoryMap:
    return RepositoryMap(
        repository_url="https://example.com/repo",
        commit_sha="abc123",
        file_count=len(modules),
        python_file_count=len(modules),
        python_modules=tuple(modules),
        test_file_paths=test_paths,
    )


# ---------------------------------------------------------------------------
# _path_stem helper
# ---------------------------------------------------------------------------


class TestPathStem:
    def test_simple_file(self):
        assert _path_stem("foo.py") == "foo"

    def test_nested_path(self):
        assert _path_stem("src/pkg/bar.py") == "bar"

    def test_windows_separator(self):
        assert _path_stem("src\\pkg\\bar.py") == "bar"

    def test_strips_test_prefix(self):
        assert _path_stem("tests/test_foo.py") == "foo"

    def test_strips_tests_prefix(self):
        assert _path_stem("tests/tests_bar.py") == "bar"

    def test_non_python_file(self):
        assert _path_stem("README.md") == "README"

    def test_no_extension(self):
        assert _path_stem("Makefile") == "Makefile"


# ---------------------------------------------------------------------------
# Empty repository
# ---------------------------------------------------------------------------


class TestEmptyRepository:
    def test_empty_repo_produces_zero_blast_radius(self):
        repo = _repo()
        analyzer = ChangeImpactAnalyzer(repo)
        report = analyzer.analyze({"src/foo.py"})
        assert report.blast_radius_score == 0.0
        assert report.total_modules_analyzed == 0
        assert report.changed_symbols == ()
        assert report.caller_references == ()
        assert report.affected_modules == ()

    def test_empty_changed_set(self):
        repo = _repo(_mod("src/a.py", "a"))
        analyzer = ChangeImpactAnalyzer(repo)
        report = analyzer.analyze([])
        assert report.changed_file_paths == ()
        assert report.changed_symbols == ()
        assert report.blast_radius_score == 0.0


# ---------------------------------------------------------------------------
# Symbol extraction
# ---------------------------------------------------------------------------


class TestChangedSymbolExtraction:
    def test_top_level_function_extracted(self):
        m = _mod("pkg/utils.py", "pkg.utils", functions=[_func("helper")])
        repo = _repo(m)
        analyzer = ChangeImpactAnalyzer(repo)
        report = analyzer.analyze({"pkg/utils.py"})
        assert len(report.changed_symbols) == 1
        sym = report.changed_symbols[0]
        assert sym.symbol_name == "helper"
        assert sym.symbol_kind == "function"
        assert sym.module_name == "pkg.utils"

    def test_class_extracted(self):
        m = _mod("pkg/core.py", "pkg.core", classes=[_cls("Processor")])
        repo = _repo(m)
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/core.py"})
        kinds = {s.symbol_kind for s in report.changed_symbols}
        assert "class" in kinds

    def test_methods_extracted_with_qualified_names(self):
        method = _method("run", "Processor")
        cls = _cls("Processor", methods=[method])
        m = _mod("pkg/core.py", "pkg.core", classes=[cls])
        repo = _repo(m)
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/core.py"})
        method_syms = [s for s in report.changed_symbols if s.symbol_kind == "method"]
        assert len(method_syms) == 1
        assert method_syms[0].qualified_name == "Processor.run"

    def test_non_python_file_in_change_set_skipped(self):
        m = _mod("src/utils.py", "utils")
        repo = _repo(m)
        report = ChangeImpactAnalyzer(repo).analyze({"README.md"})
        assert report.changed_symbols == ()

    def test_multiple_functions_and_classes(self):
        m = _mod(
            "pkg/api.py",
            "pkg.api",
            functions=[_func("get"), _func("post")],
            classes=[_cls("Router")],
        )
        repo = _repo(m)
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/api.py"})
        names = {s.symbol_name for s in report.changed_symbols}
        assert {"get", "post", "Router"} == names


# ---------------------------------------------------------------------------
# Import graph — absolute imports
# ---------------------------------------------------------------------------


class TestAbsoluteImports:
    def test_direct_importer_detected(self):
        changed = _mod("pkg/utils.py", "pkg.utils", functions=[_func("helper")])
        importer = _mod(
            "pkg/service.py",
            "pkg.service",
            imports=[_abs_import("pkg.utils", ("helper",))],
        )
        repo = _repo(changed, importer)
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/utils.py"})
        assert report.direct_callers_count == 1
        ref = report.caller_references[0]
        assert ref.referencing_file == "pkg/service.py"
        assert ref.hop_distance == 1

    def test_imported_symbols_captured(self):
        changed = _mod("pkg/utils.py", "pkg.utils", functions=[_func("helper")])
        importer = _mod(
            "pkg/service.py",
            "pkg.service",
            imports=[_abs_import("pkg.utils", ("helper", "other"))],
        )
        repo = _repo(changed, importer)
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/utils.py"})
        ref = report.caller_references[0]
        assert "helper" in ref.imported_symbols
        assert "other" in ref.imported_symbols

    def test_unrelated_module_not_in_callers(self):
        changed = _mod("pkg/a.py", "pkg.a")
        unrelated = _mod("pkg/b.py", "pkg.b", imports=[_abs_import("pkg.c")])
        pkg_c = _mod("pkg/c.py", "pkg.c")
        repo = _repo(changed, unrelated, pkg_c)
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/a.py"})
        caller_files = {r.referencing_file for r in report.caller_references}
        assert "pkg/b.py" not in caller_files

    def test_module_importing_itself_not_counted(self):
        # A module that self-imports shouldn't appear as a caller.
        m = _mod(
            "pkg/a.py",
            "pkg.a",
            functions=[_func("foo")],
            imports=[_abs_import("pkg.a", ("foo",))],
        )
        repo = _repo(m)
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/a.py"})
        assert report.direct_callers_count == 0


# ---------------------------------------------------------------------------
# Import graph — relative imports
# ---------------------------------------------------------------------------


class TestRelativeImports:
    def test_direct_relative_import_level1(self):
        """
        If ``service.py`` does ``from . import utils``, it should appear as
        a direct caller of ``utils.py``.

        Module layout:
          pkg/utils.py  =>  "pkg.utils"
          pkg/service.py => "pkg.service"
        """
        changed = _mod("pkg/utils.py", "pkg.utils", functions=[_func("helper")])
        # from . import utils  (level=1, module=None or "utils")
        rel_imp = _rel_import("utils", ("helper",), level=1)
        importer = _mod("pkg/service.py", "pkg.service", imports=[rel_imp])
        repo = _repo(changed, importer)
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/utils.py"})
        assert report.direct_callers_count == 1
        assert report.caller_references[0].hop_distance == 1

    def test_relative_import_level2(self):
        """
        ``sub/service.py`` does ``from .. import utils`` to reach ``pkg/utils.py``.
        Layout:
          pkg/utils.py      => "pkg.utils"
          pkg/sub/service.py => "pkg.sub.service"
        """
        changed = _mod("pkg/utils.py", "pkg.utils", functions=[_func("helper")])
        rel_imp = _rel_import("utils", ("helper",), level=2)
        importer = _mod("pkg/sub/service.py", "pkg.sub.service", imports=[rel_imp])
        repo = _repo(changed, importer)
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/utils.py"})
        assert report.direct_callers_count == 1


# ---------------------------------------------------------------------------
# Transitive callers (BFS)
# ---------------------------------------------------------------------------


class TestTransitiveCallers:
    def _build_chain(self) -> tuple[RepositoryMap, list[str]]:
        """
        A  ->  B  ->  C  (A imports B, B imports C)
        Changed: C.py
        Expected: B=direct (hop 1), A=transitive (hop 2)
        """
        c = _mod("pkg/c.py", "pkg.c", functions=[_func("fn_c")])
        b = _mod("pkg/b.py", "pkg.b", imports=[_abs_import("pkg.c", ("fn_c",))])
        a = _mod("pkg/a.py", "pkg.a", imports=[_abs_import("pkg.b")])
        return _repo(c, b, a), ["pkg/c.py"]

    def test_direct_and_transitive_counts(self):
        repo, changed = self._build_chain()
        report = ChangeImpactAnalyzer(repo).analyze(changed)
        assert report.direct_callers_count == 1
        assert report.transitive_callers_count == 1

    def test_hop_distances(self):
        repo, changed = self._build_chain()
        report = ChangeImpactAnalyzer(repo).analyze(changed)
        hops = {r.referencing_file: r.hop_distance for r in report.caller_references}
        assert hops["pkg/b.py"] == 1
        assert hops["pkg/a.py"] == 2

    def test_max_depth_respected(self):
        """With max_depth=1, only direct callers are included."""
        c = _mod("pkg/c.py", "pkg.c")
        b = _mod("pkg/b.py", "pkg.b", imports=[_abs_import("pkg.c")])
        a = _mod("pkg/a.py", "pkg.a", imports=[_abs_import("pkg.b")])
        repo = _repo(c, b, a)
        report = ChangeImpactAnalyzer(repo, max_depth=1).analyze({"pkg/c.py"})
        assert report.direct_callers_count == 1
        assert report.transitive_callers_count == 0

    def test_max_depth_3_follows_three_hops(self):
        """
        D -> C -> B -> A (chain of 3). With max_depth=3, D should be hop 3.
        """
        a = _mod("a.py", "a", functions=[_func("fn")])
        b = _mod("b.py", "b", imports=[_abs_import("a")])
        c = _mod("c.py", "c", imports=[_abs_import("b")])
        d = _mod("d.py", "d", imports=[_abs_import("c")])
        repo = _repo(a, b, c, d)
        report = ChangeImpactAnalyzer(repo, max_depth=3).analyze({"a.py"})
        hops = {r.referencing_file: r.hop_distance for r in report.caller_references}
        assert hops.get("b.py") == 1
        assert hops.get("c.py") == 2
        assert hops.get("d.py") == 3

    def test_blast_radius_scales_with_affected_modules(self):
        """A change that affects all 3 remaining modules should give high blast radius."""
        core = _mod("core.py", "core", functions=[_func("fn")])
        a = _mod("a.py", "a", imports=[_abs_import("core")])
        b = _mod("b.py", "b", imports=[_abs_import("core")])
        c = _mod("c.py", "c", imports=[_abs_import("core")])
        repo = _repo(core, a, b, c)
        report = ChangeImpactAnalyzer(repo).analyze({"core.py"})
        # 3 out of 4 total modules affected → 0.75
        assert report.blast_radius_score == pytest.approx(0.75, abs=0.01)

    def test_isolated_change_blast_radius_zero(self):
        a = _mod("a.py", "a", functions=[_func("fn")])
        b = _mod("b.py", "b")  # no imports of a
        repo = _repo(a, b)
        report = ChangeImpactAnalyzer(repo).analyze({"a.py"})
        assert report.blast_radius_score == 0.0
        assert report.direct_callers_count == 0


# ---------------------------------------------------------------------------
# Affected module ordering and exposure score
# ---------------------------------------------------------------------------


class TestAffectedModuleOrdering:
    def test_direct_caller_has_higher_exposure_than_transitive(self):
        c = _mod("c.py", "c", functions=[_func("fn")])
        b = _mod("b.py", "b", imports=[_abs_import("c")])
        a = _mod("a.py", "a", imports=[_abs_import("b")])
        repo = _repo(c, b, a)
        report = ChangeImpactAnalyzer(repo).analyze({"c.py"})
        scores = {m.file_path: m.exposure_score for m in report.affected_modules}
        assert scores["b.py"] > scores["a.py"]

    def test_affected_modules_sorted_descending_by_exposure(self):
        c = _mod("c.py", "c")
        b = _mod("b.py", "b", imports=[_abs_import("c")])
        a = _mod("a.py", "a", imports=[_abs_import("b")])
        repo = _repo(c, b, a)
        report = ChangeImpactAnalyzer(repo).analyze({"c.py"})
        scores = [m.exposure_score for m in report.affected_modules]
        assert scores == sorted(scores, reverse=True)

    def test_direct_import_count_on_affected_module(self):
        changed = _mod("utils.py", "utils", functions=[_func("a"), _func("b")])
        importer = _mod(
            "svc.py",
            "svc",
            imports=[_abs_import("utils", ("a", "b"))],
        )
        repo = _repo(changed, importer)
        report = ChangeImpactAnalyzer(repo).analyze({"utils.py"})
        affected = {m.file_path: m for m in report.affected_modules}
        assert affected["svc.py"].direct_import_count == 2


# ---------------------------------------------------------------------------
# Targeted test file selection
# ---------------------------------------------------------------------------


class TestTargetedTestFileSelection:
    def _test_mod(self, name: str, imports: list[ImportStatement] | None = None) -> PythonModuleMap:
        return _mod(f"tests/{name}.py", f"tests.{name}", imports=imports, is_test=True)

    def test_tier1_direct_importing_test_file_first(self):
        changed = _mod("pkg/utils.py", "pkg.utils")
        test = self._test_mod("test_utils", imports=[_abs_import("pkg.utils")])
        other_test = self._test_mod("test_something_else")
        repo = _repo(changed, test, other_test, test_paths=(
            "tests/test_utils.py", "tests/test_something_else.py"
        ))
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/utils.py"})
        # test_utils should be first (direct importer)
        assert report.targeted_test_files[0] == "tests/test_utils.py"

    def test_tier2_mirror_name_matching(self):
        """test_utils.py mirrors utils.py by filename stem."""
        changed = _mod("pkg/utils.py", "pkg.utils")
        test = self._test_mod("test_utils")  # no import, but name matches
        repo = _repo(changed, test, test_paths=("tests/test_utils.py",))
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/utils.py"})
        assert "tests/test_utils.py" in report.targeted_test_files

    def test_tier4_fallback_to_all_tests_when_nothing_found(self):
        """A changed file with no callers and no name match → all tests as fallback."""
        changed = _mod("pkg/obscure.py", "pkg.obscure")
        test_a = self._test_mod("test_alpha")
        test_b = self._test_mod("test_beta")
        repo = _repo(changed, test_a, test_b, test_paths=(
            "tests/test_alpha.py", "tests/test_beta.py"
        ))
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/obscure.py"})
        assert "tests/test_alpha.py" in report.targeted_test_files
        assert "tests/test_beta.py" in report.targeted_test_files

    def test_no_duplicate_test_files(self):
        """A test file that both imports and name-matches should appear once."""
        changed = _mod("pkg/utils.py", "pkg.utils")
        test = self._test_mod("test_utils", imports=[_abs_import("pkg.utils")])
        repo = _repo(changed, test, test_paths=("tests/test_utils.py",))
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/utils.py"})
        assert len(report.targeted_test_files) == len(set(report.targeted_test_files))

    def test_test_caller_marked_is_test_file_true(self):
        changed = _mod("core.py", "core")
        test_importer = self._test_mod("test_core", imports=[_abs_import("core")])
        repo = _repo(changed, test_importer)
        report = ChangeImpactAnalyzer(repo).analyze({"core.py"})
        test_refs = [r for r in report.caller_references if r.is_test_file]
        assert len(test_refs) == 1


# ---------------------------------------------------------------------------
# Graph caching
# ---------------------------------------------------------------------------


class TestGraphCaching:
    def test_graph_rebuilt_only_once(self):
        """Second analyze() call reuses cached graph (no exception, same result)."""
        a = _mod("a.py", "a", functions=[_func("fn")])
        b = _mod("b.py", "b", imports=[_abs_import("a")])
        repo = _repo(a, b)
        analyzer = ChangeImpactAnalyzer(repo)
        r1 = analyzer.analyze({"a.py"})
        r2 = analyzer.analyze({"a.py"})
        assert r1.blast_radius_score == r2.blast_radius_score
        assert r1.direct_callers_count == r2.direct_callers_count

    def test_different_change_sets_give_different_reports(self):
        a = _mod("a.py", "a", functions=[_func("fn")])
        b = _mod("b.py", "b", functions=[_func("fn")])
        c = _mod("c.py", "c", imports=[_abs_import("a")])
        repo = _repo(a, b, c)
        analyzer = ChangeImpactAnalyzer(repo)
        r_a = analyzer.analyze({"a.py"})
        r_b = analyzer.analyze({"b.py"})
        # Changing a.py → c is affected; changing b.py → no callers
        assert r_a.direct_callers_count == 1
        assert r_b.direct_callers_count == 0


# ---------------------------------------------------------------------------
# ImpactReport model
# ---------------------------------------------------------------------------


class TestImpactReportModel:
    def test_frozen_model(self):
        report = ImpactReport(changed_file_paths=("a.py",))
        with pytest.raises(Exception):
            report.blast_radius_score = 0.9  # type: ignore[misc]

    def test_blast_radius_bounds(self):
        """blast_radius_score must be in [0, 1]."""
        with pytest.raises(Exception):
            ImpactReport(changed_file_paths=("a.py",), blast_radius_score=1.5)

    def test_summary_string_contains_counts(self):
        a = _mod("a.py", "a", functions=[_func("fn")])
        b = _mod("b.py", "b", imports=[_abs_import("a")])
        repo = _repo(a, b)
        report = ChangeImpactAnalyzer(repo).analyze({"a.py"})
        summary = report.summary()
        assert "1 file" in summary
        assert "Blast radius" in summary

    def test_summary_truncates_long_symbol_list(self):
        """More than 5 symbols should show (+N more) in summary."""
        fns = [_func(f"f{i}") for i in range(8)]
        m = _mod("big.py", "big", functions=fns)
        repo = _repo(m)
        report = ChangeImpactAnalyzer(repo).analyze({"big.py"})
        summary = report.summary()
        assert "+3 more" in summary

    def test_total_modules_analyzed_correct(self):
        mods = [_mod(f"m{i}.py", f"m{i}") for i in range(7)]
        repo = _repo(*mods)
        report = ChangeImpactAnalyzer(repo).analyze({"m0.py"})
        assert report.total_modules_analyzed == 7

    def test_changed_file_paths_sorted(self):
        a = _mod("z.py", "z")
        b = _mod("a.py", "a")
        repo = _repo(a, b)
        report = ChangeImpactAnalyzer(repo).analyze(["z.py", "a.py"])
        assert report.changed_file_paths == ("a.py", "z.py")


# ---------------------------------------------------------------------------
# Multi-file change sets
# ---------------------------------------------------------------------------


class TestMultiFileChangeSet:
    def test_two_files_changed_symbols_from_both(self):
        m1 = _mod("pkg/a.py", "pkg.a", functions=[_func("fa")])
        m2 = _mod("pkg/b.py", "pkg.b", functions=[_func("fb")])
        repo = _repo(m1, m2)
        report = ChangeImpactAnalyzer(repo).analyze({"pkg/a.py", "pkg/b.py"})
        sym_names = {s.symbol_name for s in report.changed_symbols}
        assert {"fa", "fb"} == sym_names

    def test_callers_of_multiple_changed_modules_all_captured(self):
        m_a = _mod("a.py", "a", functions=[_func("fn_a")])
        m_b = _mod("b.py", "b", functions=[_func("fn_b")])
        # c imports a, d imports b
        m_c = _mod("c.py", "c", imports=[_abs_import("a")])
        m_d = _mod("d.py", "d", imports=[_abs_import("b")])
        repo = _repo(m_a, m_b, m_c, m_d)
        report = ChangeImpactAnalyzer(repo).analyze({"a.py", "b.py"})
        caller_files = {r.referencing_file for r in report.caller_references}
        assert "c.py" in caller_files
        assert "d.py" in caller_files

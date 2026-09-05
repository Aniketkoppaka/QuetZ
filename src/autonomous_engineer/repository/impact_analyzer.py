"""
repository/impact_analyzer.py -- Semantic Change-Impact Analyzer (Phase 3.1).

Given:
  - A ``RepositoryMap`` (AST symbol table + import graph for the full repo).
  - A set of changed file paths (the proposed patch's blast boundary).

Produces:
  - An ``ImpactReport`` containing:
      * ``ChangedSymbols``  — top-level functions/classes directly modified.
      * ``CallerReferences`` — modules that call / import those symbols.
      * ``AffectedModules`` — ranked list of modules with downstream exposure.
      * ``TargetedTestFiles`` — subset of test files most likely to exercise
                               the modified symbols; used to run focused
                               verification rather than the full suite.
      * ``BlastRadiusScore`` — normalised float [0.0, 1.0] indicating breadth
                               of downstream exposure relative to repo size.

Design constraints:
  - Pure static analysis; repository code is NEVER executed or imported.
  - All data is read from the immutable RepositoryMap; no disk access.
  - Returns a frozen Pydantic model — composable with VerificationCertificate
    and AbstentionEngine.
  - O(modules × symbols) — acceptable for repositories up to ~100 k LOC.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.domain.models import (
    PythonModuleMap,
    RepositoryMap,
)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


class ChangedSymbol(BaseModel):
    """A top-level symbol (function or class) declared in a modified file."""

    model_config = ConfigDict(frozen=True)

    file_path: str = Field(description="Repo-relative path of the defining file.")
    module_name: str = Field(description="Dotted module name of the defining module.")
    symbol_name: str = Field(description="Simple symbol name (e.g. 'process_data').")
    qualified_name: str = Field(
        description="Dotted qualified name (e.g. 'DataProcessor.process_data')."
    )
    symbol_kind: str = Field(
        description="'function', 'method', or 'class'."
    )


class CallerReference(BaseModel):
    """
    A module that imports or references a changed symbol.

    Determined by static import graph analysis: if module M imports from
    the changed module (or uses a bare ``import changed_module``), then M
    is a *direct* caller.  Transitive callers are identified by following
    the import chain up to ``max_depth`` hops.
    """

    model_config = ConfigDict(frozen=True)

    referencing_file: str = Field(description="Repo-relative path of the referencing file.")
    referencing_module: str = Field(description="Dotted module name of the referencing file.")
    imported_symbols: tuple[str, ...] = Field(
        default=(),
        description="Named symbols imported from the changed module (empty = whole-module import).",
    )
    hop_distance: int = Field(
        default=1,
        ge=1,
        description="Import-graph distance from the changed file (1 = direct import).",
    )
    is_test_file: bool = Field(
        default=False,
        description="True if this referencing file is a test file.",
    )


class AffectedModule(BaseModel):
    """A module with measurable downstream exposure to the change set."""

    model_config = ConfigDict(frozen=True)

    file_path: str = Field(description="Repo-relative path.")
    module_name: str = Field(description="Dotted module name.")
    exposure_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Normalised exposure score combining hop distance and symbol-import "
            "specificity. Higher = more directly exposed."
        ),
    )
    direct_import_count: int = Field(
        default=0,
        ge=0,
        description="Number of changed symbols directly imported.",
    )
    is_test_file: bool = Field(default=False)


class ImpactReport(BaseModel):
    """
    Complete blast-radius analysis for a proposed change set.

    All collections are ordered by decreasing relevance / exposure.
    """

    model_config = ConfigDict(frozen=True)

    changed_file_paths: tuple[str, ...] = Field(
        description="The input set of modified repo-relative file paths."
    )
    changed_symbols: tuple[ChangedSymbol, ...] = Field(
        default=(),
        description="Top-level symbols (functions/classes) exported from the changed files.",
    )
    caller_references: tuple[CallerReference, ...] = Field(
        default=(),
        description="Modules that import from or reference the changed files.",
    )
    affected_modules: tuple[AffectedModule, ...] = Field(
        default=(),
        description="All modules with downstream exposure, ranked by exposure_score.",
    )
    targeted_test_files: tuple[str, ...] = Field(
        default=(),
        description=(
            "Focused subset of test file paths most likely to exercise the changed "
            "symbols. Ordered by relevance. Use these for targeted verification."
        ),
    )
    blast_radius_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Normalised [0, 1] measure of downstream exposure breadth. "
            "0.0 = completely isolated change. 1.0 = affects every module."
        ),
    )
    total_modules_analyzed: int = Field(
        default=0,
        ge=0,
        description="Total Python modules in the repository (denominator for blast radius).",
    )
    direct_callers_count: int = Field(
        default=0,
        ge=0,
        description="Number of modules with hop_distance == 1.",
    )
    transitive_callers_count: int = Field(
        default=0,
        ge=0,
        description="Number of modules with hop_distance > 1.",
    )

    def summary(self) -> str:
        """Return a one-paragraph human-readable impact summary."""
        symbol_names = ", ".join(s.qualified_name for s in self.changed_symbols[:5])
        if len(self.changed_symbols) > 5:
            symbol_names += f" (+{len(self.changed_symbols) - 5} more)"
        test_count = len(self.targeted_test_files)
        return (
            f"Change set touches {len(self.changed_file_paths)} file(s) exposing "
            f"{len(self.changed_symbols)} symbol(s) [{symbol_names}]. "
            f"Blast radius: {self.blast_radius_score:.2f} "
            f"({self.direct_callers_count} direct + {self.transitive_callers_count} transitive callers). "
            f"Targeted test files: {test_count}."
        )


# ---------------------------------------------------------------------------
# Core analyzer
# ---------------------------------------------------------------------------

_DEFAULT_MAX_DEPTH = 3  # maximum transitive import hops to follow


class ChangeImpactAnalyzer:
    """
    Computes semantic change impact from an immutable RepositoryMap.

    Usage::

        analyzer = ChangeImpactAnalyzer(repo_map)
        report = analyzer.analyze(changed_file_paths={"src/foo/bar.py"})

    The analyzer builds its internal import graph lazily on first ``analyze``
    call and caches it for subsequent calls with the same RepositoryMap.
    """

    def __init__(
        self,
        repo_map: RepositoryMap,
        max_depth: int = _DEFAULT_MAX_DEPTH,
    ) -> None:
        self._repo_map = repo_map
        self._max_depth = max(1, max_depth)

        # Built lazily:
        # module_name -> PythonModuleMap
        self._module_index: dict[str, PythonModuleMap] | None = None
        # file_path -> PythonModuleMap
        self._file_index: dict[str, PythonModuleMap] | None = None
        # module_name -> set of module_names it imports from
        self._import_graph: dict[str, set[str]] | None = None
        # module_name -> set of module_names that import it (reverse graph)
        self._reverse_graph: dict[str, set[str]] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        changed_file_paths: set[str] | frozenset[str] | list[str],
    ) -> ImpactReport:
        """
        Compute blast radius for *changed_file_paths*.

        Parameters
        ----------
        changed_file_paths:
            Repo-relative paths of the files modified by the patch.
            Non-Python paths are accepted but contribute no symbol analysis.

        Returns
        -------
        ImpactReport
            Fully populated impact report, frozen and ready for evidence
            embedding in a VerificationCertificate.
        """
        self._ensure_graph()

        changed_paths = tuple(sorted(set(changed_file_paths)))

        # 1. Collect symbols exported from changed Python files.
        changed_symbols = self._collect_changed_symbols(changed_paths)

        # 2. Identify the module names of changed files.
        changed_module_names: set[str] = set()
        for path in changed_paths:
            mod = self._file_index.get(path)  # type: ignore[union-attr]
            if mod is not None:
                changed_module_names.add(mod.module_name)

        # 3. BFS over reverse import graph up to max_depth.
        caller_refs, affected_modules = self._compute_callers(changed_module_names)

        # 4. Identify targeted test files.
        targeted_tests = self._select_targeted_tests(
            changed_paths=changed_paths,
            changed_module_names=changed_module_names,
            caller_refs=caller_refs,
        )

        # 5. Blast radius score.
        total_modules = len(self._module_index or {})  # type: ignore[arg-type]
        unique_affected = len(set(m.file_path for m in affected_modules))
        blast_radius = (
            min(unique_affected / total_modules, 1.0) if total_modules > 0 else 0.0
        )

        direct_count = sum(1 for c in caller_refs if c.hop_distance == 1)
        transitive_count = sum(1 for c in caller_refs if c.hop_distance > 1)

        return ImpactReport(
            changed_file_paths=changed_paths,
            changed_symbols=tuple(changed_symbols),
            caller_references=tuple(caller_refs),
            affected_modules=tuple(
                sorted(affected_modules, key=lambda m: m.exposure_score, reverse=True)
            ),
            targeted_test_files=tuple(targeted_tests),
            blast_radius_score=round(blast_radius, 4),
            total_modules_analyzed=total_modules,
            direct_callers_count=direct_count,
            transitive_callers_count=transitive_count,
        )

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _ensure_graph(self) -> None:
        """Build module / file indexes and import graphs if not yet done."""
        if self._module_index is not None:
            return

        module_index: dict[str, PythonModuleMap] = {}
        file_index: dict[str, PythonModuleMap] = {}
        import_graph: dict[str, set[str]] = {}
        reverse_graph: dict[str, set[str]] = {}

        for mod in self._repo_map.python_modules:
            module_index[mod.module_name] = mod
            file_index[mod.file_path] = mod
            import_graph.setdefault(mod.module_name, set())
            reverse_graph.setdefault(mod.module_name, set())

        # Build directed import edges: A imports B  =>  import_graph[A] has B
        for mod in self._repo_map.python_modules:
            for imp in mod.imports:
                imported_name = self._resolve_import_module_name(mod, imp)
                if imported_name and imported_name in module_index:
                    import_graph[mod.module_name].add(imported_name)
                    reverse_graph.setdefault(imported_name, set()).add(mod.module_name)

        self._module_index = module_index
        self._file_index = file_index
        self._import_graph = import_graph
        self._reverse_graph = reverse_graph

    def _resolve_import_module_name(
        self,
        importer: PythonModuleMap,
        imp: Any,  # ImportStatement
    ) -> str | None:
        """
        Resolve an import statement to a dotted module name that may exist in
        this repository.

        Handles:
          - Absolute ``import foo.bar``
          - Absolute ``from foo.bar import baz``
          - Relative ``from . import baz``  (level=1)
          - Relative ``from ..sub import thing``  (level=2)

        Returns the resolved module name string, or ``None`` if unresolvable.
        """
        if imp.level == 0:
            # Absolute import — module name is directly available.
            return imp.module  # may be None for bare `import foo`

        # Relative import: compute anchor from importer's module name.
        # e.g. importer = "autonomous_engineer.repository.analyzer"
        #      level=1 => "autonomous_engineer.repository"
        parts = importer.module_name.split(".")
        # Pop (level) parts from the tail; level=1 means current package.
        anchor_parts = parts[: max(len(parts) - imp.level, 0)]
        if imp.module:
            anchor_parts.extend(imp.module.split("."))
        return ".".join(anchor_parts) if anchor_parts else None

    # ------------------------------------------------------------------
    # Symbol collection
    # ------------------------------------------------------------------

    def _collect_changed_symbols(
        self,
        changed_paths: tuple[str, ...],
    ) -> list[ChangedSymbol]:
        """
        Collect all top-level functions and classes from *changed_paths*.
        Methods are included as separate symbols with their qualified names.
        """
        symbols: list[ChangedSymbol] = []
        for path in changed_paths:
            mod = (self._file_index or {}).get(path)
            if mod is None:
                continue  # non-Python or unanalyzed file

            # Top-level functions
            for func in mod.functions:
                symbols.append(
                    ChangedSymbol(
                        file_path=path,
                        module_name=mod.module_name,
                        symbol_name=func.name,
                        qualified_name=func.qualified_name,
                        symbol_kind="function",
                    )
                )

            # Classes and their methods
            for cls in mod.classes:
                symbols.append(
                    ChangedSymbol(
                        file_path=path,
                        module_name=mod.module_name,
                        symbol_name=cls.name,
                        qualified_name=cls.qualified_name,
                        symbol_kind="class",
                    )
                )
                for method in cls.methods:
                    symbols.append(
                        ChangedSymbol(
                            file_path=path,
                            module_name=mod.module_name,
                            symbol_name=method.name,
                            qualified_name=method.qualified_name,
                            symbol_kind="method",
                        )
                    )

        return symbols

    # ------------------------------------------------------------------
    # BFS over reverse import graph
    # ------------------------------------------------------------------

    def _compute_callers(
        self,
        changed_module_names: set[str],
    ) -> tuple[list[CallerReference], list[AffectedModule]]:
        """
        BFS from *changed_module_names* over the reverse import graph up to
        ``self._max_depth`` hops.

        Returns two parallel lists:
          - ``caller_refs``     — CallerReference per referencing module.
          - ``affected_modules`` — AffectedModule per referencing module.
        """
        rev = self._reverse_graph or {}
        file_idx = self._file_index or {}
        mod_idx = self._module_index or {}

        visited: dict[str, int] = {}  # module_name -> hop_distance
        queue: list[tuple[str, int]] = []  # (module_name, hop_distance)

        # Seed BFS with all modules that directly import any changed module.
        for changed_mod in changed_module_names:
            for caller_name in rev.get(changed_mod, set()):
                if caller_name not in changed_module_names and caller_name not in visited:
                    visited[caller_name] = 1
                    queue.append((caller_name, 1))

        head = 0
        while head < len(queue):
            current_mod, current_depth = queue[head]
            head += 1

            if current_depth >= self._max_depth:
                continue

            for next_caller in rev.get(current_mod, set()):
                if next_caller not in changed_module_names and next_caller not in visited:
                    visited[next_caller] = current_depth + 1
                    queue.append((next_caller, current_depth + 1))

        # Build CallerReference and AffectedModule for each visited module.
        caller_refs: list[CallerReference] = []
        affected_modules: list[AffectedModule] = []

        for mod_name, hop in visited.items():
            mod_map = mod_idx.get(mod_name)
            if mod_map is None:
                continue

            # Collect which changed-module symbols this module imports (direct only).
            imported_symbols: tuple[str, ...] = ()
            direct_import_count = 0
            if hop == 1:
                imported_symbols, direct_import_count = self._find_imported_symbols(
                    mod_map, changed_module_names
                )

            # Exposure score: direct callers get higher scores; decays with hops.
            # Also boosted by how many symbols are specifically named (vs. wildcard).
            specificity_bonus = min(direct_import_count * 0.05, 0.2) if hop == 1 else 0.0
            exposure = max(0.0, (1.0 / hop) * 0.8 + specificity_bonus)
            exposure = round(min(exposure, 1.0), 4)

            caller_refs.append(
                CallerReference(
                    referencing_file=mod_map.file_path,
                    referencing_module=mod_name,
                    imported_symbols=imported_symbols,
                    hop_distance=hop,
                    is_test_file=mod_map.is_test_file,
                )
            )
            affected_modules.append(
                AffectedModule(
                    file_path=mod_map.file_path,
                    module_name=mod_name,
                    exposure_score=exposure,
                    direct_import_count=direct_import_count,
                    is_test_file=mod_map.is_test_file,
                )
            )

        return caller_refs, affected_modules

    def _find_imported_symbols(
        self,
        mod: PythonModuleMap,
        changed_module_names: set[str],
    ) -> tuple[tuple[str, ...], int]:
        """
        Scan *mod*'s import statements to find symbols explicitly imported
        from any of the *changed_module_names*.

        Returns ``(imported_symbol_names, count)``.
        """
        names: list[str] = []
        for imp in mod.imports:
            resolved = self._resolve_import_module_name(mod, imp)
            if resolved in changed_module_names:
                names.extend(imp.names)
        return tuple(sorted(set(names))), len(names)

    # ------------------------------------------------------------------
    # Targeted test file selection
    # ------------------------------------------------------------------

    def _select_targeted_tests(
        self,
        changed_paths: tuple[str, ...],
        changed_module_names: set[str],
        caller_refs: list[CallerReference],
    ) -> list[str]:
        """
        Select the test files most likely to exercise the changed code.

        Priority order:
          1. Test files that *directly import* from the changed modules (hop=1).
          2. Test files whose *filename* mirrors a changed source file
             (e.g. ``test_foo.py`` for ``foo.py``).
          3. All remaining test files with any hop distance.

        Returns a deduplicated ordered list of repo-relative test file paths.
        """
        seen: set[str] = set()
        ordered: list[str] = []

        def _add(path: str) -> None:
            if path not in seen:
                seen.add(path)
                ordered.append(path)

        # --- Tier 1: direct importers that are test files ---
        for ref in sorted(caller_refs, key=lambda r: r.hop_distance):
            if ref.is_test_file and ref.hop_distance == 1:
                _add(ref.referencing_file)

        # --- Tier 2: mirror-name test files ---
        all_test_paths = set(self._repo_map.test_file_paths)
        for changed_path in changed_paths:
            stem = _path_stem(changed_path)
            for test_path in all_test_paths:
                test_stem = _path_stem(test_path)
                # e.g. "foo/bar" matches "tests/test_bar" or "tests/test_foo_bar"
                if stem and (
                    test_stem == f"test_{stem}"
                    or test_stem.endswith(f"_{stem}")
                    or test_stem.endswith(f"test_{stem}")
                ):
                    _add(test_path)

        # --- Tier 3: any test-file caller ---
        for ref in sorted(caller_refs, key=lambda r: r.hop_distance):
            if ref.is_test_file:
                _add(ref.referencing_file)

        # --- Tier 4: all repo test files (fallback; only if nothing found) ---
        if not ordered:
            for tp in sorted(all_test_paths):
                _add(tp)

        return ordered


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _path_stem(file_path: str) -> str:
    """
    Return the bare filename stem (without extension) for *file_path*.
    Strips ``test_`` / ``tests_`` prefix if present, so "test_bar.py"
    and "bar.py" can be paired.
    """
    # Normalize separators and take the last component without extension.
    name = re.split(r"[/\\]", file_path)[-1]
    if "." in name:
        name = name.rsplit(".", 1)[0]
    # Remove leading test_ so "test_bar" and "bar" share the same stem.
    name = re.sub(r"^tests?_", "", name)
    return name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "AffectedModule",
    "CallerReference",
    "ChangeImpactAnalyzer",
    "ChangedSymbol",
    "ImpactReport",
]

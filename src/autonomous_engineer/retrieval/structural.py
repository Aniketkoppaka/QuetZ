"""
retrieval/structural.py -- AST structural relationship code retriever.

Expands candidate code items along structural graph edges:
1. Local import dependencies (following local imports from relevant modules)
2. Associated test files (linking implementation modules to their corresponding tests)
3. Configuration relevance (linking config files when issues indicate build/config context)
"""
from __future__ import annotations

from pathlib import Path

from autonomous_engineer.domain.models import (
    PythonModuleMap,
    RepositoryMap,
    RetrievalItem,
    RetrievalReason,
)
from autonomous_engineer.retrieval.import_resolver import LocalImportResolver

CONFIG_KEYWORDS: frozenset[str] = frozenset({
    "config", "configuration", "dependency", "dependencies", "install",
    "installation", "requirements", "pyproject", "setup", "build", "pip",
    "poetry", "version", "environment", "tox", "pytest", "mypy", "ruff",
})


class StructuralWeights:
    """Configurable score boosts for structural expansions."""

    def __init__(
        self,
        import_expansion_weight: float = 2.0,
        test_association_weight: float = 2.5,
        config_match_weight: float = 1.5,
    ) -> None:
        self.import_expansion_weight = import_expansion_weight
        self.test_association_weight = test_association_weight
        self.config_match_weight = config_match_weight


class StructuralRetriever:
    """Expands code context through AST import graphs, tests, and configuration links."""

    def __init__(
        self,
        weights: StructuralWeights | None = None,
    ) -> None:
        self._weights = weights or StructuralWeights()

    def expand(
        self,
        seed_items: list[RetrievalItem],
        repo_map: RepositoryMap,
        query: str = "",
        include_imports: bool = True,
        include_tests: bool = True,
        include_config: bool = True,
    ) -> list[RetrievalItem]:
        """
        Expand initial seed items along structural repository edges.

        Args:
            seed_items: Initial scored candidate items (typically from lexical retrieval).
            repo_map: Deterministic RepositoryMap.
            query: Original query text (used for configuration trigger checks).
            include_imports: Whether to expand local import dependencies.
            include_tests: Whether to expand associated test files.
            include_config: Whether to expand relevant configuration files.

        Returns:
            List of new and augmented RetrievalItems from structural expansion.
        """
        expanded: list[RetrievalItem] = []
        resolver = LocalImportResolver(repo_map)

        # Index modules for fast lookup
        module_by_path: dict[str, PythonModuleMap] = {
            m.file_path: m for m in repo_map.python_modules
        }

        # Identify top seed module paths
        top_seeds = sorted(
            [it for it in seed_items if it.symbol_type in ("module", "class", "method", "function")],
            key=lambda x: x.score,
            reverse=True,
        )[:5]

        seen_expansion_paths: set[str] = {it.file_path for it in seed_items}

        # 1. Local Import Expansion
        if include_imports:
            for seed in top_seeds:
                mod = module_by_path.get(seed.file_path)
                if not mod:
                    continue

                for imp in mod.imports:
                    target_path = resolver.resolve_import(seed.file_path, imp)
                    if target_path and target_path != seed.file_path and target_path not in seen_expansion_paths:
                        seen_expansion_paths.add(target_path)
                        expanded.append(
                            RetrievalItem(
                                file_path=target_path,
                                symbol_name=None,
                                symbol_type="module",
                                score=round(self._weights.import_expansion_weight, 4),
                                reasons=(
                                    RetrievalReason(
                                        strategy="structural",
                                        signal="local_import_dependency",
                                        score_contribution=self._weights.import_expansion_weight,
                                        description=(
                                            f"Imported by top match {seed.file_path!r} "
                                            f"via '{imp.module or imp.names}'"
                                        ),
                                    ),
                                ),
                            )
                        )

        # 2. Associated Test File Expansion
        if include_tests:
            for seed in top_seeds:
                p = Path(seed.file_path)
                stem = p.stem.lower()
                parent_pkg = p.parent.name.lower() if p.parent.name and p.parent.name not in ("src", "lib", "") else ""
                candidate_names = {stem}
                if parent_pkg:
                    candidate_names.add(parent_pkg)

                for test_path in repo_map.test_file_paths:
                    test_stem = Path(test_path).stem.lower()
                    test_parts = {p.lower() for p in Path(test_path).parts}
                    matches = False
                    for c in candidate_names:
                        if (
                            c in test_stem
                            or test_stem.replace("test_", "") == c
                            or test_stem.replace("_test", "") == c
                            or c in test_parts
                        ):
                            matches = True
                            break

                    if matches and test_path not in seen_expansion_paths:
                        seen_expansion_paths.add(test_path)
                        expanded.append(
                            RetrievalItem(
                                file_path=test_path,
                                symbol_name=None,
                                symbol_type="test",
                                score=round(self._weights.test_association_weight, 4),
                                reasons=(
                                    RetrievalReason(
                                        strategy="structural",
                                        signal="associated_test_file",
                                        score_contribution=self._weights.test_association_weight,
                                        description=f"Associated test file for {seed.file_path!r}",
                                    ),
                                ),
                            )
                        )

        # 3. Configuration Expansion (if query indicates config/build context)
        if include_config:
            query_words = set(query.lower().split())
            if query_words.intersection(CONFIG_KEYWORDS):
                for cfg_path in repo_map.configuration_file_paths:
                    if cfg_path not in seen_expansion_paths:
                        seen_expansion_paths.add(cfg_path)
                        expanded.append(
                            RetrievalItem(
                                file_path=cfg_path,
                                symbol_name=None,
                                symbol_type="config",
                                score=round(self._weights.config_match_weight, 4),
                                reasons=(
                                    RetrievalReason(
                                        strategy="structural",
                                        signal="configuration_relevance",
                                        score_contribution=self._weights.config_match_weight,
                                        description="Project configuration file matched issue context",
                                    ),
                                ),
                            )
                        )

        return expanded
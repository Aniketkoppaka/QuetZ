"""
retrieval/lexical.py -- Transparent multi-signal lexical code retriever.

Scores files, classes, methods, and functions based on token overlap across:
- Filenames and directory paths
- Class, function, and method identifiers
- Module and symbol docstrings
- Imported module names

Produces explainable score decompositions with RetrievalReason records.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from autonomous_engineer.domain.models import (
    ClassSymbol,
    FunctionSymbol,
    PythonModuleMap,
    RepositoryMap,
    RetrievalItem,
    RetrievalReason,
)
from autonomous_engineer.retrieval.tokenizer import CodeTokenizer


class LexicalWeights:
    """Configurable weights for lexical match signals."""

    def __init__(
        self,
        filename_weight: float = 4.0,
        symbol_name_weight: float = 3.5,
        path_weight: float = 1.5,
        docstring_weight: float = 1.0,
        import_weight: float = 0.8,
    ) -> None:
        self.filename_weight = filename_weight
        self.symbol_name_weight = symbol_name_weight
        self.path_weight = path_weight
        self.docstring_weight = docstring_weight
        self.import_weight = import_weight


class LexicalRetriever:
    """Retrieves code files and symbols using multi-signal lexical token matching."""

    def __init__(
        self,
        tokenizer: CodeTokenizer | None = None,
        weights: LexicalWeights | None = None,
    ) -> None:
        self._tokenizer = tokenizer or CodeTokenizer()
        self._weights = weights or LexicalWeights()

    def retrieve(
        self,
        query: str,
        repo_map: RepositoryMap,
    ) -> list[RetrievalItem]:
        """
        Score all files, classes, and functions in the repository against the query.

        Args:
            query: Issue title and description text.
            repo_map: Deterministic RepositoryMap.

        Returns:
            List of scored RetrievalItem objects with detailed reasons.
        """
        query_tokens = set(self._tokenizer.tokenize_text(query))
        if not query_tokens:
            return []

        results: list[RetrievalItem] = []

        # 1. Score Python modules and their symbols
        for mod in repo_map.python_modules:
            mod_items = self._score_module(mod, query_tokens)
            results.extend(mod_items)

        # 2. Score non-Python files (e.g. README.md, config files)
        for non_py_path in repo_map.non_python_file_paths:
            non_py_item = self._score_non_python_file(non_py_path, query_tokens)
            if non_py_item is not None:
                results.append(non_py_item)

        return results

    def _score_module(
        self,
        mod: PythonModuleMap,
        query_tokens: set[str],
    ) -> list[RetrievalItem]:
        """Score a Python module at the file level and symbol level."""
        items: list[RetrievalItem] = []
        p = Path(mod.file_path)

        # Module / File level scoring
        file_tokens = set(self._tokenizer.tokenize_identifier(p.stem))
        path_tokens = set(self._tokenizer.tokenize_identifier(str(p.parent))) - file_tokens

        file_overlap = query_tokens.intersection(file_tokens)
        path_overlap = query_tokens.intersection(path_tokens)

        file_reasons: list[RetrievalReason] = []
        file_score = 0.0

        if file_overlap:
            contrib = len(file_overlap) * self._weights.filename_weight
            file_score += contrib
            file_reasons.append(
                RetrievalReason(
                    strategy="lexical",
                    signal="filename_match",
                    score_contribution=contrib,
                    description=f"Matched filename tokens: {sorted(file_overlap)}",
                )
            )

        if path_overlap:
            contrib = len(path_overlap) * self._weights.path_weight
            file_score += contrib
            file_reasons.append(
                RetrievalReason(
                    strategy="lexical",
                    signal="path_match",
                    score_contribution=contrib,
                    description=f"Matched directory path tokens: {sorted(path_overlap)}",
                )
            )

        # Docstring match at module level
        if mod.docstring:
            doc_tokens = set(self._tokenizer.tokenize_text(mod.docstring))
            doc_overlap = query_tokens.intersection(doc_tokens)
            if doc_overlap:
                contrib = len(doc_overlap) * self._weights.docstring_weight
                file_score += contrib
                file_reasons.append(
                    RetrievalReason(
                        strategy="lexical",
                        signal="docstring_match",
                        score_contribution=contrib,
                        description=f"Matched module docstring tokens: {sorted(doc_overlap)}",
                    )
                )

        # Import match at module level
        import_tokens: set[str] = set()
        for imp in mod.imports:
            if imp.module:
                import_tokens.update(self._tokenizer.tokenize_identifier(imp.module))
            for n in imp.names:
                import_tokens.update(self._tokenizer.tokenize_identifier(n))

        imp_overlap = query_tokens.intersection(import_tokens)
        if imp_overlap:
            contrib = len(imp_overlap) * self._weights.import_weight
            file_score += contrib
            file_reasons.append(
                RetrievalReason(
                    strategy="lexical",
                    signal="import_match",
                    score_contribution=contrib,
                    description=f"Matched imported symbols: {sorted(imp_overlap)}",
                )
            )

        if file_score > 0:
            items.append(
                RetrievalItem(
                    file_path=mod.file_path,
                    symbol_name=None,
                    symbol_type="test" if mod.is_test_file else "module",
                    start_line=1,
                    end_line=mod.line_count or None,
                    score=round(file_score, 4),
                    reasons=tuple(file_reasons),
                )
            )

        # Symbol level scoring: Classes & Methods
        for cls_sym in mod.classes:
            items.extend(self._score_class(mod.file_path, cls_sym, query_tokens))

        # Symbol level scoring: Top-level Functions
        for func_sym in mod.functions:
            func_item = self._score_function(mod.file_path, func_sym, query_tokens)
            if func_item is not None:
                items.append(func_item)

        return items

    def _score_class(
        self,
        file_path: str,
        cls_sym: ClassSymbol,
        query_tokens: set[str],
    ) -> list[RetrievalItem]:
        """Score a class and its contained methods."""
        items: list[RetrievalItem] = []
        cls_tokens = set(self._tokenizer.tokenize_identifier(cls_sym.name))
        cls_overlap = query_tokens.intersection(cls_tokens)

        cls_reasons: list[RetrievalReason] = []
        cls_score = 0.0

        if cls_overlap:
            contrib = len(cls_overlap) * self._weights.symbol_name_weight
            cls_score += contrib
            cls_reasons.append(
                RetrievalReason(
                    strategy="lexical",
                    signal="class_name_match",
                    score_contribution=contrib,
                    description=f"Matched class name tokens: {sorted(cls_overlap)}",
                )
            )

        if cls_sym.docstring:
            doc_tokens = set(self._tokenizer.tokenize_text(cls_sym.docstring))
            doc_overlap = query_tokens.intersection(doc_tokens)
            if doc_overlap:
                contrib = len(doc_overlap) * self._weights.docstring_weight
                cls_score += contrib
                cls_reasons.append(
                    RetrievalReason(
                        strategy="lexical",
                        signal="class_docstring_match",
                        score_contribution=contrib,
                        description=f"Matched class docstring tokens: {sorted(doc_overlap)}",
                    )
                )

        if cls_score > 0:
            items.append(
                RetrievalItem(
                    file_path=file_path,
                    symbol_name=cls_sym.qualified_name,
                    symbol_type="class",
                    start_line=cls_sym.line_number,
                    end_line=cls_sym.end_line_number,
                    score=round(cls_score, 4),
                    reasons=tuple(cls_reasons),
                )
            )

        # Score methods
        for m in cls_sym.methods:
            m_item = self._score_function(file_path, m, query_tokens)
            if m_item is not None:
                items.append(m_item)

        # Score nested classes
        for nested in cls_sym.nested_classes:
            items.extend(self._score_class(file_path, nested, query_tokens))

        return items

    def _score_function(
        self,
        file_path: str,
        func_sym: FunctionSymbol,
        query_tokens: set[str],
    ) -> RetrievalItem | None:
        """Score an individual function or method."""
        fn_tokens = set(self._tokenizer.tokenize_identifier(func_sym.name))
        fn_overlap = query_tokens.intersection(fn_tokens)

        fn_reasons: list[RetrievalReason] = []
        fn_score = 0.0

        if fn_overlap:
            contrib = len(fn_overlap) * self._weights.symbol_name_weight
            fn_score += contrib
            fn_reasons.append(
                RetrievalReason(
                    strategy="lexical",
                    signal="function_name_match",
                    score_contribution=contrib,
                    description=f"Matched function name tokens: {sorted(fn_overlap)}",
                )
            )

        if func_sym.docstring:
            doc_tokens = set(self._tokenizer.tokenize_text(func_sym.docstring))
            doc_overlap = query_tokens.intersection(doc_tokens)
            if doc_overlap:
                contrib = len(doc_overlap) * self._weights.docstring_weight
                fn_score += contrib
                fn_reasons.append(
                    RetrievalReason(
                        strategy="lexical",
                        signal="function_docstring_match",
                        score_contribution=contrib,
                        description=f"Matched function docstring tokens: {sorted(doc_overlap)}",
                    )
                )

        if fn_score > 0:
            return RetrievalItem(
                file_path=file_path,
                symbol_name=func_sym.qualified_name,
                symbol_type="method" if func_sym.is_method else "function",
                start_line=func_sym.line_number,
                end_line=func_sym.end_line_number,
                score=round(fn_score, 4),
                reasons=tuple(fn_reasons),
            )
        return None

    def _score_non_python_file(
        self,
        file_path: str,
        query_tokens: set[str],
    ) -> RetrievalItem | None:
        """Score non-Python files (e.g. configs, README) against query tokens."""
        p = Path(file_path)
        file_tokens = set(self._tokenizer.tokenize_identifier(p.name))
        path_tokens = set(self._tokenizer.tokenize_identifier(str(p.parent))) - file_tokens

        file_overlap = query_tokens.intersection(file_tokens)
        path_overlap = query_tokens.intersection(path_tokens)

        reasons: list[RetrievalReason] = []
        score = 0.0

        if file_overlap:
            contrib = len(file_overlap) * self._weights.filename_weight
            score += contrib
            reasons.append(
                RetrievalReason(
                    strategy="lexical",
                    signal="filename_match",
                    score_contribution=contrib,
                    description=f"Matched non-Python filename: {sorted(file_overlap)}",
                )
            )

        if path_overlap:
            contrib = len(path_overlap) * self._weights.path_weight
            score += contrib
            reasons.append(
                RetrievalReason(
                    strategy="lexical",
                    signal="path_match",
                    score_contribution=contrib,
                    description=f"Matched non-Python path: {sorted(path_overlap)}",
                )
            )

        if score > 0:
            return RetrievalItem(
                file_path=file_path,
                symbol_name=None,
                symbol_type="file",
                score=round(score, 4),
                reasons=tuple(reasons),
            )
        return None
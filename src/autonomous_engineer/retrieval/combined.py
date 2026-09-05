"""
retrieval/combined.py -- Unified context retrieval orchestrator with budgeting.

Combines lexical matching and AST structural expansion into ranked, budgeted,
deterministic, and explainable RetrievalResults.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from autonomous_engineer.domain.models import (
    ContextBudget,
    Issue,
    RepositoryMap,
    RetrievalItem,
    RetrievalReason,
    RetrievalResult,
)
from autonomous_engineer.retrieval.lexical import LexicalRetriever
from autonomous_engineer.retrieval.structural import StructuralRetriever


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class ContextRetriever:
    """Unified context retriever supporting lexical, structural, and combined modes."""

    def __init__(
        self,
        lexical_retriever: LexicalRetriever | None = None,
        structural_retriever: StructuralRetriever | None = None,
    ) -> None:
        self._lexical = lexical_retriever or LexicalRetriever()
        self._structural = structural_retriever or StructuralRetriever()

    def retrieve(
        self,
        query_or_issue: str | Issue,
        repo_map: RepositoryMap,
        budget: ContextBudget | None = None,
        strategy: str = "combined",
        workspace_path: Path | None = None,
    ) -> RetrievalResult:
        """
        Retrieve code context for an issue or query string within a bounded budget.

        Args:
            query_or_issue: Issue domain model or raw query string.
            repo_map: Deterministic RepositoryMap.
            budget: Resource limits on retrieved items.
            strategy: 'lexical', 'structural', or 'combined'.
            workspace_path: Optional path to workspace to populate source content excerpts.

        Returns:
            Deterministic, immutable RetrievalResult with explainability breakdown.
        """
        applied_budget = budget or ContextBudget()

        # Extract text query
        if isinstance(query_or_issue, Issue):
            query = f"{query_or_issue.title} {query_or_issue.body}".strip()
        else:
            query = str(query_or_issue).strip()

        # 1. Execute retrieval strategy
        candidate_items: list[RetrievalItem] = []
        normalized_strategy = strategy.lower().replace("_", "+")

        # Always run lexical seed matching unless explicitly purely structural without seeds
        lexical_items = self._lexical.retrieve(query, repo_map)
        candidate_items.extend(lexical_items)

        if normalized_strategy != "lexical":
            include_imports = normalized_strategy in ("combined", "all", "structural", "lexical+imports")
            include_tests = normalized_strategy in ("combined", "all", "structural", "lexical+tests")
            include_config = normalized_strategy in ("combined", "all", "structural", "lexical+config")

            structural_items = self._structural.expand(
                seed_items=lexical_items,
                repo_map=repo_map,
                query=query,
                include_imports=include_imports,
                include_tests=include_tests,
                include_config=include_config,
            )
            candidate_items.extend(structural_items)

        # 2. Merge and aggregate items by (file_path, symbol_name)
        merged_items: dict[tuple[str, str | None], RetrievalItem] = {}

        for item in candidate_items:
            key = (item.file_path, item.symbol_name)
            if key not in merged_items:
                merged_items[key] = item
            else:
                existing = merged_items[key]
                new_score = round(existing.score + item.score, 4)
                new_reasons = existing.reasons + item.reasons
                merged_items[key] = RetrievalItem(
                    file_path=existing.file_path,
                    symbol_name=existing.symbol_name,
                    symbol_type=existing.symbol_type,
                    start_line=existing.start_line or item.start_line,
                    end_line=existing.end_line or item.end_line,
                    score=new_score,
                    reasons=new_reasons,
                    content=existing.content or item.content,
                )

        total_candidates = len(merged_items)

        # 3. Deterministic sorting: highest score first, then file path, line, symbol
        sorted_candidates = sorted(
            merged_items.values(),
            key=lambda x: (
                -x.score,
                x.file_path,
                x.start_line if x.start_line is not None else 0,
                x.symbol_name if x.symbol_name is not None else "",
            ),
        )

        # 4. Apply ContextBudget
        budgeted_items: list[RetrievalItem] = []
        selected_files: set[str] = set()
        selected_symbols_count = 0
        total_chars = 0

        for it in sorted_candidates:
            # File limit check
            is_new_file = it.file_path not in selected_files
            if is_new_file and len(selected_files) >= applied_budget.max_files:
                continue

            # Symbol limit check
            if it.symbol_name is not None:
                if selected_symbols_count >= applied_budget.max_symbols:
                    continue
                selected_symbols_count += 1

            # Populate content if workspace_path provided
            content = None
            char_count = 0
            if workspace_path and workspace_path.exists():
                file_full = workspace_path / it.file_path
                if file_full.exists():
                    try:
                        lines = file_full.read_text(encoding="utf-8", errors="replace").splitlines()
                        if it.start_line is not None:
                            end = it.end_line or it.start_line
                            excerpt_lines = lines[it.start_line - 1:end]
                            content = "\n".join(excerpt_lines)
                        else:
                            content = "\n".join(lines[:100])  # preview top 100 lines for file
                        char_count = len(content)
                    except Exception:
                        pass

            if total_chars + char_count > applied_budget.max_characters and budgeted_items:
                # Exceeds character budget
                continue

            selected_files.add(it.file_path)
            total_chars += char_count

            budgeted_items.append(
                RetrievalItem(
                    file_path=it.file_path,
                    symbol_name=it.symbol_name,
                    symbol_type=it.symbol_type,
                    start_line=it.start_line,
                    end_line=it.end_line,
                    score=it.score,
                    reasons=it.reasons,
                    content=content,
                )
            )

        excluded_count = total_candidates - len(budgeted_items)

        return RetrievalResult(
            query=query,
            items=tuple(budgeted_items),
            total_candidates_evaluated=total_candidates,
            excluded_by_budget_count=excluded_count,
            strategy_used=strategy,
            budget_applied=applied_budget,
            retrieved_at=_utcnow(),
        )
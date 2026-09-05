"""
execution/file_editor.py -- Atomic file modification, snapshotting, and rollback engine.

Provides safe file operations confined strictly within the repository workspace:
1. In-memory pre-change snapshotting of all touched files.
2. Atomic writes using temporary files and os.replace().
3. Deterministic 3-Tier anchor resolution (Exact, Whitespace-Normalized, AST Symbol-Scoped).
4. Clean rollback reversing changes if verification fails.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import os
import uuid
from pathlib import Path
from typing import Any

from autonomous_engineer.domain.models import ImplementationStep, StepOperation
from autonomous_engineer.execution.models import EditMatchTelemetry, FileChangeRecord


def _compute_sha256(content: str) -> str:
    """Compute SHA256 hex digest of string content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _find_symbol_line_range(source_code: str, qualified_symbol: str) -> list[tuple[int, int]]:
    """
    Locate 1-based (start_line, end_line) spans for a qualified symbol name in Python source.
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []

    parts = [p.strip() for p in qualified_symbol.split(".") if p.strip()]
    if not parts:
        return []

    spans: list[tuple[int, int]] = []

    def _search_nodes(nodes: list[ast.AST], target_parts: list[str]) -> None:
        if not target_parts:
            return
        head = target_parts[0]
        tail = target_parts[1:]

        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == head:
                    if not tail:
                        start = getattr(node, "lineno", 1)
                        end = getattr(node, "end_lineno", start)
                        spans.append((start, end))
                    elif isinstance(node, ast.ClassDef):
                        _search_nodes(node.body, tail)

    _search_nodes(tree.body, parts)

    # Fallback: if not found with top-level qualified path and parts has 1 element, search anywhere in AST
    if not spans and len(parts) == 1:
        target_name = parts[0]
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == target_name:
                    start = getattr(node, "lineno", 1)
                    end = getattr(node, "end_lineno", start)
                    spans.append((start, end))

    return spans


def _find_normalized_line_matches(
    file_lines: list[str],
    search_lines: list[str],
    line_offset: int = 0,
) -> list[tuple[int, int]]:
    """
    Find candidate line index windows [start_idx, end_idx] where non-empty stripped lines match.
    """
    search_stripped = [l.strip() for l in search_lines if l.strip()]
    if not search_stripped:
        return []

    non_blank_file_indices = [i for i, l in enumerate(file_lines) if l.strip()]
    non_blank_file_stripped = [file_lines[i].strip() for i in non_blank_file_indices]

    n_search = len(search_stripped)
    matches: list[tuple[int, int]] = []

    for j in range(len(non_blank_file_stripped) - n_search + 1):
        if non_blank_file_stripped[j : j + n_search] == search_stripped:
            start_file_idx = non_blank_file_indices[j]
            end_file_idx = non_blank_file_indices[j + n_search - 1]
            matches.append((line_offset + start_file_idx, line_offset + end_file_idx))

    return matches


def _find_fuzzy_line_matches(
    file_lines: list[str],
    search_lines: list[str],
    min_similarity: float = 0.85,
    line_offset: int = 0,
) -> list[tuple[int, int]]:
    """
    Tier 4: Sliding-window fuzzy line-sequence matcher using character/token sequence similarity.
    Tolerates minor prompt drift (trailing comments, whitespace shifts, slight token edits)
    while preserving fail-closed safety by requiring a high similarity threshold (>= 0.85)
    and strictly rejecting ambiguous matches.
    """
    search_stripped = [l.strip() for l in search_lines if l.strip()]
    if not search_stripped:
        return []

    non_blank_file_indices = [i for i, l in enumerate(file_lines) if l.strip()]
    non_blank_file_stripped = [file_lines[i].strip() for i in non_blank_file_indices]

    n_search = len(search_stripped)
    if len(non_blank_file_stripped) < n_search:
        return []

    search_joined = "\n".join(search_stripped)
    candidates: list[tuple[float, int, int]] = []

    for j in range(len(non_blank_file_stripped) - n_search + 1):
        window_lines = non_blank_file_stripped[j : j + n_search]
        window_joined = "\n".join(window_lines)
        ratio = difflib.SequenceMatcher(None, search_joined, window_joined).ratio()
        if ratio >= min_similarity:
            start_file_idx = non_blank_file_indices[j]
            end_file_idx = non_blank_file_indices[j + n_search - 1]
            candidates.append((ratio, line_offset + start_file_idx, line_offset + end_file_idx))

    if not candidates:
        return []

    # Sort descending by similarity score
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score = candidates[0][0]

    # Keep all candidates within 0.03 of best score to detect ambiguous close matches
    top_matches = [c for c in candidates if c[0] >= (best_score - 0.03)]
    return [(c[1], c[2]) for c in top_matches]


def _apply_reindented_replacement(
    file_lines: list[str],
    start_idx: int,
    end_idx: int,
    search_content: str,
    replace_content: str,
) -> str:
    """
    Apply replacement text over file_lines[start_idx : end_idx + 1], preserving authentic indentation.
    """
    matched_first_line = file_lines[start_idx]
    file_indent_len = len(matched_first_line) - len(matched_first_line.lstrip())

    search_non_empty = [l for l in search_content.splitlines() if l.strip()]
    search_indent_len = 0
    if search_non_empty:
        search_indent_len = len(search_non_empty[0]) - len(search_non_empty[0].lstrip())

    newline_char = "\r\n" if "\r\n" in matched_first_line else "\n"
    rep_lines = replace_content.splitlines()

    new_rep_lines: list[str] = []
    for line in rep_lines:
        if not line.strip():
            new_rep_lines.append(newline_char)
        else:
            curr_indent_len = len(line) - len(line.lstrip())
            rel_diff = curr_indent_len - search_indent_len
            final_indent_len = max(0, file_indent_len + rel_diff)
            new_rep_lines.append((" " * final_indent_len) + line.lstrip() + newline_char)

    prefix = "".join(file_lines[:start_idx])
    replacement = "".join(new_rep_lines)
    suffix = "".join(file_lines[end_idx + 1 :])

    return prefix + replacement + suffix


def _resolve_edit(
    current_text: str,
    search_content: str,
    replace_content: str,
    target_symbol: str | None,
    step_id: str,
    rel_path: str,
) -> tuple[str, EditMatchTelemetry]:
    """
    Resolve edit using deterministic 3-tier matching:
    Tier 1: Exact literal match
    Tier 2: Whitespace/indentation normalized line match
    Tier 3: AST symbol-scoped normalized line match
    """
    file_lines = current_text.splitlines(keepends=True)
    search_lines = search_content.splitlines()

    # --- TIER 1: Exact Literal Match ---
    if search_content in current_text:
        count = current_text.count(search_content)
        if count == 1:
            start_char = current_text.find(search_content)
            start_line = current_text[:start_char].count("\n") + 1
            end_line = start_line + search_content.count("\n")
            new_text = current_text.replace(search_content, replace_content, 1)
            telemetry = EditMatchTelemetry(
                tier_used=1,
                normalization_applied=False,
                symbol_scoped=False,
                target_symbol=target_symbol,
                original_anchor_length=len(search_content),
                matched_span_lines=(start_line, end_line),
                candidate_matches_count=1,
                ambiguity_rejected=False,
                outcome="applied",
            )
            return new_text, telemetry
        else:
            # Multiple exact occurrences -> check if target_symbol disambiguates
            if target_symbol:
                symbol_spans = _find_symbol_line_range(current_text, target_symbol)
                if len(symbol_spans) == 1:
                    sym_start_line, sym_end_line = symbol_spans[0]
                    sym_lines = file_lines[sym_start_line - 1 : sym_end_line]
                    sym_text = "".join(sym_lines)
                    sym_count = sym_text.count(search_content)
                    if sym_count == 1:
                        sym_char_idx = sym_text.find(search_content)
                        start_line = sym_start_line + sym_text[:sym_char_idx].count("\n")
                        end_line = start_line + search_content.count("\n")
                        new_sym_text = sym_text.replace(search_content, replace_content, 1)
                        new_text = (
                            "".join(file_lines[: sym_start_line - 1])
                            + new_sym_text
                            + "".join(file_lines[sym_end_line:])
                        )
                        telemetry = EditMatchTelemetry(
                            tier_used=3,
                            normalization_applied=False,
                            symbol_scoped=True,
                            target_symbol=target_symbol,
                            original_anchor_length=len(search_content),
                            matched_span_lines=(start_line, end_line),
                            candidate_matches_count=1,
                            ambiguity_rejected=False,
                            outcome="applied",
                        )
                        return new_text, telemetry
                    elif sym_count > 1:
                        raise ValueError(
                            f"Step {step_id!r}: Ambiguous match: found {sym_count} matching blocks within symbol {target_symbol!r} in {rel_path!r}."
                        )
                elif len(symbol_spans) > 1:
                    raise ValueError(
                        f"Step {step_id!r}: Ambiguous symbol: found {len(symbol_spans)} definitions for symbol {target_symbol!r} in {rel_path!r}."
                    )
            # If no target_symbol or symbol couldn't resolve, raise file-level ambiguity
            raise ValueError(
                f"Step {step_id!r}: Ambiguous match: found {count} matching blocks for search_content in {rel_path!r}."
            )

    # --- TIER 2: Normalized Line Match ---
    matches = _find_normalized_line_matches(file_lines, search_lines)

    if len(matches) == 1:
        start_idx, end_idx = matches[0]
        new_text = _apply_reindented_replacement(file_lines, start_idx, end_idx, search_content, replace_content)
        telemetry = EditMatchTelemetry(
            tier_used=2,
            normalization_applied=True,
            symbol_scoped=False,
            target_symbol=target_symbol,
            original_anchor_length=len(search_content),
            matched_span_lines=(start_idx + 1, end_idx + 1),
            candidate_matches_count=1,
            ambiguity_rejected=False,
            outcome="applied",
        )
        return new_text, telemetry

    # --- TIER 3: AST Symbol-Scoped Match ---
    if target_symbol:
        symbol_spans = _find_symbol_line_range(current_text, target_symbol)
        if len(symbol_spans) == 1:
            sym_start_line, sym_end_line = symbol_spans[0]
            sym_lines = file_lines[sym_start_line - 1 : sym_end_line]
            sym_matches = _find_normalized_line_matches(sym_lines, search_lines, line_offset=sym_start_line - 1)
            if len(sym_matches) > 1:
                raise ValueError(
                    f"Step {step_id!r}: Ambiguous match: found {len(sym_matches)} matching blocks within symbol {target_symbol!r} in {rel_path!r}."
                )
            elif len(sym_matches) == 1:
                start_idx, end_idx = sym_matches[0]
                new_text = _apply_reindented_replacement(file_lines, start_idx, end_idx, search_content, replace_content)
                telemetry = EditMatchTelemetry(
                    tier_used=3,
                    normalization_applied=True,
                    symbol_scoped=True,
                    target_symbol=target_symbol,
                    original_anchor_length=len(search_content),
                    matched_span_lines=(start_idx + 1, end_idx + 1),
                    candidate_matches_count=1,
                    ambiguity_rejected=False,
                    outcome="applied",
                )
                return new_text, telemetry
        elif len(symbol_spans) > 1:
            raise ValueError(
                f"Step {step_id!r}: Ambiguous symbol: found {len(symbol_spans)} definitions for symbol {target_symbol!r} in {rel_path!r}."
            )

    if len(matches) > 1:
        # Ambiguous across file and symbol scope did not resolve it
        raise ValueError(
            f"Step {step_id!r}: Ambiguous match: found {len(matches)} matching blocks for search_content in {rel_path!r}."
        )

    # --- TIER 4: High-Confidence Fuzzy Anchor Match ---
    fuzzy_matches = _find_fuzzy_line_matches(file_lines, search_lines, min_similarity=0.85)
    if len(fuzzy_matches) == 1:
        start_idx, end_idx = fuzzy_matches[0]
        new_text = _apply_reindented_replacement(file_lines, start_idx, end_idx, search_content, replace_content)
        telemetry = EditMatchTelemetry(
            tier_used=4,
            normalization_applied=True,
            symbol_scoped=False,
            target_symbol=target_symbol,
            original_anchor_length=len(search_content),
            matched_span_lines=(start_idx + 1, end_idx + 1),
            candidate_matches_count=1,
            ambiguity_rejected=False,
            outcome="applied",
        )
        return new_text, telemetry
    elif len(fuzzy_matches) > 1:
        raise ValueError(
            f"Step {step_id!r}: Ambiguous match: found {len(fuzzy_matches)} candidate fuzzy matches (>=0.85 similarity) for search_content in {rel_path!r}."
        )

    # Fail closed
    raise ValueError(f"Step {step_id!r}: search_content was not found in {rel_path!r}.")


class SafeFileEditor:
    """Performs atomic, auditable file edits with full rollback capability and 3-tier anchor matching."""

    def __init__(self) -> None:
        # Maps relative file path -> original content (None if file was newly created)
        self._snapshots: dict[str, str | None] = {}
        self._applied_changes: list[FileChangeRecord] = []
        self._edit_telemetries: list[EditMatchTelemetry] = []

    @property
    def applied_changes(self) -> tuple[FileChangeRecord, ...]:
        """List of all FileChangeRecord objects applied so far."""
        return tuple(self._applied_changes)

    @property
    def edit_telemetries(self) -> tuple[EditMatchTelemetry, ...]:
        """List of all EditMatchTelemetry records collected during execution."""
        return tuple(self._edit_telemetries)

    def apply_step(self, workspace: Path, step: ImplementationStep) -> FileChangeRecord:
        """
        Apply an atomic file modification for a single ImplementationStep.

        Args:
            workspace: Confined workspace root path.
            step: The ImplementationStep to apply.

        Returns:
            FileChangeRecord documenting original and resulting file states.

        Raises:
            ValueError: If target path escapes workspace boundary or search_content is not found.
            RuntimeError: If file write or IO operation fails.
        """
        workspace_resolved = workspace.resolve()
        target_path = (workspace_resolved / step.target_file).resolve()

        if not target_path.is_relative_to(workspace_resolved):
            raise ValueError(f"Security violation: path {step.target_file!r} escapes workspace boundary.")

        # Capture pre-change snapshot if this file has not been touched yet in this execution
        rel_path = step.target_file
        if rel_path not in self._snapshots:
            if target_path.exists():
                self._snapshots[rel_path] = target_path.read_text(encoding="utf-8", errors="replace")
            else:
                self._snapshots[rel_path] = None

        orig_content = self._snapshots[rel_path]
        orig_hash = _compute_sha256(orig_content) if orig_content is not None else None

        new_content: str | None = None
        match_telemetry: EditMatchTelemetry | None = None

        if step.operation in (StepOperation.ADD_FILE, StepOperation.ADD_TEST):
            new_content = step.content if step.content is not None else ""
            self._atomic_write(target_path, new_content)

        elif step.operation == StepOperation.DELETE_FILE:
            if target_path.exists():
                target_path.unlink()
            new_content = None

        else:
            # Modification operations (MODIFY_SYMBOL, REFACTOR_FILE, UPDATE_CONFIGURATION, etc.)
            if not target_path.exists():
                raise RuntimeError(f"Target file {rel_path!r} does not exist for modification.")

            current_text = target_path.read_text(encoding="utf-8", errors="replace")

            if step.search_content is not None:
                replacement = step.replace_content if step.replace_content is not None else ""
                new_content, match_telemetry = _resolve_edit(
                    current_text=current_text,
                    search_content=step.search_content,
                    replace_content=replacement,
                    target_symbol=step.target_symbol,
                    step_id=step.step_id,
                    rel_path=rel_path,
                )
                self._edit_telemetries.append(match_telemetry)
            elif step.content is not None:
                new_content = step.content
            else:
                # No payload provided; retain existing content
                new_content = current_text

            self._atomic_write(target_path, new_content)

        new_hash = _compute_sha256(new_content) if new_content is not None else None

        record = FileChangeRecord(
            file_path=rel_path,
            operation=step.operation,
            original_content=orig_content,
            new_content=new_content,
            original_hash=orig_hash,
            new_hash=new_hash,
            match_telemetry=match_telemetry,
        )
        self._applied_changes.append(record)
        return record

    def rollback(self, workspace: Path) -> tuple[bool, str | None]:
        """
        Revert all applied file changes to their original pre-execution snapshot state.

        Returns:
            (True, None) on success, or (False, error_message) if rollback encounters an IO error.
        """
        workspace_resolved = workspace.resolve()
        errors: list[str] = []

        # Restore files in reverse order
        for rel_path, orig_content in reversed(list(self._snapshots.items())):
            target_path = (workspace_resolved / rel_path).resolve()
            try:
                if orig_content is None:
                    # File was newly created -> delete it
                    if target_path.exists():
                        target_path.unlink()
                else:
                    # File existed originally -> restore original content
                    self._atomic_write(target_path, orig_content)
            except Exception as e:
                errors.append(f"Failed to rollback {rel_path!r}: {e}")

        if errors:
            return False, "; ".join(errors)
        return True, None

    def _atomic_write(self, target_path: Path, content: str) -> None:
        """Write content to temporary file in same directory and atomically replace target."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_name = f".tmp_{uuid.uuid4().hex}"
        tmp_path = target_path.parent / tmp_name

        try:
            tmp_path.write_text(content, encoding="utf-8")
            os.replace(tmp_path, target_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise
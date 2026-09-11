"""
repository/go_rust_analyzer.py -- Structural Code Analyzers for Go and Rust.

Provides:
- Go Module & Function/Struct/Interface symbol indexing (go.mod, .go files)
- Rust Crate & Function/Struct/Impl/Trait symbol indexing (Cargo.toml, .rs files)
- Test file detection for Go (*_test.go) and Rust (tests/*.rs, #[test])
- Symbol existence validation for post-patch static verification in polyglot codebases.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class PolyglotSymbol(BaseModel):
    """Represents a function, struct, or type in Go or Rust."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: str  # "function", "struct", "interface", "trait", "impl"
    is_exported: bool = False
    line_number: int = 1


class PolyglotModuleMap(BaseModel):
    """Structural index of a single Go or Rust file."""

    model_config = ConfigDict(frozen=True)

    file_path: str
    language: str  # "go" or "rust"
    is_test_file: bool = False
    symbols: tuple[PolyglotSymbol, ...] = Field(default=())
    imports: tuple[str, ...] = Field(default=())


# Regex patterns for Go
_GO_FUNC = re.compile(r"(?m)^func\s+(?:\([^)]+\)\s+)?(?P<name>[a-zA-Z0-9_]+)(?:\[[^\]]+\])?\s*\(")
_GO_TYPE = re.compile(r"(?m)^type\s+(?P<name>[a-zA-Z0-9_]+)(?:\[[^\]]+\])?\s+(?P<kind>struct|interface)")
_GO_IMPORT = re.compile(r'(?m)^\s*(?:import\s+)?"(?P<pkg>[^"]+)"')

# Regex patterns for Rust
_RUST_FN = re.compile(r"(?m)^\s*(?:pub(?:\([^)]+\))?\s+)?(?:async\s+)?fn\s+(?P<name>[a-zA-Z0-9_]+)")
_RUST_STRUCT_TRAIT = re.compile(r"(?m)^\s*(?:pub(?:\([^)]+\))?\s+)?(?P<kind>struct|enum|trait)\s+(?P<name>[a-zA-Z0-9_]+)")
_RUST_USE = re.compile(r"(?m)^\s*use\s+(?P<path>[^;]+);")


class PolyglotCodeAnalyzer:
    """Analyzes Go (.go) and Rust (.rs) files for symbols and dependencies."""

    def is_test_file(self, file_path: str) -> bool:
        norm = file_path.replace("\\", "/").lower()
        if norm.endswith("_test.go"):
            return True
        if norm.endswith(".rs") and ("/tests/" in norm or norm.startswith("tests/") or norm.endswith("_test.rs")):
            return True
        return False

    def analyze_source(self, code: str, file_path: str) -> PolyglotModuleMap:
        norm = file_path.replace("\\", "/").lower()
        is_go = norm.endswith(".go")
        is_rust = norm.endswith(".rs")
        lang = "go" if is_go else ("rust" if is_rust else "unknown")
        is_test = self.is_test_file(file_path)

        symbols: list[PolyglotSymbol] = []
        imports: list[str] = []

        if is_go:
            # Go imports
            for m in _GO_IMPORT.finditer(code):
                imports.append(m.group("pkg"))

            # Go functions
            for m in _GO_FUNC.finditer(code):
                name = m.group("name")
                lineno = code.count("\n", 0, m.start()) + 1
                is_exp = name[0].isupper() if name else False
                symbols.append(PolyglotSymbol(name=name, kind="function", is_exported=is_exp, line_number=lineno))

            # Go types
            for m in _GO_TYPE.finditer(code):
                name = m.group("name")
                kind = m.group("kind")
                lineno = code.count("\n", 0, m.start()) + 1
                is_exp = name[0].isupper() if name else False
                symbols.append(PolyglotSymbol(name=name, kind=kind, is_exported=is_exp, line_number=lineno))

        elif is_rust:
            # Rust imports
            for m in _RUST_USE.finditer(code):
                imports.append(m.group("path").strip())

            # Rust functions
            for m in _RUST_FN.finditer(code):
                name = m.group("name")
                lineno = code.count("\n", 0, m.start()) + 1
                is_exp = "pub" in code[max(0, m.start() - 10) : m.start() + 4]
                symbols.append(PolyglotSymbol(name=name, kind="function", is_exported=is_exp, line_number=lineno))

            # Rust structs, enums, traits
            for m in _RUST_STRUCT_TRAIT.finditer(code):
                name = m.group("name")
                kind = m.group("kind")
                lineno = code.count("\n", 0, m.start()) + 1
                is_exp = "pub" in code[max(0, m.start() - 10) : m.start() + 4]
                symbols.append(PolyglotSymbol(name=name, kind=kind, is_exported=is_exp, line_number=lineno))

        return PolyglotModuleMap(
            file_path=file_path,
            language=lang,
            is_test_file=is_test,
            symbols=tuple(symbols),
            imports=tuple(sorted(set(imports))),
        )

    def check_symbol_present(self, mod: PolyglotModuleMap, symbol_name: str) -> bool:
        target_base = symbol_name.split(".")[-1]
        for s in mod.symbols:
            if s.name == symbol_name or s.name == target_base:
                return True
        return False
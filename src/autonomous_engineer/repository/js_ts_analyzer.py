"""
repository/js_ts_analyzer.py -- JavaScript & TypeScript Structural AST Analyzer for QuetZ.

Parses .js, .jsx, .ts, .tsx modules to extract structural symbols:
- Functions (regular, async, generator, arrow functions)
- Classes & Methods
- ES Module Imports and Exports
- Test suite detection (Jest, Vitest, Mocha)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JsTsFunctionSymbol(BaseModel):
    """Represents a function or method in JavaScript/TypeScript."""

    model_config = ConfigDict(frozen=True)

    name: str
    is_async: bool = False
    is_export: bool = False
    parameters: tuple[str, ...] = Field(default=())
    line_number: int = 1


class JsTsClassSymbol(BaseModel):
    """Represents a class declaration in JavaScript/TypeScript."""

    model_config = ConfigDict(frozen=True)

    name: str
    is_export: bool = False
    methods: tuple[str, ...] = Field(default=())
    line_number: int = 1


class JsTsModuleMap(BaseModel):
    """Structural index of a single JavaScript or TypeScript file."""

    model_config = ConfigDict(frozen=True)

    file_path: str
    is_typescript: bool = False
    is_test_file: bool = False
    functions: tuple[JsTsFunctionSymbol, ...] = Field(default=())
    classes: tuple[JsTsClassSymbol, ...] = Field(default=())
    imports: tuple[str, ...] = Field(default=())
    exports: tuple[str, ...] = Field(default=())


# Regex patterns for JavaScript/TypeScript syntax
_FUNC_PATTERN = re.compile(
    r"""(?m)^(?:(?P<export>export\s+(?:default\s+)?)?(?P<async>async\s+)?function\s*(?P<name>[a-zA-Z0-9_$]+)\s*\((?P<params>[^)]*)\))"""
)

_ARROW_PATTERN = re.compile(
    r"""(?m)^(?:(?P<export>export\s+)?(?:const|let|var)\s+(?P<name>[a-zA-Z0-9_$]+)\s*=\s*(?P<async>async\s+)?(?:\((?P<params>[^)]*)\)|[a-zA-Z0-9_$]+)\s*=>)"""
)

_CLASS_PATTERN = re.compile(
    r"""(?m)^(?:(?P<export>export\s+(?:default\s+)?)?class\s+(?P<name>[a-zA-Z0-9_$]+)(?:\s+extends\s+[a-zA-Z0-9_$.]+)?(?:\s+implements\s+[a-zA-Z0-9_$,\s]+)?\s*\{(?P<body>[\s\S]*?)^\})"""
)

_METHOD_PATTERN = re.compile(
    r"""(?m)^\s*(?:(?:public|private|protected|static|async|readonly)\s+)*(?P<name>[a-zA-Z0-9_$]+)\s*\((?P<params>[^)]*)\)"""
)

_CLASS_ARROW_METHOD = re.compile(
    r"""(?m)^\s*(?:(?:public|private|protected|static|readonly)\s+)*(?P<name>[a-zA-Z0-9_$]+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[a-zA-Z0-9_$]+)\s*=>"""
)

_INTERFACE_TYPE_PATTERN = re.compile(
    r"""(?m)^(?:(?P<export>export\s+)?(?:interface|type)\s+(?P<name>[a-zA-Z0-9_$]+))"""
)

_IMPORT_PATTERN = re.compile(
    r"""(?m)^import\s+(?:(?:{[^}]+}|\*\s+as\s+[a-zA-Z0-9_$]+|[a-zA-Z0-9_$]+)\s+from\s+)?['"]([^'"]+)['"]"""
)


class JsTsAnalyzer:
    """Analyzes JavaScript and TypeScript files into structural symbol indexes."""

    def is_test_file(self, file_path: str) -> bool:
        norm = file_path.replace("\\", "/").lower()
        filename = norm.split("/")[-1]
        return bool(
            re.search(r"\.(?:test|spec)\.[jt]sx?$", filename)
            or "/__tests__/" in norm
            or norm.startswith("test/")
            or norm.startswith("tests/")
        )

    def analyze_source(self, code: str, file_path: str) -> JsTsModuleMap:
        is_ts = file_path.endswith((".ts", ".tsx"))
        is_test = self.is_test_file(file_path)

        functions: list[JsTsFunctionSymbol] = []
        classes: list[JsTsClassSymbol] = []
        imports: list[str] = []
        exports: list[str] = []

        # 1. Imports
        for match in _IMPORT_PATTERN.finditer(code):
            imports.append(match.group(1))

        # 2. Named functions
        for match in _FUNC_PATTERN.finditer(code):
            name = match.group("name")
            is_async = bool(match.group("async"))
            is_exp = bool(match.group("export"))
            raw_params = match.group("params") or ""
            params = tuple(p.strip().split(":")[0].strip() for p in raw_params.split(",") if p.strip())

            # Compute 1-based line number
            start_pos = match.start()
            lineno = code.count("\n", 0, start_pos) + 1

            functions.append(
                JsTsFunctionSymbol(
                    name=name,
                    is_async=is_async,
                    is_export=is_exp,
                    parameters=params,
                    line_number=lineno,
                )
            )
            if is_exp:
                exports.append(name)

        # 3. Arrow functions
        for match in _ARROW_PATTERN.finditer(code):
            name = match.group("name")
            is_async = bool(match.group("async"))
            is_exp = bool(match.group("export"))
            raw_params = match.group("params") or ""
            params = tuple(p.strip().split(":")[0].strip() for p in raw_params.split(",") if p.strip())

            start_pos = match.start()
            lineno = code.count("\n", 0, start_pos) + 1

            functions.append(
                JsTsFunctionSymbol(
                    name=name,
                    is_async=is_async,
                    is_export=is_exp,
                    parameters=params,
                    line_number=lineno,
                )
            )
            if is_exp:
                exports.append(name)

        # 4. Classes and their methods
        for match in _CLASS_PATTERN.finditer(code):
            name = match.group("name")
            is_exp = bool(match.group("export"))
            body = match.group("body") or ""
            start_pos = match.start()
            lineno = code.count("\n", 0, start_pos) + 1

            # Extract class methods from body
            methods: list[str] = []
            for m in _METHOD_PATTERN.finditer(body):
                m_name = m.group("name")
                if m_name not in ("constructor", "if", "for", "while", "switch", "catch"):
                    methods.append(m_name)

            for m in _CLASS_ARROW_METHOD.finditer(body):
                m_name = m.group("name")
                if m_name not in methods:
                    methods.append(m_name)

            classes.append(
                JsTsClassSymbol(
                    name=name,
                    is_export=is_exp,
                    methods=tuple(methods),
                    line_number=lineno,
                )
            )
            if is_exp:
                exports.append(name)

        # 5. Interfaces & Type aliases (TypeScript)
        for match in _INTERFACE_TYPE_PATTERN.finditer(code):
            name = match.group("name")
            is_exp = bool(match.group("export"))
            if is_exp:
                exports.append(name)

        return JsTsModuleMap(
            file_path=file_path,
            is_typescript=is_ts,
            is_test_file=is_test,
            functions=tuple(functions),
            classes=tuple(classes),
            imports=tuple(sorted(set(imports))),
            exports=tuple(sorted(set(exports))),
        )

    def check_symbol_present(self, module_map: JsTsModuleMap, symbol_name: str) -> bool:
        """Check if a given function, class, or method symbol exists in the module."""
        target_base = symbol_name.split(".")[-1]

        # Check functions
        for f in module_map.functions:
            if f.name == symbol_name or f.name == target_base:
                return True

        # Check classes and methods
        for c in module_map.classes:
            if c.name == symbol_name or c.name == target_base:
                return True
            for m in c.methods:
                if m == symbol_name or m == target_base or f"{c.name}.{m}" == symbol_name:
                    return True

        # Check exports
        if symbol_name in module_map.exports or target_base in module_map.exports:
            return True

        return False

    def analyze_file(self, path: Path, relative_to: Path | None = None) -> JsTsModuleMap:
        rel_str = str(path.relative_to(relative_to)) if relative_to else str(path)
        content = path.read_text(encoding="utf-8", errors="replace")
        return self.analyze_source(content, rel_str)
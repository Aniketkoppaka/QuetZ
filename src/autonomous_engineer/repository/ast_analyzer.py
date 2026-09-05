"""
repository/ast_analyzer.py -- Pure syntactic Python AST parser and symbol extractor.

Extracts structural symbols (classes, functions, methods, imports) using Python stdlib ast.
Repository code is NEVER executed or imported.
"""
from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

from autonomous_engineer.domain.models import (
    ClassSymbol,
    FunctionSymbol,
    ImportStatement,
    ParseFailure,
    PythonModuleMap,
)


def _format_node_expr(node: ast.AST) -> str:
    """Format an AST expression (e.g. base class) into a syntactic string."""
    try:
        return ast.unparse(node)
    except Exception:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{_format_node_expr(node.value)}.{node.attr}"
        return type(node).__name__


def _format_decorator(node: ast.AST) -> str:
    """Format a decorator AST expression with leading @."""
    expr = _format_node_expr(node)
    return expr if expr.startswith("@") else f"@{expr}"


def _extract_parameters(args_node: ast.arguments) -> tuple[str, ...]:
    """Extract list of parameter names from an ast.arguments node."""
    params: list[str] = []

    # Positional-only args (Python 3.8+)
    for arg in getattr(args_node, "posonlyargs", []):
        params.append(arg.arg)

    # Standard positional args
    for arg in args_node.args:
        params.append(arg.arg)

    # *vararg
    if args_node.vararg:
        params.append(f"*{args_node.vararg.arg}")

    # Keyword-only args
    for arg in args_node.kwonlyargs:
        params.append(arg.arg)

    # **kwarg
    if args_node.kwarg:
        params.append(f"**{args_node.kwarg.arg}")

    return tuple(params)


def _derive_module_name(relative_path: str) -> str:
    """Derive dotted Python module name from repository-relative path."""
    clean = relative_path.replace("\\", "/")
    if clean.endswith(".py"):
        clean = clean[:-3]
    elif clean.endswith(".pyi"):
        clean = clean[:-4]

    parts = clean.split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]

    return ".".join(parts) if parts else "__main__"


class PythonAstAnalyzer:
    """Extracts structural symbols and imports from Python source files without execution."""

    def analyze_file(
        self,
        workspace_path: Path,
        relative_path: str,
        is_test_file: bool = False,
        max_file_size_bytes: int | None = None,
    ) -> PythonModuleMap | ParseFailure:
        """
        Read and syntactically parse a Python source file.

        Args:
            workspace_path: Root path of the repository workspace.
            relative_path: Repo-relative path to the Python file.
            is_test_file: Whether the file was flagged as a test.
            max_file_size_bytes: Optional limit on single file size.

        Returns:
            PythonModuleMap on success, or ParseFailure if decoding/syntax fails.
        """
        full_path = workspace_path / relative_path

        # 1. Size check
        if max_file_size_bytes is not None:
            try:
                size = full_path.stat().st_size
                if size > max_file_size_bytes:
                    return ParseFailure(
                        file_path=relative_path,
                        error_type="FileSizeLimitExceeded",
                        message=f"File size ({size} bytes) exceeds maximum limit ({max_file_size_bytes} bytes)",
                    )
            except OSError as exc:
                return ParseFailure(
                    file_path=relative_path,
                    error_type="FileAccessError",
                    message=str(exc),
                )

        # 2. Read bytes and detect encoding
        try:
            raw_bytes = full_path.read_bytes()
        except Exception as exc:
            return ParseFailure(
                file_path=relative_path,
                error_type="FileReadError",
                message=str(exc),
            )

        try:
            encoding, _ = tokenize.detect_encoding(io.BytesIO(raw_bytes).readline)
            source_text = raw_bytes.decode(encoding)
        except Exception as exc:
            return ParseFailure(
                file_path=relative_path,
                error_type="UnicodeDecodeError",
                message=f"Failed to decode source with detected encoding: {exc}",
            )

        # 3. Parse AST
        try:
            tree = ast.parse(source_text, filename=relative_path)
        except SyntaxError as exc:
            return ParseFailure(
                file_path=relative_path,
                error_type="SyntaxError",
                message=exc.msg or str(exc),
                line_number=exc.lineno,
                offset=exc.offset,
            )
        except Exception as exc:
            return ParseFailure(
                file_path=relative_path,
                error_type=type(exc).__name__,
                message=str(exc),
            )

        # 4. Extract symbols and imports
        imports: list[ImportStatement] = []
        classes: list[ClassSymbol] = []
        functions: list[FunctionSymbol] = []

        line_count = len(source_text.splitlines())
        module_docstring = ast.get_docstring(tree)
        module_name = _derive_module_name(relative_path)

        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    imports.append(
                        ImportStatement(
                            module=alias.name,
                            names=(alias.name,),
                            alias=alias.asname,
                            is_from=False,
                            level=0,
                            line_number=stmt.lineno,
                        )
                    )
            elif isinstance(stmt, ast.ImportFrom):
                imports.append(
                    ImportStatement(
                        module=stmt.module,
                        names=tuple(a.name for a in stmt.names),
                        alias=stmt.names[0].asname if len(stmt.names) == 1 else None,
                        is_from=True,
                        level=stmt.level,
                        line_number=stmt.lineno,
                    )
                )
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(self._extract_function(stmt, parent_qualname=""))
            elif isinstance(stmt, ast.ClassDef):
                classes.append(self._extract_class(stmt, parent_qualname=""))

        return PythonModuleMap(
            file_path=relative_path,
            module_name=module_name,
            is_test_file=is_test_file,
            line_count=line_count,
            docstring=module_docstring,
            imports=tuple(imports),
            classes=tuple(classes),
            functions=tuple(functions),
        )

    def _extract_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        parent_qualname: str = "",
        is_method: bool = False,
    ) -> FunctionSymbol:
        """Extract FunctionSymbol from a FunctionDef / AsyncFunctionDef AST node."""
        qualname = f"{parent_qualname}.{node.name}" if parent_qualname else node.name
        decorators = tuple(_format_decorator(d) for d in node.decorator_list)
        params = _extract_parameters(node.args)
        doc = ast.get_docstring(node)

        return FunctionSymbol(
            name=node.name,
            qualified_name=qualname,
            line_number=node.lineno,
            end_line_number=getattr(node, "end_lineno", None),
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_method=is_method,
            decorators=decorators,
            parameters=params,
            docstring=doc,
        )

    def _extract_class(
        self,
        node: ast.ClassDef,
        parent_qualname: str = "",
    ) -> ClassSymbol:
        """Extract ClassSymbol (and its methods / nested classes) from a ClassDef node."""
        qualname = f"{parent_qualname}.{node.name}" if parent_qualname else node.name
        bases = tuple(_format_node_expr(b) for b in node.bases)
        decorators = tuple(_format_decorator(d) for d in node.decorator_list)
        doc = ast.get_docstring(node)

        methods: list[FunctionSymbol] = []
        nested_classes: list[ClassSymbol] = []

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(
                    self._extract_function(item, parent_qualname=qualname, is_method=True)
                )
            elif isinstance(item, ast.ClassDef):
                nested_classes.append(
                    self._extract_class(item, parent_qualname=qualname)
                )

        return ClassSymbol(
            name=node.name,
            qualified_name=qualname,
            line_number=node.lineno,
            end_line_number=getattr(node, "end_lineno", None),
            base_classes=bases,
            decorators=decorators,
            methods=tuple(methods),
            nested_classes=tuple(nested_classes),
            docstring=doc,
        )
# ADR-004: Python Standard Library `ast` for Structural Repository Analysis

**Status:** Accepted
**Date:** 2026-08-28
**Milestone:** 2.2

## Context

To enable downstream code retrieval, dependency understanding, and implementation planning, the system needs to analyze acquired Python repositories into a deterministic structural map (`RepositoryMap`).

We evaluated candidate parsing and static analysis technologies:
1. **Python standard library `ast` module**
2. **Tree-sitter** (via `tree-sitter` / `tree-sitter-python` bindings)
3. **LibCST** (Concrete Syntax Tree parser)
4. **Language Server Protocol (LSP) / Jedi**

## Decision

We choose **Python standard library `ast`** for structural repository analysis in Milestone 2.2.

We will NOT introduce `tree-sitter`, `libcst`, or LSP tools at this stage.

## Rationale

### 1. Zero External Dependencies & High Reliability
- Python's built-in `ast` and `tokenize` modules are part of the standard library, requiring no C-extension compilation, prebuilt binaries, or third-party wheels.
- `ast.parse` is mature, fast, and maintained in lockstep with the Python language specification.

### 2. Pure Syntactic Safety
- `ast.parse` parses source code into a syntax tree without importing or executing any repository code.
- Repository code is treated strictly as untrusted text data. No decorators, module-level code, or setup scripts are evaluated.

### 3. Sufficient Structural Granularity for Milestone 2.2
- Standard `ast` provides exact line numbers (`lineno`, `end_lineno`), docstrings (`ast.get_docstring`), inheritance hierarchies (`ClassDef.bases`), function/method definitions (`FunctionDef`, `AsyncFunctionDef`), decorators (`decorator_list`), and import statements (`Import`, `ImportFrom`).
- This satisfies all requirements for structural indexing, symbol navigation, and test detection without CST preservation (comments/formatting) or full semantic symbol resolution.

### 4. Deterministic and Robust Error Isolation
- Syntax errors (`SyntaxError`) and encoding errors (`UnicodeDecodeError`) are caught cleanly per-file and transformed into structured `ParseFailure` records without crashing the whole repository analysis.

## Alternatives Considered & Deferred

- **Tree-sitter:** High-speed incremental parsing and multi-language support. Deferred because Python is our current target language and standard `ast` has zero dependency overhead. Tree-sitter may be reconsidered if polyglot support or incremental parsing during editing is needed.
- **LibCST:** Preserves whitespace and comments for refactoring/code rewriting. Not needed for read-only structural analysis; will be considered during controlled code modification (Milestone 4).
- **LSP / Jedi:** High-fidelity semantic type inference and cross-module definition jumping. Heavyweight process model deferred until advanced retrieval requires type-directed search.

## Consequences

- **Python Version Compatibility:** `ast.parse` uses the host Python runtime grammar (Python 3.11+ in our environment). Files utilizing future syntax not supported by the host interpreter will produce structured `ParseFailure` entries rather than breaking the pipeline.
- **Syntactic Only:** Imports and base classes are extracted as written syntactically; semantic symbol resolution across files is deferred to the retrieval layer.
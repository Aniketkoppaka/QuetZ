# ADR-005: Context Retrieval Architecture (Lexical + Structural Expansion)

**Status:** Accepted
**Date:** 2026-08-29
**Milestone:** 3

## Context

The Autonomous Software Engineer must identify and retrieve the most relevant source files, classes, methods, and functions from an analyzed repository (`RepositoryMap`) to address a given `Issue`.

We needed to establish:
1. Whether lexical search + structural graph expansion is sufficient as a deterministic baseline.
2. Whether semantic embeddings / vector databases are necessary at this stage.
3. How to provide transparent, inspectable explanations for why code items were retrieved.
4. How to bound retrieved context within a predictable token/character budget for downstream planning.

## Decision

1. We implement a **Hybrid Lexical and Structural Retrieval Pipeline** using:
   - **Sub-identifier Tokenization:** CamelCase, snake_case, path, and identifier decomposition.
   - **Multi-signal Lexical Matching:** Scored against filenames, symbols, docstrings, and imports.
   - **Structural Graph Expansion:** Following conservative local imports, associated test files, and class hierarchies.
   - **Budgeting & Deterministic Ranking:** Strict context budgets with explainable score decompositions and lexicographical tie-breakers.

2. We **defer semantic embeddings and vector databases**.
   - Embeddings introduce heavy third-party dependencies (PyTorch/ONNX/sentence-transformers), external API costs, non-deterministic latency, and offline evaluation complexity without proven incremental gain over symbol-aware structural expansion on small-to-medium Python codebases.

## Rationale

### 1. Explainability & Evaluation
- Every retrieval item returns an explicit list of `RetrievalReason` records (e.g. `filename_match`, `symbol_match`, `import_relationship`, `test_association`).
- This allows deterministic evaluation using standard information retrieval metrics (Precision@K, Recall@K, MRR) and provides diagnostic transparency when diagnosing retrieval errors.

### 2. Structural Precision on Codebases
- Software engineering issues frequently reference exact error names, classes, functions, and module paths.
- AST-derived structural relationships (e.g., if `auth/service.py` is relevant, inspecting `auth/database.py` and `tests/test_auth.py`) capture critical context that generic text embeddings often dilute.

### 3. Pure Python Standard Library & Zero Infrastructure
- The entire lexical tokenizer, BM25-inspired term scorer, AST graph traversal, and evaluation harness run completely offline in pure Python with zero external network or database dependencies.

## Consequences

- **Local Import Resolution Limitations:** Dynamic imports, `importlib`, and complex namespace packages are not resolved; unresolved imports are safely skipped without error.
- **Evaluation Baseline Established:** Benchmark results establish a reproducible baseline against which any future embedding experiments must be measured.
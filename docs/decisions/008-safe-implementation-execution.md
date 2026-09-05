# ADR-008: Safe Implementation Execution, Atomicity, and Rollback Architecture

**Status:** Accepted
**Date:** 2026-08-30
**Milestone:** 6

## Context

Milestone 4 established the formal planning protocol (`ImplementationPlan`, `PlanValidator`), and Milestone 5 integrated the structured LLM planning layer.
In Milestone 6, we introduce the **execution and verification layer** responsible for turning a validated `ImplementationPlan` into concrete repository modifications and verification results.

Key challenges addressed:
1. **Plan Authority:** The execution engine must never have open-ended writing authority or execute arbitrary LLM-generated shell commands. It must only execute operations explicitly authorized in a validated `ImplementationPlan`.
2. **Editing Strategy:** Evaluating direct file replacement vs. unified diffs vs. structured text replacements vs. AST editing.
3. **Pre-flight & Stale-Plan Protection:** Preventing modifications if repository state, target symbols, or file hashes have drifted since planning.
4. **Atomicity & Rollback:** Guaranteeing clean rollback to pre-execution workspace state if any step or verification check fails.
5. **Secure Verification:** Restricting test runner execution to strict allowlisted commands with sanitized environments, no shell invocation (`shell=False`), and strict timeouts.
6. **Zero Dependencies:** Pure Python standard library (`pathlib`, `ast`, `subprocess`, `hashlib`, `os`) + Pydantic v2.

## Decision

1. **Editing Strategy — Structured Text and Atomic File Operations:**
   - `ImplementationStep` is enhanced with optional structured edit fields:
     - `content: str | None`: Full content for `ADD_FILE`/`ADD_TEST` or full file replacement.
     - `search_content: str | None` and `replace_content: str | None`: Exact substring replacement for surgical symbol/file edits.
   - **Rationale:** Structured exact replacement avoids fuzzy patch drift and third-party patch library dependencies while remaining robust, auditable, and rollback-friendly.
   - **Atomicity:** All file writes use temporary files in the same directory (`.tmp_{uuid}`) followed by `os.replace()`.

2. **Pre-Flight Validation Engine (`ExecutionPreflight`):**
   - Strictly enforces Plan Authority: target paths must be inside the repository workspace root (`path.resolve().is_relative_to(workspace)`).
   - Stale plan protection: verifies target files/symbols exist and initial file SHA256 hashes match expectations before any filesystem mutation occurs.
   - If preflight fails, **zero files are touched**.

3. **In-Memory Snapshotting & Rollback Engine (`SafeFileEditor`):**
   - Prior to modifying, creating, or deleting any file, an in-memory snapshot of the pre-execution state is captured.
   - If any step fails or static/dynamic verification fails, the editor restores modified files, restores deleted files, and removes newly created files in reverse order.

4. **Multi-Tier Verification (`ExecutionVerifier`):**
   - **Static Verification:** `ast.parse` validates Python syntax on all modified/created files; symbol existence checks verify expected declarations.
   - **Dynamic Test Verification:** Secure subprocess execution with allowlisted commands (`pytest`, `python -m pytest`, `unittest`), sanitized environment (stripping credentials/tokens), strict execution timeout, and non-interactive execution (`shell=False`).

5. **Execution Determinism (`PlanExecutionResult`):**
   - `PlanExecutionResult.deterministic_dict()` separates deterministic execution states (status, file changes, hashes, verification outcomes) from non-deterministic timestamps (`started_at`, `completed_at`, `duration_ms`).

## Consequences

- **Safety Guarantee:** The LLM cannot directly write to the filesystem, execute arbitrary commands, or modify undeclared files.
- **Zero External Dependencies:** Built entirely with Python standard library and Pydantic v2.
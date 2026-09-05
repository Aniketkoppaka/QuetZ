# Architecture Overview

**Status:** Milestone 1 — Domain model and workflow state machine implemented.

---

## High-Level Pipeline

```
GitHub Issue
    |
    v
[1] Repository Acquisition   (ACQUIRING phase)
    |
    v
[2] Repository Understanding (MAPPING phase)
    |
    v
[3] Code Retrieval           (RETRIEVING phase)
    |
    v
[4] Implementation Planning  (PLANNING phase)
    |
    v
[5] Controlled Code Modification (IMPLEMENTING phase)
    |
    v
[6] Sandboxed Execution      (EXECUTING phase)
    |
    v
[7] Test / Check Results     (EVALUATING phase)
    |
   / \
  /   \
 v     v
[8]  REVIEWING (tests passed)
Repair    |
Loop      v
REPAIRING -> PLANNING (if reviewer needs changes or tests failed)
             |
             v
          [9] Final Verification (VERIFYING phase)
             |
             v
          [10] Patch / PR       (SUBMITTING phase)
             |
             v
          COMPLETED
```

---

## Workflow State Machine (Milestone 1)

The `WorkflowPhase` enum defines all valid states. The `VALID_TRANSITIONS`
frozenset defines permitted `(from, to)` pairs. `WorkflowRun.transition()`
is the only entry point for state changes.

### States

| Phase | Kind | Description |
|-------|------|-------------|
| `INITIALISED` | Active | Task created, not yet started |
| `ACQUIRING` | Active | Cloning/fetching the repository |
| `MAPPING` | Active | Building RepositoryMap |
| `RETRIEVING` | Active | Locating relevant code context |
| `PLANNING` | Active | Producing an ImplementationPlan |
| `IMPLEMENTING` | Active | Applying code changes |
| `EXECUTING` | Active | Running tests in sandbox |
| `EVALUATING` | Active | Parsing/interpreting test results |
| `REPAIRING` | Active | Diagnosing failure, preparing next attempt |
| `REVIEWING` | Active | Independent review of the patch |
| `VERIFYING` | Active | Final clean-room verification |
| `SUBMITTING` | Active | Creating PR / patch file |
| `COMPLETED` | **Terminal** | Successfully resolved |
| `FAILED` | **Terminal** | Irrecoverably failed |
| `ABANDONED` | **Terminal** | Repair exhausted or operator-cancelled |

### Key Transition Rules

- **Normal forward path:** INITIALISED → ACQUIRING → MAPPING → RETRIEVING
  → PLANNING → IMPLEMENTING → EXECUTING → EVALUATING → REVIEWING
  → VERIFYING → SUBMITTING → COMPLETED
- **Repair path:** EVALUATING → REPAIRING → PLANNING (loops back)
- **Review repair:** REVIEWING → REPAIRING → PLANNING (loops back)
- **Failure:** any active phase → FAILED
- **Abandonment:** any active phase → ABANDONED
- **Repair exhaustion:** REPAIRING → ABANDONED

### Enforcement

`TerminalStateError` is raised on any transition attempt from a terminal state.
`InvalidTransitionError` is raised for any `(from, to)` pair not in `VALID_TRANSITIONS`.
The transition table is tested directly: no terminal phase may appear as a source.

---

## Domain Model (Milestone 1)

All models live in `autonomous_engineer.domain`. All are immutable (Pydantic
`frozen=True`). No model depends on LLM SDKs, GitHub, Docker, or databases.

### `autonomous_engineer.domain.errors`

| Class/Enum | Purpose |
|-----------|---------|
| `FailureCategory` | 18 distinct failure categories (str enum, JSON-serializable) |
| `WorkflowError` | Base exception for programmatic workflow bugs |
| `InvalidTransitionError` | Raised when a transition is not in VALID_TRANSITIONS |
| `TerminalStateError` | Raised when attempting to exit a terminal state |

### `autonomous_engineer.domain.models`

| Model | Purpose |
|-------|---------|
| `Issue` | Primary input: issue ID, title, body, repo URL, branch |
| `Repository` | Acquired workspace: URL, path, SHA, branch |
| `RepositoryMap` | Structural summary of a scanned repository |
| `CodeContext` | Single retrieved code excerpt with relevance score |
| `ImplementationPlan` | Structured plan with steps, attempt number |
| `ExecutionResult` | Raw output from one sandboxed execution |
| `TestOutcome` | Enum: passed/failed/error/skipped/xfailed/xpassed |
| `TestCaseResult` | Single test case outcome with message |
| `TestSuiteResult` | Aggregate of all test case results; `all_passed` property |
| `FailureDetail` | Structured failure representation with `FailureCategory` |
| `RepairAttempt` | One iteration of the repair loop (plan + execution + result) |
| `ReviewVerdict` | Enum: approved/rejected/needs_changes |
| `ReviewResult` | Independent reviewer output with structured feedback |
| `PatchSummary` | Lightweight patch metadata (diff path, line counts) |
| `FinalResult` | Terminal outcome for evaluation harness |

### `autonomous_engineer.domain.states`

| Symbol | Purpose |
|--------|---------|
| `WorkflowPhase` | Enum of all 15 workflow states |
| `TERMINAL_PHASES` | frozenset of {COMPLETED, FAILED, ABANDONED} |
| `VALID_TRANSITIONS` | frozenset of 38 permitted (from, to) pairs |
| `TransitionRecord` | Audit log entry: from/to phase, triggered_by, reason, timestamp |
| `WorkflowRun` | Complete immutable run state; exposes `.transition()` |

---

## Component Descriptions (Planned)

### [1] Repository Acquisition
**Package:** `autonomous_engineer.repository` (Implemented in Milestone 2.1)

| Field | Detail |
|-------|--------|
| **Responsibility** | Acquire repository into isolated workspace and verify immutable revision |
| **Inputs** | `RepositoryReference` (URL, requested revision), `AcquisitionOptions` |
| **Outputs** | `Repository` domain object (URL, workspace_path, commit_sha, branch) |
| **Constraints** | Subprocess isolation (`shell=False`), hooks disabled (`core.hooksPath=""`), no interactive prompts (`GIT_TERMINAL_PROMPT=0`), strict resource limits |
| **Dependencies** | Git CLI via standard library `subprocess` (ADR-003) |

Key classes:
- `GitAcquisitionService`: Main entrypoint for repository acquisition, checkout, and verification.
- `RepositoryReference`: Input validation model for URLs and revisions (prohibits credential leaks, flag injection).
- `AcquisitionOptions`: Configures timeout, max size (default 500MB), max files (50k), and submodule policies.
- `WorkspaceManager`: Creates isolated directories and guarantees cleanup (handling Windows file locks).
- `GitCli`: Controlled subprocess runner.

---

### [2] Repository Understanding
**Package:** `autonomous_engineer.repository` (Implemented in Milestone 2.2)

| Field | Detail |
|-------|--------|
| **Responsibility** | Scan files deterministically and extract structural AST symbols into `RepositoryMap` |
| **Inputs** | `Repository` domain object, `AnalysisOptions` |
| **Outputs** | `RepositoryMap` domain object (classes, functions, methods, imports, docstrings, test/config files) |
| **Constraints** | Pure syntactic parsing (zero code execution), deterministic sorted ordering, isolated parse failures |
| **Dependencies** | Python standard library `ast` & `tokenize` (ADR-004) |

Key classes:
- `RepositoryAnalyzer`: High-level service coordinating file scanning and AST analysis.
- `FileScanner`: Traverses workspace deterministically, ignoring `.git` / caches, and classifies Python, test, and config files.
- `PythonAstAnalyzer`: Syntactic AST parser extracting classes, inheritance, decorators, functions, methods, parameters, and imports.
- `AnalysisOptions`: Configurable limits (max file count, max file size, max bytes read).
- `PythonModuleMap`, `ClassSymbol`, `FunctionSymbol`, `ImportStatement`, `ParseFailure`: Structural domain value objects.

---

### [3] Code Retrieval
**Package:** `autonomous_engineer.retrieval` (Implemented in Milestone 3)

| Field | Detail |
|-------|--------|
| **Responsibility** | Retrieve the most relevant source files, classes, methods, and functions for an issue |
| **Inputs** | `Issue` (or query string), `RepositoryMap`, `ContextBudget` |
| **Outputs** | `RetrievalResult` containing ranked `RetrievalItem`s with explainable `RetrievalReason` decompositions |
| **Constraints** | Bounded context budget (max files, max symbols, max characters), deterministic ranking with tie-breaking, zero code execution |
| **Dependencies** | Python standard library only (ADR-005) |

Key classes:
- `ContextRetriever`: Main entrypoint coordinating lexical search, structural expansion, and budget enforcement.
- `LexicalRetriever`: Multi-signal token matcher scoring filenames, directory paths, classes, methods, functions, docstrings, and imports.
- `StructuralRetriever`: Expands candidate items along local import dependencies, associated test files, and configuration relevance.
- `CodeTokenizer`: Identifier-aware tokenizer splitting camelCase, snake_case, and path components.
- `LocalImportResolver`: Purely static resolver for relative and absolute local Python imports.
- `RetrievalEvaluator`: Information Retrieval benchmark harness computing Precision@K, Recall@K, and MRR.

---

### [4] Implementation Planning
**Package:** `autonomous_engineer.agents`, `autonomous_engineer.domain` (Implemented in Milestones 4 & 5)

| Field | Detail |
|-------|--------|
| **Responsibility** | Formulate grounded, validated, deterministic implementation plans via LLMs |
| **Inputs** | `PlannerInput` (`Issue`, `Repository`, `RepositoryMap`, `RetrievalResult`, `attempt_number`, `previous_failure`) |
| **Outputs** | `ImplementationPlan` containing atomic `ImplementationStep` records |
| **Constraints** | Strict DAG dependency integrity, path safety, hallucination prevention against `RepositoryMap`, evidence grounding, bounded repair retries |
| **Dependencies** | Pure Python standard library & Pydantic v2 (ADR-006, ADR-007) |

Key classes:
- `LLMPlanner`: Grounded implementation planner with bounded repair loop correcting schema and semantic violations.
- `LLMClientInterface` & `HttpLLMClient`, `MockLLMClient`: Decoupled provider abstraction for JSON-structured generation.
- `PlannerPromptBuilder`: Builds system, user, and repair prompts enforcing strict evidence grounding rules.
- `ImplementationPlan`: Immutable structured plan with summary, rationale, atomic steps, assumptions, and uncertainties.
- `ImplementationStep`: Atomic step specifying operation type, target file/symbol, rationale, expected behavior, dependencies, evidence, and verification.
- `StepEvidence` & `EvidenceSource`: Formal provenance grounding steps to `RETRIEVED_CONTEXT`, `REPOSITORY_MAP`, `NEW_FILE`, or `EXPLICIT_ASSUMPTION`.
- `PlanValidator`: Comprehensive validator enforcing DAG cycle detection, path safety, and file/symbol hallucination detection.
- `PlannerInput` & `PlannerInterface`: Formal input/output protocol contracts.
- `ImplementationAgentContract`: Formal specification of coding-agent assumptions vs. mandatory verifications.
- `PlannerBenchmarkHarness` & `PlanningValidationBenchmark`: Test harnesses evaluating generation accuracy across 10 issue categories.

---

### [5] Safe Implementation Execution & Verification
**Package:** `autonomous_engineer.execution` (Implemented in Milestone 6)

| Field | Detail |
|-------|--------|
| **Responsibility** | Deterministically execute validated `ImplementationPlan` steps, perform atomic file modifications, run static & test verifications, and auto-rollback upon failure |
| **Inputs** | `ExecutionRequest` (`workspace_path`, `plan`, `policy`, `initial_file_hashes`) |
| **Outputs** | `PlanExecutionResult` containing `FileChangeRecord`s, `VerificationResult`s, status, and rollback flags |
| **Constraints** | Plan authority (cannot touch undeclared files), atomic temporary writes (`.tmp` + `os.replace`), strict test command allowlist, no shell execution (`shell=False`), sanitized environment, automatic snapshot rollback on failure |
| **Dependencies** | Pure Python standard library (`ast`, `subprocess`, `pathlib`, `hashlib`, `os`) & Pydantic v2 (ADR-008) |

Key classes:
- `ExecutionEngine`: Primary orchestrator managing pre-flight validation, step execution, verification, and rollback.
- `ExecutionRequest` & `ExecutionPolicy`: Configurable boundaries governing allowed operations, timeouts, max files, and test commands.
- `ExecutionPreflight`: Pre-flight validator checking plan authority, path boundary safety, stale file hashes, symbol presence on disk, and topological DAG ordering.
- `SafeFileEditor`: Confined atomic file editor performing structured substring replacements with in-memory snapshotting and full rollback.
- `ExecutionVerifier`: Multi-tier verification engine running static AST parsing, symbol checks, and secure subprocess test commands.
- `PlanExecutionResult` & `FileChangeRecord`: Audit-safe execution records with deterministic dictionary serialization.
- `ExecutionBenchmarkHarness`: Evaluator running 13 benchmark scenarios covering valid modifications, stale hashes, syntax errors, path traversal, unauthorized commands, and rollbacks.
---

### [6] Real-World Evaluation & Benchmark Harness
**Package:** `autonomous_engineer.evaluation` (Implemented in Milestone 7)

| Field | Detail |
|-------|--------|
| **Responsibility** | Execute reproducible end-to-end evaluation across historical open-source software engineering issues with strict ground-truth separation |
| **Inputs** | `RealBenchmarkIssue` registry, workspace directories, `RepositoryMap` cache, `LLMClientInterface` |
| **Outputs** | `EndToEndReport` and `BenchmarkRunResult`s with metrics and mutually exclusive failure classifications |
| **Constraints** | Strict ground-truth isolation (evaluator metadata never leaked to planner), mutually exclusive failure taxonomy precedence, explicit Live vs. Mock LLM tracking, zero external evaluation dependencies |
| **Dependencies** | Pure Python standard library & Pydantic v2 (ADR-009) |

Key classes:
- `RealBenchmarkRunner`: Primary orchestrator executing acquisition, retrieval, planning, execution, and verification pipelines.
- `RealBenchmarkIssue`: Benchmark issue specification capturing parent commit SHA, reference fix SHA, issue text, expected affected files, and verification status.
- `BENCHMARK_REGISTRY`: Verified registry of historical Python issues across `pallets/click`, `psf/requests`, `marshmallow`, `urllib3`, `bottle`, and documented excluded cases.
- `EvaluationFailureCategory`: Mutually exclusive failure taxonomy (`ISSUE_RESOLVED`, `RETRIEVAL_FAILURE`, `PLANNING_FAILURE`, `EXEC_REPRESENTATION_FAILURE`, `EXECUTION_FAILURE`, `VERIFICATION_FAILURE`, `ENVIRONMENT_FAILURE`).
- `LiveLLMStatus`: Explicit tracking of `LIVE_LLM_AVAILABLE`, `LIVE_LLM_UNAVAILABLE`, and `MOCK_MODE`.
- `EvaluationAblationConfig`: Configuration toggles for structural retrieval expansion and planner repair loops.
- `EndToEndReport` & `BenchmarkRunResult`: Comprehensive evaluation reports with deterministic dictionary serialization.

### [7] Test / Check Results
**Package:** `autonomous_engineer.execution`

| Field | Detail |
|-------|--------|
| **Responsibility** | Parse raw ExecutionResult into TestSuiteResult |
| **Inputs** | `ExecutionResult` |
| **Outputs** | `TestSuiteResult` |
| **Constraints** | Must handle partial/truncated output gracefully |
| **Dependencies** | pytest JUnit XML output format |

---

### [8] Failure Analysis + Bounded Repair Loop
**Package:** `autonomous_engineer.orchestration`

| Field | Detail |
|-------|--------|
| **Responsibility** | Diagnose failures and trigger repair; enforce iteration cap |
| **Inputs** | `TestSuiteResult`, `RepairAttempt` history, `ImplementationPlan` |
| **Outputs** | Updated `ImplementationPlan`, or transition to ABANDONED |
| **Constraints** | Max iterations from `MAX_REPAIR_ITERATIONS` env var |
| **State model** | `EVALUATING -> REPAIRING -> PLANNING` loop |

---

### [9] Independent Review
**Package:** `autonomous_engineer.review`

| Field | Detail |
|-------|--------|
| **Responsibility** | Separate agent reviews the patch without implementation history |
| **Inputs** | Patch diff, `Issue`, `RepositoryMap` |
| **Outputs** | `ReviewResult` (verdict, feedback) |
| **Constraints** | Reviewer must not see internal reasoning or repair history |
| **State model** | `REVIEWING -> VERIFYING` (approved) or `REVIEWING -> REPAIRING` |

---

### [10] Final Verification
**Package:** `autonomous_engineer.execution`

| Field | Detail |
|-------|--------|
| **Responsibility** | Final test run on a clean checkout |
| **Inputs** | Patch, target repository |
| **Outputs** | `TestSuiteResult` (must pass for COMPLETED) |

---

### [11] Patch / Pull Request
**Package:** `autonomous_engineer.github`

| Field | Detail |
|-------|--------|
| **Responsibility** | Generate unified diff; open GitHub PR |
| **Inputs** | Workspace diff, `Issue` metadata |
| **Outputs** | `PatchSummary`; PR URL |
| **Dependencies** | GitHub API (PAT or GitHub App TBD) |

---

## Supporting Components

### Configuration (`autonomous_engineer.config`)
Loads and validates environment variables. Exposes a typed, immutable
configuration object. Fails fast on missing required values.
*(Not yet implemented.)*

### Observability (`autonomous_engineer.observability`)
Structured logging, trace context, basic metrics. All components log through
this interface. Backend configurable (file, console, OTLP).
*(Not yet implemented.)*

### Evaluation (`autonomous_engineer.evaluation`)
Harness for benchmarking against known-answer datasets (e.g. SWE-bench).
*(Not yet implemented.)*

---

## Architectural Constraints

1. **No component may import from a higher abstraction layer.**
   `domain` has no dependencies on `agents`; `agents` may depend on `tools`.

2. **All external I/O is isolated behind module boundaries.**
   LLM calls: `agents`. GitHub: `github`. Docker: `execution`.

3. **Each component must be testable in isolation.**
   Dependencies are injected; external services are mockable.

4. **The orchestration layer owns all state.**
   Individual components are stateless functions/classes where possible.

5. **WorkflowRun is the single source of truth for run state.**
   All phase data flows through WorkflowRun.transition(); no ambient mutable state.

---

## Open Research Questions (Pre-Milestone 2)

| Question | Why it Matters |
|----------|---------------|
| LLM provider and model selection | Affects cost, latency, context window |
| Retrieval strategy for large repos | Determines if vector DB is needed |
| Docker SDK vs CLI wrapper | Affects dependency footprint and portability |
| GitHub access method (PAT vs. App) | Affects rate limits and security |
| Test framework assumptions beyond pytest | Whether other runners need support |
| Patch format (unified diff vs. file replacement) | Affects review quality |
| Plan representation format (JSON schema vs. free text) | LLM integration design |
| Configuration system design | How to load and validate env vars with full typing |
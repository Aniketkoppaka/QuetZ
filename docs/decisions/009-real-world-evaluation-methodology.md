# ADR-009: Real-World Evaluation Methodology, Failure Taxonomy, and Ground-Truth Separation

**Status:** Accepted
**Date:** 2026-08-30
**Milestone:** 7

## Context

Milestones 0 through 6 established and verified the core components of the autonomous software engineer: domain models, repository acquisition, AST mapping, context retrieval, grounded planning, plan validation, atomic execution, verification, and automatic rollback.
In Milestone 7, we transition from unit/synthetic architectural validation to **empirical evaluation on real-world open-source software engineering issues**.

Key challenges addressed:
1. **Ground-Truth Leakage:** Preventing evaluator metadata (such as reference patches, reference commit SHAs, and expected affected files) from contaminating the retrieval or planning context.
2. **Failure Classification:** Establishing an unambiguous, mutually exclusive failure taxonomy with deterministic precedence rules to distinguish retrieval, planning, execution, verification, and environment failures.
3. **Execution Expressiveness:** Measuring what classes of real-world edits can be expressed by `SafeFileEditor` without silently compromising security boundaries.
4. **Live vs. Mock LLM Distinction:** Explicitly tracking whether experiments reflect live model reasoning or offline architectural validation.
5. **Sample Size & Generalizability:** Ensuring evaluation results are reported honestly as diagnostic measurements rather than overclaimed general solutions.

## Decision

1. **Benchmark Registry & Ground-Truth Isolation (`RealBenchmarkIssue`):**
   - Each benchmark issue captures parent commit SHA, reference commit SHA, issue title, issue body, and expected affected files.
   - `RealBenchmarkIssue.to_planner_issue()` strips all evaluator metadata, guaranteeing zero information leakage into `PlannerInput`.
   - The registry explicitly categorizes entries into `VERIFIED`, `CANDIDATE`, and `EXCLUDED` (with documented rationale for scope boundaries like C-extensions or live database daemons).

2. **Mutually Exclusive Failure Taxonomy (`EvaluationFailureCategory`):**
   - Applied via strict precedence rules:
     1. `ENVIRONMENT_FAILURE`: Workspace or environment setup failed.
     2. `RETRIEVAL_FAILURE`: Zero ground-truth target files were retrieved.
     3. `PLANNING_FAILURE`: LLM planner failed to produce a valid grounded plan.
     4. `EXEC_REPRESENTATION_FAILURE`: Plan is valid but required change cannot be expressed via structured string replacement.
     5. `EXECUTION_FAILURE`: Preflight checks rejected plan or filesystem write failed.
     6. `VERIFICATION_FAILURE`: Edits applied but static AST checks or test suite failed.
     7. `ISSUE_RESOLVED`: All steps executed and all verification checks passed.

3. **Live LLM Status Tracking (`LiveLLMStatus`):**
   - The runner actively detects the presence of live API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) and labels every run as `LIVE_LLM_AVAILABLE`, `LIVE_LLM_UNAVAILABLE`, or `MOCK_MODE`.
   - If no live credentials exist, results are reported as offline architectural validation without claiming empirical model reasoning.

4. **Ablation Framework (`EvaluationAblationConfig`):**
   - Configurable toggles for structural retrieval expansion and planner repair loops ($N=1$ vs $N=3$) while keeping safety controls (`PlanValidator`, `ExecutionPreflight`) active.

## Consequences

- **Scientific Rigor:** Prevents false positive benchmark numbers caused by evaluator data contamination.
- **Root-Cause Clarity:** Isolates exact failure stages (retrieval vs. planning vs. execution expressiveness vs. verification).
# ADR-011: Ground-Truth Real-Repository Validation Methodology & Evaluator-Side Separation

**Status:** Accepted
**Date:** 2026-08-30
**Milestone:** 9.5 (Ground-Truth Real-Repository Validation)

## Context

Prior milestones established the autonomous engineering architecture, deterministic retrieval, grounded LLM planning, safe execution, and evaluation infrastructure.
Before claiming benchmark numbers or evaluating LLM capabilities on historical repository issues, the benchmark dataset itself must be verified for scientific reproducibility.

Key requirements:
1. **Empirical Defect Verification:** Every benchmark case must prove that the regression test genuinely fails on the buggy parent commit SHA.
2. **Evaluator-Side Reference Fix Verification:** Every case must prove that applying the historical reference fix converts the failing test into a passing test.
3. **Strict Ground-Truth Isolation:** Reference commit SHAs, patches, diffs, and expected affected files are strictly confined to evaluator-side validation and never exposed to the autonomous planning agent.
4. **Distinct Ground-Truth Taxonomy:** Separating dataset/environment validation outcomes (`BUG_NOT_REPRODUCED`, `DEPENDENCY_ENVIRONMENT_FAILURE`, `METADATA_INCONSISTENCY`, `VALIDATED`) from autonomous pipeline failure categories.

## Decision

1. **Evaluator-Side Validation Harness (`GroundTruthValidator`):**
   - Implements a multi-phase validation protocol:
     - **Phase A (Buggy Parent):** Checks out pinned parent SHA, runs regression test, verifies expected non-zero exit code, and checks for dependency/import crashes.
     - **Phase B (Reference Fix):** Applies historical reference fix on evaluator side and verifies test passes (exit code 0).
     - **Phase C (Metadata & SHA Invariants):** Verifies parent SHA != reference SHA, affected files match, and test commands are reproducible.
2. **Ground-Truth Taxonomy (`GroundTruthValidationStatus`):**
   - `VALIDATED`: Bug reproduces on parent and resolves on reference fix.
   - `REPOSITORY_ACQUISITION_FAILURE`: Repository checkout or workspace creation failed.
   - `PARENT_CHECKOUT_FAILURE`: Pinned parent commit SHA could not be checked out.
   - `DEPENDENCY_ENVIRONMENT_FAILURE`: Missing runtime libraries/modules caused test crash.
   - `BUG_NOT_REPRODUCED`: Regression test unexpectedly passed on the buggy parent commit.
   - `UNRELATED_PARENT_TEST_FAILURE`: Unrelated test suite failure occurred.
   - `REFERENCE_FIX_FAILURE`: Evaluator could not apply the historical reference patch.
   - `REFERENCE_TEST_FAILURE`: Test still fails after applying the historical fix.
   - `METADATA_INCONSISTENCY`: Pinned parent SHA equals reference SHA or metadata is invalid.
3. **Clean Workspace Lifecycle:**
   - Evaluator runs inside isolated temporary directories and disposes of modified states between cases.

## Consequences

- **Scientific Integrity:** Prevents evaluating autonomous agents on flawed, non-reproducible, or already-passing benchmark issues.
- **Root-Cause Clarity:** Isolates environment/dependency constraints from algorithmic planning capability.
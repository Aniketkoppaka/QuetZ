# ADR-014: Ground-Truth Baseline Matrix Execution & Candidate Validation

## Context & Problem Statement
Milestone 11 reconstructed the benchmark registry with authentic historical candidate pull requests and commits across public open-source repositories. However, in accordance with scientific rigor, candidates cannot be declared ground-truth verified merely because their Git SHAs exist remotely.

Milestone 12 executes the empirical validation matrix across all 12 authentic candidate cases to determine:
1. Does the buggy parent commit reproduce the intended historical bug/failure?
2. Does the reference fix commit resolve the failure cleanly?
3. Does the actual reference Git diff correspond to the claimed bug and expected affected files?

## Decision

1. **Explicit Ground-Truth Validation Taxonomy:**
   Implemented the fine-grained validation taxonomy distinguishing exact failure stages:
   - `GROUND_TRUTH_VERIFIED`
   - `PARENT_FETCH_FAILURE`
   - `PARENT_CHECKOUT_FAILURE`
   - `ENVIRONMENT_BUILD_FAILURE`
   - `BUG_NOT_REPRODUCED`
   - `REFERENCE_FETCH_FAILURE`
   - `REFERENCE_CHECKOUT_FAILURE`
   - `REFERENCE_TEST_FAILURE`
   - `PATCH_CORRESPONDENCE_FAILURE`

2. **Per-Candidate Telemetry & Serialization:**
   Recorded full stdout/stderr, exit codes, parent/reference Git SHAs, and actual affected files in `evaluation/matrix_results.json`.

3. **Status Classification of Candidates:**
   - Candidate status designated as `AUTHENTICALLY_SOURCED_CANDIDATE` prior to matrix validation.
   - Status `GROUND_TRUTH_VERIFIED` reserved strictly for cases that pass all 7 validation gates.

4. **Preservation of Empirical Reality (No Benchmark Gaming):**
   - Discrepancies between expected test selectors and actual PR diffs were preserved and classified rather than manufactured to pass.
   - Historical dependency constraints (e.g. legacy requests/urllib3 imports in modern Python 3.11) are explicitly classified as `BUG_NOT_REPRODUCED` or `ENVIRONMENT_BUILD_FAILURE`.

## Consequences & Invariants
- **Frozen Pipeline Baseline:** M0–M11 architecture (retrieval, planning, validation, execution) remained completely untouched.
- **Scientific Gate:** Live LLM evaluation remains gated until benchmark candidates achieve verified status in reproducible containerized environments.
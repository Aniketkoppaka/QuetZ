# ADR-013: Authentic Historical Benchmark Reconstruction & Ground-Truth Verification

## Context & Problem Statement
Milestone 10 revealed that while the evaluation infrastructure was operational, the underlying 8-case benchmark registry (`BENCHMARK_REGISTRY`) contained synthetic hexadecimal placeholder commit hashes (`5e123456789abcdef...`, `7a3456789abcdef...`) rather than real upstream Git history. Furthermore, no candidate had undergone rigorous empirical reproduction and reference-fix validation.

Evaluating an autonomous LLM on synthetic or guessed commits would guarantee dataset integrity defects and invalidate empirical findings. Milestone 11 reconstructs the benchmark dataset from authentic historical pull requests, issues, and Git commit histories across public open-source Python repositories (`pallets/click`, `psf/requests`, `marshmallow-code/marshmallow`).

## Decision

1. **Candidate Pool Discovery & Source Hierarchy:**
   - Surveyed ~20 real-world candidates from upstream GitHub repositories.
   - Enforced authoritative source hierarchy: Upstream Git commit history > Merged PR metadata > Issue tracker > Test suite diffs.
   - Discarded synthetic placeholders and unverified candidates.

2. **Schema & Provenance Enhancement:**
   - Extended `RealBenchmarkIssue` with:
     - `issue_url: str | None` (Public issue tracker reference)
     - `pull_request_url: str | None` (Merged pull request URL)
     - `provenance_sources: tuple[str, ...]` (Authoritative historical sources)
     - `executor_expressiveness_category: str` (`CATEGORY_A_DIRECTLY_EXPRESSIBLE`, `CATEGORY_B_REQUIRES_SMALL_EXTENSION`, `CATEGORY_C_NOT_CURRENTLY_EXPRESSIBLE`)
     - `python_version_requirement: str` (Minimum Python runtime version)
     - `ground_truth_status: GroundTruthValidationStatus` (Lifecycle status)

3. **Ground-Truth Isolation Guarantee:**
   - `RealBenchmarkIssue.to_planner_issue()` strips all reference patch summaries, expected affected files, reference commit SHAs, test commands, and provenance sources.
   - Planner receives strictly: `id`, `title`, `body`, and `repository_url`.

4. **Zero Synthetic / Guessed Commit SHAs:**
   - All final benchmark entries are verified against upstream Git remotes using full 40-character commit hashes.
   - No mock sequential hexadecimal hashes (`123456789abcdef`) or guessed SHAs are permitted.

5. **Empirical Ground-Truth Lifecycle Statuses:**
   - `CANDIDATE`
   - `METADATA_VERIFIED`
   - `PARENT_COMMIT_VERIFIED`
   - `BUG_REPRODUCED`
   - `REFERENCE_FIX_VERIFIED`
   - `FULLY_GROUND_TRUTH_VERIFIED`
   - `ENVIRONMENT_BLOCKED`
   - `INVALID_CASE`

## Consequences & Invariants
- **Frozen Pipeline Baseline:** M0–M10 core architecture (retrieval heuristics, prompt builders, validators, file editor, repair loop) remains strictly untouched.
- **Scientific Integrity:** The benchmark consists solely of authentic historical open-source bugs with inspectable diffs and verifiable Git parent commits.
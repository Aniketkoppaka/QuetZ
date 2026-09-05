# ADR-012: Reproducible Real-Repository Benchmark Environment, SHA Integrity Audit, and Ground-Truth Completion

**Status:** Accepted
**Date:** 2026-08-30
**Milestone:** 10 (Reproducible Real-Repository Benchmark Environment & Ground-Truth Completion)

## Context

In Milestones 7 through 9.5, the autonomous software engineering agent architecture and ground-truth validation protocols were designed and tested.
Milestone 10 shifts focus to **empirical environment feasibility, upstream Git repository reachability, and historical commit SHA verification** across the 8 registered benchmark issues.

Key findings & challenges:
1. **Environment Feasibility:** The host environment is Windows 10 without WSL enabled and without an active Docker daemon.
2. **Commit SHA Integrity Audit:** Forensic examination of `BENCHMARK_REGISTRY` in `src/autonomous_engineer/evaluation/dataset.py` revealed that the 8 registered cases currently contain **synthetic hexadecimal placeholder SHAs** (e.g. `5e123456789abcdef...`, `7a3456789abcdef...`) rather than real upstream Git commit hashes.
3. **Scientific Rule on Dataset Defects:** In accordance with the critical scientific rule, synthetic SHAs must NOT be silently patched or fabricated into artificial successes. Instead, they are formally classified as `METADATA_INCONSISTENCY` (dataset integrity defects) and documented as blocking empirical reproduction on real upstream remotes.

## Decision

1. **Environment Feasibility Auditing (`BenchmarkEnvironmentAuditor`):**
   - Automatically audits Python, Git CLI, Docker daemon connectivity, WSL availability, and remote network reachability.
   - Reports exact runtime limitations without masking platform constraints.

2. **Upstream Commit SHA Integrity Verification (`GroundTruthBenchmarkRunner`):**
   - Explicitly tests commit SHAs against upstream Git remotes.
   - Detects synthetic placeholder hashes and categorizes affected cases as `METADATA_INCONSISTENCY` with detailed diagnostic notes.

3. **Machine-Readable Ground-Truth Persistence (`GroundTruthArtifactPersistence`):**
   - Saves `environment.json`, `ground_truth_results.json`, and `summary.json` to `evaluation/runs/<run_id>/` for complete traceability.

## Consequences

- **Transparency:** Prevents false claims of empirical reproduction on unverified synthetic SHAs.
- **Actionable Dataset Roadmap:** Formally identifies the need for authentic upstream commit SHA curation and containerized Linux test execution prior to live LLM evaluation.
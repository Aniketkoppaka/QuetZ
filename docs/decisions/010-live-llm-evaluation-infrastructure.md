# ADR-010: Live LLM Evaluation Infrastructure, Secret Non-Disclosure, and Artifact Persistence

**Status:** Accepted
**Date:** 2026-08-30
**Milestone:** 8

## Context

Milestone 7 established the dataset models, ground-truth isolation invariants, and mutually exclusive failure classification taxonomy for real-world software engineering issues.
In Milestone 8, we build the **live LLM evaluation infrastructure** to execute the real-world benchmark against live providers (or deterministic offline mock environments when credentials are absent), while preserving complete observability, secret scrubbing, and machine-readable persistence.

Key challenges addressed:
1. **Explicit Mode Disambiguation:** Preventing mock results from ever masquerading as live LLM evaluations.
2. **Secret Scrubbing & Credential Protection:** Guaranteeing that API keys, Authorization headers, and bearer tokens are never printed to stdout/stderr, logged in exceptions, or written to disk in benchmark result JSON.
3. **Reproducible Machine-Readable Artifacts:** Persisting structured outputs to `evaluation/runs/<run_id>/` with `environment.json`, `benchmark_results.json`, and `summary.json`.
4. **Parent Commit vs. Reference Fix Isolation:** Ensuring live models receive only the buggy parent commit state, with ground-truth fixes used exclusively for post-hoc evaluator comparisons.
5. **Deterministic Baseline Before Optimization:** Enforcing that the first live evaluation measures the frozen M0–M7 zero-shot baseline without ad-hoc prompt tuning or executor heuristics.

## Decision

1. **Provider Configuration & Safe Environment Auditor (`LLMProviderConfig`, `EnvironmentAuditor`):**
   - Configures OpenAI-compatible JSON-schema transport via environment variables (`OPENAI_API_KEY`, `OPENAI_API_BASE`, `OPENAI_MODEL`).
   - `LLMProviderConfig.masked_dict()` strictly replaces API keys with `[REDACTED_SECRET]`.
   - `EnvironmentAuditor.audit()` inspects Python, Git, Pytest, and network capabilities without exposing sensitive values.

2. **Explicit Evaluation Modes (`EvaluationMode`):**
   - `LIVE`: Real HTTP requests executed against the live LLM provider.
   - `MOCK`: Offline deterministic mock transport used for architectural validation.
   - `UNAVAILABLE`: Live evaluation requested but no credentials configured in environment. The runner terminates cleanly with `LIVE LLM EVALUATION: NOT EXECUTED`.

3. **Machine-Readable Artifact Persistence (`BenchmarkRunPersistence`):**
   - Saves sanitized run artifacts to `evaluation/runs/<run_id>/`:
     - `environment.json`: System and provider audit.
     - `benchmark_results.json`: Detailed per-case retrieval, planning, execution traces, and failure classifications.
     - `summary.json`: Aggregate metrics (resolved rate, mean Recall@3, MRR, failure distribution).
   - Deep recursive secret scrubbing ensures no authorization tokens appear in persisted files.

4. **CLI Runner (`autonomous_engineer.evaluation.cli`):**
   - Provides a standardized CLI with `--mode`, `--case`, `--category`, `--output-dir`, and `--dry-run` options.

## Consequences

- **Safety Guarantee:** Live LLM integration introduces zero security risks or credential leakage vulnerabilities.
- **Scientific Integrity:** Live evaluation metrics cannot be confused with offline mock metrics.
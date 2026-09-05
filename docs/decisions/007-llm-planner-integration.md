# ADR-007: LLM Planner Integration, Structured Output, and Grounded Repair Loop

**Status:** Accepted
**Date:** 2026-08-29
**Milestone:** 5

## Context

Milestone 4 established the formal planning protocol (`PlannerInput`, `ImplementationStep`, `ImplementationPlan`, `PlanValidator`).
In Milestone 5, we introduce a structured LLM-backed implementation planner capable of converting retrieved context and issue descriptions into grounded implementation plans.

Key challenges addressed:
1. **Provider Decoupling & Compatibility Boundary:** The planner architecture must not depend on vendor SDKs or monolithic agent frameworks, but must acknowledge the concrete transport compatibility limits.
2. **Hallucination Prevention & Prompt Injections:** Untrusted issue text, repository code, docstrings, and comments could attempt prompt injection or fabricate non-existent repository entities.
3. **Bounded Repair Loop:** Schema and semantic validation errors must be exposed back to the LLM for bounded correction without permitting the model to fabricate repository facts.
4. **Architectural vs. Empirical Separation:** Deterministic validation of the planning pipeline must be explicitly separated from live model reliability evaluations.

## Decision

1. **Provider-Neutral Client Abstraction vs. Initial Concrete Transport:**
   - **Provider-Neutral Abstraction:** `LLMClientInterface` defines `generate(messages, config, response_schema) -> LLMResponse`.
   - **Concrete Initial Transport:** `HttpLLMClient` uses pure Python standard library (`urllib.request`) targeting OpenAI-compatible `/chat/completions` endpoints with `json_schema` response formatting.
   - **Mock Transport:** `MockLLMClient` provides deterministic in-memory execution for offline regression testing and fault injection simulation.

2. **Grounded Prompt Engineering & Anti-Injection Boundary (`PlannerPromptBuilder`):**
   - The prompt explicitly frames repository code, docstrings, issue descriptions, and retrieved snippets as **untrusted data**, not system instructions.
   - Strict provenance hierarchy:
     - **Verified Facts:** `RetrievalResult` excerpts and `RepositoryMap` symbols.
     - **Permitted New Artifacts:** `NEW_FILE` operations for new files.
     - **Explicit Hypotheses:** `EXPLICIT_ASSUMPTION` declarations.
     - **Forbidden:** `UNSUPPORTED` fabrications (rejected by `PlanValidator`).
   - For ambiguous or incomplete context, the prompt commands the planner to populate `unresolved_uncertainties` or `assumptions` rather than manufacturing confidence.

3. **Bounded Repair Loop & Non-Manufacturing Invariant (`LLMPlanner`):**
   - If initial generation violates Pydantic schema or `PlanValidator` invariants (e.g. hallucinated files, circular dependencies), `LLMPlanner` feeds structured error diagnostics back to the model.
   - **Critical Safety Invariant:** The repair loop never mutates repository facts, module maps, or retrieval results. Only the generated plan output changes between turns.
   - Retries are capped at `max_retries` (default 3). If retries are exhausted, the plan is rejected with full validation diagnostics.

4. **Secret Scrubbing & Audit Logging:**
   - `PlanningAuditRecord` captures token usage, latency, and error diagnostics.
   - No HTTP Authorization headers, API keys, bearer tokens, or environment variables are stored in audit records.

## Consequences

- **Safety Guarantee:** The LLM cannot write to the filesystem, execute code, or bypass `PlanValidator`.
- **Zero External SDK Dependencies:** Implemented using pure Python standard library + Pydantic v2.
- **Empirical Boundary:** The deterministic validation architecture is fully verified via automated tests and synthetic fault injection; live LLM planning quality remains model-dependent.
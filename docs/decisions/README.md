# Architectural Decision Records (ADRs)

This directory contains Architectural Decision Records for the
autonomous-software-engineer project.

## Format

Each ADR is a markdown file named `NNN-short-title.md` where `NNN` is a
zero-padded sequence number.

Suggested sections:

```markdown
# ADR-NNN: Title

**Status:** Proposed | Accepted | Superseded | Deprecated
**Date:** YYYY-MM-DD

## Context
Why was this decision necessary?

## Decision
What was decided?

## Rationale
Why was this option chosen over alternatives?

## Consequences
What are the trade-offs and follow-on implications?
```

## Index

| ADR | Title | Status | Milestone |
|-----|-------|--------|-----------|
| [ADR-001](001-domain-modeling-approach.md) | Domain Modeling Approach (Pydantic v2) | Accepted | 1 |
| [ADR-002](002-state-machine-design.md) | Workflow State Machine Design | Accepted | 1 |
| [ADR-003](003-git-acquisition-approach.md) | Git CLI via Subprocess Wrapper | Accepted | 2.1 |
| [ADR-004](004-ast-analysis-approach.md) | Python stdlib AST for Repository Analysis | Accepted | 2.2 |
| [ADR-005](005-context-retrieval-architecture.md) | Context Retrieval Architecture | Accepted | 3 |
| [ADR-006](006-implementation-planning-protocol.md) | Implementation Planning Protocol & Validation | Accepted | 4 |
| [ADR-007](007-llm-planner-integration.md) | LLM Planner Integration & Grounded Planning | Accepted | 5 |
| [ADR-008](008-safe-implementation-execution.md) | Safe Implementation Execution & Verification | Accepted | 6 |
| [ADR-009](009-real-world-evaluation-methodology.md) | Real-World Evaluation Methodology & Failure Taxonomy | Accepted | 7 |
| [ADR-010](010-live-llm-evaluation-infrastructure.md) | Live LLM Evaluation Infrastructure & Secret Non-Disclosure | Accepted | 8 |
| [ADR-011](011-ground-truth-real-repository-validation.md) | Ground-Truth Real-Repository Validation Methodology | Accepted | 9.5 |
| [ADR-012](012-reproducible-benchmark-environment-and-ground-truth.md) | Benchmark Environment Feasibility & SHA Integrity Audit | Accepted | 10 |
| [ADR-013](013-authentic-historical-benchmark-reconstruction.md) | Authentic Historical Benchmark Reconstruction & Ground-Truth Verification | Accepted | 11 |
| [ADR-014](014-ground-truth-baseline-matrix-execution.md) | Ground-Truth Baseline Matrix Execution & Candidate Validation | Accepted | 12 |
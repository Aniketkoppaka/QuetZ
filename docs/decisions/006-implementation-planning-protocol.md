# ADR-006: Implementation Planning Protocol & Context Grounding Validation

**Status:** Accepted
**Date:** 2026-08-29
**Milestone:** 4

## Context

Downstream autonomous coding agents require a structured, unambiguous, and grounded `ImplementationPlan` to resolve GitHub issues without architectural deviation or hallucination.

Unconstrained LLM planners tend to:
1. Reference non-existent files or fabricated symbol names ("hallucinations").
2. Formulate circular or contradictory implementation dependencies.
3. Emit vague steps that leave architectural intent open to arbitrary coding-agent interpretation.
4. Blur the line between verified repository facts and speculative assumptions.

We needed to establish a strict, deterministic domain schema and validation protocol governing planning inputs, implementation steps, evidence traceability, and dependency graphs before any LLM integration.

## Decision

1. **Structured Atomic Steps (`ImplementationStep`):**
   - Replace free-form string tuples with typed, immutable `ImplementationStep` records.
   - Each step specifies `step_id`, `operation` (from enum `StepOperation`), `target_file`, `target_symbol`, `description`, `rationale`, `expected_behavior`, `dependencies`, `evidence` (`StepEvidence`), and `verification_requirement`.

2. **Evidence Hierarchy & Hallucination Prevention (`EvidenceSource`):**
   - Every step links its target file and symbol to an explicit `EvidenceSource`:
     - `RETRIEVED_CONTEXT`: Directly present in `RetrievalResult`.
     - `REPOSITORY_MAP`: Present in the structural `RepositoryMap` file/symbol inventory.
     - `NEW_FILE`: Created by an explicit `ADD_FILE` step.
     - `EXPLICIT_ASSUMPTION`: Declared as an explicit assumption by the planner.
   - Any target file or symbol not satisfying this hierarchy is classified as `UNSUPPORTED` and rejected by the validator.

3. **Deterministic Plan Validation (`PlanValidator`):**
   - All plans must pass a dedicated, pure-Python validation suite verifying:
     - Direct Acyclic Graph (DAG) dependency integrity with cycle detection.
     - Path safety (repo-relative POSIX forward slashes, no absolute or `..` paths).
     - Symbol existence checks against `PythonModuleMap`.
     - Step ID uniqueness and non-empty descriptions.

4. **Planner Protocol Interface (`PlannerInterface` & `PlannerInput`):**
   - Planners accept `PlannerInput` (`Issue`, `Repository`, `RepositoryMap`, `RetrievalResult`, `attempt_number`, `previous_failure`) and return an immutable `ImplementationPlan`.
   - The protocol remains decoupled from any specific LLM provider or orchestration framework.

## Consequences

- **Strict Validation Overhead:** Planners cannot emit arbitrary text or vague action lists; every step must reference existing or declared artifacts.
- **Auditable Provenance:** Every change is traceable from Issue → Retrieval Evidence → Implementation Step → Verification Requirement.
- **Zero LLM Dependency in Milestone 4:** The schema, protocol, and validation harness are completely testable and measurable with deterministic unit and benchmark suites.
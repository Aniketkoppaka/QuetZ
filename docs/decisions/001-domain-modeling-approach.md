# ADR-001: Domain Modeling Approach

**Status:** Accepted  
**Date:** 2026-08-27  
**Milestone:** 1

---

## Context

The autonomous workflow must represent a rich set of domain concepts: issues,
repositories, plans, execution results, test outcomes, repair attempts, review
results, and final outcomes. These models must be:

- Typed and validated (wrong types should be caught early, not silently propagated)
- Immutable (state mutations must go through controlled transitions, not arbitrary field assignment)
- Serializable (workflow runs must be reconstructable from stored state for observability)
- Dependency-light (the domain layer must not import LLM SDKs, Docker, GitHub clients, or databases)

Four modeling approaches were evaluated:

| Approach | Validation | JSON (de)serialization | Immutability | Notes |
|----------|-----------|------------------------|--------------|-------|
| `dataclasses` | None built-in | Manual converters required | `frozen=True` (shallow only) | Simple but requires significant boilerplate for serialization |
| `pydantic` v2 | Runtime, field-level | `.model_dump_json()` / `.model_validate_json()` | `frozen=True` enforces deep immutability | Already installed (transitive dep); best-in-class serialization |
| `attrs` | Via validators | Requires `cattrs` add-on | `frozen=True` | Good library but adds cattrs complexity; less ecosystem familiarity |
| `NamedTuple` | None | Via `_asdict()` + manual | Inherently immutable | No field validation, poor inheritance, awkward optional fields |

## Decision

**Use Pydantic v2 for all domain models.**

Pydantic v2 (version 2.13.4, already installed on this system as a transitive
dependency of langsmith) was selected because:

1. **Runtime validation** — field-level validators catch wrong types before they
   propagate through the workflow. The cost of fixing a bad `Issue.repository_url`
   at construction time is far lower than discovering it during repository acquisition.

2. **Lossless JSON round-trip** — `.model_dump_json()` and `.model_validate_json()`
   handle `datetime`, `Path`, `Enum`, nested models, and tuples without manual
   schema writing. This is essential for workflow reconstruction.

3. **Enforced immutability** — `model_config = ConfigDict(frozen=True)` makes all
   mutations raise `ValidationError`. This prevents accidental state mutation
   outside the controlled `WorkflowRun.transition()` method.

4. **No new dependency** — Pydantic is already present. Choosing it avoids adding
   an entirely new package to the dependency tree.

5. **datetime serialization** — Pydantic v2 serializes `datetime` to ISO 8601
   automatically. This is critical for the audit log timestamps.

## Rejected Alternatives

- **Plain `dataclasses`**: Rejected because runtime validation requires manual
  `__post_init__` logic for every field, and JSON serialization requires either
  `dataclasses.asdict()` (no type reconstruction) or a manual schema. The
  maintenance burden grows linearly with model count.

- **`attrs` + `cattrs`**: Rejected because it introduces two packages where one
  suffices. `cattrs` structuring requires explicit converters for custom types.
  The benefit over Pydantic is marginal for this use case.

- **`NamedTuple`**: Rejected because it has no field-level validation, poor
  support for `Optional` fields with default `None`, and awkward inheritance.

- **State-machine libraries (`transitions`, `python-statemachine`)**: Not applicable
  to this decision, but evaluated separately — see ADR-002.

## Consequence

Pydantic v2 is now a **runtime dependency** of the project (not just a dev
dependency). This is intentional: the domain layer is used at runtime, not only
in tests. Pydantic will be added to the `[project]` `dependencies` list in
`pyproject.toml`.

The `tuple` type is used instead of `list` for multi-value fields (e.g.
`repair_attempts: tuple[RepairAttempt, ...]`) to enforce immutability at the
collection level. Pydantic v2 handles tuple fields correctly in serialization.
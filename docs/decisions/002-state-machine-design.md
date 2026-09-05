# ADR-002: Workflow State Machine Design

**Status:** Accepted  
**Date:** 2026-08-27  
**Milestone:** 1

---

## Context

The autonomous workflow must not be an uncontrolled sequence of LLM calls or
function invocations. The system must have explicit, validated state transitions
so that:

- Illegal transitions (e.g. PLANNING → COMPLETED) are rejected at runtime.
- The complete history of a run is reconstructable from the transition log.
- States are mutually exclusive and precisely named.
- Failure and repair semantics are first-class concepts.

The question is how to implement this FSM.

## Options Evaluated

### Option A: External state-machine library (`transitions`, `python-statemachine`)

Libraries such as `transitions` (0.9.x) or `python-statemachine` provide
decorator-based DSLs for declaring states, transitions, and guards.

**Advantages:** Less boilerplate; built-in diagrams; guard conditions.  
**Disadvantages:**
- Adds a dependency with its own release cycle and magic.
- Decorators obscure the explicit transition table (the authoritative contract).
- Both libraries use mutation-based state tracking incompatible with our
  immutability requirement.
- Testing invariants requires understanding library internals.
- The workflow is ~12 states — not complex enough to justify a framework.

### Option B: Custom FSM with explicit transition table

A `frozenset` of `(from_phase, to_phase)` tuples constitutes the complete,
auditable contract. The `WorkflowRun.transition()` method is the only entry
point for state mutation. It validates against this table and returns a new
`WorkflowRun` object.

**Advantages:**
- Zero new dependencies.
- The transition table is the readable specification; tests run directly against it.
- Immutability is natural: `transition()` returns a new object.
- Every transition produces a `TransitionRecord` (audit log entry) automatically.
- The exact set of valid transitions is visible in a single screen of code.

**Disadvantages:**
- Slightly more code than a library decorator.
- No built-in state diagram generation (acceptable at this stage).

### Option C: Ad-hoc if/else chains in each component

Each component decides which state to move to.

**Rejected immediately**: Not testable, not auditable, not maintainable.

## Decision

**Use a custom FSM: `WorkflowPhase` enum + `VALID_TRANSITIONS` frozenset +
`WorkflowRun.transition()` method.**

## State Design

States are named for the phase being *entered*, not the action being performed.
This avoids ambiguous verb/noun combinations and aligns with FSM convention.

```
WorkflowPhase enum:
  INITIALISED   → Task created, not yet started
  ACQUIRING     → Cloning/fetching the repository
  MAPPING       → Building RepositoryMap
  RETRIEVING    → Locating relevant code context
  PLANNING      → Producing ImplementationPlan
  IMPLEMENTING  → Applying code changes via tools
  EXECUTING     → Running tests in sandbox
  EVALUATING    → Parsing and interpreting test results
  REPAIRING     → Diagnosing failure, preparing next attempt
  REVIEWING     → Independent review of the patch
  VERIFYING     → Final clean-room verification run
  SUBMITTING    → Creating PR / patch file
  COMPLETED     → [TERMINAL] Successfully resolved
  FAILED        → [TERMINAL] Irrecoverably failed
  ABANDONED     → [TERMINAL] Limits exceeded or operator-cancelled
```

Terminal states (`COMPLETED`, `FAILED`, `ABANDONED`) have no outgoing
transitions. `TerminalStateError` is raised if a caller tries to escape them.

## Transition Semantics

Each call to `WorkflowRun.transition(to_phase, triggered_by, reason, **updates)`
validates the `(current_phase, to_phase)` pair and produces:

1. A new `WorkflowRun` with the updated phase and any provided field updates.
2. A `TransitionRecord` appended to the immutable `transition_log`.

The `TransitionRecord` captures:
- `from_phase`, `to_phase`
- `triggered_by` (component or event name)
- `reason` (human-readable explanation)
- `occurred_at` (UTC timestamp)
- `metadata` (arbitrary dict for ad-hoc context)

This gives enough information to answer:
> What state were we in? What state are we entering? Why? When? What triggered it?

## Failure and Repair Semantics

- **Failure**: Any non-terminal phase can transition to `FAILED` (or `ABANDONED`
  for repair exhaustion from `REPAIRING`). Callers attach a `FailureDetail` via
  `**updates`, which the new `WorkflowRun` stores in its `failure` field.
- **Repair**: `EVALUATING → REPAIRING → PLANNING` is the repair loop path.
  Each iteration adds a `RepairAttempt` to `repair_attempts`. The orchestrator
  enforces the iteration cap externally (not in the FSM itself, which would
  conflate control flow with state representation).

## What Intentionally Remains Unresolved

- **Persistence**: The FSM does not know about databases. Callers can serialize
  `WorkflowRun.model_dump_json()` to any store.
- **Concurrency**: No concurrent access assumptions. Single-threaded runs.
  Multi-agent parallelism is deferred.
- **Rollback**: The FSM records history but does not implement rollback.
  If needed, callers can replay the transition log.
# Milestone 19 — Implementation & Regression Validation Report

**Date:** 2026-09-04  
**Status:** M19 IMPLEMENTATION VALIDATED — AWAITING LIVE EVALUATION  
**Milestone:** M19 (Scaffold-Preserving Diagnostic Repair)  
**Hypothesis Under Test:** **H7** (Scaffold-Preserving Repair Prompting)  
**Primary Reference:** `evaluation/runs/m19_design.md`  

---

## 1. Summary of Changes

Milestone 19 implemented the single approved intervention to test hypothesis **H7**:
> Retain deterministic diagnostic compaction (`compact_diagnostic()`) to provide concise single-line error messages, while restoring the verbatim rejected-plan JSON string (`invalid_plan_str`) under `=== PREVIOUS REJECTED PLAN (JSON PAYLOAD) ===`.

This restores the in-context structural template/scaffold required by `nvidia/nemotron-3-ultra-550b-a55b:free` to perform localized repairs rather than re-synthesizing complete plans from scratch.

### Files Modified:
1. `src/autonomous_engineer/agents/prompt_builder.py`:
   - Updated `build_repair_prompt()` to output `invalid_plan_str.strip()` instead of `compact_plan_representation()`.
   - Maintained `compact_diagnostic()` for formatting each `PlanValidationError`.
   - Preserved `compact_plan_representation()` as a module helper.
2. `tests/unit/test_llm_planner.py`:
   - Updated `test_8_repair_loop_integration` to verify that `build_repair_prompt()` includes both compact error lines and the JSON payload.
   - Added `test_9_compact_plan_helper_remains_available` to ensure helper functions remain backward-compatible and tested.

---

## 2. Test Verification Results

1. **Focused Unit Tests:**
   - Command: `pytest tests/unit/test_llm_planner.py -k "TestM18DiagnosticCompaction"`
   - Result: **9 passed, 0 failures in 0.51s**
2. **Full Regression Test Suite:**
   - Command: `pytest`
   - Result: **285 passed, 0 failures, 0 errors in 36.66s**

---

## 3. Invariants & Frozen Components Audit

* Model: `nvidia/nemotron-3-ultra-550b-a55b:free` (FROZEN)
* Provider: OpenRouter (FROZEN)
* Sampling: Temp 0.0, Max Tokens 4096, Context Budget 120,000 (FROZEN)
* Repair Budget: $N \le 3$ (FROZEN)
* SafeFileEditor: 3-tier matcher (FROZEN)
* Pre-Execution AST Syntax Gate: Active (FROZEN)
* Historical Version Grounding: Active (FROZEN)
* Retrieval: BM25 + AST Ranking (FROZEN)
* Benchmark Suite: Exactly the 6 verified cases (FROZEN)

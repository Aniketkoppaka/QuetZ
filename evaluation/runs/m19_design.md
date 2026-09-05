# Milestone 19 — Experimental Design: Scaffold-Preserving Diagnostic Repair

**Date:** 2026-09-04  
**Status:** M19 DESIGN COMPLETE  
**Milestone:** M19 (Controlled Single-Variable Experiment)  
**Hypothesis Under Test:** **H7 (Scaffold-Preserving Repair Prompting)**  
**Target Intervention:** Retain deterministic compact diagnostics (H6-A) while restoring the detailed rejected-plan JSON scaffold (reversing H6-B) in `PlannerPromptBuilder.build_repair_prompt()`.  
**Control Baseline:** Milestone 17 (`run_20260904_101007_ea3d13`) and Milestone 18 (`run_20260904_143651_9b10ba`)  
**Evaluation Population:** Exactly 6 `GROUND_TRUTH_VERIFIED` authentic benchmark cases  

---

## 1. Scientific Context & Hypothesis Formulation

In M18.1, forensic decomposition demonstrated that the regression in planning validity (from 66.7% in M17 to 16.7% in M18) was primarily caused by **H6-B**: replacing the rejected plan's JSON payload with a high-level step outline (`- step-id: op -> target_file`). Without the previous JSON scaffold, the free model was forced to re-synthesize entire multi-step plans from scratch, resulting in severe indentation defects, token concatenation (`import copyimport pickle`), and malformed JSON.

Conversely, **H6-A** (deterministic diagnostic compaction: single-lining error messages while preserving error types, fields, file paths, line/column numbers, and substantive messages) was mechanistically clean and caused no information loss.

### The Scientific Question for M19:
> **Does restoring the verbatim rejected-plan JSON scaffold while retaining compact diagnostics (H7) recover planning validity and repair-loop completion without triggering output budget exhaustion?**

---

## 2. The Single Approved Intervention

In `src/autonomous_engineer/agents/prompt_builder.py`:
1. In `PlannerPromptBuilder.build_repair_prompt()`:
   - **Retain:** `compact_diagnostic(err)` to present all validation errors concisely on single lines.
   - **Intervene:** Restore the full verbatim `invalid_plan_str` under `=== PREVIOUS REJECTED PLAN (JSON PAYLOAD) ===`, eliminating the lossy `compact_plan_representation()` outline in the active repair prompt.
   - Retain `compact_diagnostic` and `compact_plan_representation` functions in the module for backward compatibility and unit test integrity.

---

## 3. Invariants & Frozen Components

All other aspects of the system remain strictly frozen:
* **Model:** `nvidia/nemotron-3-ultra-550b-a55b:free`
* **Provider & Endpoint:** OpenRouter (`https://openrouter.ai/api/v1`)
* **Sampling Parameters:** Temperature = `0.0`, Max Tokens = `4096`, Context Budget = `120,000` chars
* **Repair Budget:** $N \le 3$ attempts
* **Matcher:** SafeFileEditor 3-tier matcher (M15)
* **Historical Grounding:** Parent commit header (M16)
* **Syntax Validation:** Pre-execution in-memory AST syntax gating (M17)
* **Retrieval Strategy:** BM25 + AST Ranking (Top-5, 0.5/0.5 weights)
* **Benchmark Cases:** The exact 6 verified authentic cases (`REAL-CLICK-02`, `REAL-CLICK-03`, `REAL-MARSHMALLOW-01`, `REAL-MARSHMALLOW-02`, `REAL-MARSHMALLOW-03`, `REAL-MARSHMALLOW-04`)
* **Harness & Verifiers:** Multi-tier verification, static AST check, transactional rollback. Zero ground-truth leakage.

---

## 4. Primary & Secondary Metrics

1. **Primary Metric:**
   - End-to-end task resolution rate (`resolved_cases / 6`).
2. **Secondary Metrics:**
   - Planning validity rate (`valid_plans / 6`): Target recovery from M18's 16.7% toward or exceeding M17's 66.7%.
   - Pre-execution syntax error interceptions and repair recoveries.
   - Downstream execution reach (number of cases reaching `ExecutionEngine`).
   - Transactional rollback success rate (target 100%).

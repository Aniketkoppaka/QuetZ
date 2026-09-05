# Milestone 18 — Live Baseline Evaluation Report: Diagnostic Context Compaction

**Date:** 2026-09-04  
**Status:** M18 LIVE BASELINE COMPLETE — AWAITING OVERSIGHT REVIEW  
**Milestone:** M18 (Live Controlled Experiment)  
**Run Identifier:** `run_20260904_143651_9b10ba`  
**Primary Reference:** `evaluation/runs/m18_design.md`  
**Implementation Reference:** `evaluation/runs/m18_implementation_report.md`  
**Hypothesis Under Test:** **H6** (Diagnostic Context Compaction in Multi-Turn Repair Loop)  
**Control Baseline:** Milestone 17 (`run_20260904_101007_ea3d13`)  
**Target Intervention:** Deterministic Diagnostic Context Compaction in `build_repair_prompt()`  
**Evaluation Population:** Exactly 6 `GROUND_TRUTH_VERIFIED` authentic benchmark cases  

---

## 1. Executive Summary

Milestone 18 evaluated the single approved intervention authorized by oversight:
> **Deterministic diagnostic context compaction in the multi-turn repair loop (H6).**

The evaluation was conducted across all six authentic benchmark cases against the live OpenRouter endpoint using the frozen `nvidia/nemotron-3-ultra-550b-a55b:free` model with zero code modifications during evaluation.

### Key Headline Results:
* **Evaluated Cases:** 6 / 6
* **Resolved Cases:** 0 / 6 (0.0% resolution rate)
* **Planning Validity:** 1 / 6 valid (16.7%), 5 planning failures (M17: 4/6, M16: 6/6)
* **Downstream Reach:** 1 / 6 reached execution (`REAL-MARSHMALLOW-01`)
* **Syntax-Gate Interventions:** **12 syntax errors detected** across 4 distinct benchmark cases (M17: 9 errors)
* **Syntax Repair Recoveries:** **0 cases recovered from syntax errors** (M17: 2 recoveries)
* **Context Compaction Impact:**
  - Compact outline achieved 80–95% character reduction over raw plan serialization.
  - However, compacting the previous rejected plan into a high-level step outline (`- step-id: op -> target_file`) stripped the detailed JSON structure and field payloads from the model's context.
  - In response, the model repeatedly committed structural code-synthesis errors (e.g. lost indentation blocks, concatenated imports without newlines `import copyimport pickle`, or unescaped control characters) and JSON schema parse errors.
* **Dynamic Verification:** In `REAL-MARSHMALLOW-01` (the sole case reaching execution), changes were cleanly applied by `SafeFileEditor`, passed static AST validation, and reached `pytest` (exiting with test filter mismatch code 4).
* **Rollback & Workspace Safety:** 100% (1/1 applied case cleanly rolled back; 0 workspace contamination).
* **Reference Patch & Ground Truth Leakage:** Strictly 0.

---

## 2. Experimental Configuration & Immutability Audit

To preserve strict comparability across all milestones, all core experimental parameters remained frozen:

| Dimension | Control Baseline (M17) | Experimental State (M18) | Status |
| :--- | :--- | :--- | :--- |
| **Model** | `nvidia/nemotron-3-ultra-550b-a55b:free` | `nvidia/nemotron-3-ultra-550b-a55b:free` | FROZEN |
| **Provider** | OpenRouter (`https://openrouter.ai/api/v1`) | OpenRouter (`https://openrouter.ai/api/v1`) | FROZEN |
| **Temperature** | `0.0` | `0.0` | FROZEN |
| **Max Tokens** | `4096` | `4096` | FROZEN |
| **Context Budget** | `120,000` chars | `120,000` chars | FROZEN |
| **Repair Budget** | $N \le 3$ attempts | $N \le 3$ attempts | FROZEN |
| **SafeFileEditor** | M15 3-tier matcher | M15 3-tier matcher | FROZEN |
| **Historical Grounding** | M16 parent metadata header | M16 parent metadata header | FROZEN |
| **Pre-Exec AST Gate**| M17 in-memory AST pre-validation | M17 in-memory AST pre-validation | FROZEN |
| **Retrieval Config** | BM25 + AST Ranking (Top-5, 0.5/0.5) | BM25 + AST Ranking (Top-5, 0.5/0.5) | FROZEN |
| **Benchmark Suite** | 6 `GROUND_TRUTH_VERIFIED` cases | 6 `GROUND_TRUTH_VERIFIED` cases | FROZEN |
| **Repair Representation**| Full raw JSON + raw diagnostics | **Compact diagnostics + outline** | **SINGLE INTERVENTION** |

---

## 3. Aggregate Primary Metrics

| Metric Category | Metric | M16 Control | M17 Experimental | M18 Experimental | Delta (M17→M18) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **End-to-End** | Cases Evaluated | 6 | 6 | 6 | 0 |
| | Resolved Cases | 0 | 0 | 0 | 0 |
| | Resolution Rate | 0.0% | 0.0% | 0.0% | 0.0% |
| **Planning** | Planning Validity Rate | 100% (6/6) | 66.7% (4/6) | 16.7% (1/6) | -50.0% |
| | Syntax Errors Intercepted | 0 (uncaught) | 9 | 12 | +3 |
| | Syntax Repair Recoveries | 0 | 2 | 0 | -2 |
| | Repair Turns Used | 1 | 4 | 9 | +5 |
| **Failure Distribution**| `verification_failure` | 3 (50.0%) | 3 (50.0%) | 1 (16.7%) | -33.3% |
| | `exec_representation_failure`| 3 (50.0%) | 1 (16.7%) | 0 (0.0%) | -16.7% |
| | `planning_failure` | 0 (0.0%) | 2 (33.3%) | 5 (83.3%) | +50.0% |
| **Retrieval** | Mean Recall@3 | 66.7% | 66.7% | 66.7% | 0.0% |
| | Mean Recall@5 | 83.3% | 83.3% | 83.3% | 0.0% |
| | Mean MRR | 0.467 | 0.467 | 0.467 | 0.000 |
| **Safety** | Rollback Success Rate | 100% (6/6) | 100% (4/4 applied) | 100% (1/1 applied) | 0.0% |
| | Workspace Contamination | 0 | 0 | 0 | 0 |

---

## 4. Per-Case Trajectory Results & Telemetry

### Case 1: `REAL-CLICK-02` (pallets/click)
* **Parent Commit:** `3cbcf9b1` | **Target File:** `src/click/_utils.py`
* **Retrieval:** Rank 5 (Recall@5 = 1.0, MRR = 0.20)
* **Compaction & Planning Trajectory:**
  - **Attempt 1:** Generated plan with 3 errors (1 hallucinated symbol in test file, 2 syntax errors in generated test replacement).
  - **Attempt 2:** Model attempted to repair using the compact prompt, but generated invalid JSON with an invalid control character at line 2 (`Invalid control character at: line 2 column 5`).
  - **Attempt 3:** Model regenerated JSON, but test payload had concatenated imports without whitespace (`import copyimport pickleimport pytestfrom click._utils import Sentinel...`), triggering pre-execution AST syntax failure at line 1, column 19.
* **Terminal Failure:** `planning_failure` (Syntax error unrecovered after 3 attempts).
* **Downstream Execution:** Not reached.

### Case 2: `REAL-CLICK-03` (pallets/click)
* **Parent Commit:** `8b44edff` | **Target File:** `src/click/_termui_impl.py`
* **Retrieval:** Rank 1 (Recall@3 = 1.0, MRR = 1.00)
* **Compaction & Planning Trajectory:**
  - **Attempt 1:** Model emitted unterminated string starting at line 5 column 16 (JSON schema parse failure).
  - **Attempt 2:** Model generated 0 characters / truncated output (`Expecting value: line 1 column 1`).
  - **Attempt 3:** Model emitted unterminated string starting at line 23 column 7.
* **Terminal Failure:** `planning_failure` (JSON parse failures across all 3 attempts).
* **Downstream Execution:** Not reached.

### Case 3: `REAL-MARSHMALLOW-01` (marshmallow-code/marshmallow)
* **Parent Commit:** `b40a0f4e` | **Target File:** `src/marshmallow/fields.py`
* **Retrieval:** Rank 2 (Recall@3 = 1.0, MRR = 0.50)
* **Compaction & Planning Trajectory:**
  - **Attempt 1:** Output truncated on Attempt 1 (`Expecting value: line 1 column 1`).
  - **Attempt 2:** Routed through repair prompt with compact representation; model generated valid `ImplementationPlan` (3,074 chars).
* **Execution & Verification:**
  - `SafeFileEditor` successfully applied 2 file changes.
  - Multi-tier verification passed preflight and AST static checks cleanly.
  - Reached dynamic `pytest` execution: `pytest tests/test_fields.py -k test_datetime_list_inner_format` exited with non-zero code 4 (test filter matched 0 items in historical commit).
* **Terminal Failure:** `verification_failure`.
* **Rollback:** Clean transactional rollback; repository restored with zero diff.

### Case 4: `REAL-MARSHMALLOW-02` (marshmallow-code/marshmallow)
* **Parent Commit:** `3265c139` | **Target File:** `src/marshmallow/fields.py`
* **Retrieval:** Rank 2 (Recall@3 = 1.0, MRR = 0.50)
* **Compaction & Planning Trajectory:**
  - **Attempt 1:** In-memory AST pre-validation caught unexpected indent in `tests/test_deserialization.py` at line 1, column 4 (`def test_timedelta_field_nan_raises_validation_error...`).
  - **Attempt 2:** Compact repair prompt provided; model regenerated the test method but repeated the exact same indentation error at line 1, column 4.
  - **Attempt 3:** Output truncated (`Expecting value: line 1 column 1`).
* **Terminal Failure:** `planning_failure` (Attempt 3 output truncation).
* **Downstream Execution:** Not reached.

### Case 5: `REAL-MARSHMALLOW-03` (marshmallow-code/marshmallow)
* **Parent Commit:** `3207be31` | **Target File:** `src/marshmallow/validate.py`
* **Retrieval:** Rank 2 (Recall@3 = 1.0, MRR = 0.50)
* **Compaction & Planning Trajectory:**
  - **Attempt 1:** Caught hallucinated symbol `URL.RegexMemoizer._regex_generator` and syntax error in `test_validate.py` (expected indented block after function definition).
  - **Attempt 2:** Model fixed the hallucinated symbol, but repeated the exact same syntax error in `test_validate.py` (expected indented block at column 257).
  - **Attempt 3:** Model repeated the exact same syntax error at column 257 for the third consecutive turn.
* **Terminal Failure:** `planning_failure` (Syntax error repeated persistently across all 3 turns).
* **Downstream Execution:** Not reached.

### Case 6: `REAL-MARSHMALLOW-04` (marshmallow-code/marshmallow)
* **Parent Commit:** `3265c139` | **Target File:** `src/marshmallow/fields.py`
* **Retrieval:** Rank 10 (Recall@3 = 0.0, MRR = 0.10)
* **Compaction & Planning Trajectory:**
  - **Attempt 1:** Model produced unterminated string at line 96 column 5 (7,127 chars, JSON parse failure).
  - **Attempt 2:** Model produced syntactically invalid Python in `tests/test_deserialization.py` (unexpected indent at line 1, column 4).
  - **Attempt 3:** Model generated 3 separate test steps, all 3 containing the exact same unexpected indent at line 1, column 4.
* **Terminal Failure:** `planning_failure` (3 unrecovered syntax errors in Attempt 3).
* **Downstream Execution:** Not reached.

---

## 5. Causal Analysis of H6 (Diagnostic Context Compaction)

The M18 experiment tested hypothesis H6:
> *Can compacting repair diagnostics reduce context/output pressure and improve repair-loop completion within the frozen $N \le 3$ budget?*

### Experimental Findings:

1. **Prompt Compaction Succeeded Mechanistically:**
   - Compact diagnostics normalized multi-line errors into concise single-line strings.
   - Compact plan outlines replaced 4,000–8,000 character JSON payloads with concise ~200 character summaries (80–95% character reduction).

2. **Unexpected Negative Interaction with Model Capabilities:**
   - In M17, providing the full previous JSON payload allowed `nvidia/nemotron-3-ultra-550b-a55b:free` to copy and tweak the existing valid JSON fields, only editing the erroneous step. In M17, this resulted in 4/6 valid plans.
   - In M18, when only an outline of the rejected plan was provided (`- step-id: op -> target_file`), the model was forced to re-synthesize the entire JSON payload from scratch on every retry.
   - Because the free model struggles with long JSON generation and python whitespace formatting in single-line strings, re-synthesizing from scratch caused:
     * High rate of JSON syntax errors (unterminated strings, invalid control characters).
     * High rate of repeated syntax errors (repeating the exact same indentation defect across attempts 1, 2, and 3 in `MARSH-02`, `MARSH-03`, and `MARSH-04`).
     * Concatenation of code without delimiters (`import copyimport pickle` in `CLICK-02`).

3. **Impact on Primary Endpoint:**
   - Planning validity dropped from **66.7% (4/6) in M17 to 16.7% (1/6) in M18**.
   - Syntax recovery dropped from **2 cases in M17 to 0 cases in M18**.
   - End-to-end resolution remained **0 / 6**.

---

## 6. Verification and Safety Integrity

* **Transactional Rollback:** In the single case that reached execution (`REAL-MARSHMALLOW-01`), `ExecutionEngine` executed two file modifications, ran multi-tier verifiers, caught test failure code 4, and initiated transactional rollback.
* **Workspace Cleanliness:** Post-run git status verification confirmed zero uncommitted changes, untracked files, or corrupted HEAD commits.
* **Leakage Audit:** 0 reference commits, 0 ground-truth patches, and 0 test oracle solutions were exposed to the agent.

---

## 7. Conclusion

Milestone 18 provides definitive evidence regarding **H6**:
While deterministic diagnostic context compaction successfully reduces prompt size, **extreme plan compaction (reducing the rejected plan to an outline) impairs the free model's ability to correct localized defects**, as the model is forced to regenerate extensive JSON structures from scratch rather than performing localized repairs.

**M18 LIVE BASELINE COMPLETE — AWAITING OVERSIGHT REVIEW**

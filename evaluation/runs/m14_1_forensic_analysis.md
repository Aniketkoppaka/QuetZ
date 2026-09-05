# Milestone 14.1 — M14-FREE Forensic Trajectory Audit Report

**Evaluation Model:** `nvidia/nemotron-3-ultra-550b-a55b:free`  
**Provider / API:** `openai-compatible` via OpenRouter (`https://openrouter.ai/api/v1`)  
**Generation Configuration:** `Temperature = 0.0`, `Max Tokens = 4096`, `Context Budget = 120,000 chars`  
**Evaluated Population:** Exactly 6 `GROUND_TRUTH_VERIFIED` Benchmark Cases  
**Immutable Run Directory:** `evaluation/runs/run_20260902_125455_c3cc4e`  
**Analysis Date:** 2026-09-02  
**Milestone Mode:** Forensic Trajectory Audit (Analysis-Only)

---

## 1. Executive Summary

During the **Milestone 14-FREE** controlled live baseline evaluation, all 6 empirically verified real-world benchmark cases (`REAL-CLICK-02`, `REAL-CLICK-03`, `REAL-MARSHMALLOW-01`, `REAL-MARSHMALLOW-02`, `REAL-MARSHMALLOW-03`, `REAL-MARSHMALLOW-04`) executed end-to-end against live inference from `nvidia/nemotron-3-ultra-550b-a55b:free`.

### Summary of Observed Baseline Metrics
* **Resolution Rate:** `0 / 6 (0.0%)`
* **Planning Validity Rate:** `6 / 6 (100.0%)` — The model adhered to the structured JSON schema, valid DAG topological dependencies, and relative path boundaries across all 6 cases.
* **Safe Rollback Success Rate:** `6 / 6 (100.0%)` — In all 6 failed execution attempts, the autonomous `SafeFileEditor` and AST verification engine detected the defect before workspace contamination and safely restored the workspace to the pristine parent Git commit.
* **Target File Retrieval:** Mean Recall@3 = `66.7%` (4/6 cases), Mean Recall@5 = `83.3%` (5/6 cases), Mean MRR = `0.467`.
* **Failure Distribution:** 
  * `exec_representation_failure`: 3 cases (50.0%)
  * `verification_failure`: 3 cases (50.0%)

This forensic audit analyzes the step-by-step trajectories of all six cases to establish the root causes, distinguish model limitations from architectural constraints, evaluate the repair loop dynamics, and rank scientific hypotheses.

---

## 2. Baseline Integrity & Artifact Preservation Confirmation

The immutable run artifacts from Milestone 14-FREE were audited and confirmed intact:
* Directory: `evaluation/runs/run_20260902_125455_c3cc4e`
* Files Verified:
  * `m14_free_telemetry.json` (12,564 bytes)
  * `benchmark_results.json` (13,538 bytes)
  * `summary.json` (14,868 bytes)
  * `environment.json` (880 bytes)

Zero modifications were made to the baseline data, prompts, retrieval ranking, planner schema, execution engine, or verifier logic.

---

## 3. Per-Case Forensic Trajectory Analysis

### Case 1: `REAL-CLICK-02` (pallets/click)
* **Parent SHA:** `3cbcf9b11546f4cf10b36d3e2e531733ba6fe001`
* **Ground-Truth Target:** `src/click/_utils.py`
* **Outcome:** `NOT_RESOLVED` (`exec_representation_failure`) | **Duration:** 61.34s | **Attempts:** 1

#### Trajectory Breakdown
1. **Issue Understanding:** `UNDERSTOOD`  
   The model clearly understood the issue description: Sentinel enum members fail copy/deepcopy/pickle due to Python Enum duplication mechanics.
2. **Target Identification:** `CORRECT`  
   Retrieval ranked `src/click/_utils.py` at rank 5. The model selected `src/click/_utils.py` as its primary modification target in the generated plan.
3. **Intended Solution:** `CORRECT`  
   The plan outlined adding `__copy__`, `__deepcopy__`, and `__reduce__` methods to the `_Sentinel` class to preserve identity upon duplication.
4. **Edit Representation & Execution Failure:**  
   Execution failed at `step-3`. The model specified a `search_content` block for `src/click/_utils.py` that contained slightly hallucinated docstrings and inaccurate whitespace that did not match the authentic file content.
   * *Mechanism:* The model had the full file context retrieved in its context window, but failed to copy the verbatim exact anchor string.
5. **Repair Loop Effectiveness:**  
   `Repair engaged: No` (Execution aborted immediately during initial atomic transaction application; transaction rolled back cleanly).
6. **Counterfactual Architecture Assessment:** `YES`  
   If the model had provided the verbatim matching `search_content` for `_Sentinel`, `SafeFileEditor` would have applied the edit, the AST verifier would have confirmed validity, and the targeted pytest selector would have executed.

---

### Case 2: `REAL-CLICK-03` (pallets/click)
* **Parent SHA:** `8b44edfff7d9a6c895fa804148c16b3a0bc9efb5`
* **Ground-Truth Target:** `src/click/_termui_impl.py`
* **Outcome:** `NOT_RESOLVED` (`verification_failure`) | **Duration:** 183.08s | **Attempts:** 3

#### Trajectory Breakdown
1. **Issue Understanding:** `UNDERSTOOD`  
   The model understood that `ProgressBar.render_progress` must settle on the final position when iteration completes.
2. **Target Identification:** `CORRECT`  
   Retrieval ranked `src/click/_termui_impl.py` at rank 1 (MRR = 1.0). The model targeted `src/click/_termui_impl.py` and `tests/test_termui.py`.
3. **Intended Solution:** `CORRECT`  
   The plan aimed to update `render_progress` to calculate the final bar width upon `is_completed` or `finished`.
4. **Edit Representation & Execution Failure:**  
   The edit applied to `src/click/_termui_impl.py`, but the model generated malformed Python syntax (missing indentation in line 156) and an unindented function block in `tests/test_termui.py`.
5. **Verifier & Repair Loop Effectiveness:**  
   * `Repair engaged: Yes` (3 attempts).
   * Verifier provided explicit syntax diagnostics: `[syntax_ast] src/click/_termui_impl.py: SyntaxError: invalid syntax (_termui_impl.py, line 156)`.
   * *Repair behavior:* On attempts 2 and 3, the model acknowledged the syntax error in its reasoning, but its subsequent edits repeated indentation errors in neighboring code blocks.
   * `Repair recovered task: No`.
6. **Counterfactual Architecture Assessment:** `YES`  
   The execution engine successfully applied the edits, and the AST verifier correctly prevented broken syntax from persisting. If the model had produced valid syntax, verification would have proceeded to subprocess testing.

---

### Case 3: `REAL-MARSHMALLOW-01` (marshmallow-code/marshmallow)
* **Parent SHA:** `b40a0f4e33823e6d0f341f7e8684e359a99060d1`
* **Ground-Truth Target:** `src/marshmallow/fields.py`
* **Outcome:** `NOT_RESOLVED` (`verification_failure`) | **Duration:** 113.94s | **Attempts:** 2

#### Trajectory Breakdown
1. **Issue Understanding:** `UNDERSTOOD`  
   The model identified that `DateTime` fields nested inside containers access `schema.opts` instead of `root.opts`, causing an `AttributeError`.
2. **Target Identification:** `CORRECT`  
   Retrieval placed `src/marshmallow/fields.py` at rank 2 (Recall@3 = 1.0). The model selected `src/marshmallow/fields.py`.
3. **Intended Solution:** `CORRECT`  
   The plan explicitly proposed replacing `self.schema.opts` with `getattr(self.root, 'opts', None)` or `self.root.opts` in `DateTime._bind_to_schema`.
4. **Edit Representation & Execution Failure:**  
   The edit applied, but introduced `SyntaxError: unexpected indent (fields.py, line 336)` and a corrupted header in `tests/test_fields.py`.
5. **Verifier & Repair Loop Effectiveness:**  
   * `Repair engaged: Yes` (2 attempts).
   * Verifier provided: `[syntax_ast] unexpected indent (fields.py, line 336)`.
   * *Repair behavior:* In attempt 2, the model attempted to fix line 336 but introduced an unmatched parenthesis in the surrounding block.
   * `Repair recovered task: No`.
6. **Counterfactual Architecture Assessment:** `YES`  
   The fix concept was accurate and the target file was correct. Valid code synthesis would have passed AST verification.

---

### Case 4: `REAL-MARSHMALLOW-02` (marshmallow-code/marshmallow)
* **Parent SHA:** `3265c13945a9533f9a3ade8d47eb9b32412c4c27`
* **Ground-Truth Target:** `src/marshmallow/fields.py`
* **Outcome:** `NOT_RESOLVED` (`exec_representation_failure`) | **Duration:** 128.39s | **Attempts:** 2

#### Trajectory Breakdown
1. **Issue Understanding:** `UNDERSTOOD`  
   The model understood that `TimeDelta` deserialization raises `ValueError` on `NaN` and must catch both `(OverflowError, ValueError)` to raise `ValidationError`.
2. **Target Identification:** `CORRECT`  
   Retrieval placed `src/marshmallow/fields.py` at rank 2. Target file selected correctly.
3. **Intended Solution:** `CORRECT`  
   The model designed the exact intended catch block: `except (OverflowError, ValueError) as error: raise ValidationError(...)`.
4. **Edit Representation & Execution Failure:**  
   The `search_content` supplied by the model included an extra blank line and altered comment formatting that was not in `src/marshmallow/fields.py` at SHA `3265c139`.
   * *Mechanism:* The model attempted to recall the function signature from general training rather than matching the verbatim retrieved context snippet.
5. **Verifier & Repair Loop Effectiveness:**  
   * `Repair engaged: Yes` (2 attempts).
   * Diagnostic provided: `search_content was not found in 'src/marshmallow/fields.py'`.
   * *Repair behavior:* On attempt 2, the model modified the `replace_content` but failed to adjust the mismatched `search_content` anchor string.
   * `Repair recovered task: No`.
6. **Counterfactual Architecture Assessment:** `YES`  
   The conceptual fix was 100% aligned with the canonical solution. The failure was strictly an edit anchoring mismatch.

---

### Case 5: `REAL-MARSHMALLOW-03` (marshmallow-code/marshmallow)
* **Parent SHA:** `3207be31474530f7c0685dfbd7b4faca5b35fbf5`
* **Ground-Truth Target:** `src/marshmallow/validate.py`
* **Outcome:** `NOT_RESOLVED` (`verification_failure`) | **Duration:** 157.14s | **Attempts:** 2

#### Trajectory Breakdown
1. **Issue Understanding:** `UNDERSTOOD`  
   The model recognized that `validate.URL` regex rejected URLs where a fragment `#` directly follows an empty path without a trailing slash.
2. **Target Identification:** `CORRECT`  
   Retrieval placed `src/marshmallow/validate.py` at rank 2.
3. **Intended Solution:** `PARTIALLY_CORRECT`  
   The model modified the regular expression in `validate.py` to allow `#` in the tail pattern, but also attempted to append a new standalone test function `test_url_fragment_variations` into `tests/test_validate.py`.
4. **Edit Representation & Execution Failure:**  
   The edit applied, but the new test function was placed inside an existing class scope with invalid indentation, causing the symbolic verifier to fail: `Symbol 'test_url_fragment_variations' not found in 'tests/test_validate.py' after edits`.
5. **Verifier & Repair Loop Effectiveness:**  
   * `Repair engaged: Yes` (2 attempts).
   * Diagnostic: `Symbol 'test_url_fragment_variations' not found after edits`.
   * *Repair behavior:* Attempt 2 repeated the same placement error without restructuring the class-level indentation.
   * `Repair recovered task: No`.
6. **Counterfactual Architecture Assessment:** `YES`  
   The symbolic verifier accurately detected that the claimed test symbol was inaccessible.

---

### Case 6: `REAL-MARSHMALLOW-04` (marshmallow-code/marshmallow)
* **Parent SHA:** `3265c13945a9533f9a3ade8d47eb9b32412c4c27`
* **Ground-Truth Target:** `src/marshmallow/fields.py`
* **Outcome:** `NOT_RESOLVED` (`exec_representation_failure`) | **Duration:** 118.34s | **Attempts:** 2

#### Trajectory Breakdown
1. **Issue Understanding:** `UNDERSTOOD`  
   The model understood that `Enum` fields with `by_value=True` containing a `None` member should default `allow_none=True`.
2. **Target Identification:** `CORRECT`  
   Retrieval ranked `src/marshmallow/fields.py` at rank 10 due to high test-file density in the query match. However, the planner successfully filtered past the distractors and selected `src/marshmallow/fields.py`.
3. **Intended Solution:** `CORRECT`  
   The plan proposed checking `self.enum` members for `None` during `Enum.__init__` and setting `self.allow_none = True`.
4. **Edit Representation & Execution Failure:**  
   `search_content` failed to match in `src/marshmallow/fields.py` because the model provided an `__init__` parameter list from a newer version of marshmallow rather than the exact signature at parent commit `3265c139`.
5. **Verifier & Repair Loop Effectiveness:**  
   * `Repair engaged: Yes` (2 attempts).
   * Diagnostic: `search_content was not found in 'src/marshmallow/fields.py'`.
   * `Repair recovered task: No`.
6. **Counterfactual Architecture Assessment:** `YES`  
   If the exact signature match had been provided, the change would have executed cleanly.

---

## 4. Failure Mechanism & Attribution Matrix

| Case ID | Issue Understanding | Target File Identification | Conceptually Correct Solution | Primary Failure Mechanism | Primary Diagnosis | Secondary Diagnosis |
| :--- | :---: | :---: | :---: | :--- | :--- | :--- |
| **REAL-CLICK-02** | `UNDERSTOOD` | `CORRECT` | `CORRECT` | Inexact `search_content` substring anchor | `MODEL_EDIT_REPRESENTATION_FAILURE` | None |
| **REAL-CLICK-03** | `UNDERSTOOD` | `CORRECT` | `CORRECT` | Malformed Python indentation in source & test edits | `MODEL_CODE_SYNTHESIS_FAILURE` | `REPAIR_FAILURE` |
| **REAL-MARSHMALLOW-01** | `UNDERSTOOD` | `CORRECT` | `CORRECT` | Unexpected indent in multi-line replacement block | `MODEL_CODE_SYNTHESIS_FAILURE` | `REPAIR_FAILURE` |
| **REAL-MARSHMALLOW-02** | `UNDERSTOOD` | `CORRECT` | `CORRECT` | Hallucinated whitespace/comments in search anchor | `MODEL_EDIT_REPRESENTATION_FAILURE` | `REPAIR_FAILURE` |
| **REAL-MARSHMALLOW-03** | `UNDERSTOOD` | `CORRECT` | `PARTIALLY_CORRECT` | Test function symbol misplaced inside class scope | `MODEL_CODE_SYNTHESIS_FAILURE` | `REPAIR_FAILURE` |
| **REAL-MARSHMALLOW-04** | `UNDERSTOOD` | `CORRECT` | `CORRECT` | Version-mismatched `__init__` signature in search anchor | `MODEL_EDIT_REPRESENTATION_FAILURE` | `RETRIEVAL_FAILURE` (Rank 10) |

---

## 5. Architecture vs. Model Failure Attribution

### Were Any Failures Caused by Architectural / Infrastructure Bugs?
* **Executor / SafeFileEditor:** **No.** `SafeFileEditor` strictly adhered to its contract. It rejected search blocks that did not exist in the target file, preventing corruption, and atomically rolled back.
* **Verifier:** **No.** The AST parser and symbol validator accurately caught genuine Python syntax errors (`SyntaxError: unexpected indent`, `SyntaxError: invalid syntax`) and missing symbols.
* **Preflight / Security Boundaries:** **No.** Preflight checks operated without false rejections.
* **Evaluator Isolation:** **No.** Ground truth isolation was strictly maintained without data leakage.

### Model Limitations Identified
1. **Edit Anchor Reproduction Precision:** `nvidia/nemotron-3-ultra-550b-a55b:free` repeatedly struggled to copy literal multi-line strings verbatim from the retrieved context. Instead of copying exact character sequences, it reconstructed them from memory, introducing subtle whitespace, docstring, or comment discrepancies.
2. **Indentation Sensitivity in String Replacement:** When generating replacement blocks that integrate into indented classes or methods, the model frequently lost indentation context (e.g. producing 4 spaces when 8 were required, or mixing indentation levels).
3. **Repair Convergence:** While the repair loop successfully fed syntax and execution errors back to the model, the model's repair strategy lacked multi-step debugging capability. When informed of a syntax or anchor error, it tended to regenerate another variant with different syntax or anchor defects rather than diagnosing the exact line offset.

---

## 6. Repair-Loop Dynamics Analysis

| Metric | Value |
| :--- | :--- |
| **Cases Where Repair Loop Engaged** | **5 / 6 (83.3%)** (`REAL-CLICK-03`, `REAL-MARSHMALLOW-01`, `02`, `03`, `04`) |
| **Total Repair Iterations** | **6 repair attempts** across 5 cases |
| **Cases Successfully Recovered by Repair** | **0 / 5 (0.0%)** |
| **Actionability of Provided Diagnostics** | **100.0%** (Every diagnostic included exact error type, file path, line number, or missing substring) |
| **Model Diagnostic Comprehension** | **High** (Model reasoning acknowledged the reported syntax/substring error) |
| **Repair Strategy Effectiveness** | **Low** (Model lacked the synthesis precision to correct indentation or verbatim string matching) |

---

## 7. Cross-Case Quantitative Summary

```
Total Evaluated Cases:                           6
--------------------------------------------------
Issue Understanding:
  - UNDERSTOOD:                                  6 / 6 (100.0%)
  - PARTIALLY_UNDERSTOOD:                        0 / 6 (0.0%)
  - MISUNDERSTOOD:                               0 / 6 (0.0%)

Target File Identification:
  - CORRECT:                                     6 / 6 (100.0%)
  - INCORRECT:                                   0 / 6 (0.0%)

Intended Solution Concept:
  - CORRECT:                                     5 / 6 (83.3%)
  - PARTIALLY_CORRECT:                           1 / 6 (16.7%)
  - INCORRECT:                                   0 / 6 (0.0%)

Failure Root Causes:
  - MODEL_EDIT_REPRESENTATION_FAILURE:           3 / 6 (50.0%)
  - MODEL_CODE_SYNTHESIS_FAILURE:                3 / 6 (50.0%)
  - ARCHITECTURE / EXECUTOR / VERIFIER FAILURE:  0 / 6 (0.0%)

Counterfactual Capability of Frozen Pipeline:
  - Capable of accepting valid edit (YES):       6 / 6 (100.0%)
  - Architecture blocked valid edit (NO):        0 / 6 (0.0%)
```

---

## 8. Scientific Hypothesis Ranking

Based on the empirical evidence gathered from the six trajectories, the candidate hypotheses are ranked as follows:

1. **`H3: Exact edit representation is the primary bottleneck` (Rank 1 - Strongest Evidence)**  
   *Evidence:* In 3/6 cases (`REAL-CLICK-02`, `REAL-MARSHMALLOW-02`, `REAL-MARSHMALLOW-04`), the model formulated the conceptually correct patch and correctly identified the target file, but failed purely because it could not reproduce the exact `search_content` anchor from the retrieved file content.
2. **`H4: Code synthesis / syntax correctness is the primary bottleneck` (Rank 2 - Strong Evidence)**  
   *Evidence:* In 3/6 cases (`REAL-CLICK-03`, `REAL-MARSHMALLOW-01`, `REAL-MARSHMALLOW-03`), the edits were successfully matched and applied by the editor, but were rejected because the model generated invalid Python AST syntax (unexpected indents, malformed definitions).
3. **`H5: Repair-loop reasoning is a major contributing bottleneck` (Rank 3 - Moderate Evidence)**  
   *Evidence:* In 5/5 cases where repair engaged, the model received actionable diagnostic feedback with line numbers and file paths, but failed to converge on a valid syntactic or anchor correction within the budget ($N \le 3$).
4. **`H1: Retrieval is a minor contributing factor` (Rank 4 - Weak Evidence)**  
   *Evidence:* Target file Recall@5 was 83.3% and the model identified the correct target file in 100% of cases. Retrieval rank was 10 in only 1 case (`REAL-MARSHMALLOW-04`), where the planner still overcame the distraction.
5. **`H2: Planner / issue reasoning is NOT a primary bottleneck` (Rank 5 - Refuted by Data)**  
   *Evidence:* The model demonstrated clear comprehension of all 6 issues and formulated conceptually sound repair strategies in all cases.
6. **`H6: Architecture / executor / verifier is NOT the bottleneck` (Rank 6 - Refuted by Data)**  
   *Evidence:* The architectural safety systems functioned flawlessly: 100% plan validation accuracy, 100% accurate AST syntax detection, and 100% clean rollback without workspace corruption.

---

## 9. Scientific Limitations

1. **Single Open-Weights Model Sample:** This forensic analysis characterizes the specific capabilities and failure modes of `nvidia/nemotron-3-ultra-550b-a55b:free`. These findings cannot be generalized to proprietary frontier models (e.g. GPT-4o, Claude 3.5 Sonnet) without direct comparative evaluation.
2. **Search/Replace Edit Representation Sensitivity:** The substring replacement format requires exact character-level fidelity. Models optimized for generative text rather than structured diff generation exhibit higher error rates under strict substring matching.
3. **Sample Size:** The population is strictly limited to the 6 empirically verified ground-truth cases.

---

## 10. Recommended Next Experimental Questions (For Future Milestones)

The following scientific questions should guide future investigation:

1. **Model Capability Comparison (Milestone 15 / Paid Baseline):**  
   *When frontier models (such as GPT-4o or Claude 3.5 Sonnet) are evaluated on the identical 6-case frozen baseline, do they resolve the exact edit representation and indentation syntax bottlenecks observed in Nemotron 3 Ultra?*
2. **Edit Representation Expressiveness vs Precision:**  
   *Does an alternative edit representation (e.g. unified diffs with line-number fuzzy matching, or AST-node replacement) reduce `exec_representation_failure` rates for open-weights models without compromising execution safety?*
3. **Targeted Repair Prompt Formatting:**  
   *Can repair prompts provide concrete code excerpt windows surrounding the failed search anchor or syntax error to improve open-weights model repair convergence?*

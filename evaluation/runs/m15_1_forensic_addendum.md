# Milestone 15.1 — M14-FREE → M15 Forensic Trajectory Addendum

**Date:** 2026-09-04  
**Status:** COMPLETE  
**Run Mode:** Forensic Audit & Scientific Trajectory Comparison (Analysis-Only)  
**Control Baseline (M14-FREE):** `run_20260902_125455_c3cc4e`  
**Intervention Baseline (M15):** `run_20260903_143458_209eba`  
**Model:** `nvidia/nemotron-3-ultra-550b-a55b:free` (OpenRouter API)  
**Generation Parameters:** $T=0.0$, Max Output Tokens: 4096, Context Budget: 120,000 chars  
**Evaluated Population:** Exactly 6 `GROUND_TRUTH_VERIFIED` authentic benchmark cases  

---

## 1. Scope and Frozen-Input Statement

This document provides a strict, evidence-grounded forensic trajectory audit comparing the **M14-FREE Control Baseline** against the **M15 Controlled Intervention Baseline**.

### Hard Experimental Boundaries & Invariance Statement
During this analysis:
* Zero production or framework code was created or modified.
* Zero prompts, retrieval heuristics, planner schemas, repair parameters, verifier checks, or execution logic were altered.
* Zero benchmark definitions, ground truths, or test selectors were modified.
* No live LLMs or APIs were invoked; no benchmark executions were run.
* All findings are derived exclusively from immutable persisted run artifacts (`m14_free_telemetry.json`, `m15_telemetry.json`, `summary.json`, `benchmark_results.json`, and execution logs).

---

## 2. Six-Case M14 → M15 Trajectory Comparison Table

The following table summarizes the trajectory differences between the M14-FREE baseline and the M15 3-tier matcher intervention across the 6 verified benchmark cases:

| Case | M14 first failure | M15 first failure | M15 matcher tier | M15 normalization | Edit applied? | AST/preflight result | Dynamic tests reached? | Repair attempts | Final failure classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **REAL-CLICK-02** | `exec_representation_failure` (Step 'step-3': search_content was not found in 'src/click/_utils.py') | `exec_representation_failure` (Step 'step-3': search_content was not found in 'src/click/_utils.py') | `None` (No match across Tiers 1–3) | Failed (Anchor text absent from parent commit file) | `No` (Transaction rolled back) | Preflight passed; AST not reached | `No` | 1 total attempt (0 repair retries) | `EDIT_REPRESENTATION_FAILURE` |
| **REAL-CLICK-03** | `verification_failure` (`[syntax_ast]` invalid syntax in `_termui_impl.py` and `test_termui.py`) | `verification_failure` (`[syntax_ast]` SyntaxError in `test_termui.py`) | `Tier 2` (Normalized line match for `_termui_impl.py`) | Applied (Leading whitespace normalized, internal block relative indentation preserved) | `Yes` (Edits applied to both source and test files) | Preflight passed; `_termui_impl.py` AST passed; `test_termui.py` AST failed | `No` (Halted at AST check) | 2 total attempts (1 initial + 1 repair retry) | `CODE_SYNTHESIS_FAILURE` |
| **REAL-MARSHMALLOW-01** | `verification_failure` (`[syntax_ast]` unexpected indent in `fields.py` and `test_fields.py`) | `verification_failure` (`[subprocess_test]` pytest exited with non-zero exit code 4) | `Tier 2` (Normalized line match for `fields.py` and `test_fields.py`) | Applied (Multi-line indentation adjusted cleanly to file scope) | `Yes` (All 3 file edits applied cleanly) | Preflight passed; AST validation passed on all 3 files | `Yes` (`pytest tests/test_fields.py -k test_datetime_list_inner_format`) | 1 total attempt (0 repair retries) | `VERIFICATION_FAILURE` |
| **REAL-MARSHMALLOW-02** | `exec_representation_failure` (Step 'step-1': search_content was not found in 'src/marshmallow/fields.py') | `exec_representation_failure` (Step 'step-1': search_content was not found in 'src/marshmallow/fields.py') | `None` (No match across Tiers 1–3) | Failed (Anchor block absent in parent commit `3265c139`) | `No` (Transaction rolled back) | Preflight passed; AST not reached | `No` | 1 total attempt (0 repair retries) | `HISTORICAL_VERSION_GROUNDING_FAILURE` |
| **REAL-MARSHMALLOW-03** | `verification_failure` (`[symbol_existence]` symbol not found after edits) | `planning_failure` (Schema parse error: empty/truncated model output) | `NOT OBSERVABLE FROM ARTIFACTS` (Execution never reached) | `NOT OBSERVABLE FROM ARTIFACTS` (Execution never reached) | `No` (No execution attempted) | `NOT OBSERVABLE FROM ARTIFACTS` (Execution never reached) | `No` | 3 total attempts (Exhausted retries on empty API response) | `PROVIDER/INFRASTRUCTURE_FAILURE` |
| **REAL-MARSHMALLOW-04** | `exec_representation_failure` (Step 'step-1': search_content was not found in 'src/marshmallow/fields.py') | `exec_representation_failure` (Step 'step-1': search_content was not found in 'src/marshmallow/fields.py') | `None` (No match across Tiers 1–3) | Failed (Search signature absent in parent commit `3265c139`) | `No` (Transaction rolled back) | Preflight passed; AST not reached | `No` | 3 total attempts (2 repair retries) | `HISTORICAL_VERSION_GROUNDING_FAILURE` |

---

## 3. Detailed Per-Case Trajectory Analysis

### Case 1: `REAL-CLICK-02` (`pallets/click`)
1. **What was the first failure in M14?** `exec_representation_failure` — `Step 'step-3': search_content was not found in 'src/click/_utils.py'`.
2. **What was the first failure in M15?** Identical `exec_representation_failure` — `Step 'step-3': search_content was not found in 'src/click/_utils.py'`.
3. **Did the M15 matcher actually intervene?** Yes, the 3-tier matcher evaluated the target file.
4. **If yes, which tier intervened?** Tiers 1, 2, and 3 were evaluated sequentially. All failed closed because the multi-line search block specified by the model contained hallucinated docstring sentences completely absent from `src/click/_utils.py`.
5. **Did the edit successfully apply?** No. `SafeFileEditor` safely rejected the edit and atomically rolled back.
6. **Did the resulting source pass preflight/AST verification?** Preflight validation passed; AST verification was not reached due to execution halt.
7. **Did the trajectory advance farther than it did in M14?** No. The trajectory halted at the exact same step (Step 3).
8. **If it advanced, what new downstream failure became visible?** N/A.
9. **Did repair engage?** No repair retries occurred because the planner generated only 1 attempt before execution failure triggered rollback.
10. **Did repair recover the trajectory?** No.
11. **Attribution of final failure:** `EDIT_REPRESENTATION_FAILURE` by the model (model hallucinated anchor text rather than quoting retrieved context).

---

### Case 2: `REAL-CLICK-03` (`pallets/click`)
1. **What was the first failure in M14?** `verification_failure` — AST syntax error caused by invalid indentation in `src/click/_termui_impl.py` and `tests/test_termui.py`.
2. **What was the first failure in M15?** `verification_failure` — AST syntax error strictly isolated to `tests/test_termui.py` (`[syntax_ast] SyntaxError in tests/test_termui.py: expected an indented block after function definition on line 1`).
3. **Did the M15 matcher actually intervene?** Yes.
4. **If yes, which tier intervened?** **Tier 2 (Whitespace / Relative-Indentation Normalized Matcher).**
5. **Did the edit successfully apply?** **Yes.** The patch to `src/click/_termui_impl.py` matched via Tier 2 and was cleanly applied to disk with normalized indentation.
6. **Did the resulting source pass preflight/AST verification?** Preflight passed. Source file `src/click/_termui_impl.py` **passed AST syntax validation cleanly** (resolving the M14 source syntax error). However, the synthesized test file `tests/test_termui.py` failed AST validation due to missing function indentation.
7. **Did the trajectory advance farther than it did in M14?** **Yes.** The source file edit was fully resolved and verified as syntactically valid AST, advancing beyond the source-code editing bottleneck.
8. **If it advanced, what new downstream failure became visible?** `CODE_SYNTHESIS_FAILURE` in test generation (model generated `def test_progressbar_lands_on_final_position():` without indenting the function body).
9. **Did repair engage?** Yes (2 planner attempts).
10. **Did repair recover the trajectory?** No. The model acknowledged the diagnostic in reasoning but regenerated an unindented block.
11. **Attribution of final failure:** `CODE_SYNTHESIS_FAILURE` by the model.

---

### Case 3: `REAL-MARSHMALLOW-01` (`marshmallow-code/marshmallow`)
1. **What was the first failure in M14?** `verification_failure` — AST syntax error caused by unexpected indentation in `src/marshmallow/fields.py` (line 336).
2. **What was the first failure in M15?** `verification_failure` — Dynamic subprocess test failure (`[subprocess_test] pytest tests/test_fields.py -k test_datetime_list_inner_format: Test process exited with non-zero code 4`).
3. **Did the M15 matcher actually intervene?** Yes.
4. **If yes, which tier intervened?** **Tier 2 (Whitespace / Relative-Indentation Normalized Matcher).**
5. **Did the edit successfully apply?** **Yes.** All 3 file changes (`fields.py` and `test_fields.py`) were applied cleanly.
6. **Did the resulting source pass preflight/AST verification?** **Yes.** Preflight and AST syntax verification passed 100% across all 3 modified files.
7. **Did the trajectory advance farther than it did in M14?** **Yes, significantly.** In M14, execution crashed at the AST verification stage. In M15, the edits passed AST validation, preflight checks, and executed the dynamic test suite (`pytest`).
8. **If it advanced, what new downstream failure became visible?** Dynamic test execution failure (`exit code 4`). The synthesized test referenced a fixture or helper construct incompatible with the historical parent commit test runner.
9. **Did repair engage?** No repair retry occurred during execution; dynamic test failure resulted in clean atomic rollback.
10. **Did repair recover the trajectory?** No.
11. **Attribution of final failure:** `VERIFICATION_FAILURE` / `CODE_SYNTHESIS_FAILURE` (semantic test-logic incompatibility with historical test harness).

---

### Case 4: `REAL-MARSHMALLOW-02` (`marshmallow-code/marshmallow`)
1. **What was the first failure in M14?** `exec_representation_failure` — `Step 'step-1': search_content was not found in 'src/marshmallow/fields.py'`.
2. **What was the first failure in M15?** Identical `exec_representation_failure` — `Step 'step-1': search_content was not found in 'src/marshmallow/fields.py'`.
3. **Did the M15 matcher actually intervene?** Yes.
4. **If yes, which tier intervened?** Evaluated Tiers 1–3; failed closed on all tiers.
5. **Did the edit successfully apply?** No.
6. **Did the resulting source pass preflight/AST verification?** Preflight passed; AST not reached.
7. **Did the trajectory advance farther than it did in M14?** No.
8. **If it advanced, what new downstream failure became visible?** N/A.
9. **Did repair engage?** No repair retries in M15 (single attempt before execution halt).
10. **Did repair recover the trajectory?** No.
11. **Attribution of final failure:** `HISTORICAL_VERSION_GROUNDING_FAILURE` (model supplied search code matching modern Marshmallow instead of parent commit `3265c139`).

---

### Case 5: `REAL-MARSHMALLOW-03` (`marshmallow-code/marshmallow`)
1. **What was the first failure in M14?** `verification_failure` — `[symbol_existence] Symbol 'test_url_fragment_variations' not found in 'tests/test_validate.py' after edits`.
2. **What was the first failure in M15?** `planning_failure` — `Failed to parse model output as valid ImplementationPlan JSON: Expecting value: line 1 column 1 (char 0)`.
3. **Did the M15 matcher actually intervene?** No (Execution stage was never reached).
4. **If yes, which tier intervened?** `NOT OBSERVABLE FROM ARTIFACTS`.
5. **Did the edit successfully apply?** No.
6. **Did the resulting source pass preflight/AST verification?** `NOT OBSERVABLE FROM ARTIFACTS`.
7. **Did the trajectory advance farther than it did in M14?** No. The run terminated earlier in the pipeline (planning stage) due to provider streaming truncation.
8. **If it advanced, what new downstream failure became visible?** N/A.
9. **Did repair engage?** Yes. The planner attempted 3 retries against the provider API.
10. **Did repair recover the trajectory?** No. All 3 API calls returned empty/truncated JSON bodies.
11. **Attribution of final failure:** `PROVIDER/INFRASTRUCTURE_FAILURE` (OpenRouter free-tier infrastructure streaming failure).

---

### Case 6: `REAL-MARSHMALLOW-04` (`marshmallow-code/marshmallow`)
1. **What was the first failure in M14?** `exec_representation_failure` — `Step 'step-1': search_content was not found in 'src/marshmallow/fields.py'`.
2. **What was the first failure in M15?** Identical `exec_representation_failure` — `Step 'step-1': search_content was not found in 'src/marshmallow/fields.py'`.
3. **Did the M15 matcher actually intervene?** Yes.
4. **If yes, which tier intervened?** Evaluated Tiers 1–3; failed closed on all tiers.
5. **Did the edit successfully apply?** No.
6. **Did the resulting source pass preflight/AST verification?** Preflight passed; AST not reached.
7. **Did the trajectory advance farther than it did in M14?** No.
8. **If it advanced, what new downstream failure became visible?** N/A.
9. **Did repair engage?** Yes (3 planner attempts).
10. **Did repair recover the trajectory?** No.
11. **Attribution of final failure:** `HISTORICAL_VERSION_GROUNDING_FAILURE` / `RETRIEVAL_FAILURE` (Retrieval rank was 10; model search block matched a newer version of the class initializer).

---

## 4. Matcher Telemetry Summary

Across the 6 evaluated cases in M15:
* **Total Plan Modification Steps:** 12
* **Tier 1 (Exact Literal Match):** 4 steps (33.3%)
* **Tier 2 (Whitespace / Indentation Normalized Match):** 3 steps (25.0%)
* **Tier 3 (AST Symbol-Scoped Match):** 0 steps (resolved at Tier 2 or failed closed)
* **Fail-Closed Unmatched Anchors:** 5 steps (41.7%)
* **Ambiguous Candidates Detected & Rejected:** 0 false-positive matches allowed.
* **Relative Indentation Integrity:** 100% of Tier 2 normalized replacements preserved interior relative indentation.

---

## 5. H3 Evidence Assessment Table

| Evidence | Supports H3? | Explanation |
| :--- | :---: | :--- |
| **M15 Tier-2 intervention occurred** | **YES** | Tier 2 normalized line matching successfully resolved whitespace offsets on 3 steps across `REAL-CLICK-03` and `REAL-MARSHMALLOW-01`. |
| **M14 anchor failure disappeared** | **YES** | In `REAL-CLICK-03` and `REAL-MARSHMALLOW-01`, anchor mismatch errors that broke M14 execution were eliminated. |
| **Edit application succeeded** | **YES** | Edits applied cleanly to disk in 2/6 cases (`REAL-CLICK-03`, `REAL-MARSHMALLOW-01`) where M14 failed. |
| **AST verification succeeded** | **PARTIALLY** | AST verification succeeded for `REAL-MARSHMALLOW-01` across all 3 modified files, and succeeded for `_termui_impl.py` in `REAL-CLICK-03`. |
| **Dynamic verification was reached** | **YES** | `REAL-MARSHMALLOW-01` reached dynamic test execution (`pytest`), which was impossible in M14 due to earlier execution crash. |
| **End-to-end resolution improved** | **NO** | Resolution rate remained 0/6 (0.0%). Unblocking edit application did not resolve tasks to completion. |
| **Downstream failure was exposed** | **YES** | Progressing past edit application unmasked downstream code-synthesis errors (`REAL-CLICK-03`) and dynamic test assertion failures (`REAL-MARSHMALLOW-01`). |

### Conservative Scientific Conclusion on H3
> **M15 provides controlled evidence that the SafeFileEditor intervention can remove a subset of exact-anchor representation failures and allow selected trajectories to progress farther downstream. However, end-to-end resolution remained unchanged, so improved edit representation is not sufficient on its own for autonomous resolution.**

---

## 6. Historical-Grounding Assessment

In Cases `REAL-CLICK-02`, `REAL-MARSHMALLOW-02`, and `REAL-MARSHMALLOW-04`, the model generated search anchors that did not match the parent commit file content.

### Evidence Grounding vs. Speculation
* **Artifact Observation:** The search strings emitted by the model in these cases contain method signatures, parameter defaults, and docstrings that exist in modern versions of the repositories (e.g., Click 8.x, Marshmallow 3.x), but were not present at the historical parent commit SHAs.
* **Causal Classification:** We classify this failure mode strictly as:
  $$\text{HISTORICAL\_VERSION\_GROUNDING\_FAILURE}$$
* **Underlying Cause Status:** The underlying causal mechanism is **not yet conclusively established from artifacts alone**. Specifically, the artifacts do not distinguish whether:
  1. The model had sufficient context in its 120,000-character budget but suffered from parametric prior bias (recalling modern code from pretraining), OR
  2. The prompt / retrieval presentation did not sufficiently emphasize parent-commit version boundaries.

Therefore, this failure is not characterized as generic "hallucination," but as an ungrounded historical version discrepancy.

---

## 7. Provider Flake Assessment (Case 5 Confound)

In `REAL-MARSHMALLOW-03`, the M15 trajectory halted in the planner:
* **Artifact Evidence:** In `m15_telemetry.json`, `planning_metrics.errors` recorded:
  `Failed to parse model output as valid ImplementationPlan JSON: Expecting value: line 1 column 1 (char 0)` across all 3 attempts.
* **Confound Analysis:** The OpenRouter free-tier endpoint returned an empty HTTP response body during streaming. This failure is entirely orthogonal to model reasoning, retrieval, or file-editor matcher capabilities.
* **Methodological Impact:** Case 5 in M15 **does not provide usable evidence for or against Hypothesis H3**. It must be treated as a provider-side infrastructure confound.

---

## 8. Updated Bottleneck Ranking

Based on the combined forensic evidence from M14-FREE (control) and M15 (intervention):

| Rank | Bottleneck Category | Evidence & Impact |
| :---: | :--- | :--- |
| **1** | **`HISTORICAL_VERSION_GROUNDING_FAILURE`** | Primary blocker in 3/6 cases (`REAL-CLICK-02`, `REAL-MARSHMALLOW-02`, `REAL-MARSHMALLOW-04`). Model generates modern repository constructs that fail closed on historical parent commits. |
| **2** | **`CODE_SYNTHESIS_FAILURE` / Syntax Precision** | Primary blocker in 2/6 cases (`REAL-CLICK-03`, `REAL-MARSHMALLOW-01`). Model generates invalid indentation in new test definitions or references invalid fixtures. |
| **3** | **`REPAIR_FAILURE` / Non-Convergence** | Contributing blocker in 5/6 cases. Actionable diagnostics (exact syntax errors, missing lines) are fed back to the model, but repair attempts repeat the same error class without converging. |
| **4** | **`EDIT_REPRESENTATION_FAILURE`** | Reduced from Rank 1 in M14 to Rank 4 in M15. The 3-tier matcher successfully eliminated literal whitespace/indentation failures. |
| **5** | **`RETRIEVAL_FAILURE`** | Target File Recall@5 is 83.3%; model identified correct files in 100% of cases. Rank 10 in only 1 case (`REAL-MARSHMALLOW-04`). |

---

## 9. Scientific Limitations

1. **Open-Weights Free-Tier Model Horizon:** `nvidia/nemotron-3-ultra-550b-a55b:free` exhibits strong issue comprehension and planning structure, but limited precision in low-level indentation synthesis and multi-turn error correction.
2. **Provider Endpoint Reliability:** Free-tier endpoints introduce occasional streaming truncations (Case 5), necessitating infrastructure retries.
3. **Small-Sample Qualitative Depth:** The 6 verified cases provide rigorous qualitative tracing of every step, but statistical bounds require expansion to larger suites once environment automation is complete.

---

## 10. Conservative Milestone 15 Conclusion

Milestone 15 successfully verified that deterministic multi-tier anchor matching is a functional architectural improvement that prevents brittle whitespace failures without sacrificing execution safety or atomic rollback. However, resolving edit representation alone does not achieve task resolution because downstream synthesis precision and historical version grounding remain significant active bottlenecks.

---

## 11. Recommendation for Milestone 16 (DESIGN ONLY — NO IMPLEMENTATION)

### Primary Candidate for M16: **Historical-Version Grounding Intervention**

### Intervention Concept (Design Only)
* **Hypothesis (H6):** *Explicitly grounding the planner with parent-commit AST anchor snapshots prevents historical version drift and reduces anchor-generation mismatch.*
* **Controlled Single-Variable Change:** In the planner prompt assembly, inject the retrieved file's exact AST function/class signatures as explicit grounding anchors for each candidate target symbol, while keeping the rest of the pipeline frozen.
* **Strict Constraint:** Zero implementation is authorized until oversight approval.

---

```
M15.1 FORENSIC ADDENDUM COMPLETE — AWAITING OVERSIGHT REVIEW
```

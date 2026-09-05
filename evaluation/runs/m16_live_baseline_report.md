# Milestone 16 — Live Evaluation Baseline Report: Historical-Version Grounding

**Date:** 2026-09-04  
**Status:** COMPLETE — AWAITING OVERSIGHT REVIEW  
**Milestone:** M16  
**Run ID:** `run_20260904_092015_091ccd`  
**Run Directory:** `evaluation/runs/run_20260904_092015_091ccd`  
**Telemetry File:** `evaluation/runs/run_20260904_092015_091ccd/m16_telemetry.json`  
**Evaluation Population:** Exactly 6 `GROUND_TRUTH_VERIFIED` authentic benchmark cases  
**Model:** `nvidia/nemotron-3-ultra-550b-a55b:free`  
**Provider / Endpoint:** `openai-compatible` via OpenRouter (`https://openrouter.ai/api/v1`)  
**Generation Parameters:** $T=0.0$, Max Output Tokens: 4096, Context Budget: 120,000 characters  
**Intervention Under Test:** Additive, deterministic Historical-Version Grounding Header in `PlannerPromptBuilder.build_user_prompt()`  
**Control Baseline:** Milestone 15 (`run_20260903_143458_209eba`)  

---

## 1. Executive Summary & Core Results

The **Milestone 16 live benchmark evaluation** was executed against all 6 authentic `GROUND_TRUTH_VERIFIED` cases under strict experimental freeze. The only authorized difference between M15 and M16 was the addition of the deterministic Historical-Version Grounding Header in the planner user prompt.

### Summary of Observed M16 Metrics
* **Resolved Cases:** `0 / 6 (0.0%)`
* **Planning Validity Rate:** `6 / 6 (100.0%)` — In contrast to M15 where provider streaming truncation caused a planning failure on Case 5, all 6 cases generated valid, schema-conforming `ImplementationPlan` DAGs in M16.
* **Safe Transactional Rollback Success:** `6 / 6 (100.0%)` — SafeFileEditor atomic rollback operated flawlessly; zero unverified edits persisted to disk.
* **Retrieval Metrics (Strict Invariance Confirmed):** Mean Recall@3 = `66.7%`, Mean Recall@5 = `83.3%`, Mean MRR = `0.467`.
* **Failure Distribution:**
  * `verification_failure`: 3 cases (50.0%) (`REAL-CLICK-02`, `REAL-CLICK-03`, `REAL-MARSHMALLOW-01`)
  * `exec_representation_failure`: 3 cases (50.0%) (`REAL-MARSHMALLOW-02`, `REAL-MARSHMALLOW-03`, `REAL-MARSHMALLOW-04`)
* **Full Regression Suite:** `266 passed in 40.52s` (0 failures, 0 errors, 0 warnings).

---

## 2. Experimental Integrity & Non-Oracle Checks

Prior to and during the run, the following invariants were maintained and verified:
1. **Zero Reference Leakage:** The planner input context contained zero reference patch hunks, child commit SHAs, commit messages, or evaluator test selectors.
2. **Deterministic Mechanical Derivation:** The historical grounding header was populated solely from the authentic parent Git commit checkout.
3. **SafeFileEditor Invariance:** SafeFileEditor remained 100% frozen at the M15 3-tier matcher configuration.
4. **Evaluator Isolation:** Expected test commands and ground-truth definitions remained strictly evaluator-side.
5. **Baseline Artifact Immutability:** M14-FREE (`run_20260902_125455_c3cc4e`) and M15 (`run_20260903_143458_209eba`) remain unmodified.

---

## 3. Six-Case Live Results Overview

| Case ID | Repository | Parent Commit | Target File | Retrieval Rank | Planning Valid | Matcher Tier | Dynamic Tests Reached? | Result | Failure Category |
| :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **REAL-CLICK-02** | pallets/click | `3cbcf9b1` | `src/click/_utils.py` | 5 | Yes (3 att) | Tier 1/2 applied | No (AST fail) | Unresolved | `verification_failure` |
| **REAL-CLICK-03** | pallets/click | `8b44edff` | `src/click/_termui_impl.py` | 1 | Yes (3 att) | Tier 2 applied | No (AST fail) | Unresolved | `verification_failure` |
| **REAL-MARSHMALLOW-01** | marshmallow-code | `b40a0f4e` | `src/marshmallow/fields.py` | 2 | Yes (3 att) | Tier 2 applied | **Yes** (pytest) | Unresolved | `verification_failure` |
| **REAL-MARSHMALLOW-02** | marshmallow-code | `3265c139` | `src/marshmallow/fields.py` | 2 | Yes (1 att) | None (Unmatched) | No | Unresolved | `exec_representation_failure` |
| **REAL-MARSHMALLOW-03** | marshmallow-code | `3207be31` | `src/marshmallow/validate.py` | 2 | Yes (2 att) | None (Unmatched) | No | Unresolved | `exec_representation_failure` |
| **REAL-MARSHMALLOW-04** | marshmallow-code | `3265c139` | `src/marshmallow/fields.py` | 10 | Yes (1 att) | None (Unmatched) | No | Unresolved | `exec_representation_failure` |

---

## 4. M15 → M16 Paired Comparison

### Aggregate Metrics Comparison:
| Metric | M15 (Control) | M16 (Intervention) | Delta ($\Delta$) | Empirical Interpretation |
| :--- | --: | --: | --: | :--- |
| **Resolved Cases** | 0 / 6 | 0 / 6 | 0 | Primary endpoint unchanged |
| **Resolution Rate** | 0.0% | 0.0% | 0.0% | No task resolution |
| **Planning Validity Rate** | 5 / 6 (83.3%) | 6 / 6 (100.0%) | +16.7% | Case 5 unblocked at planning stage |
| **Target Recall@3** | 66.7% | 66.7% | 0.0% | Retrieval unchanged (frozen) |
| **Target Recall@5** | 83.3% | 83.3% | 0.0% | Retrieval unchanged (frozen) |
| **Mean MRR** | 0.467 | 0.467 | 0.000 | Retrieval unchanged (frozen) |
| **Exec Representation Failures** | 3 (50.0%) | 3 (50.0%) | 0 | Absolute count unchanged |
| **Verification Failures** | 2 (33.3%) | 3 (50.0%) | +1 | Case 1 migrated into verification |
| **Planning Failures** | 1 (16.7%) | 0 (0.0%) | -1 | No provider/schema dropouts |
| **Safe Rollback Rate** | 100.0% | 100.0% | 0.0% | Safety guarantees preserved |

### Case-by-Case Trajectory Comparison:
| Case ID | M15 First Failure | M16 First Failure | Grounding Effect | Trajectory Progression | Final Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **REAL-CLICK-02** | `exec_representation_failure` (Step-3 search_content not found) | `verification_failure` (`SyntaxError` in `tests/test_utils/test_sentinel.py`) | Model anchored in `_utils.py`, applied 2 changes, but emitted malformed test file | **Advanced past execution into AST verification** | Unresolved (`verification_failure`) |
| **REAL-CLICK-03** | `verification_failure` (`SyntaxError` in `test_termui.py`) | `verification_failure` (`SyntaxError` in `_termui_impl.py:156`) | Model repeated invalid indentation in `_termui_impl.py` | Same phase (AST verification failure) | Unresolved (`verification_failure`) |
| **REAL-MARSHMALLOW-01** | `verification_failure` (Pytest exit code 4) | `verification_failure` (Pytest exit code 4) | 4 changes applied cleanly via Tier 2; dynamic tests executed | Reached dynamic test execution stage | Unresolved (`verification_failure`) |
| **REAL-MARSHMALLOW-02** | `exec_representation_failure` (Step-1 search_content not found) | `exec_representation_failure` (Step-1 search_content not found) | Ineffective; search anchor still assumed modern signatures | No change (halted at Step 1) | Unresolved (`exec_representation_failure`) |
| **REAL-MARSHMALLOW-03** | `planning_failure` (Provider JSON truncation) | `exec_representation_failure` (Step-1 search_content not found) | Successfully generated valid plan, but search anchor mismatched historical `validate.py` | **Advanced from planning into execution** | Unresolved (`exec_representation_failure`) |
| **REAL-MARSHMALLOW-04** | `exec_representation_failure` (Step-1 search_content not found) | `exec_representation_failure` (Step-1 search_content not found) | Ineffective; model still targeted modern `Enum` initializer | No change (halted at Step 1) | Unresolved (`exec_representation_failure`) |

---

## 5. Detailed Forensic Trajectory Analysis

### Case 1: `REAL-CLICK-02` (pallets/click)
* **M15 Result:** `exec_representation_failure` (failed at step-3 in `_utils.py`).
* **M16 Result:** `verification_failure`.
* **Trajectory Dynamics:** In M16, with historical repository grounding, the model successfully aligned its search anchor in `src/click/_utils.py` and applied both planned modifications (2 file changes applied). However, when adding the new unit test file `tests/test_utils/test_sentinel.py`, the model synthesized a file starting with invalid Python syntax on line 1. The AST verifier immediately caught this defect and triggered safe rollback.
* **Attribution:** **Trajectory advanced farther.** Edit representation bottleneck was unblocked, unmasking `CODE_SYNTHESIS_FAILURE` downstream.

### Case 2: `REAL-CLICK-03` (pallets/click)
* **M15 Result:** `verification_failure` (test file AST syntax error).
* **M16 Result:** `verification_failure` (source file AST syntax error).
* **Trajectory Dynamics:** The model attempted 3 repair iterations. While Tier 2 matched the anchor in `src/click/_termui_impl.py`, the model generated an unindented replacement block at line 156. The AST verifier caught `SyntaxError: invalid syntax` and safely rolled back.
* **Attribution:** `CODE_SYNTHESIS_FAILURE`. The historical grounding header did not prevent indentation synthesis errors.

### Case 3: `REAL-MARSHMALLOW-01` (marshmallow-code/marshmallow)
* **M15 Result:** `verification_failure` (subprocess pytest exit code 4).
* **M16 Result:** `verification_failure` (subprocess pytest exit code 4).
* **Trajectory Dynamics:** The model generated 4 changes across `src/marshmallow/fields.py` and test modules. All edits applied cleanly via Tier 2 normalized matching and passed AST verification across all files. The execution engine progressed to dynamic testing: `pytest tests/test_fields.py -k test_datetime_list_inner_format`. The pytest process terminated with exit code 4 (test invocation / selector mismatch in historical marshmallow test suite).
* **Attribution:** `VERIFICATION_FAILURE` (semantic test harness incompatibility).

### Case 4: `REAL-MARSHMALLOW-02` (marshmallow-code/marshmallow)
* **M15 Result:** `exec_representation_failure` (step-1 search_content not found).
* **M16 Result:** `exec_representation_failure` (step-1 search_content not found).
* **Trajectory Dynamics:** The model generated a `search_content` block targeting `TimeDelta` deserialization in `src/marshmallow/fields.py`. The anchor included parameter formatting and comments that were absent at commit `3265c139`.
* **Attribution:** `HISTORICAL_VERSION_GROUNDING_FAILURE`. Factual grounding alone was insufficient to override the model's parametric training memory.

### Case 5: `REAL-MARSHMALLOW-03` (marshmallow-code/marshmallow)
* **M15 Result:** `planning_failure` (OpenRouter API truncation error).
* **M16 Result:** `exec_representation_failure`.
* **Trajectory Dynamics:** In M16, the provider endpoint functioned properly and returned valid plans across 2 attempts (100% planning validity). However, the planned edit in `src/marshmallow/validate.py` specified a `search_content` string that did not exist in the parent commit file.
* **Attribution:** In M15, this case was confounded by provider dropouts. In M16, the case advanced cleanly into execution where an authentic `EDIT_REPRESENTATION_FAILURE` / `HISTORICAL_VERSION_GROUNDING_FAILURE` occurred.

### Case 6: `REAL-MARSHMALLOW-04` (marshmallow-code/marshmallow)
* **M15 Result:** `exec_representation_failure`.
* **M16 Result:** `exec_representation_failure`.
* **Trajectory Dynamics:** Retrieval ranked `src/marshmallow/fields.py` at rank 10. The planner correctly targeted `fields.py`, but its `search_content` quoted a modern signature of `Enum.__init__` rather than the historical parent commit signature.
* **Attribution:** `HISTORICAL_VERSION_GROUNDING_FAILURE`.

---

## 6. Scientific Hypothesis Assessment (H4)

### Evaluated Hypothesis
> **H4:** *Historical-version grounding is a significant bottleneck in autonomous issue resolution because the model can rely on knowledge of modern repository APIs/fixtures that are absent from the historical parent commit being repaired.*

### Empirical Findings:
1. **End-to-End Resolution:** Remained **0 / 6 (0.0%)**.
2. **Trajectory Advancement:** In **2 of the 6 cases**, trajectories advanced farther down the pipeline:
   * `REAL-CLICK-02` advanced from `exec_representation_failure` to `verification_failure` (edits successfully applied to `src/click/_utils.py`).
   * `REAL-MARSHMALLOW-03` advanced from `planning_failure` to `exec_representation_failure` (generating a valid 2-attempt plan).
3. **Persistence of Version Drift:** In Cases 4 and 6, the model continued to emit search anchors reflecting modern repository signatures despite the presence of the checked-out parent commit metadata header.

### Defensible Scientific Conclusion:
> **M16 provides evidence that factual historical-version grounding context reduces upstream failures and allows select trajectories to advance into execution and verification (as observed in `REAL-CLICK-02`). However, end-to-end task resolution remained 0/6 (0.0%), demonstrating that passive factual grounding headers are insufficient on their own to overcome parametric training priors or resolve downstream code-synthesis bottlenecks.**

---

## 7. Provider & Infrastructure Telemetry

* **Total API Calls Executed:** 13 generation/repair calls across 6 cases.
* **Provider Errors / Truncations:** 0 (OpenRouter free-tier streaming operated without dropouts).
* **Mean Run Latency per Case:** 127.6 seconds.
* **Transactional Rollback Reliability:** 6 / 6 rollbacks succeeded with zero git tree dirt.

---

## 8. Post-Run Regression & Workspace Validation

1. **Unit & Regression Suite:** `python -m pytest tests/ -q` $\to$ **266 passed in 40.52s**.
2. **Production Code Modifications:** Only the single authorized modification in `src/autonomous_engineer/agents/prompt_builder.py`.
3. **Workspace Isolation:** Clean working tree confirmed.
4. **Historical Baseline Artifacts:** M14-FREE and M15 artifacts preserved intact.

---

```
M16 LIVE EVALUATION COMPLETE — AWAITING OVERSIGHT REVIEW
```

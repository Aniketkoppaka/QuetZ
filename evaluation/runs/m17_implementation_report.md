# Milestone 17 — Implementation & Validation Report: Pre-Execution AST Syntax Validation

**Date:** 2026-09-04  
**Status:** IMPLEMENTATION COMPLETE — AWAITING OVERSIGHT REVIEW  
**Milestone:** M17 (Implementation Phase)  
**Primary Reference:** `evaluation/runs/m17_design_revision.md`  
**Hypothesis Under Test:** **H5** (Code-Synthesis & Pre-Execution Syntactic Precision Bottleneck)  
**Target Component:** `src/autonomous_engineer/agents/validator.py` (`PlanValidator`)  
**Control Baseline:** Milestone 16 (`run_20260904_092015_091ccd`)  
**Benchmark Suite Status:** FROZEN — ZERO BENCHMARK RUNS, ZERO LIVE LLM CALLS  

---

## 1. Executive Summary

Milestone 17 implements the single approved intervention established in `evaluation/runs/m17_design_revision.md`:
> **Deterministic AST syntax validation of hypothetical post-edit Python files before real execution.**

In M16.1, forensic audits revealed that in 100% of advanced trajectories (`REAL-CLICK-02`, `REAL-CLICK-03`, `REAL-MARSHMALLOW-01`), whenever file edits applied cleanly to disk, execution terminated catastrophically at the post-execution AST verification phase due to model-synthesized syntax errors (`SyntaxError: invalid syntax` on merged imports or unindented replacement blocks).

This intervention closes that causal gap by pre-validating candidate Python files purely in memory during plan validation. When a model proposes code modifications or file additions that produce invalid Python syntax, `PlanValidator` intercepts the syntax violation and routes exact line, column, and parser diagnostics back into the existing planner repair loop ($N \le 3$) *before* execution or atomic rollback occurs.

All 10 focused M17 unit tests passed, and all 276 repository regression tests passed with zero failures.

---

## 2. Exact Intervention Implemented

The intervention was added directly into `src/autonomous_engineer/agents/validator.py`:

1. **In-Memory Sequential Simulation of Proposed Edits:**
   * Group all plan steps targeting `.py` files by relative file path.
   * For each target file, simulate the cumulative edit state purely in memory:
     $$\text{state}_0 \xrightarrow{\text{step 1}} \text{state}_1 \xrightarrow{\text{step 2}} \dots \xrightarrow{\text{step } k} \text{state}_k$$
2. **Reuse of Frozen M15 Anchor Matching:**
   * For modification steps (`MODIFY_SYMBOL`, `REFACTOR_FILE`, etc.), `PlanValidator` calls the existing `_resolve_edit()` from `autonomous_engineer.execution.file_editor`.
   * The base file content is loaded from `planner_input.repository.workspace_path` without mutating any file on disk.
3. **AST Syntax Validation:**
   * For `ADD_FILE` and `ADD_TEST`: parses `ast.parse(step.content, filename=rel_path)`.
   * For modifications: parses `ast.parse(simulated_text, filename=rel_path)` on the complete hypothetical post-edit file.
4. **Deterministic Syntax Diagnostics:**
   * If `ast.parse()` raises `SyntaxError as e`, a `PlanValidationError` is recorded with:
     - `field = "replace_content"` (or `"content"`)
     - `error_type = "syntax_error"`
     - `message = "Syntactically invalid Python generated for {rel_path}: line {e.lineno}, column {e.offset}: {e.msg}. Text: {e.text.strip()}"`
5. **Preserving M16 Anchor Failure Semantics:**
   * If `_resolve_edit()` raises an anchor mismatch or ambiguity exception (`ValueError`), `PlanValidator` deliberately ignores it during syntax validation.
   * This guarantees that anchor mismatch behavior remains identical to M16, isolating strictly **Code-Synthesis / Syntax Precision (H5)**.

---

## 3. Modified Files

| File | Type | Lines Changed | Description of Changes |
| :--- | :--- | :--- | :--- |
| `src/autonomous_engineer/agents/validator.py` | Production | +96 lines | Imported `ast`, `Path`, and `_resolve_edit`. Added step 6 (`_validate_python_syntax`) in `validate()`. Implemented `_validate_python_syntax()` private helper. |
| `tests/unit/test_planning.py` | Test | +336 lines | Added `TestM17PreExecutionSyntaxValidation` containing 10 mandatory unit tests for M17. |

**Total Production Files Modified:** Exactly 1 (`validator.py`).  
**Total Test Files Modified:** Exactly 1 (`test_planning.py`).  
**Other Files Modified:** 0.

---

## 4. Candidate-File Construction Mechanism

* **Workspace Access:** `planner_input.repository.workspace_path` provides read-only access to authentic checked-out repository source files.
* **In-Memory Buffering:** The validator reads `target_file_path.read_text(encoding="utf-8", errors="replace")` into a local Python string variable (`simulated_text`).
* **Zero Disk Mutation:** `open()`, `.write()`, `.write_text()`, and `os.replace()` are never called by `PlanValidator`.
* **Sequential Multi-Edit Composition:** Multiple steps on the same file sequentially transform `simulated_text` in memory, ensuring that downstream steps are evaluated in the context of preceding edits within the plan.

---

## 5. AST Validation Semantics: Why Fragment Parsing Was Rejected

As established in the revised design:
* Parsing `step.replace_content` in isolation causes severe false rejections on valid code snippets (e.g., `elif`, `else`, `except`, `finally`, `return`, `yield`, or indented blocks), because they cannot form legal standalone Python modules.
* Parsing the **hypothetical resulting file** in full ensures:
  1. Valid indented replacement fragments succeed when integrated into valid surrounding code.
  2. Replacements that appear valid in isolation but introduce mismatched delimiters, unclosed brackets, or invalid indentation relative to surrounding code are accurately rejected.
  3. 100% semantic fidelity to what `ExecutionVerifier.verify_static()` will encounter post-execution.

---

## 6. SafeFileEditor Immutability Confirmation

`SafeFileEditor` in `src/autonomous_engineer/execution/file_editor.py` is **STRICTLY FROZEN**:
* `SafeFileEditor` class: 0 lines changed.
* `_resolve_edit()`: 0 lines changed.
* `_find_normalized_line_matches()`: 0 lines changed.
* `_find_symbol_line_range()`: 0 lines changed.
* `_apply_reindented_replacement()`: 0 lines changed.
* Matcher tiers (Tier 1, 2, 3) and ambiguity guards: 0 lines changed.
* Atomic disk snapshotting and transactional rollback: 0 lines changed.

`PlanValidator` directly imports and reuses the existing `_resolve_edit` function without modifying or duplicating its logic.

---

## 7. Anchor-Failure Isolation

To prevent confounding `MODEL_EDIT_REPRESENTATION_FAILURE` with `MODEL_CODE_SYNTHESIS_FAILURE`:
* If `_resolve_edit()` fails to anchor `search_content` (due to nonexistent anchor or ambiguous match), `_validate_python_syntax()` catches the exception and passes silently.
* The plan is not rejected during validation for anchor mismatch.
* Instead, anchor resolution continues to be handled exclusively at execution time by `SafeFileEditor`, exactly as in M16.
* This ensures that only genuine syntactic failures cause plan rejection at validation time.

---

## 8. Repair-Loop Interaction

* When `_validate_python_syntax()` records a `PlanValidationError(error_type="syntax_error")`, `val_result.is_valid` becomes `False`.
* In `LLMPlanner.plan_with_audit()`, the existing frozen repair loop is invoked:
  - The frozen `PlannerPromptBuilder.build_repair_prompt()` formats the syntax error into the user repair prompt:
    ```
    === VALIDATION ERRORS DETECTED ===
    1. [syntax_error] [Step: step-1] (Field: replace_content): Syntactically invalid Python generated for src/click/_termui_impl.py: line 156, column 12: invalid syntax. Text: def getchar(echo=False):
    ```
  - The planner retries up to the frozen limit of $N \le 3$.
  - No new repair prompts, agents, heuristics, or budget increases were introduced.

---

## 9. Telemetry Surface

The existing telemetry capture points in `LLMPlanner` (`PlanningAuditRecord.errors`), `PlanExecutionResult`, `EditMatchTelemetry`, and `BenchmarkRunResult` already record:
* `validation_result.errors`: captures `[syntax_error]` error strings, target files, line numbers, and column offsets.
* `total_attempts`: captures how many repair iterations were required.
* `execution_metrics`: captures whether execution was attempted, changes applied, verifications executed, and rollback status.
* `failure_category`: classifies final terminal failure into mutually exclusive categories.

Zero ground-truth or reference patch data is exposed to the model or telemetry.

---

## 10. Leakage and Anti-Oracle Audit

* **Reference Patches:** 0 access. `PlanValidator` has no reference to ground-truth patch files.
* **Child Commit SHAs:** 0 access.
* **Evaluator Ground Truth:** 0 access. `expected_affected_files` and `expected_test_command` remain strictly in `RealBenchmarkIssue` on the evaluation side.
* **Hidden Test Selectors:** 0 access.
* **Autonomous Repair / Code Rewriting:** 0 oracle repair. The syntax gate strictly validates and reports errors; it never rewrites, modifies, or fixes model code.

---

## 11. Unit Test Results

The 10 focused M17 tests in `tests/unit/test_planning.py::TestM17PreExecutionSyntaxValidation` were executed:
```
tests/unit/test_planning.py::TestM17PreExecutionSyntaxValidation::test_1_complete_valid_add_file_succeeds PASSED
tests/unit/test_planning.py::TestM17PreExecutionSyntaxValidation::test_2_complete_invalid_add_file_rejected PASSED
tests/unit/test_planning.py::TestM17PreExecutionSyntaxValidation::test_3_valid_indented_replacement_fragment_succeeds PASSED
tests/unit/test_planning.py::TestM17PreExecutionSyntaxValidation::test_4_fragment_valid_in_isolation_but_invalid_in_context_rejected PASSED
tests/unit/test_planning.py::TestM17PreExecutionSyntaxValidation::test_5_multiple_sequential_edits_simulated_correctly PASSED
tests/unit/test_planning.py::TestM17PreExecutionSyntaxValidation::test_6_anchor_mismatch_remains_m16_behavior_not_syntax_error PASSED
tests/unit/test_planning.py::TestM17PreExecutionSyntaxValidation::test_7_ambiguous_anchor_remains_unchanged PASSED
tests/unit/test_planning.py::TestM17PreExecutionSyntaxValidation::test_8_no_real_workspace_mutation_during_syntax_validation PASSED
tests/unit/test_planning.py::TestM17PreExecutionSyntaxValidation::test_9_syntax_diagnostics_contain_line_and_column_information PASSED
tests/unit/test_planning.py::TestM17PreExecutionSyntaxValidation::test_10_syntax_failure_enters_existing_repair_loop_without_changing_budget PASSED

====================== 10 passed in 0.58s ======================
```

---

## 12. Full Regression Results

The complete test suite across all subsystems was executed:
```
============================= test session starts =============================
platform win32 -- Python 3.11.5, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\anike\Downloads\autonomous-software-engineer
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.11.0, langsmith-0.4.59, asyncio-0.23.6, cov-7.1.0
asyncio: mode=Mode.STRICT
collected 276 items

tests\unit\test_authentic_benchmark.py .........                         [  3%]
tests\unit\test_domain_models.py ....................................... [ 17%]
.............                                                            [ 22%]
tests\unit\test_evaluation_harness.py .........                          [ 25%]
tests\unit\test_execution.py ......................                      [ 33%]
tests\unit\test_ground_truth_environment.py ......                       [ 35%]
tests\unit\test_ground_truth_validation.py .........                     [ 38%]
tests\unit\test_live_evaluation.py .........                             [ 42%]
tests\unit\test_llm_planner.py ......................                    [ 50%]
tests\unit\test_package_import.py ................                       [ 55%]
tests\unit\test_planning.py ........................                     [ 64%]
tests\unit\test_repository_acquisition.py ......................         [ 72%]
tests\unit\test_repository_analysis.py ......................            [ 80%]
tests\unit\test_retrieval.py .............                               [ 85%]
tests\unit\test_state_machine.py ....................................... [ 99%]
..                                                                       [100%]

============================ 276 passed in 53.97s =============================
```
* **Total Tests Collected:** 276
* **Total Tests Passed:** 276 (100%)
* **Failures / Errors:** 0
* **Regressions:** 0

---

## 13. Frozen-Component Audit

| Component | Status | Verification Check |
| :--- | :--- | :--- |
| **Model** | FROZEN | `nvidia/nemotron-3-ultra-550b-a55b:free` |
| **Provider** | FROZEN | OpenRouter |
| **Generation Parameters** | FROZEN | $T=0.0$, Max Tokens: 4096, Context: 120,000 chars |
| **Benchmark Suite** | FROZEN | Exactly 6 `GROUND_TRUTH_VERIFIED` cases (`CLICK-02`, `03`, `MARSHMALLOW-01`, `02`, `03`, `04`) |
| **Parent Commits / Test Selectors** | FROZEN | 0 changes |
| **Retrieval Architecture** | FROZEN | BM25 + AST Ranking (Top-5, 0.5/0.5 weights) |
| **Historical Grounding** | FROZEN | Deterministic parent metadata header in `PlannerPromptBuilder` |
| **SafeFileEditor** | FROZEN | 3-tier matcher, snapshotting, and rollback intact |
| **Repair Policy** | FROZEN | Attempt budget $N \le 3$, existing prompt builder |
| **Post-Execution Verifier** | FROZEN | Static AST, Symbol Existence, Subprocess Pytest runner |
| **Rollback Behavior** | FROZEN | Transactional rollback on verification failure |

---

## 14. Scientific Validity Assessment

By validating the hypothetical post-edit file rather than isolated fragments, M17 eliminates the construct confound:
1. Valid fragments (like indented method returns or `elif` branches) are evaluated within their complete AST scope, preventing false rejections.
2. Syntactically broken modifications (such as merged imports or unindented statement blocks) are caught immediately and surfaced to the model with precise line/column feedback.
3. Anchor mismatch handling is left untouched, guaranteeing that M17 measures only the causal effect of **Code-Synthesis / Syntax Precision (H5)**.

---

## 15. Remaining Risks & Edge Cases

* **Parametric Model Capacity:** The model (`nvidia/nemotron-3-ultra-550b-a55b:free`) may be unable to fix syntax errors even when provided exact line/column diagnostics within the 3 repair attempts. If all 3 attempts fail, M17 will cleanly establish this model capacity boundary.
* **Semantic Patch Errors:** If the syntax gate succeeds and allows trajectories to reach dynamic test execution, patches may still fail unit tests if the repair logic is semantically incorrect.

---

## 16. Benchmark & Live Execution Status

* **Live Benchmark Executed:** **NO.**
* **Live LLM / API Calls Made:** **0.**
* **OpenRouter Quota Consumed:** **0 tokens.**
* **Historical Artifacts (`m14`, `m15`, `m16`, `m17_design*.md`):** Strictly untouched and immutable.

```
M17 IMPLEMENTATION COMPLETE — AWAITING OVERSIGHT REVIEW
```

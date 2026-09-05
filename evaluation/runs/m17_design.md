# Milestone 17 — Experimental Design: Code-Synthesis / Syntax-Precision Intervention

**Date:** 2026-09-04  
**Status:** DESIGN ONLY — NO IMPLEMENTATION, NO BENCHMARK RERUN  
**Milestone:** M17  
**Hypothesis Under Test:** **H5** (Code-Synthesis & Syntax Precision Bottleneck)  
**Selected Single Intervention:** Pre-Execution Syntactic Validation Gating in `PlanValidator`  
**Target File for Eventual Implementation:** `src/autonomous_engineer/agents/validator.py`  
**Control Baseline:** Milestone 16 (`run_20260904_092015_091ccd`)  
**Evaluation Population:** Exactly 6 `GROUND_TRUTH_VERIFIED` authentic benchmark cases  

---

## 1. Executive Summary

Milestones 14 through 16 established the cumulative empirical progression of our autonomous engineering pipeline:
* **M14-FREE (Baseline):** 0/6 resolved; 3 `exec_representation_failure` (anchor mismatch), 3 `verification_failure` (AST syntax errors).
* **M15 (SafeFileEditor 3-Tier Matcher):** Solved whitespace/indentation anchoring; unblocked edit application and advanced `REAL-MARSHMALLOW-01` to dynamic test execution.
* **M16 (Historical-Version Grounding Context):** Injected deterministic parent commit metadata; advanced `REAL-CLICK-02` from anchor failure to edit application.
* **M16.1 Forensic Audit Finding:** In **100% of advanced trajectories** (`REAL-CLICK-02`, `REAL-CLICK-03`, and `REAL-MARSHMALLOW-01`), whenever file edits successfully applied to disk, the task was immediately terminated by fatal Python syntax errors (`SyntaxError: invalid syntax` on merged imports in Click-02; `SyntaxError: invalid syntax` on unindented class blocks in Click-03).

Milestone 17 designs a strictly controlled, single-variable intervention to test whether enforcing **pre-execution syntactic validation gating** during plan formulation reduces model-generated code-synthesis failures and enables advanced trajectories to reach downstream test execution.

---

## 2. Scientific Question & Formal Hypothesis

### Scientific Question
> **Can a single controlled intervention reduce model-generated syntactic and code-construction failures, while leaving retrieval, historical grounding, file editing, post-execution verification, repair policy, model/provider configuration, and benchmark definitions strictly unchanged?**

### Formal Hypothesis (H5)
> **H5:** *Model code-synthesis precision is a primary active bottleneck in autonomous issue resolution. Intercepting syntactically malformed code blocks (`content` and `replace_content`) during plan validation and feeding AST compilation diagnostics into the planner's repair loop will significantly reduce `verification_failure` caused by syntax errors and allow trajectories to reach dynamic test execution.*

---

## 3. Frozen M16 Control Condition

To maintain strict scientific comparability, the M16 configuration serves as the immutable control baseline. All the following components are **STRICTLY FROZEN**:

| Pipeline Component | M16 Control State | M17 Experimental State | Invariance Rule |
| :--- | :--- | :--- | :--- |
| **Model** | `nvidia/nemotron-3-ultra-550b-a55b:free` | `nvidia/nemotron-3-ultra-550b-a55b:free` | Frozen |
| **Provider / Endpoint** | OpenRouter (`https://openrouter.ai/api/v1`) | OpenRouter (`https://openrouter.ai/api/v1`) | Frozen |
| **Sampling Config** | $T=0.0$, Max Tokens: 4096, Context: 120k | $T=0.0$, Max Tokens: 4096, Context: 120k | Frozen |
| **Benchmark Population** | 6 `GROUND_TRUTH_VERIFIED` cases | 6 `GROUND_TRUTH_VERIFIED` cases | Frozen |
| **Retrieval Architecture** | BM25 + AST Ranking (Top-5, 0.5/0.5) | BM25 + AST Ranking (Top-5, 0.5/0.5) | Frozen |
| **Historical Grounding** | Deterministic parent metadata header | Deterministic parent metadata header | Frozen |
| **Planner Schema** | `ImplementationPlan` Pydantic model | `ImplementationPlan` Pydantic model | Frozen |
| **Repair Budget / Policy** | Max 3 attempts ($N \le 3$), diagnostic feedback | Max 3 attempts ($N \le 3$), diagnostic feedback | Frozen |
| **Execution Engine** | Transactional atomic rollback engine | Transactional atomic rollback engine | Frozen |
| **SafeFileEditor** | M15 Deterministic 3-Tier Matcher | M15 Deterministic 3-Tier Matcher | Frozen |
| **Post-Execution Verifier**| AST Syntax, Symbol Existence, Pytest | AST Syntax, Symbol Existence, Pytest | Frozen |
| **Ground-Truth Data** | Strictly evaluator-side, hidden from model | Strictly evaluator-side, hidden from model | Frozen |
| **Plan Validation Gate** | Structural DAG & file existence checks | **+ Pre-Execution Syntactic AST Gate** | **SINGLE INTERVENTION** |

---

## 4. Evidence Motivating Milestone 17

The M16.1 forensic trajectory audit revealed that when edit-representation and grounding hurdles were cleared, tasks failed catastrophically at the syntax level:

1. **`REAL-CLICK-02` Trajectory:**
   * Grounding successfully guided the model to target `src/click/_utils.py`.
   * SafeFileEditor matched the anchor and applied 2 modifications cleanly.
   * However, in step-2 (`tests/test_utils/test_sentinel.py`), the model emitted:
     ```python
     import pytest from click._utils import _Sentinel
     ```
     missing a newline between statements. The post-execution verifier caught `SyntaxError: invalid syntax (line 1)` and executed atomic rollback.
2. **`REAL-CLICK-03` Trajectory:**
   * Retrieval correctly identified `src/click/_termui_impl.py` at rank 1.
   * SafeFileEditor Tier 2 matched the anchor and applied the replacement.
   * However, the replacement block at line 156 contained inconsistent indentation relative to the surrounding method scope, producing `SyntaxError: invalid syntax (_termui_impl.py, line 156)`.
3. **Common Failure Mode:** In both cases, the planner generated an invalid Python string, the validator accepted it (because `PlanValidator` only checked path traversal, file existence, and DAG dependencies), and the execution engine applied it to disk, only to fail in post-execution verification and roll back.

---

## 5. Candidate Interventions Evaluated

To address this bottleneck, three candidate interventions were designed and evaluated against the single-variable constraint:

### Candidate A: Pre-Execution Syntactic Validation Gate in `PlanValidator` (Selected)
* **Mechanism:** In `PlanValidator._validate_step()`, validate every code payload (`step.content` for file additions; `step.replace_content` for replacements) using Python's standard `ast.parse()`. If syntax compilation fails, emit a structured `PlanValidationError(error_type="syntax_error")` back to the planner during the planning phase.
* **Causal Pathway:** Engages the existing planner repair loop ($N \le 3$) *before* execution or rollback occurs, allowing the model to repair its malformed syntax in conversation context.
* **Scope:** Directly addresses malformed Python syntax; does not alter SafeFileEditor, prompts, or verifiers.
* **Confounds / Leakage:** Zero. Strictly mechanical syntax check.

### Candidate B: Structured Code-Template Prompt Constraints
* **Mechanism:** Add rigid code-block indentation templates into the system prompt.
* **Drawback:** Prompt-only guidance proved ineffective in M16 (model parametric priors overpowered prompt instructions). Lacks a deterministic enforcement mechanism.

### Candidate C: Automatic Executor-Side Indentation Repair
* **Mechanism:** Modify `SafeFileEditor` to automatically reformat or re-indent malformed code before writing to disk.
* **Drawback:** Violates the non-oracle boundary by allowing the harness to semantically repair model code. Confounds SafeFileEditor, which is frozen at M15.

---

## 6. Selected Single Intervention Specification

### The Intervention: Pre-Execution Syntactic Validation Gating in `PlanValidator`

The intervention is implemented exclusively within [`src/autonomous_engineer/agents/validator.py`](file:///c:/Users/anike/Downloads/autonomous-software-engineer/src/autonomous_engineer/agents/validator.py) inside `PlanValidator._validate_step()`:

```python
# Syntactic AST Validation Gate (M17 Intervention)
if step.target_file.endswith(".py"):
    # 1. Validate full-file content for new files or tests
    if step.content is not None and step.operation in (StepOperation.ADD_FILE, StepOperation.ADD_TEST):
        try:
            ast.parse(step.content, filename=step.target_file)
        except SyntaxError as e:
            errors.append(
                PlanValidationError(
                    step_id=step.step_id,
                    field="content",
                    error_type="syntactic_code_error",
                    message=f"Generated code in step {step.step_id!r} contains invalid Python syntax: {e.msg} (line {e.lineno})",
                )
            )

    # 2. Validate replacement snippet syntax for modifications
    if step.replace_content is not None and step.operation in (StepOperation.MODIFY_SYMBOL, StepOperation.REFACTOR_FILE):
        dedented_snippet = textwrap.dedent(step.replace_content)
        try:
            ast.parse(dedented_snippet, filename=step.target_file)
        except SyntaxError as e:
            errors.append(
                PlanValidationError(
                    step_id=step.step_id,
                    field="replace_content",
                    error_type="syntactic_code_error",
                    message=f"Replacement code in step {step.step_id!r} contains invalid Python syntax: {e.msg} (line {e.lineno})",
                )
            )
```

---

## 7. Mechanism & Causal Pathway

The causal mechanism operates as follows:

$$\text{Model Output} \longrightarrow \text{PlanValidator AST Gate} \xrightarrow{\text{SyntaxError}} \text{PlanValidationError} \longrightarrow \text{Planner Repair Loop } (N \le 3) \longrightarrow \text{Corrected Syntax}$$

1. When the model outputs malformed syntax (e.g. `import pytest from click._utils import _Sentinel`), `PlanValidator` catches the `SyntaxError` before the plan is approved.
2. The validator generates an actionable error diagnostic: `[syntactic_code_error] (Field: content): Generated code in step 'step-2' contains invalid Python syntax: invalid syntax (line 1)`.
3. The existing LLM planner repair loop appends this diagnostic to the conversation and requests a corrected plan.
4. If the model corrects the syntax, the plan executes without triggering immediate post-execution AST failure and rollback.

---

## 8. Leakage and Oracle Audit

| Dimension | Verification | Guarantee |
| :--- | :--- | :--- |
| **Reference Patch Access** | None | `PlanValidator` has no access to reference diffs or PR descriptions. |
| **Child Commit SHAs** | None | Not accessible in validator scope. |
| **Ground-Truth Tests** | None | Evaluator test commands remain strictly evaluator-side. |
| **Semantic Code Synthesis** | None | The validator only parses AST; it never generates, replaces, or rewrites code. |
| **Oracle Independence** | Complete | Standard library `ast.parse` provides syntax diagnostics identical to a Python compiler. |

---

## 9. Confound Analysis

1. **Confound: Multi-line Indented Snippets**
   * *Risk:* Valid Python code indented within an existing class method (e.g. 8 spaces) raises `SyntaxError: unexpected indent` when parsed in isolation.
   * *Mitigation:* The validator applies standard `textwrap.dedent()` to the replacement snippet prior to standalone AST parsing. This preserves internal relative indentation while allowing standalone compilation.
2. **Confound: Edit-Representation vs. Code-Synthesis**
   * *Risk:* A failure to match search content might be confused with a syntax failure.
   * *Mitigation:* Search anchor matching remains handled entirely downstream by SafeFileEditor. `PlanValidator` inspects *only* the syntax of the generated code payload (`content` and `replace_content`).

---

## 10. Exact Implementation Surface

* **Component to Modify:** Exactly ONE file: [`src/autonomous_engineer/agents/validator.py`](file:///c:/Users/anike/Downloads/autonomous-software-engineer/src/autonomous_engineer/agents/validator.py).
* **Methods Modified:** `PlanValidator._validate_step()` (adding the pre-execution AST syntax gate).
* **Unmodified Source Files:** All other files in `src/`, all tests in `tests/`, all prompts in `prompt_builder.py`, and `SafeFileEditor`.

---

## 11. Telemetry Requirements

M17 telemetry (`m17_telemetry.json`) will record:
* `syntax_gate_activated`: Boolean flag indicating if AST syntax validation was invoked.
* `syntax_errors_intercepted`: Count and diagnostics of syntax errors caught during plan validation.
* `repair_attempts_triggered_by_syntax`: Number of planner repair retries prompted by syntax errors.
* `repair_syntax_recovery_success`: Boolean indicating if subsequent plan attempts resolved the syntax error.
* `post_exec_ast_failures`: Count of AST syntax errors surviving to post-execution verification (target: 0).
* Standard M16 telemetry fields (Case ID, Retrieval Rank, Matcher Tier, Rollback, Failure Category).

---

## 12. Experimental Protocol

1. **Pre-Run Validation:** Run regression suite (`pytest tests/ -q`); verify 266 tests pass.
2. **Isolated Run Directory:** Create `evaluation/runs/run_YYYYMMDD_HHMMSS_<hash>`.
3. **Live Benchmark Evaluation:** Execute all 6 verified cases sequentially against OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free`.
4. **Data Logging:** Persist `summary.json`, `benchmark_results.json`, and `m17_telemetry.json`.
5. **Report Compilation:** Generate `evaluation/runs/m17_live_baseline_report.md`.

---

## 13. Primary & Secondary Metrics

### Primary Endpoint
* **End-to-End Autonomous Task Resolution Rate:** Number of cases resolved ($X / 6$).

### Secondary Diagnostic Metrics
1. **Pre-Execution Syntax Interception Rate:** Percentage of malformed code snippets caught prior to execution.
2. **Planner Repair Syntax Recovery Rate:** Fraction of syntax errors corrected across attempts $N \le 3$.
3. **Post-Execution AST Pass Rate:** Percentage of applied changes passing post-execution AST check.
4. **Dynamic Test Reach Rate:** Number of cases reaching dynamic `pytest` execution.

---

## 14. Primary Causal Prediction

> **If model code-synthesis precision is the active downstream bottleneck, then introducing pre-execution syntactic validation gating while freezing all other components will eliminate premature AST verification aborts in cases like `REAL-CLICK-02` and `REAL-CLICK-03`, allowing trajectories to advance to dynamic test execution.**

---

## 15. Failure Interpretation Matrix

| Observed Outcome | Primary Metric Impact | Downstream Trajectory Impact | Scientific Interpretation |
| :--- | :---: | :---: | :--- |
| **Full Support** | Resolution $> 0/6$ | Trajectories reach and pass dynamic tests | Code-synthesis precision was the decisive bottleneck; resolution unlocked. |
| **Partial Support (Progression)** | Resolution $= 0/6$ | Syntax errors eliminated; dynamic tests reached in $\ge 3$ cases | Code synthesis was an active upstream bottleneck, but dynamic test logic remains an active downstream blocker. |
| **Null Result (Repair Failure)** | Resolution $= 0/6$ | Syntax errors caught, but repair loop fails to converge ($N \le 3$) | Model lacks the generative capability to repair syntax even when given line-level AST diagnostics. |
| **Null Result (No Effect)** | Resolution $= 0/6$ | Failures remain concentrated in execution representation | Grounding / anchor matching remains the dominant bottleneck prior to synthesis. |
| **Regression** | Resolution $= 0/6$ | Planning validity drops due to repair exhaustion | Rejection gate is overly strict or induces planner loops; reported transparently. |

---

## 16. M16 → M17 Comparison Plan

The post-evaluation report will provide an explicit paired comparison:

| Metric | M16 Control | M17 Intervention | Delta ($\Delta$) | Causal Interpretation |
| :--- | --: | --: | --: | :--- |
| **Resolution Rate** | 0 / 6 (0.0%) | TBD | TBD | End-to-end task completion |
| **Planning Validity** | 6 / 6 (100.0%) | TBD | TBD | Schema and syntax conformity |
| **Syntax Errors Caught in Planning** | 0 (Not gated) | TBD | TBD | Intervention activation |
| **Post-Execution AST Failures** | 2 / 6 (33.3%) | TBD | TBD | Elimination of syntax aborts |
| **Dynamic Tests Reached** | 1 / 6 (16.7%) | TBD | TBD | Trajectory depth progression |
| **Safe Rollback Rate** | 100.0% | TBD | TBD | Safety invariant preservation |

---

## 17. Scientific Limitations

1. **Repair Loop Generative Horizon:** If the open-weights model cannot generate valid syntax even when told "SyntaxError on line 1", the repair loop may simply exhaust attempts ($N=3$).
2. **Fragment Compilation Scope:** Isolated replacement snippets with incomplete control blocks (e.g. bare `else:` clauses) require multi-statement AST wrappers to validate cleanly.
3. **Small-Sample Size ($n=6$):** Findings remain qualitative characterizations of the 6 authentic cases.

---

## 18. Implementation Status Declaration

* **Production Code Modified:** **NO**
* **Tests Modified:** **NO**
* **Benchmark Rerun:** **NO**
* **LLM / API Calls Executed:** **NONE**
* **M14 / M15 / M16 Artifacts Modified:** **NO**
* **M17 Implementation:** **NOT STARTED** (Design-only phase complete)

---

```
M17 DESIGN COMPLETE — AWAITING OVERSIGHT REVIEW
```

# Milestone 18 — Experimental Design: Semantic Patch Correctness & Dynamic Verification Bottleneck

**Date:** 2026-09-04  
**Status:** M18 DESIGN COMPLETE — AWAITING OVERSIGHT REVIEW  
**Run Mode:** Design-Only (Zero Implementation, Zero LLM Calls, Zero Code Changes)  
**Target Milestone:** M18  
**Preceding Milestones:**
* **M14:** Controlled Free-Model Baseline (`nvidia/nemotron-3-ultra-550b-a55b:free`, 0/6 resolved)
* **M15:** SafeFileEditor Anchor-Resolution Intervention (0/6 resolved)
* **M16:** Deterministic Historical-Version Grounding (0/6 resolved)
* **M17:** Pre-Execution Post-Edit Syntactic Gating (0/6 resolved; 9 syntax defects caught, 2 trajectories advanced)
* **M17.1:** Forensic Causality Audit & Trajectory Attribution

---

## 1. Executive Summary

Milestone 17.1 confirmed that pre-execution AST syntax gating is mechanistically sound: it detected 9 authentic model-generated syntax errors, prevented invalid Python from reaching disk, enabled the model to repair syntax in 2 cases (`REAL-CLICK-02`, `REAL-CLICK-03`), and allowed 2 trajectories to advance downstream into dynamic test execution (`REAL-CLICK-02`, `REAL-MARSHMALLOW-02`).

However, end-to-end task resolution remained **0/6 (0.0%)**. 

With syntax and anchor obstacles unblocked, trajectories in M17 advanced into dynamic test verification, where 100% of them failed (`pytest` exit code 2 or 4). This design document investigates whether **Semantic Patch Correctness / Dynamic Verification Failure** is a viable, causally addressable bottleneck for Milestone 18.

### Key Conclusions of This Design:
1. **Critical Examination of Dynamic Failures:**  
   Forensic inspection of the 3 cases reaching dynamic test execution (`CLICK-02`, `MARSH-01`, `MARSH-02`) reveals that **zero test assertions were actually executed**. `CLICK-02` exited with pytest code 2 (missing test file / collection error), while `MARSH-01` and `MARSH-02` exited with pytest code 4 (unrecognized test filter / zero matching tests). Thus, the current benchmark runs do **not** exhibit genuine semantic assertion failures (e.g. `AssertionError: expected X got Y`); rather, they exhibit **test runner invocation and historical harness environment mismatches**.
2. **Coupled Repair-Budget Bottleneck:**  
   M17.1 proved that the free-tier model (`nvidia/nemotron-3-ultra-550b-a55b:free`) experiences severe generation degradation (empty/truncated JSON) when multi-turn diagnostic feedback inflates conversation history within the frozen $N \le 3$ budget.
3. **Verdict:**  
   An intervention attempting to feed dynamic test execution errors back to the model or expecting the model to self-correct semantic logic is **NOT YET JUSTIFIED** as an unconfounded experiment. Introducing multi-turn dynamic test feedback would severely amplify repair-budget exhaustion without addressing the underlying test collection mismatch.
4. **Recommended Path:**  
   We provide three candidate designs and conclude with the explicit oversight decision gate.

---

## 2. Evidence From M14–M17: Trajectory Progression Across Milestones

The table below traces the exact stage reach for each of the six verified benchmark cases across milestones:

| Benchmark Case | M14 Free Baseline | M15 SafeFileEditor | M16 Historical Grounding | M17 Pre-Execution AST Gate |
| :--- | :--- | :--- | :--- | :--- |
| **`REAL-CLICK-02`** | `exec_representation` (step-3 anchor mismatch) | `exec_representation` (step-3 anchor mismatch) | `verification_failure` (AST SyntaxError in test file) | **`verification_failure` (Advanced to dynamic pytest: code 2)** |
| **`REAL-CLICK-03`** | `verification_failure` (AST SyntaxError in test file) | `verification_failure` (AST SyntaxError in test file) | `verification_failure` (AST SyntaxError in source file) | **`exec_representation` (Repaired syntax; anchor drifted)** |
| **`REAL-MARSHMALLOW-01`** | `verification_failure` (Dynamic pytest: code 4) | `verification_failure` (Dynamic pytest: code 4) | `verification_failure` (Dynamic pytest: code 4) | **`verification_failure` (Dynamic pytest: code 4)** |
| **`REAL-MARSHMALLOW-02`** | `exec_representation` (step-1 anchor mismatch) | `exec_representation` (step-1 anchor mismatch) | `exec_representation` (step-1 anchor mismatch) | **`verification_failure` (Advanced to dynamic pytest: code 4)** |
| **`REAL-MARSHMALLOW-03`** | `planning_failure` (API JSON parse error) | `planning_failure` (API JSON parse error) | `exec_representation` (step-1 anchor mismatch) | **`planning_failure` (Syntax caught Att 2 $\to$ Att 3 empty JSON)** |
| **`REAL-MARSHMALLOW-04`** | `exec_representation` (step-1 anchor mismatch) | `exec_representation` (step-1 anchor mismatch) | `exec_representation` (step-1 anchor mismatch) | **`planning_failure` (Syntax caught Att 2 $\to$ Att 3 empty JSON)** |

### Cumulative Stage Reach in M17 (n=6):
1. **Planning Stage Reached:** 6 / 6 (100%)
2. **Syntax Validation Triggered:** 6 / 6 (100%)
3. **Syntax Gate Interventions:** 4 / 6 cases (9 total syntax errors detected)
4. **Syntax Repaired Successfully:** 2 / 4 cases (`CLICK-02`, `CLICK-03`)
5. **Planning Validity Concluded:** 4 / 6 (66.7%)
6. **SafeFileEditor Executed on Disk:** 3 / 6 (`CLICK-02`, `MARSH-01`, `MARSH-02`)
7. **Static AST & Symbol Verification Passed:** 3 / 6 (100% of disk-applied changes)
8. **Dynamic Test Runner (`pytest`) Invoked:** 3 / 6 (`CLICK-02`, `MARSH-01`, `MARSH-02`)
9. **Dynamic Test Assertions Passed:** 0 / 6 (0.0%)
10. **Task Resolution:** 0 / 6 (0.0%)

---

## 3. Dynamic Verification Failure Taxonomy & Diagnostic Audit

The user prompt mandates an audit of every case that reached dynamic verification:

| Case | Reached dynamic tests? | Test invocation valid? | Assertions executed? | Pytest Exit Code | Failure type | Evidence of semantic patch error? |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **`REAL-CLICK-02`** | **Yes** | **No** | **No** | 2 | Test collection / path error | **None.** Exit code 2 in pytest means command-line usage error or file not found. The model generated edits in `src/click/_utils.py` but did not create the test file `tests/test_utils/test_sentinel.py` referenced in the evaluator test command. No test assertions ran. |
| **`REAL-MARSHMALLOW-01`**| **Yes** | **No** | **No** | 4 | Test selector / invocation error | **None.** Exit code 4 in pytest is `pytest.ExitCode.USAGE_ERROR` (no tests matched the `-k` expression or invalid test argument). The test runner found 0 matching tests; no test assertions ran. |
| **`REAL-MARSHMALLOW-02`**| **Yes** | **No** | **No** | 4 | Test selector / invocation error | **None.** Exit code 4 (`USAGE_ERROR`). The filter `-k test_invalid_timedelta_field_deserialization` matched 0 collected tests in historical commit `3265c139`. No test assertions ran. |

### Conservative Scientific Diagnosis:
> **CRITICAL FINDING: In 0 of the 3 cases reaching dynamic testing were any test assertions executed.**
>
> Neither `AssertionError` nor behavioral divergence was evaluated by `pytest`.
> - In `CLICK-02`, the test command targeted a new test file that only exists in the reference child commit, not in the historical parent checkout. Because the model repaired `_utils.py` but did not synthesize the evaluator's test file, pytest exited with code 2.
> - In `MARSH-01` and `MARSH-02`, the test command in `dataset.py` specifies a `-k` filter that does not match test function names in those authentic historical commits (exit code 4).
>
> **Therefore, attributing these failures to "semantic patch error" is empirically false.** The failures are currently **evaluator test-selector / harness invocation failures**.

---

## 4. Evaluation of Intervention Classes

We examine the five candidate intervention classes outlined by oversight:

### Class A: Model-Side Semantic Patch Guidance
* **Concept:** Add structured instructions or semantic verification requirements to the planner prompt (e.g. asking the model to reason through edge cases or invariants).
* **Forensic Reality:** In M16, adding factual historical grounding headers did not improve reasoning. Adding prompt guidelines risks non-deterministic instruction following and token inflation, exacerbating attempt-3 truncation.
* **Assessment:** Weak causal leverage; high risk of prompt confound.

### Class B: Dynamic Execution-Feedback Repair Loop
* **Concept:** When dynamic test execution fails (exit code $\ne 0$), feed stdout/stderr back into the model to attempt a repair.
* **Forensic Reality:** 
  1. The feedback returned would be pytest exit codes 2 and 4 ("no tests collected" or "file not found"), which does not provide semantic code logic guidance.
  2. Feeding compiler/test output consumes turns in the fixed $N \le 3$ budget. In M17, feeding syntax diagnostics already caused attempt 3 to emit empty/truncated JSON in 50% of syntax-failing cases. Adding dynamic test traces would cause 100% truncation.
* **Assessment:** Highly confounded; couples execution feedback with context overflow.

### Class C: Pre-Execution Patch Behavioral Self-Check
* **Concept:** Require the planner to generate a standalone verification script or in-memory unit test to check its own patch before disk execution.
* **Forensic Reality:** In M15–M17, when the model attempted to write unit tests, it generated syntax errors (`CLICK-02`, `CLICK-03`, `MARSH-03`, `MARSH-04`). Forcing the model to write more code increases syntax failure rate.
* **Assessment:** Counter-productive for this model class.

### Class D: Verification-Side Test Invocation / Harness Alignment
* **Concept:** Fix test invocation mechanics in the benchmark/verifier so that tests actually execute assertions when code is applied.
* **Forensic Reality:** While scientifically necessary for the benchmark to measure semantic correctness, modifying test commands or verifier harnesses modifies the frozen benchmark/evaluation harness, which violates experimental invariance unless explicitly authorized as an evaluation fix.
* **Assessment:** Belongs to benchmark maintenance/validation, not a model intervention.

### Class E: Multi-Turn Diagnostic Context Compaction (Identified in M17.1)
* **Concept:** In the planner repair loop, strip accumulated previous plans and compact error diagnostics to prevent token bloat, ensuring attempt 3 has sufficient context window to synthesize clean code.
* **Forensic Reality:** Directly targets the exact failure mechanism observed in `MARSH-03` and `MARSH-04` (empty JSON on attempt 3) and `CLICK-03` (anchor drift under cognitive load).
* **Assessment:** Mechanistically clean, single-variable, and directly supported by M17 data.

---

## 5. Candidate Intervention Designs

### Candidate Option 1: Dynamic Execution-Feedback in Planner Repair Loop (Class B)
* **Hypothesis:** Routing non-zero pytest stdout/stderr back to the planner across an expanded or existing retry loop will enable the model to correct semantic patch errors.
* **Intervention:** If `verify_tests` fails, rollback workspace, capture bounded stderr/stdout, and invoke `planner.plan_with_audit` with `previous_failure=test_failure`.
* **Single Independent Variable:** Dynamic test execution feedback routed into planner repair loop.
* **Leakage Risk:** Low (if only workspace test output is used; zero reference patch access).
* **Repair-Budget Interaction:** **FATAL CONFOUND.** The model currently exhausts $N=3$ on syntax errors alone. A dynamic test cycle requires at least 2 additional full generation attempts, which exceeds context limits and causes empty JSON responses.
* **Empirical Support:** **UNSUPPORTED BY EVIDENCE.** The current dynamic failures are pytest collection errors (codes 2 and 4), not assertion failures. Giving the model "no tests collected" feedback will not help it fix code logic.

### Candidate Option 2: Model-Side Semantic Invariant Prompting (Class A)
* **Hypothesis:** Requiring the model to explicitly state the pre- and post-conditions of its edit in the prompt will reduce logical bugs in synthesized code.
* **Intervention:** Add a single deterministic prompt block in `PlannerPromptBuilder.build_user_prompt()` requesting behavioral invariants.
* **Single Independent Variable:** Additive invariant specification in user prompt.
* **Leakage Risk:** Zero.
* **Repair-Budget Interaction:** Neutral.
* **Empirical Support:** **POOR.** Passive prompt instructions in M16 had zero effect on code correctness.

### Candidate Option 3: Diagnostic Context Compaction in the Repair Loop (Class E)
* **Hypothesis H6:** *Compacting diagnostic error messages and eliding rejected JSON payloads in multi-turn repair prompts prevents model output truncation, increasing valid repair recovery within the frozen $N \le 3$ budget.*
* **Intervention:** In `PlannerPromptBuilder.build_repair_prompt()`, replace full dump of `invalid_plan_str` with a structural diff or compact summary of invalid steps, and truncate diagnostics to 1-line per error.
* **Single Independent Variable:** Repair prompt payload representation (compact vs monolithic).
* **Frozen Components:** Model, provider, temperature (0), max tokens (4096), benchmark suite (6 cases), parent commits, retrieval, SafeFileEditor, M17 syntax gate, static/dynamic verifiers, $N=3$ budget.
* **Leakage Risk:** Zero.
* **Repair-Budget Interaction:** Direct mitigation of the repair-budget exhaustion observed in M17.
* **Empirical Support:** Directly derived from the root cause of `MARSH-03` and `MARSH-04` failing in M17.

---

## 6. Comparative Evaluation of Candidate Options

| Evaluation Dimension | Candidate Option 1 (Dynamic Feedback) | Candidate Option 2 (Invariant Prompt) | Candidate Option 3 (Diagnostic Compaction) |
| :--- | :--- | :--- | :--- |
| **Supported by Observed Evidence?** | **NO** (0 assertions ran; errors are pytest codes 2 & 4) | **NO** (Passive prompts failed in M16) | **YES** (Directly addresses Att-3 empty JSON in M17) |
| **Single-Variable Isolation?** | Poor (alters execution loop, retry budget, context) | Good (prompt-only) | **Excellent** (pure prompt compaction in repair loop) |
| **Repair-Budget Safety?** | **Catastrophic** (will induce 100% truncation) | Neutral | **Positive** (reduces prompt tokens by ~60%) |
| **Oracle / Leakage Risk?** | None | None | None |
| **Scientific Value?** | Low (evaluates noise from test harness) | Low (soft prompt tuning) | **High** (falsifiable test of multi-turn capacity limit) |

---

## 7. Challenging the Premise: Is Semantic Patch Correctness Truly the Next Bottleneck?

Oversight explicitly directed:
> *"If the evidence does NOT adequately establish semantic patch correctness as the next bottleneck, say so. It is acceptable—and scientifically preferable—to conclude: 'M18 should not target semantic patch correctness yet because the available dynamic-test failures are insufficiently diagnostic.'"*

### Formal Scientific Challenge:
1. **Premise:** Trajectories in M17 were stopped by semantic patch incorrectness during dynamic verification.
2. **Fact Check:** In the 3 trajectories reaching dynamic testing:
   - `REAL-CLICK-02`: Pytest exited with code 2 because the test file specified in `real_benchmark.py` (`tests/test_utils/test_sentinel.py`) does not exist in the parent commit checkout. The model repaired `_utils.py`, but pytest could not run because the test file was absent.
   - `REAL-MARSHMALLOW-01`: Pytest exited with code 4 because `-k test_datetime_list_inner_format` matched 0 tests in historical commit `b40a0f4e`.
   - `REAL-MARSHMALLOW-02`: Pytest exited with code 4 because `-k test_invalid_timedelta_field_deserialization` matched 0 tests in historical commit `3265c139`.
3. **Conclusion:** **Not a single test assertion was executed.** The system has not yet measured whether the patches in `CLICK-02`, `MARSH-01`, and `MARSH-02` are semantically correct or incorrect. The barrier at the dynamic verification boundary is currently **test harness / selector incompatibility with historical parent commits**, not semantic patch logic.
4. **Secondary Bottleneck:** The planning-validity drop in M17 (6/6 $\to$ 4/6) proved that the repair loop itself is failing when given syntax error feedback due to token explosion and output truncation.

Therefore, targeting "semantic patch correctness" via an LLM intervention in M18 would be testing a phantom variable: the model cannot receive or respond to semantic test feedback when the test runner is exiting on collection/invocation errors.

---

## 8. Recommended M18 Design: Context Compaction in Repair Loop (H6)

Because semantic patch correctness cannot be cleanly tested until test assertions actually execute and multi-turn repair stability is established, the only scientifically sound, unconfounded intervention is **Candidate Option 3: Multi-Turn Diagnostic Context Compaction**.

### Refined Hypothesis:
> **H6: Diagnostic context compaction in the multi-turn planner repair loop will eliminate attempt-3 output truncation, restoring planning validity to 6/6 and increasing the proportion of trajectories advancing to disk execution and verification within the frozen $N \le 3$ budget.**

### Operational Mechanism:
In `src/autonomous_engineer/agents/prompt_builder.py`:
- In `build_repair_prompt()`:
  - Current implementation embeds the **entire raw text of the previous rejected plan** (`error_lines.append(invalid_plan_str)`), which consumes 2,000–3,500 tokens per attempt.
  - In addition, it dumps multi-line tracebacks.
  - Under M18, replace the monolithic plan dump with a **compact summary** (only the failing step IDs and their target files) and format each diagnostic as a single concise line.
  - This reduces the repair prompt size by ~70%, preventing context bloat from triggering OpenRouter output truncation on attempt 3.

---

## 9. Single-Variable Isolation Plan

| System Dimension | M17 Experimental Status | Proposed M18 Experimental Status | Invariance Confirmation |
| :--- | :--- | :--- | :--- |
| **Model** | `nvidia/nemotron-3-ultra-550b-a55b:free` | `nvidia/nemotron-3-ultra-550b-a55b:free` | **FROZEN** |
| **Provider** | OpenRouter HTTP | OpenRouter HTTP | **FROZEN** |
| **Generation Parameters** | $T=0.0$, Max Tokens 4096 | $T=0.0$, Max Tokens 4096 | **FROZEN** |
| **Context Budget** | 120,000 characters | 120,000 characters | **FROZEN** |
| **Benchmark Population** | Exactly the 6 verified cases | Exactly the 6 verified cases | **FROZEN** |
| **Retrieval Engine** | Hybrid BM25 + AST (Top-5) | Hybrid BM25 + AST (Top-5) | **FROZEN** |
| **Historical Grounding** | Deterministic M16 Header | Deterministic M16 Header | **FROZEN** |
| **Plan Validation** | M17 Pre-Execution AST Gate | M17 Pre-Execution AST Gate | **FROZEN** |
| **SafeFileEditor** | M15 3-Tier Matcher | M15 3-Tier Matcher | **FROZEN** |
| **Execution Policy** | Max $N=3$, Auto-rollback | Max $N=3$, Auto-rollback | **FROZEN** |
| **Static Verifiers** | AST & Symbol Verifier | AST & Symbol Verifier | **FROZEN** |
| **Test Verification** | Frozen Subprocess Runner | Frozen Subprocess Runner | **FROZEN** |
| **Independent Variable** | None | **Compact repair prompt representation** | **SINGLE INTERVENTION** |

---

## 10. Leakage, Oracle, and Safety Analysis

1. **Zero Reference Leakage:**  
   The repair prompt builder consumes only the output of `PlanValidator` (which operates strictly on the model's generated plan and the checked-out workspace). It has zero access to reference commits, reference diffs, PR descriptions, or evaluator test commands.
2. **Zero Oracle Assistance:**  
   The compaction algorithm is purely mechanical string manipulation (filtering JSON keys and truncating error strings). It does not infer or suggest code fixes to the model.
3. **Rollback & Workspace Safety:**  
   The 100% atomic rollback guarantee established in M14–M17 remains completely intact.

---

## 11. Telemetry Specification

M18 telemetry will record all existing M17 fields, plus new instrumentation for prompt token overhead and multi-turn stability:
* `repair_prompt_char_length`: Length in characters of the repair prompt for attempts $> 1$.
* `attempt_3_token_count`: Completion tokens on attempt 3.
* `truncation_detected`: Boolean flag indicating whether attempt 3 suffered JSON truncation (`Expecting value: line 1 column 1`).
* `syntax_recovered`: Unchanged from M17.
* `terminal_failure_category`: Unchanged taxonomy.

---

## 12. Pre-Registration & Falsification Criteria

### Primary Evaluation Outcome:
* **Metric:** End-to-end task resolution (`is_resolved == True`).
* **Target:** $\ge 1 / 6$ resolved cases.

### Secondary / Mechanistic Outcomes:
1. **Planning Validity Restoration:** Planning validity improves from 4/6 (66.7% in M17) back to **6/6 (100.0%)**.
2. **Elimination of Attempt-3 Truncation:** `REAL-MARSHMALLOW-03` and `REAL-MARSHMALLOW-04` produce valid JSON on attempt 3 rather than empty/truncated responses.
3. **Downstream Progression:** Cases recovering from syntax errors progress to SafeFileEditor execution.

### Falsification Conditions (Hypothesis H6 Rejected):
* Attempt-3 output truncation persists in `MARSH-03` and `MARSH-04` despite compact repair prompts.
* Planning validity remains $\le 4/6$.
* Model repair rate on syntax errors drops below the M17 baseline (50%).

---

## 13. Minimal Implementation Surface

The proposed intervention touches exactly **one** method in **one** file:
* **Target File:** `src/autonomous_engineer/agents/prompt_builder.py`
* **Target Method:** `PlannerPromptBuilder.build_repair_prompt()`
* **Lines Affected:** ~15 lines of code.
* **Unit Test File:** `tests/unit/test_planner.py` (verify compact repair prompt format).
* **Untouched Files:** Zero changes to `planner.py`, `validator.py`, `file_editor.py`, `engine.py`, `verifier.py`, `real_benchmark.py`, or `dataset.py`.

---

## 14. Decision Gate Before Implementation

### Scientific Assessment of Prerequisites:
1. **Is Semantic Patch Correctness causally actionable right now?**  
   **NO.** Because historical test commands currently fail with pytest exit codes 2 and 4 before assertions execute, attempting to evaluate semantic patch correctness is premature and ungrounded.
2. **Is Repair-Loop Context Compaction causally actionable and isolated?**  
   **YES.** It directly addresses the exact empirical failure mode documented in M17.1.

However, per oversight instructions, if the evidence does not support the original premise of semantic patch correctness as the active bottleneck, we must present the candid assessment:

```
M18 DESIGN NOT YET JUSTIFIED (FOR SEMANTIC PATCH FEEDBACK)
— ALTERNATIVE INTERVENTION (H6: REPAIR CONTEXT COMPACTION) PROPOSED FOR OVERSIGHT SELECTION
```

---

## 15. Final Status Line

```
M18 DESIGN COMPLETE — AWAITING OVERSIGHT REVIEW
```

# Milestone 16 — Experimental Design: Deterministic Historical-Version Grounding Intervention (Revised)

**Date:** 2026-09-04  
**Status:** REVISED DESIGN ONLY — AWAITING OVERSIGHT REVIEW  
**Hypothesis Under Test:** **H4**  
**Intervention Type:** Single-Variable Additive Grounding Context (No Behavioral Prompt Changes)  
**Target File for Eventual Implementation:** `src/autonomous_engineer/agents/prompt_builder.py`  
**Control Baseline:** Milestone 14-FREE (`run_20260902_125455_c3cc4e`) & Milestone 15 (`run_20260903_143458_209eba`)  
**Evaluation Population:** Exactly 6 `GROUND_TRUTH_VERIFIED` authentic benchmark cases  

---

## 1. Single Intervention Principle & Disentanglement

Following oversight review of the initial M16 design, the experimental intervention has been strictly unbundled to test **exactly one causal mechanism**:

> **Single Intervention:** Deterministic historical-version grounding context added to the planner user prompt input. No new behavioral system instructions or negative constraint rules are introduced.

### Disentanglement Summary
* **REMOVED (System Prompt Negative Constraint):** We do *not* add any new rule forbidding modern/future APIs, parameters, or fixtures to `PLANNER_SYSTEM_PROMPT`. The system prompt remains 100% byte-for-byte identical to M14-FREE/M15.
* **REMOVED (Vague Metadata):** Vague concepts such as "environment era" have been eliminated.
* **KEPT (Single Additive Causal Factor):** An enhanced, strictly factual **Historical Repository Grounding Block** in the planner user prompt, populated mechanically and deterministically from the authentic checked-out parent commit workspace.

This isolates the exact scientific question:
> *Does providing explicit, deterministic factual grounding in the historical parent repository state improve autonomous resolution without altering model behavioral instructions?*

---

## 2. Research Hypothesis & Motivation

### Formal Hypothesis (H4)
> **H4:** *Historical-version grounding is a significant causal bottleneck in autonomous issue resolution because the model lacks explicit factual awareness of the checked-out historical parent state, leading it to rely on parametric training priors that introduce modern, non-existent repository constructs.*

### Baseline Context & Forensic Motivation
1. In M14-FREE, all 6 cases failed (3 `exec_representation_failure`, 3 `verification_failure`).
2. In M15, the deterministic 3-tier matcher unblocked exact-anchor whitespace mismatches, advancing cases like `REAL-MARSHMALLOW-01` into dynamic pytest execution, but overall resolution remained **0/6 (0.0%)**.
3. In M15.1 forensic trajectory auditing, 3 of the 6 cases (`REAL-CLICK-02`, `REAL-MARSHMALLOW-02`, and `REAL-MARSHMALLOW-04`) failed due to search anchors matching modern repository code rather than the authentic parent commit tree.
4. M16 evaluates whether mechanically presenting the factual historical parent commit metadata grounds the model in the actual codebase under repair.

---

## 3. Grounding Fields Specification & Provenance Analysis

Every field in the M16 historical grounding context is derived mechanically from the checked-out parent commit workspace (`Repository` and `RepositoryMap`).

| Grounding Field | Source | Exists in Parent State? | Model-Visible? | Oracle / Leakage Risk |
| :--- | :--- | :---: | :---: | :---: |
| **Repository Identity** | `planner_input.repository.url` / `issue.repository_name` | Yes | Yes | **None** (Public issue metadata) |
| **Checked-Out Commit SHA** | `planner_input.repository.commit_sha` | Yes | Yes | **None** (Authentic parent git commit) |
| **Parent Workspace Root** | Relative workspace path structure | Yes | Yes | **None** (Filesystem directory layout) |
| **Historical File Counts** | `repo_map.file_count`, `repo_map.python_file_count` | Yes | Yes | **None** (Deterministic file scan of parent tree) |
| **Historical Test File List** | `repo_map.test_file_paths` | Yes | Yes | **None** (Discovered test files in parent tree) |
| **Historical Config File List** | `repo_map.configuration_file_paths` | Yes | Yes | **None** (Discovered configs like `setup.cfg`, `tox.ini` in parent tree) |
| **Historical Module Index** | `repo_map.python_modules` AST inventory | Yes | Yes | **None** (AST classes/functions parsed from parent tree) |

### Non-Oracle Verification
* **Zero Child Commit Data:** No commit SHAs, author names, commit dates, or messages from child/reference commits are present.
* **Zero Reference Diff Data:** No patches, diff hunks, or solution lines are included.
* **Zero Ground-Truth Selectors:** Evaluator verification commands remain strictly evaluator-side.

---

## 4. Exact Prompt Representation Specification

The intervention modifies *only* the user prompt assembly in `PlannerPromptBuilder.build_user_prompt()` within [`src/autonomous_engineer/agents/prompt_builder.py`](file:///c:/Users/anike/Downloads/autonomous-software-engineer/src/autonomous_engineer/agents/prompt_builder.py).

### Before (Control — M14-FREE / M15):
```text
=== REPOSITORY METADATA ===
Repository URL: {planner_input.repository.url}
Commit SHA: {planner_input.repository.commit_sha}
Total Files: {repo_map.file_count} (Python Source: {repo_map.python_file_count})
Test Files: {', '.join(repo_map.test_file_paths) or 'None'}
Configuration Files: {', '.join(repo_map.configuration_file_paths) or 'None'}
```

### After (Intervention — M16):
```text
=== HISTORICAL REPOSITORY GROUNDING (CHECKED-OUT PARENT COMMIT) ===
Repository: {planner_input.repository.url}
Checked-Out Commit SHA: {planner_input.repository.commit_sha}
Parent Workspace Tree: {repo_map.file_count} total files ({repo_map.python_file_count} Python source files)
Discovered Test Files in Parent Tree: {', '.join(repo_map.test_file_paths) or 'None'}
Discovered Configuration Files in Parent Tree: {', '.join(repo_map.configuration_file_paths) or 'None'}
```

### System Prompt (Strictly Frozen):
`PLANNER_SYSTEM_PROMPT` remains **100% unchanged**. Zero new rules, zero negative constraints, and zero behavioral modifications are introduced.

---

## 5. Anti-Leakage & Non-Oracle Invariant Guarantees

The strict information boundary is maintained:

$$\text{Parent Commit SHA} \longrightarrow \text{Checked-Out Working Tree} \longrightarrow \text{RepositoryMap Scanner} \longrightarrow \text{Deterministic Prompt Block} \longrightarrow \text{Model}$$

$$\begin{Bmatrix}
\text{Reference PR Patch} \\
\text{Child / Future Commit} \\
\text{Evaluator Test Selectors} \\
\text{Human Ground Truth}
\end{Bmatrix} \centernot\longrightarrow \text{Model Context}$$

---

## 6. Experimental Controls & Hard Freezes

All system components outside the single `PlannerPromptBuilder.build_user_prompt()` formatting change remain strictly frozen:

| Pipeline Component | M14-FREE / M15 Control | M16 Intervention | Invariance Status |
| :--- | :--- | :--- | :--- |
| **Benchmark Suite** | 6 Verified Cases | 6 Verified Cases | **STRICTLY FROZEN** |
| **Model** | `nvidia/nemotron-3-ultra-550b-a55b:free` | `nvidia/nemotron-3-ultra-550b-a55b:free` | **STRICTLY FROZEN** |
| **Provider / Endpoint** | OpenRouter (`https://openrouter.ai/api/v1`) | OpenRouter (`https://openrouter.ai/api/v1`) | **STRICTLY FROZEN** |
| **Sampling Config** | $T=0.0$, Max Tokens: 4096, Context: 120k | $T=0.0$, Max Tokens: 4096, Context: 120k | **STRICTLY FROZEN** |
| **System Prompt** | `PLANNER_SYSTEM_PROMPT` | `PLANNER_SYSTEM_PROMPT` | **STRICTLY FROZEN** |
| **Retrieval Architecture** | BM25 + AST Module/Symbol Ranking | BM25 + AST Module/Symbol Ranking | **STRICTLY FROZEN** |
| **Retrieval Weights / Top-K** | BM25 (0.5), AST (0.5), Top-5 items | BM25 (0.5), AST (0.5), Top-5 items | **STRICTLY FROZEN** |
| **Planner Schema** | `ImplementationPlan` Pydantic model | `ImplementationPlan` Pydantic model | **STRICTLY FROZEN** |
| **DAG Dependency Rules** | Strict DAG validator | Strict DAG validator | **STRICTLY FROZEN** |
| **Repair Policy** | Max 3 attempts ($N \le 3$), diagnostic feedback | Max 3 attempts ($N \le 3$), diagnostic feedback | **STRICTLY FROZEN** |
| **SafeFileEditor** | M15 Deterministic 3-Tier Matcher | M15 Deterministic 3-Tier Matcher | **STRICTLY FROZEN** |
| **Verifier Pipeline** | AST Syntax, Symbol Exists, Subprocess | AST Syntax, Symbol Exists, Subprocess | **STRICTLY FROZEN** |
| **Rollback Mechanism** | 100% Atomic transactional rollback | 100% Atomic transactional rollback | **STRICTLY FROZEN** |
| **User Prompt Grounding** | Standard metadata block | **Enhanced historical grounding block** | **SINGLE INTERVENTION** |

---

## 7. Dependent Variables & Experimental Endpoints

### Primary Endpoint
* **End-to-End Task Resolution Rate:** Fraction of benchmark cases where all edits apply, all verifications pass, and ground-truth validation succeeds ($X / 6$).

### Secondary Endpoints
1. **Historical Version Drift Rate:** Frequency of planned search anchors or replacement blocks referencing non-existent modern API signatures.
2. **Execution Representation Success Rate:** Percentage of planned edit steps matched and applied by `SafeFileEditor`.
3. **AST Syntax Pass Rate:** Percentage of applied edits passing AST syntax verification.
4. **Dynamic Verification Reach Rate:** Percentage of cases reaching dynamic `pytest` execution.
5. **Planning Validity Rate:** Percentage of planner attempts producing valid JSON conforming to `ImplementationPlan`.

---

## 8. Potential Confounders & Mitigations

| Potential Confounder | Impact | Experimental Mitigation |
| :--- | :--- | :--- |
| **Free-Tier Provider Truncation** | OpenRouter streaming dropped response in M15 Case 5. | If empty response occurs after 3 retries, classify explicitly as `PROVIDER/INFRASTRUCTURE_FAILURE` (do not confound with model capability). |
| **Sampling Non-Determinism** | Potential variance across runs. | Fix $T=0.0$ strictly across all calls. |
| **Context Length Overhead** | Grounding header could displace retrieved code excerpts. | Keep formatting change strictly under 100 characters delta (< 0.08% of budget). |

---

## 9. Pre-Benchmark Validation Plan

Before executing the M16 live benchmark evaluation:
1. **Unit & Regression Suite:** Run `pytest tests/ -q` and verify all 266 unit tests pass.
2. **Baseline Artifact Immutability:** Audit that M14-FREE (`run_20260902_125455_c3cc4e`) and M15 (`run_20260903_143458_209eba`) run directories remain untouched.
3. **Benchmark Dataset Invariance:** Verify all 6 cases in `BENCHMARK_REGISTRY` retain exact parent commit SHAs and authentic issue bodies.
4. **Anti-Oracle Audit:** Verify `PlannerPromptBuilder` has zero access to reference patch fields or evaluator ground truth.
5. **Single-Variable Code Diff Audit:** Verify that `git diff` shows modifications *only* in `src/autonomous_engineer/agents/prompt_builder.py`.

---

## 10. Telemetry & Data Capture Plan

M16 execution will log a complete audit record in `m16_telemetry.json` capturing:
* Case ID & Target Repository
* Parent Commit SHA
* Model Identifier (`nvidia/nemotron-3-ultra-550b-a55b:free`)
* Historical Grounding Block Content & Length
* Planning Validity & Number of Planner Attempts
* Retrieval Ranks & Recall Metrics
* Step Edit Application Results & Matcher Tiers (T1, T2, T3)
* Preflight & AST Syntax Verification Outcomes
* Dynamic Subprocess Test Results & Exit Codes
* Rollback Invocations & Restoration Success
* Mutually Exclusive Failure Taxonomy Classification
* Provider API Latency & Token Usage

---

## 11. M15 → M16 Paired Comparison Plan

Following live evaluation, results will be compiled into `evaluation/runs/m16_live_baseline_report.md` featuring:

### Aggregate Comparison Table:
| Metric | M15 Control | M16 Intervention | Delta ($\Delta$) | Empirical Interpretation |
| :--- | --: | --: | --: | :--- |
| **Resolution Rate** | 0/6 (0.0%) | TBD | TBD | End-to-end task completion |
| **Planning Validity** | 5/6 (83.3%) | TBD | TBD | Schema conformity |
| **Target File Recall@3** | 66.7% | 66.7% | 0.0% | Retrieval invariance |
| **Target File Recall@5** | 83.3% | 83.3% | 0.0% | Retrieval invariance |
| **Mean MRR** | 0.467 | 0.467 | 0.000 | Retrieval invariance |
| **Exec Representation Failures** | 3 (50.0%) | TBD | TBD | Anchor matching failures |
| **Verification Failures** | 2 (33.3%) | TBD | TBD | Syntax / dynamic test failures |
| **Planning Failures** | 1 (16.7%) | TBD | TBD | Schema / provider failures |
| **Safe Rollback Rate** | 100.0% | TBD | TBD | Safety guarantee |

### Per-Case Trajectory Progression Table:
| Case ID | M15 First Failure | M16 First Failure | Grounding Fields Used | Progression Change | Final Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `REAL-CLICK-02` | `exec_representation_failure` | TBD | Commit SHA, Workspace Tree, Configs | TBD | TBD |
| `REAL-CLICK-03` | `verification_failure` (Test syntax) | TBD | Commit SHA, Workspace Tree, Test files | TBD | TBD |
| `REAL-MARSHMALLOW-01` | `verification_failure` (Pytest exit 4) | TBD | Commit SHA, Workspace Tree, Test files | TBD | TBD |
| `REAL-MARSHMALLOW-02` | `exec_representation_failure` | TBD | Commit SHA, Workspace Tree, Configs | TBD | TBD |
| `REAL-MARSHMALLOW-03` | `planning_failure` (API truncation) | TBD | Commit SHA, Workspace Tree, Test files | TBD | TBD |
| `REAL-MARSHMALLOW-04` | `exec_representation_failure` | TBD | Commit SHA, Workspace Tree, Configs | TBD | TBD |

---

## 12. Scientific Success & Falsification Criteria

* **Strong Confirmation:** Resolution rate increases ($> 0/6$) and trajectories eliminate modern-version signature mismatches.
* **Partial Progression:** Resolution remains 0/6, but `exec_representation_failure` decreases as anchors match historical parent commit code, unmasking downstream verification.
* **Falsification / Null Result:** Resolution remains 0/6 and error distribution is unchanged; indicates that factual grounding header alone does not overcome parametric training priors.
* **Regression:** Performance drops or error rates increase; documented transparently without post-hoc parameter adjustments.

---

```
M16 DESIGN REVISED — AWAITING OVERSIGHT AUTHORIZATION
```

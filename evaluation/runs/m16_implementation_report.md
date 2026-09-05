# Milestone 16 — Implementation & Verification Report: Historical-Version Grounding

**Date:** 2026-09-04  
**Status:** IMPLEMENTATION COMPLETE — AWAITING OVERSIGHT AUTHORIZATION FOR LIVE EVALUATION  
**Milestone:** M16  
**Intervention Type:** Single-Variable Additive Grounding Context (No Behavioral Prompt Changes)  
**Modified File:** `src/autonomous_engineer/agents/prompt_builder.py`  
**Control Baselines:** M14-FREE (`run_20260902_125455_c3cc4e`) & M15 (`run_20260903_143458_209eba`)  
**Evaluation Population:** Exactly 6 `GROUND_TRUTH_VERIFIED` authentic benchmark cases  

---

## 1. Implementation Summary

In accordance with oversight authorization for Milestone 16, the approved single-variable intervention—**Deterministic Historical-Version Grounding Header**—has been implemented in `PlannerPromptBuilder.build_user_prompt()`.

### Key Implementation Principles Maintained:
1. **Single Causal Factor Only:** Only the user prompt's repository metadata header was modified. Zero behavioral rules, zero negative constraints ("do not assume modern APIs"), and zero system prompt instructions were added or altered.
2. **Deterministic & Mechanically Generated:** All grounding fields originate solely from existing, deterministic `Repository` and `RepositoryMap` structures generated during repository AST scanning of the checked-out parent commit.
3. **Anti-Oracle & Non-Leakage Guarantee:** Zero child commit information, reference patch diffs, evaluator test selectors, or solution hints cross into the model context.
4. **Frozen Downstream Architecture:** `SafeFileEditor` (M15 3-tier matcher), retrieval scoring/ranking, DAG validator, Pydantic schemas, repair budget ($N \le 3$), and verification pipelines remain 100% frozen.

---

## 2. Exact Files Modified

* **Modified:** [`src/autonomous_engineer/agents/prompt_builder.py`](file:///c:/Users/anike/Downloads/autonomous-software-engineer/src/autonomous_engineer/agents/prompt_builder.py)
* **Unchanged / Strictly Frozen:** All other source files in `src/`, all tests in `tests/`, and all benchmark definitions.

---

## 3. Exact Intervention Added

Inside `PlannerPromptBuilder.build_user_prompt()`, section 2 was replaced with the deterministic historical grounding block:

```python
        # 2. Historical Repository Grounding
        repo_map = planner_input.repo_map
        sections.append(
            f"=== HISTORICAL REPOSITORY GROUNDING (CHECKED-OUT PARENT COMMIT) ===\n"
            f"Repository: {planner_input.repository.url}\n"
            f"Checked-Out Commit SHA: {planner_input.repository.commit_sha}\n"
            f"Parent Workspace Tree: {repo_map.file_count} total files ({repo_map.python_file_count} Python source files)\n"
            f"Discovered Test Files in Parent Tree: {', '.join(repo_map.test_file_paths) or 'None'}\n"
            f"Discovered Configuration Files in Parent Tree: {', '.join(repo_map.configuration_file_paths) or 'None'}"
        )
```

`PLANNER_SYSTEM_PROMPT` was **not modified** and remains identical to the M14/M15 baseline.

---

## 4. Source Audit for Every Grounding Field

Every field exposed in the historical grounding header was audited for provenance, determinism, and leakage risk:

| Field | Exact Source | Parent-Derived? | Deterministic? | Oracle Leakage Risk |
| :--- | :--- | :---: | :---: | :---: |
| **`Repository`** | `planner_input.repository.url` | Yes | Yes | **None** (Public upstream git repository URL) |
| **`Checked-Out Commit SHA`** | `planner_input.repository.commit_sha` | Yes | Yes | **None** (The authentic git commit checked out in workspace) |
| **`Parent Workspace Tree`** | `repo_map.file_count`, `repo_map.python_file_count` | Yes | Yes | **None** (Mechanical filesystem count of checked-out parent tree) |
| **`Discovered Test Files in Parent Tree`** | `repo_map.test_file_paths` | Yes | Yes | **None** (List of discovered test files in checked-out parent tree) |
| **`Discovered Configuration Files in Parent Tree`** | `repo_map.configuration_file_paths` | Yes | Yes | **None** (List of discovered config files in checked-out parent tree) |

---

## 5. Leakage & Anti-Oracle Audit

An explicit audit was conducted across the codebase to ensure zero ground-truth data or reference commit artifacts can enter `PlannerPromptBuilder`:

1. **Reference Patch Diff:** Inaccessible (`PlannerInput` does not receive or store reference patch diffs).
2. **Child / Reference Commit SHA:** Inaccessible (`PlannerInput.repository.commit_sha` is set strictly to `issue.parent_commit_sha`).
3. **Ground-Truth Test Selectors:** Inaccessible (`issue.expected_test_command` is passed exclusively to `ExecutionEngine.execute()` at the evaluator stage, never to `PlannerInput`).
4. **Evaluator Failure Classifications:** Inaccessible.

---

## 6. Frozen-Component Audit

| Pipeline Component | Status | Verification Evidence |
| :--- | :--- | :--- |
| **Model** | `nvidia/nemotron-3-ultra-550b-a55b:free` | Unchanged |
| **Provider** | OpenRouter (`https://openrouter.ai/api/v1`) | Unchanged |
| **Generation Config** | $T=0.0$, Max Tokens: 4096, Context: 120,000 | Unchanged |
| **System Prompt** | `PLANNER_SYSTEM_PROMPT` | Byte-for-byte unchanged |
| **Retrieval System** | BM25 + AST Module/Symbol Ranking | Unchanged |
| **Retrieval Weights / Top-K** | BM25 (0.5), AST (0.5), Top-5 Items | Unchanged |
| **Planner Schema** | `ImplementationPlan` Pydantic model | Unchanged |
| **DAG Dependency Rules** | Strict DAG validator | Unchanged |
| **Repair Policy** | Max 3 attempts ($N \le 3$), diagnostic feedback | Unchanged |
| **SafeFileEditor** | M15 Deterministic 3-Tier Matcher | Byte-for-byte unchanged |
| **Verifier Pipeline** | AST Syntax, Symbol Existence, Subprocess Test | Unchanged |
| **Rollback Mechanism** | 100% Atomic transactional rollback | Unchanged |

---

## 7. Planner-Context Before / After Comparison

### Before (Control — M14-FREE / M15):
```text
=== REPOSITORY METADATA ===
Repository URL: https://github.com/pallets/click
Commit SHA: 3cbcf9b11546f4cf10b36d3e2e531733ba6fe001
Total Files: 79 (Python Source: 42)
Test Files: tests/test_basic.py, tests/test_commands.py, tests/test_compat.py, ...
Configuration Files: setup.py, setup.cfg, tox.ini
```

### After (Intervention — M16):
```text
=== HISTORICAL REPOSITORY GROUNDING (CHECKED-OUT PARENT COMMIT) ===
Repository: https://github.com/pallets/click
Checked-Out Commit SHA: 3cbcf9b11546f4cf10b36d3e2e531733ba6fe001
Parent Workspace Tree: 79 total files (42 Python source files)
Discovered Test Files in Parent Tree: tests/test_basic.py, tests/test_commands.py, tests/test_compat.py, ...
Discovered Configuration Files in Parent Tree: setup.py, setup.cfg, tox.ini
```

---

## 8. Unit & Regression Testing Results

The full test suite was executed against the modified codebase:
```bash
python -m pytest tests/ -q
# 266 passed in 45.66s (0 failures, 0 errors, 0 warnings)
```
* **Unit Tests Passed:** 266 / 266 (100%)
* **Failures / Errors:** 0
* **Warnings:** 0

---

## 9. Baseline Artifact & Evaluation Safety Audit

* **Benchmark Cases Modified:** **NO** (All 6 cases retain exact authentic parent SHAs and issue texts)
* **Ground Truth Modified:** **NO** (Evaluator ground-truth validation remains unchanged)
* **Reference Patch Exposed:** **NO** (Strict information boundary confirmed)
* **M14-FREE Baseline Artifacts Modified:** **NO** (`evaluation/runs/run_20260902_125455_c3cc4e/` intact)
* **M15 Baseline Artifacts Modified:** **NO** (`evaluation/runs/run_20260903_143458_209eba/` intact)
* **LLM / API Calls Executed:** **NONE** (Zero live model calls made during implementation/validation)
* **Live Evaluation Status:** **NOT RUN** (Awaiting oversight review and authorization)

---

```
M16 IMPLEMENTATION COMPLETE — AWAITING OVERSIGHT AUTHORIZATION FOR LIVE EVALUATION
```

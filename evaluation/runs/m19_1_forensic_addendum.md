# Milestone 19.1 — Forensic Trajectory Analysis & Causality Audit Report

**Date:** 2026-09-04  
**Status:** M19.1 FORENSIC ANALYSIS COMPLETE  
**Milestone:** M19.1 (Analysis-Only)  
**Control Baselines:** M17 (`run_20260904_101007_ea3d13`) and M18 (`run_20260904_143651_9b10ba`)  
**Intervention Baseline (M19):** `run_20260904_174600_cdd7b6`  
**Model:** `nvidia/nemotron-3-ultra-550b-a55b:free` (OpenRouter API)  
**Population:** Exactly 6 `GROUND_TRUTH_VERIFIED` authentic benchmark cases  

---

## 1. Executive Summary & Causal Attribution

Milestone 19 tested hypothesis **H7**:
> *Restoring the verbatim rejected-plan JSON scaffold while retaining compact diagnostics recovers planning validity and repair-loop completion without triggering output budget exhaustion.*

### Forensic Answers to Core Evaluation Questions:
1. **Did the intervention change the intended mechanism?**  
   **YES (SUPPORTED).** Restoring the JSON scaffold directly re-established the working-memory template for `nvidia/nemotron-3-ultra-550b-a55b:free`. Planning validity rebounded from 1/6 (16.7%) to 4/6 (66.7%), and downstream reach rebounded from 1/6 to 4/6.
2. **Did it improve repair recovery?**  
   **YES (SUPPORTED).** Syntax recoveries reached an all-time benchmark record: **3 cases successfully repaired pre-execution syntax defects** (`REAL-CLICK-02`, `REAL-MARSHMALLOW-01`, and `REAL-MARSHMALLOW-04`). In M18, 0 cases recovered.
3. **Did it improve end-to-end task resolution?**  
   **NO (NOT SUPPORTED).** Resolution remained strictly **0 / 6 (0.0%)**.
4. **Why did resolution remain 0/6?**  
   Removing upstream syntax and planning blocks allowed trajectories to advance downstream, where they hit two fundamental barriers:
   - **Downstream Edit Representation (Anchor Drift):** In 3 of the 4 valid cases (`CLICK-02`, `MARSH-02`, `MARSH-04`), repairing syntax in subsequent turns led the model to alter subtle characters in its `search_content` anchor strings, causing `SafeFileEditor` to fail closed with `search_content was not found`.
   - **Dynamic Verification Environment Mismatch:** In the single case that applied edits to disk (`MARSH-01`), dynamic `pytest` execution failed due to post-edit AST errors or historical test harness mismatches (exit codes 2 and 4, zero executed assertions).

---

## 2. Hypothesis Status Classification

| Hypothesis | Classification | Causal Evidence |
| :--- | :---: | :--- |
| **H1 (Retrieval Recall)** | **SUPPORTED** | Target files retrieved at Recall@3 = 66.7%, Recall@5 = 83.3%, MRR = 0.467 across all runs. Retrieval is not the bottleneck. |
| **H2 (Anchor Resolution)** | **PARTIALLY SUPPORTED** | SafeFileEditor 3-tier matcher resolves fuzzy formatting on turn 1, but cannot overcome complete anchor drift across repair turns. |
| **H3 (Historical Grounding)**| **PARTIALLY SUPPORTED**| Prevents hallucinated external dependencies, but does not fix test runner environment divergence. |
| **H5 (Pre-Exec AST Gate)** | **SUPPORTED** | Intercepted 15 syntax defects before disk execution in M19, enabling 3 complete in-memory recoveries. |
| **H6 (Diagnostic Compaction)**| **PARTIALLY SUPPORTED**| Diagnostic single-lining (H6-A) is clean and effective. Plan outline compaction (H6-B) caused severe regression. |
| **H7 (Scaffold Restoration)** | **SUPPORTED** | Fully restored planning validity (66.7%) and execution reach (66.7%). |
| **End-to-End Resolution** | **NOT SUPPORTED (0/6)**| Fundamental model code-synthesis capability ceiling and historical benchmark harness limitations prevent task resolution. |

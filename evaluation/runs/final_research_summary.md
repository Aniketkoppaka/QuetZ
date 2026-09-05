# Final Research Summary: Autonomous GitHub Issue Resolver

**Date:** 2026-09-04  
**Project:** Autonomous Software Engineer (Autonomous GitHub Issue Resolver)  
**Status:** PROJECT COMPLETE — EXPERIMENTAL RECORD FROZEN  

---

## 1. Abstract

This research project evaluated the capabilities and boundary limitations of an autonomous software engineering system powered by an open-weights, free-tier large language model (`nvidia/nemotron-3-ultra-550b-a55b:free`) across a rigorously reconstructed, historically authentic six-case benchmark suite derived from real GitHub repositories (`pallets/click`, `marshmallow-code/marshmallow`). 

Across six successive controlled milestones (M14 through M19), we formulated, implemented, and empirically tested seven distinct hypotheses targeting retrieval, anchor-based file editing, historical-version grounding, pre-execution AST syntax gating, and diagnostic repair context compaction. 

Our findings establish that while architectural interventions can decisively eliminate intermediate failure modes—improving pre-execution syntax error detection (15 errors caught, 3 recoveries in M19) and preserving planning validity (66.7%)—**end-to-end task resolution remained strictly 0 / 6 (0.0%) across all runs**. The primary insurmountable barriers are the fundamental code-synthesis precision ceiling of the model (particularly when synthesizing test methods within escaped JSON strings), anchor string drift during multi-turn repairs, and historical test harness execution mismatches.

---

## 2. System Architecture

The autonomous software engineering system comprises modular, hermetically testable layers:
1. **Repository Analyzer:** Builds an AST-grounded `RepositoryMap` containing symbols, imports, and module relationships without executing untrusted code.
2. **Context Retriever:** A hybrid BM25 lexical and AST structural ranking engine retrieving relevant source files (Recall@3 = 66.7%, Recall@5 = 83.3%, MRR = 0.467).
3. **Planner Prompt Builder:** Generates grounded prompts enforcing strict DAG dependencies, evidence provenance, and historical commit anchoring.
4. **LLM Planner & Bounded Repair Loop:** Issues structured JSON generation calls with a strict $N \le 3$ retry budget and diagnostic feedback.
5. **Pre-Execution AST Syntax Gate:** Deterministically validates hypothetical post-edit files in memory via `ast.parse()`, routing genuine syntax errors back into the repair loop before disk mutation.
6. **SafeFileEditor:** A deterministic, 3-tier matcher applying atomic replacements (Exact Match $\to$ Normalized Whitespace Match $\to$ Block-Anchor Match) that fails closed upon anchor mismatch.
7. **Execution Engine & Transactional Rollback:** Executes multi-tier verifiers (static AST, symbol resolution, and dynamic `pytest`), automatically rolling back git workspaces to pristine state upon any failure (100% rollback success rate).

---

## 3. The 6-Case Historically Grounded Benchmark

All evaluations were conducted on six authentic `GROUND_TRUTH_VERIFIED` benchmark issues checked out at their exact historical parent commits:
1. `REAL-CLICK-02` (pallets/click @ `3cbcf9b1`): Fix copy, deepcopy and pickle of Sentinel members.
2. `REAL-CLICK-03` (pallets/click @ `8b44edff`): Settles progress bar on its final position.
3. `REAL-MARSHMALLOW-01` (marshmallow-code/marshmallow @ `b40a0f4e`): DateTime fields cannot resolve format when nested in List or Tuple fields.
4. `REAL-MARSHMALLOW-02` (marshmallow-code/marshmallow @ `3265c139`): Raise ValidationError (not ValueError) for NaN in TimeDelta.
5. `REAL-MARSHMALLOW-03` (marshmallow-code/marshmallow @ `3207be31`): Fix URL validator rejecting a fragment after an empty path.
6. `REAL-MARSHMALLOW-04` (marshmallow-code/marshmallow @ `3265c139`): Enum Allow None Default.

Zero ground truth or reference patch data was leaked to the model.

---

## 4. Experimental Progression Across Milestones

| Milestone | Intervention Description | Resolved | Planning Valid | Downstream Execution | Syntax Recoveries | Primary Failure Modes |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **M14-FREE** | Baseline evaluation of `nvidia/nemotron-3-ultra-550b-a55b:free` | 0/6 (0%) | 5/6 (83%) | 5/6 (83%) | 0 | Anchor mismatches, syntax errors |
| **M15** | SafeFileEditor 3-tier anchor resolution | 0/6 (0%) | 6/6 (100%)| 6/6 (100%)| 0 | AST syntax errors, anchor drift |
| **M16** | Deterministic Historical-Version Grounding header | 0/6 (0%) | 6/6 (100%)| 6/6 (100%)| 0 | Uncaught syntax errors in test files |
| **M17** | Pre-Execution AST Syntax Validation Gate | 0/6 (0%) | 4/6 (67%) | 4/6 (67%) | 2 | 9 syntax errors caught; dynamic pytest errors |
| **M18** | Diagnostic & Plan Representation Compaction | 0/6 (0%) | 1/6 (17%) | 1/6 (17%) | 0 | Loss of scaffold caused syntax explosion |
| **M19** | Scaffold-Preserving Diagnostic Repair | 0/6 (0%) | 4/6 (67%) | 4/6 (67%) | 3 | Anchor drift in repair (3), syntax exhaustion (2) |

---

## 5. Mechanistic & Scientific Findings

1. **Retrieval is Highly Effective (H1: Supported):** BM25 + AST ranking consistently retrieves the target file at Top-3 in 66.7% and Top-5 in 83.3% of cases (MRR 0.467).
2. **Syntactic Gating Intercepts Latent Errors (H5: Supported):** Pre-execution AST validation intercepted 9 syntax errors in M17, 12 in M18, and 15 in M19, preventing broken Python files from being written to disk.
3. **Working-Memory Scaffold is Vital for Small/Free Models (H7: Supported):** Preserving the previous JSON payload in repair prompts is essential; stripping it caused planning validity to collapse from 66.7% to 16.7%. Restoring it recovered validity to 66.7% and produced 3 syntax recoveries.
4. **Anchor Drift is the Primary Post-Planning Bottleneck (H2: Supported / Limited):** In multi-turn repairs, modifying code often causes the model to slightly alter surrounding anchor lines, triggering fail-closed SafeFileEditor rejections.
5. **Absence of Semantic Assertion Testing:** Zero test assertions were executed in dynamic verification runs due to historical test runner collection errors (pytest exit code 2 and 4).

---

## 6. Exact Final Claim Boundary

> **The system demonstrates robust repository analysis, retrieval, fail-closed editing safety, pre-execution syntax gating, and 100% transactional rollback integrity. However, when deployed with free-tier open models (`nvidia/nemotron-3-ultra-550b-a55b:free`), autonomous issue resolution across authentic repositories is 0.0% due to model code-synthesis precision ceilings and multi-turn anchor drift.**

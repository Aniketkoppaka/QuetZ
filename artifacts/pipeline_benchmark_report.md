# ASE Autonomous Pipeline Benchmark Report

- **Generated At**: `2026-09-05T17:29:16.354211+00:00`
- **Total Scenarios Evaluated**: 5
- **Benchmark Accuracy**: `100.0%` (5/5)
- **Resolved (Completed)**: 3
- **Abstained (Safe Fallback)**: 1
- **Failed**: 1
- **Reproduction Grounded Fixes**: 1

| Scenario ID | Expected | Actual | Matched | Skills Matched | Verdict |
|---|---|---|---|---|---|
| `bench-01-reproduced-fix` | `completed` | `completed` | [MATCH] | none | approved |
| `bench-02-vacuous-rejection` | `abstained` | `abstained` | [MATCH] | python_bug_fix | n/a |
| `bench-03-multi-module-api-migration` | `completed` | `completed` | [MATCH] | none | approved |
| `bench-04-mutation-verification` | `completed` | `completed` | [MATCH] | dependency_upgrade | approved |
| `bench-05-unauthorized-rejection` | `failed` | `failed` | [MATCH] | none | n/a |
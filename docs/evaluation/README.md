# Evaluation Documentation

This directory contains documentation about the evaluation strategy and
benchmark results for the autonomous-software-engineer system.

## Planned Evaluation Approach

- **Primary benchmark:** SWE-bench (or a curated subset thereof)
- **Key metric:** Issue resolve rate (% of issues where final tests pass)
- **Secondary metrics:** Iteration count, time-to-patch, token cost
- **Evaluation harness:** `autonomous_engineer.evaluation` package

## Status

Evaluation harness is not yet implemented (planned: Milestone 10).

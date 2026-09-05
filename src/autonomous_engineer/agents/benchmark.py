"""
agents/benchmark.py -- Planning evaluation and validation benchmark harness.

Provides:
1. PlanningValidationBenchmark: Tests deterministic PlanValidator error detection against synthetic fault injections.
2. PlannerBenchmarkHarness: Evaluates LLMPlanner instances across 10 diverse issue categories.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.agents.planner import LLMPlanner, PlanningResult
from autonomous_engineer.agents.protocol import PlannerInput
from autonomous_engineer.agents.validator import PlanValidationResult, PlanValidator
from autonomous_engineer.domain.models import ImplementationPlan


# ---------------------------------------------------------------------------
# 1. Validator Benchmark (Evaluation of PlanValidator Correctness)
# ---------------------------------------------------------------------------


class PlanningBenchmarkTestCase(BaseModel):
    """A test case in the planning validation benchmark."""

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(description="Unique benchmark test case identifier")
    name: str = Field(description="Human-readable title of test case")
    category: str = Field(description="Fault category tested")
    plan: ImplementationPlan = Field(description="Plan subjected to validation")
    planner_input: PlannerInput = Field(description="Grounding input contract")
    should_be_valid: bool = Field(description="True if the plan is expected to pass validation")
    expected_error_types: tuple[str, ...] = Field(
        default=(),
        description="Expected validation error types if plan is invalid",
    )
    rationale: str = Field(default="", description="Explanation of test scenario")


@dataclass(frozen=True)
class ValidationBenchmarkReport:
    """Statistical summary of planning validator performance against benchmark suite."""

    total_cases: int
    correctly_classified: int
    accuracy: float
    false_positives: int  # Valid plans erroneously rejected
    false_negatives: int  # Invalid plans erroneously accepted
    detected_error_types: tuple[str, ...]
    case_results: tuple[dict[str, Any], ...]


class PlanningValidationBenchmark:
    """Executes validation over planning benchmark test suites."""

    def run(
        self,
        test_cases: list[PlanningBenchmarkTestCase] | tuple[PlanningBenchmarkTestCase, ...],
        validator: PlanValidator | None = None,
    ) -> ValidationBenchmarkReport:
        """
        Evaluate PlanValidator across all benchmark test cases.
        """
        v = validator or PlanValidator()
        total = len(test_cases)
        correct = 0
        fp = 0
        fn = 0
        detected_types: set[str] = set()
        case_results: list[dict[str, Any]] = []

        for tc in test_cases:
            res: PlanValidationResult = v.validate(tc.plan, tc.planner_input)
            actual_error_types = {e.error_type for e in res.errors}
            detected_types.update(actual_error_types)

            matched_validity = (res.is_valid == tc.should_be_valid)

            if matched_validity:
                correct += 1
            else:
                if tc.should_be_valid and not res.is_valid:
                    fp += 1
                elif not tc.should_be_valid and res.is_valid:
                    fn += 1

            case_results.append(
                {
                    "case_id": tc.case_id,
                    "name": tc.name,
                    "category": tc.category,
                    "expected_valid": tc.should_be_valid,
                    "actual_valid": res.is_valid,
                    "expected_errors": tc.expected_error_types,
                    "actual_errors": tuple(actual_error_types),
                    "passed": matched_validity,
                }
            )

        accuracy = round(correct / total, 4) if total > 0 else 1.0

        return ValidationBenchmarkReport(
            total_cases=total,
            correctly_classified=correct,
            accuracy=accuracy,
            false_positives=fp,
            false_negatives=fn,
            detected_error_types=tuple(sorted(detected_types)),
            case_results=tuple(case_results),
        )


# ---------------------------------------------------------------------------
# 2. Planner Benchmark (Evaluation of LLMPlanner End-to-End Generation)
# ---------------------------------------------------------------------------


class PlannerBenchmarkScenario(BaseModel):
    """A realistic issue scenario for end-to-end LLM planning evaluation."""

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(description="Unique benchmark scenario identifier (e.g. 'A-EXACT-ID')")
    name: str = Field(description="Descriptive name")
    category: str = Field(
        description="Category: 'exact_identifier', 'behavioral', 'error_message', 'multi_file', "
                    "'indirect_dependency', 'test_related', 'configuration', 'distractor', "
                    "'ambiguous', 'insufficient_context'",
    )
    planner_input: PlannerInput = Field(description="Complete grounding input for the planner")
    expected_affected_files: tuple[str, ...] = Field(
        default=(),
        description="Files expected to be targeted in valid plans",
    )
    expected_symbols: tuple[str, ...] = Field(
        default=(),
        description="Symbols expected to be modified or referenced",
    )
    requires_uncertainty_or_assumptions: bool = Field(
        default=False,
        description="True if scenario intentionally requires declaring assumptions/uncertainties",
    )
    description: str = Field(default="")


@dataclass(frozen=True)
class PlannerEvaluationReport:
    """Comprehensive evaluation metrics for an LLMPlanner across benchmark scenarios."""

    total_scenarios: int
    valid_plan_rate: float
    file_grounding_accuracy: float
    symbol_grounding_accuracy: float
    evidence_validity_rate: float
    dependency_validity_rate: float
    repair_success_rate: float
    first_attempt_valid_count: int
    first_attempt_invalid_count: int
    repaired_successfully_count: int
    failed_repair_count: int
    max_attempts: int
    average_attempts: float
    case_results: tuple[dict[str, Any], ...]


class PlannerBenchmarkHarness:
    """Evaluates an LLMPlanner implementation against a suite of planning scenarios."""

    def evaluate(
        self,
        planner: LLMPlanner,
        scenarios: list[PlannerBenchmarkScenario] | tuple[PlannerBenchmarkScenario, ...],
    ) -> PlannerEvaluationReport:
        """
        Run LLMPlanner across scenarios and compute aggregate metrics.
        """
        total = len(scenarios)
        if total == 0:
            return PlannerEvaluationReport(
                total_scenarios=0,
                valid_plan_rate=0.0,
                file_grounding_accuracy=0.0,
                symbol_grounding_accuracy=0.0,
                evidence_validity_rate=0.0,
                dependency_validity_rate=0.0,
                repair_success_rate=0.0,
                first_attempt_valid_count=0,
                first_attempt_invalid_count=0,
                repaired_successfully_count=0,
                failed_repair_count=0,
                max_attempts=0,
                average_attempts=0.0,
                case_results=(),
            )

        valid_count = 0
        file_grounding_hits = 0
        symbol_grounding_hits = 0
        evidence_valid_count = 0
        dependency_valid_count = 0
        first_attempt_valid_count = 0
        first_attempt_invalid_count = 0
        repaired_successfully_count = 0
        failed_repair_count = 0
        max_attempts_seen = 0
        total_attempts_sum = 0
        case_results: list[dict[str, Any]] = []

        for sc in scenarios:
            res: PlanningResult = planner.plan_with_audit(sc.planner_input)
            total_attempts_sum += res.total_attempts
            max_attempts_seen = max(max_attempts_seen, res.total_attempts)

            is_valid = res.is_valid and res.plan is not None
            if is_valid:
                valid_count += 1

            if res.total_attempts == 1:
                if is_valid:
                    first_attempt_valid_count += 1
                else:
                    first_attempt_invalid_count += 1
            else:
                first_attempt_invalid_count += 1
                if is_valid:
                    repaired_successfully_count += 1
                else:
                    failed_repair_count += 1

            # Detailed checks on generated plan
            file_match = False
            symbol_match = False
            ev_valid = False
            dep_valid = False

            if res.plan is not None:
                plan = res.plan
                # Check affected files
                actual_files = set(plan.affected_files)
                if sc.expected_affected_files:
                    if any(f in actual_files for f in sc.expected_affected_files):
                        file_grounding_hits += 1
                        file_match = True
                else:
                    file_grounding_hits += 1
                    file_match = True

                # Check symbols
                actual_symbols = {s.target_symbol for s in plan.steps if s.target_symbol}
                if sc.expected_symbols:
                    if any(sym in actual_symbols for sym in sc.expected_symbols):
                        symbol_grounding_hits += 1
                        symbol_match = True
                else:
                    symbol_grounding_hits += 1
                    symbol_match = True

                # Check evidence validity
                if all(s.evidence is not None and s.evidence.source.value != "unsupported" for s in plan.steps):
                    evidence_valid_count += 1
                    ev_valid = True

                # Check dependency validity
                if not any(e.error_type in ("circular_dependency", "self_dependency", "unknown_dependency") for e in res.validation_result.errors):
                    dependency_valid_count += 1
                    dep_valid = True

            case_results.append(
                {
                    "case_id": sc.case_id,
                    "name": sc.name,
                    "category": sc.category,
                    "is_valid": is_valid,
                    "attempts": res.total_attempts,
                    "file_match": file_match,
                    "symbol_match": symbol_match,
                    "evidence_valid": ev_valid,
                    "dependency_valid": dep_valid,
                    "errors": [e.message for e in res.validation_result.errors],
                }
            )

        valid_rate = round(valid_count / total, 4)
        file_acc = round(file_grounding_hits / total, 4)
        sym_acc = round(symbol_grounding_hits / total, 4)
        ev_rate = round(evidence_valid_count / total, 4)
        dep_rate = round(dependency_valid_count / total, 4)
        total_rep_attempts = repaired_successfully_count + failed_repair_count
        rep_rate = round(repaired_successfully_count / total_rep_attempts, 4) if total_rep_attempts > 0 else 1.0
        avg_att = round(total_attempts_sum / total, 2)

        return PlannerEvaluationReport(
            total_scenarios=total,
            valid_plan_rate=valid_rate,
            file_grounding_accuracy=file_acc,
            symbol_grounding_accuracy=sym_acc,
            evidence_validity_rate=ev_rate,
            dependency_validity_rate=dep_rate,
            repair_success_rate=rep_rate,
            first_attempt_valid_count=first_attempt_valid_count,
            first_attempt_invalid_count=first_attempt_invalid_count,
            repaired_successfully_count=repaired_successfully_count,
            failed_repair_count=failed_repair_count,
            max_attempts=max_attempts_seen,
            average_attempts=avg_att,
            case_results=tuple(case_results),
        )
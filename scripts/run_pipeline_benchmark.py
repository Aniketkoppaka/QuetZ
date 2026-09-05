"""
scripts/run_pipeline_benchmark.py -- Live Benchmark & Self-Assessment Runner (Addition 3).

Executes the unified AutonomousPipeline across curated benchmark scenarios:
  1. python_bug_fix with verified reproduction
  2. vacuous_test_rejection (ensuring the system safely abstains)
  3. syntax_mutation_verification (ensuring mutation testing catches alterations)

Generates a machine-readable JSON report and a formatted Markdown report in artifacts/.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Add src to sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from autonomous_engineer.domain.models import (
    ImplementationPlan,
    ImplementationStep,
    Issue,
    Repository,
    StepOperation,
)
from autonomous_engineer.domain.states import WorkflowPhase
from autonomous_engineer.evaluation.pipeline_eval import (
    BenchmarkScenario,
    PipelineBenchmarkHarness,
)
from autonomous_engineer.orchestration.pipeline import (
    AutonomousPipeline,
    PipelineConfig,
)
from autonomous_engineer.repository.analyzer import RepositoryAnalyzer
from autonomous_engineer.verification.reproduction import ReproductionCandidate


def run_benchmark() -> int:
    print("=" * 70)
    print("Starting Live ASE Autonomous Pipeline Benchmark Run")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Build sample module & test in temp workspace
        app_file = tmp_path / "calc.py"
        app_file.write_text(
            "def safe_divide(a, b):\n    return a / b\n",
            encoding="utf-8",
        )
        test_file = tmp_path / "test_calc.py"
        test_file.write_text(
            "from calc import safe_divide\n\n"
            "def test_division():\n"
            "    assert safe_divide(10, 2) == 5\n\n"
            "def test_divide_by_zero():\n"
            "    assert safe_divide(10, 0) == 0\n",
            encoding="utf-8",
        )

        repo = Repository(
            url="file://" + str(tmp_path),
            workspace_path=tmp_path,
            commit_sha="bench_head",
        )

        analyzer = RepositoryAnalyzer()
        repo_map = analyzer.analyze(repo)

        # Scenario 1: Legitimate bug fix (ZeroDivisionError handling)
        issue_1 = Issue(
            id="bench/issue#1",
            title="ZeroDivisionError in safe_divide",
            body="safe_divide crashes when divisor b is 0. Should return 0.0.",
            repository_url=repo.url,
        )
        repro_1 = ReproductionCandidate(
            test_command="pytest test_calc.py -k test_divide_by_zero",
            expected_failure_pattern="ZeroDivisionError",
        )
        plan_1 = ImplementationPlan(
            plan_id="plan-bench-1",
            issue_id=issue_1.id,
            summary="Handle zero divisor gracefully",
            rationale="Return 0.0 if b == 0 else a / b",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    target_file="calc.py",
                    operation=StepOperation.MODIFY_SYMBOL,
                    description="Return 0.0 on zero division",
                    search_content="return a / b",
                    replace_content="return 0.0 if b == 0 else a / b",
                ),
            ),
        )
        sc_1 = BenchmarkScenario(
            scenario_id="bench-01-reproduced-fix",
            issue=issue_1,
            expected_outcome=WorkflowPhase.COMPLETED,
            reproduction_candidate=repro_1,
            description="Fix zero division error with reproduction proof",
        )

        # Scenario 2: Vacuous test attempt (require_reproduction rejects tests that pass pre-patch)
        issue_2 = Issue(
            id="bench/issue#2",
            title="Spurious bug report for normal division",
            body="Division by 2 supposedly broken.",
            repository_url=repo.url,
        )
        repro_2 = ReproductionCandidate(
            test_command="pytest test_calc.py -k test_division",
        )
        plan_2 = ImplementationPlan(
            plan_id="plan-bench-2",
            issue_id=issue_2.id,
            summary="No-op change",
            rationale="Unnecessary change",
            steps=(
                ImplementationStep(
                    step_id="step-noop-1",
                    target_file="calc.py",
                    operation=StepOperation.MODIFY_SYMBOL,
                    description="No-op step",
                ),
            ),
        )
        sc_2 = BenchmarkScenario(
            scenario_id="bench-02-vacuous-rejection",
            issue=issue_2,
            expected_outcome=WorkflowPhase.ABSTAINED,
            reproduction_candidate=repro_2,
            description="Reject candidate test that already passes on unpatched code",
        )

        # Scenario 3: Multi-file API migration & deprecation
        api_core = tmp_path / "core.py"
        api_core.write_text("def legacy_compute(x):\n    return x * 2\n", encoding="utf-8")
        api_consumer = tmp_path / "consumer.py"
        api_consumer.write_text("from core import legacy_compute\ndef process(val):\n    return legacy_compute(val) + 1\n", encoding="utf-8")
        api_test = tmp_path / "test_consumer.py"
        api_test.write_text("from consumer import process\ndef test_consumer_flow():\n    assert process(5) == 11\n", encoding="utf-8")

        repo_map = analyzer.analyze(repo)

        issue_3 = Issue(
            id="bench/issue#3",
            title="Migrate legacy_compute to modernized compute_v2",
            body="Deprecated legacy_compute must be upgraded to compute_v2 across core and consumer.",
            repository_url=repo.url,
        )
        plan_3 = ImplementationPlan(
            plan_id="plan-bench-3",
            issue_id=issue_3.id,
            summary="Refactor legacy_compute to compute_v2 with backwards-compatible alias",
            rationale="Maintain backward compatibility while introducing modernized function",
            steps=(
                ImplementationStep(
                    step_id="step-api-1",
                    target_file="core.py",
                    operation=StepOperation.MODIFY_SYMBOL,
                    search_content="def legacy_compute(x):\n    return x * 2",
                    replace_content="def compute_v2(x):\n    return x * 2\n\nlegacy_compute = compute_v2",
                    description="Introduce compute_v2 and alias legacy_compute",
                ),
            ),
        )
        sc_3 = BenchmarkScenario(
            scenario_id="bench-03-multi-module-api-migration",
            issue=issue_3,
            expected_outcome=WorkflowPhase.COMPLETED,
            description="Multi-module API upgrade with backward-compatible alias",
        )

        # Scenario 4: Mutation testing catches unverified behavioral change
        calc_extra = tmp_path / "validator.py"
        calc_extra.write_text("def is_positive(n: int) -> bool:\n    return n > 0\n", encoding="utf-8")
        test_extra = tmp_path / "test_validator.py"
        test_extra.write_text("from validator import is_positive\ndef test_positive():\n    assert is_positive(5) is True\n", encoding="utf-8")

        repo_map = analyzer.analyze(repo)

        issue_4 = Issue(
            id="bench/issue#4",
            title="Update is_positive threshold boundary",
            body="Non-negative numbers should be treated as positive.",
            repository_url=repo.url,
        )
        plan_4 = ImplementationPlan(
            plan_id="plan-bench-4",
            issue_id=issue_4.id,
            summary="Update boundary to include zero",
            rationale="Allow zero as positive",
            steps=(
                ImplementationStep(
                    step_id="step-val-1",
                    target_file="validator.py",
                    operation=StepOperation.MODIFY_SYMBOL,
                    search_content="return n > 0",
                    replace_content="return n >= 0",
                    description="Change strict inequality to non-negative",
                ),
            ),
        )
        sc_4 = BenchmarkScenario(
            scenario_id="bench-04-mutation-verification",
            issue=issue_4,
            expected_outcome=WorkflowPhase.COMPLETED,
            description="Verify behavioral modification under mutation testing",
        )

        # Scenario 5: Unauthorized file modification rejected fail-closed
        issue_5 = Issue(
            id="bench/issue#5",
            title="Unauthorized edit outside target scope",
            body="Attempt to modify ungrounded security configuration.",
            repository_url=repo.url,
        )
        plan_5 = ImplementationPlan(
            plan_id="plan-bench-5",
            issue_id=issue_5.id,
            summary="Unauthorized modification",
            rationale="Attempting edit on missing file",
            steps=(
                ImplementationStep(
                    step_id="step-unauth-1",
                    target_file="secret_credentials.py",
                    operation=StepOperation.MODIFY_SYMBOL,
                    search_content="secret = 123",
                    replace_content="secret = 456",
                    description="Unauthorized edit",
                ),
            ),
        )
        sc_5 = BenchmarkScenario(
            scenario_id="bench-05-unauthorized-rejection",
            issue=issue_5,
            expected_outcome=WorkflowPhase.FAILED,
            description="Fail-closed rejection of ungrounded file modification",
        )

        harness = PipelineBenchmarkHarness()
        config = PipelineConfig(
            require_reproduction=True,
            run_mutation_testing=True,
        )

        suite = [
            (sc_1, repo, repo_map, plan_1),
            (sc_2, repo, repo_map, plan_2),
            (sc_3, repo, repo_map, plan_3),
            (sc_4, repo, repo_map, plan_4),
            (sc_5, repo, repo_map, plan_5),
        ]

        print("Executing benchmark suite through PipelineBenchmarkHarness...")
        report = harness.run_suite(suite, config=config)

        print("\n" + report.to_markdown())

        # Persist report
        artifacts_dir = repo_root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        report_file = artifacts_dir / "pipeline_benchmark_report.md"
        report_file.write_text(report.to_markdown(), encoding="utf-8")
        print(f"\nArtifact persisted to: {report_file}")

    return 0


if __name__ == "__main__":
    sys.exit(run_benchmark())

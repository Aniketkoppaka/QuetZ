"""
tests/unit/test_mutation.py -- Tests for Phase 3.3 Mutation-Based Assertion Strength Checker.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autonomous_engineer.domain.models import StepOperation
from autonomous_engineer.execution.models import (
    ExecutionPolicy,
    FileChangeRecord,
    VerificationResult,
    VerificationType,
)
from autonomous_engineer.verification.mutation import (
    AstMutantGenerator,
    MutantDefinition,
    MutantStatus,
    MutationOperatorType,
    MutationReport,
    MutationTester,
)


class TestAstMutantGenerator:
    def test_generates_comparison_mutants(self):
        generator = AstMutantGenerator()
        code = "def is_positive(x):\n    return x > 0\n"
        mutants = generator.generate_mutants(code, "utils.py")

        assert len(mutants) >= 1
        m_def, m_src = mutants[0]
        assert m_def.operator_type == MutationOperatorType.COMPARE_OP_FLIP
        assert "<=" in m_src or "x <= 0" in m_src

    def test_generates_boolean_constant_mutants(self):
        generator = AstMutantGenerator()
        code = "def get_flag():\n    return True\n"
        mutants = generator.generate_mutants(code, "flags.py")

        assert len(mutants) >= 1
        m_def, m_src = mutants[0]
        assert m_def.operator_type == MutationOperatorType.BOOLEAN_CONSTANT_FLIP
        assert "False" in m_src

    def test_generates_bool_op_mutants(self):
        generator = AstMutantGenerator()
        code = "def check(a, b):\n    return a and b\n"
        mutants = generator.generate_mutants(code, "logic.py")

        assert len(mutants) >= 1
        m_def, m_src = mutants[0]
        assert m_def.operator_type == MutationOperatorType.BOOL_OP_FLIP
        assert "or" in m_src

    def test_generates_arithmetic_mutants(self):
        generator = AstMutantGenerator()
        code = "def add(a, b):\n    return a + b\n"
        mutants = generator.generate_mutants(code, "math.py")

        assert len(mutants) >= 1
        m_def, m_src = mutants[0]
        assert m_def.operator_type == MutationOperatorType.ARITH_OP_FLIP
        assert "-" in m_src

    def test_syntax_error_returns_empty(self):
        generator = AstMutantGenerator()
        mutants = generator.generate_mutants("def broken(:", "broken.py")
        assert mutants == []


class TestMutationTester:
    def test_all_mutants_killed_yields_perfect_score(self, tmp_path: Path):
        py_file = tmp_path / "calc.py"
        original_code = "def check(x):\n    return x > 0\n"
        py_file.write_text(original_code, encoding="utf-8")

        mock_verifier = MagicMock()
        # When test runs against mutant, it fails (mutant killed)
        mock_verifier.verify_tests.return_value = VerificationResult(
            verification_type=VerificationType.SUBPROCESS_TEST,
            target="pytest",
            passed=False,
            exit_code=1,
            error_message="Test failed on mutant",
        )

        tester = MutationTester(verifier=mock_verifier)
        change = FileChangeRecord(
            file_path="calc.py",
            operation=StepOperation.MODIFY_SYMBOL,
        )

        report = tester.evaluate_mutations(
            workspace=tmp_path,
            changes=(change,),
            policy=ExecutionPolicy(),
            max_mutants_total=2,
        )

        assert report.total_mutants_tested == 1
        assert report.mutants_killed == 1
        assert report.mutants_survived == 0
        assert report.mutation_score == 1.0
        # Check that file content was restored
        assert py_file.read_text(encoding="utf-8") == original_code

    def test_survived_mutant_lowers_score(self, tmp_path: Path):
        py_file = tmp_path / "calc.py"
        original_code = "def check(x):\n    return x > 0\n"
        py_file.write_text(original_code, encoding="utf-8")

        mock_verifier = MagicMock()
        # When test runs against mutant, it passes (mutant survived)
        mock_verifier.verify_tests.return_value = VerificationResult(
            verification_type=VerificationType.SUBPROCESS_TEST,
            target="pytest",
            passed=True,
            exit_code=0,
        )

        tester = MutationTester(verifier=mock_verifier)
        change = FileChangeRecord(
            file_path="calc.py",
            operation=StepOperation.MODIFY_SYMBOL,
        )

        report = tester.evaluate_mutations(
            workspace=tmp_path,
            changes=(change,),
            policy=ExecutionPolicy(),
            max_mutants_total=2,
        )

        assert report.total_mutants_tested == 1
        assert report.mutants_killed == 0
        assert report.mutants_survived == 1
        assert report.mutation_score == 0.0
        assert py_file.read_text(encoding="utf-8") == original_code

    def test_no_python_changes_returns_safe_report(self, tmp_path: Path):
        tester = MutationTester()
        change = FileChangeRecord(
            file_path="README.md",
            operation=StepOperation.MODIFY_SYMBOL,
        )
        report = tester.evaluate_mutations(
            workspace=tmp_path,
            changes=(change,),
            policy=ExecutionPolicy(),
        )
        assert report.total_mutants_tested == 0
        assert report.mutation_score == 1.0


class TestMutationReport:
    def test_to_markdown(self):
        report = MutationReport(
            total_mutants_tested=5,
            mutants_killed=4,
            mutants_survived=1,
            mutation_score=0.8,
        )
        md = report.to_markdown()
        assert "Mutation-Based Verification Strength Report" in md
        assert "80.0%" in md
        assert "STRONG TEST RIGOR" in md

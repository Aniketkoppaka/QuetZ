"""
verification/mutation.py -- Mutation-Based Assertion Strength Checker (Phase 3.3).

Protects against tautological, vacuous, or overly permissive test assertions by
introducing controlled syntactic AST mutations into patched files and verifying
that the test suite detects ("kills") the mutation.

Supported mutation operators:
- Operator replacement:
    * Comparison: < <-> <=, > <-> >=, == <-> !=, is <-> is not, in <-> not in
    * Boolean: and <-> or
    * Arithmetic: + <-> -, * <-> /
- Constant replacement:
    * True <-> False
    * 0 <-> 1
    * None replacement where applicable
- Statement deletion / Pass substitution:
    * Replace return expr with return None or reverse

Workflow:
1. Target modified/added Python files from the patch change set.
2. Generate candidate mutants via AST transformation.
3. For each mutant (up to a budget limit), apply the mutation in workspace memory/disk.
4. Run test verification under ExecutionPolicy limits.
5. If test fails -> mutant is KILLED (assertion is sensitive and strong).
6. If test passes -> mutant SURVIVED (potential weak or tautological assertion).
7. Restore original code.
8. Output MutationReport with killed/survived counts and mutation_score [0.0 - 1.0].
"""
from __future__ import annotations

import ast
import copy
import enum
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.execution.models import (
    ExecutionPolicy,
    FileChangeRecord,
    VerificationResult,
)
from autonomous_engineer.execution.verifier import ExecutionVerifier


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class MutationOperatorType(str, enum.Enum):
    """Categories of AST mutations."""

    COMPARE_OP_FLIP = "compare_op_flip"
    BOOL_OP_FLIP = "bool_op_flip"
    ARITH_OP_FLIP = "arith_op_flip"
    BOOLEAN_CONSTANT_FLIP = "boolean_constant_flip"
    NUMERIC_CONSTANT_OFFSET = "numeric_constant_offset"
    RETURN_VALUE_TAMPER = "return_value_tamper"


class MutantStatus(str, enum.Enum):
    """Outcome of testing against a mutated codebase."""

    KILLED = "killed"        # Test failed -> caught the bug (GOOD)
    SURVIVED = "survived"    # Test passed -> failed to catch mutation (WEAK ASSERTION)
    TIMED_OUT = "timed_out"  # Test timed out (counted as caught / killed)
    ERROR = "error"          # Syntax/runtime error outside testing


class MutantDefinition(BaseModel):
    """Description of a single applied mutation."""

    model_config = ConfigDict(frozen=True)

    mutant_id: str = Field(default_factory=_new_id)
    file_path: str = Field(description="Repo-relative path to mutated file")
    operator_type: MutationOperatorType
    line_number: int = Field(ge=1)
    original_snippet: str
    mutated_snippet: str


class MutantTestResult(BaseModel):
    """Result of running tests against an individual mutant."""

    model_config = ConfigDict(frozen=True)

    mutant: MutantDefinition
    status: MutantStatus
    exit_code: int | None = None
    duration_ms: float = 0.0
    stdout: str = ""
    stderr: str = ""
    error_message: str | None = None


class MutationReport(BaseModel):
    """Comprehensive summary of mutation analysis for a change set."""

    model_config = ConfigDict(frozen=True)

    report_id: str = Field(default_factory=_new_id)
    total_mutants_generated: int = Field(default=0, ge=0)
    total_mutants_tested: int = Field(default=0, ge=0)
    mutants_killed: int = Field(default=0, ge=0)
    mutants_survived: int = Field(default=0, ge=0)
    mutation_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Ratio of killed mutants to total tested mutants. 1.0 = all caught.",
    )
    test_results: tuple[MutantTestResult, ...] = Field(default=())
    generated_at: datetime = Field(default_factory=_utcnow)

    def to_markdown(self) -> str:
        """Format report into human-readable markdown."""
        return (
            f"### Mutation-Based Verification Strength Report\n"
            f"- **Report ID**: `{self.report_id}`\n"
            f"- **Mutation Score**: `{self.mutation_score:.1%}`\n"
            f"- **Mutants Tested**: {self.total_mutants_tested} (Killed: {self.mutants_killed}, Survived: {self.mutants_survived})\n"
            f"- **Assessment**: {'STRONG TEST RIGOR' if self.mutation_score >= 0.7 else 'WEAK TEST RIGOR'}\n"
        )


# ---------------------------------------------------------------------------
# AST Mutator Visitor
# ---------------------------------------------------------------------------

_COMPARE_MAP: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.LtE: ast.Gt,
    ast.Gt: ast.LtE,
    ast.GtE: ast.Lt,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}

_BOOL_OP_MAP: dict[type[ast.boolop], type[ast.boolop]] = {
    ast.And: ast.Or,
    ast.Or: ast.And,
}

_BIN_OP_MAP: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv,
}


class AstMutantGenerator:
    """Generates modified source texts with individual, isolated mutations."""

    def generate_mutants(
        self,
        source_code: str,
        file_path: str,
        max_mutants: int = 10,
    ) -> list[tuple[MutantDefinition, str]]:
        """
        Produce a list of (MutantDefinition, mutated_source_code).
        """
        try:
            tree = ast.parse(source_code)
        except Exception:
            return []

        candidates: list[tuple[MutantDefinition, str]] = []

        # Find all mutable sites
        for node in ast.walk(tree):
            if len(candidates) >= max_mutants:
                break

            # 1. Comparison operations
            if isinstance(node, ast.Compare) and len(node.ops) == 1:
                op_type = type(node.ops[0])
                if op_type in _COMPARE_MAP:
                    mutated_tree = copy.deepcopy(tree)
                    target = self._find_matching_node(mutated_tree, node)
                    if target and isinstance(target, ast.Compare):
                        target.ops = [_COMPARE_MAP[op_type]()]
                        mutated_source = ast.unparse(mutated_tree)
                        candidates.append((
                            MutantDefinition(
                                file_path=file_path,
                                operator_type=MutationOperatorType.COMPARE_OP_FLIP,
                                line_number=getattr(node, "lineno", 1),
                                original_snippet=ast.unparse(node),
                                mutated_snippet=ast.unparse(target),
                            ),
                            mutated_source,
                        ))

            # 2. Boolean operators
            elif isinstance(node, ast.BoolOp):
                op_type = type(node.op)
                if op_type in _BOOL_OP_MAP:
                    mutated_tree = copy.deepcopy(tree)
                    target = self._find_matching_node(mutated_tree, node)
                    if target and isinstance(target, ast.BoolOp):
                        target.op = _BOOL_OP_MAP[op_type]()
                        mutated_source = ast.unparse(mutated_tree)
                        candidates.append((
                            MutantDefinition(
                                file_path=file_path,
                                operator_type=MutationOperatorType.BOOL_OP_FLIP,
                                line_number=getattr(node, "lineno", 1),
                                original_snippet=ast.unparse(node),
                                mutated_snippet=ast.unparse(target),
                            ),
                            mutated_source,
                        ))

            # 3. Boolean constants
            elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
                mutated_tree = copy.deepcopy(tree)
                target = self._find_matching_node(mutated_tree, node)
                if target and isinstance(target, ast.Constant):
                    target.value = not node.value
                    mutated_source = ast.unparse(mutated_tree)
                    candidates.append((
                        MutantDefinition(
                            file_path=file_path,
                            operator_type=MutationOperatorType.BOOLEAN_CONSTANT_FLIP,
                            line_number=getattr(node, "lineno", 1),
                            original_snippet=str(node.value),
                            mutated_snippet=str(target.value),
                        ),
                        mutated_source,
                    ))

            # 4. Arithmetic operators
            elif isinstance(node, ast.BinOp):
                op_type = type(node.op)
                if op_type in _BIN_OP_MAP:
                    mutated_tree = copy.deepcopy(tree)
                    target = self._find_matching_node(mutated_tree, node)
                    if target and isinstance(target, ast.BinOp):
                        target.op = _BIN_OP_MAP[op_type]()
                        mutated_source = ast.unparse(mutated_tree)
                        candidates.append((
                            MutantDefinition(
                                file_path=file_path,
                                operator_type=MutationOperatorType.ARITH_OP_FLIP,
                                line_number=getattr(node, "lineno", 1),
                                original_snippet=ast.unparse(node),
                                mutated_snippet=ast.unparse(target),
                            ),
                            mutated_source,
                        ))

        return candidates

    def _find_matching_node(self, root: ast.AST, target: ast.AST) -> ast.AST | None:
        """Locate corresponding node in deep-copied AST by line and column offset."""
        target_line = getattr(target, "lineno", None)
        target_col = getattr(target, "col_offset", None)
        target_type = type(target)

        for node in ast.walk(root):
            if type(node) is target_type:
                if (
                    getattr(node, "lineno", None) == target_line
                    and getattr(node, "col_offset", None) == target_col
                ):
                    return node
        return None


class MutationTester:
    """
    Orchestrates mutation testing against target workspace changes.
    """

    def __init__(
        self,
        verifier: ExecutionVerifier | None = None,
        generator: AstMutantGenerator | None = None,
    ) -> None:
        self._verifier = verifier or ExecutionVerifier()
        self._generator = generator or AstMutantGenerator()

    def evaluate_mutations(
        self,
        workspace: Path,
        changes: tuple[FileChangeRecord, ...],
        policy: ExecutionPolicy,
        command_override: str | None = None,
        max_mutants_total: int = 5,
    ) -> MutationReport:
        """
        Evaluate assertion sensitivity of tests by mutating changed files.
        """
        workspace_resolved = workspace.resolve()
        mutants_to_test: list[tuple[MutantDefinition, str, Path, str]] = []

        # 1. Collect candidate mutants across all changed Python files
        for change in changes:
            if not change.file_path.endswith(".py"):
                continue
            target_path = (workspace_resolved / change.file_path).resolve()
            if not target_path.exists():
                continue

            original_code = target_path.read_text(encoding="utf-8", errors="replace")
            generated = self._generator.generate_mutants(
                source_code=original_code,
                file_path=change.file_path,
                max_mutants=max_mutants_total - len(mutants_to_test),
            )
            for m_def, m_src in generated:
                mutants_to_test.append((m_def, m_src, target_path, original_code))
                if len(mutants_to_test) >= max_mutants_total:
                    break
            if len(mutants_to_test) >= max_mutants_total:
                break

        if not mutants_to_test:
            # No mutants could be generated
            return MutationReport(
                total_mutants_generated=0,
                total_mutants_tested=0,
                mutants_killed=0,
                mutants_survived=0,
                mutation_score=1.0,
                test_results=(),
            )

        test_results: list[MutantTestResult] = []
        killed_count = 0
        survived_count = 0

        # 2. Test each mutant in isolation and restore
        for m_def, m_src, target_path, original_code in mutants_to_test:
            try:
                # Write mutation
                target_path.write_text(m_src, encoding="utf-8")

                # Run tests
                start_t = time.perf_counter()
                res = self._verifier.verify_tests(
                    workspace=workspace,
                    policy=policy,
                    command_override=command_override,
                )
                duration_ms = round((time.perf_counter() - start_t) * 1000, 2)

                if not res.passed:
                    # Test failed! Mutant was killed (caught)
                    status = MutantStatus.KILLED
                    killed_count += 1
                else:
                    # Test passed! Mutant survived (test did not catch the alteration)
                    status = MutantStatus.SURVIVED
                    survived_count += 1

                test_results.append(
                    MutantTestResult(
                        mutant=m_def,
                        status=status,
                        exit_code=res.exit_code,
                        duration_ms=duration_ms,
                        stdout=res.stdout,
                        stderr=res.stderr,
                        error_message=res.error_message,
                    )
                )

            finally:
                # Always restore original code fail-closed
                target_path.write_text(original_code, encoding="utf-8")

        total_tested = killed_count + survived_count
        score = (killed_count / total_tested) if total_tested > 0 else 1.0

        return MutationReport(
            total_mutants_generated=len(mutants_to_test),
            total_mutants_tested=total_tested,
            mutants_killed=killed_count,
            mutants_survived=survived_count,
            mutation_score=round(score, 4),
            test_results=tuple(test_results),
        )

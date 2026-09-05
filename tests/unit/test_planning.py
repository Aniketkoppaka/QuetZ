"""
tests/unit/test_planning.py

Comprehensive tests for Milestone 4: Implementation planning domain models,
step contracts, DAG dependency validation, hallucination detection, evidence grounding,
immutability, determinism, and planning validation benchmark.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from autonomous_engineer.agents import (
    ImplementationAgentContract,
    PlanValidationError,
    PlanValidationResult,
    PlanValidator,
    PlannerInput,
    PlannerInterface,
    PlanningBenchmarkTestCase,
    PlanningValidationBenchmark,
)
from autonomous_engineer.domain.models import (
    ClassSymbol,
    ContextBudget,
    EvidenceSource,
    FunctionSymbol,
    ImplementationPlan,
    ImplementationStep,
    ImportStatement,
    Issue,
    PythonModuleMap,
    Repository,
    RepositoryMap,
    RetrievalItem,
    RetrievalReason,
    RetrievalResult,
    StepEvidence,
    StepOperation,
)


# ---------------------------------------------------------------------------
# Fixtures for Planning Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def plan_repo_map() -> RepositoryMap:
    """A multi-module repository map for testing plan grounding."""
    auth_service = PythonModuleMap(
        file_path="src/auth/service.py",
        module_name="src.auth.service",
        line_count=100,
        classes=(
            ClassSymbol(
                name="AuthenticationService",
                qualified_name="AuthenticationService",
                line_number=10,
                end_line_number=60,
                methods=(
                    FunctionSymbol(
                        name="authenticate_user",
                        qualified_name="AuthenticationService.authenticate_user",
                        line_number=15,
                        end_line_number=30,
                    ),
                    FunctionSymbol(
                        name="validate_token",
                        qualified_name="AuthenticationService.validate_token",
                        line_number=32,
                        end_line_number=55,
                    ),
                ),
            ),
        ),
    )

    auth_db = PythonModuleMap(
        file_path="src/auth/database.py",
        module_name="src.auth.database",
        line_count=80,
        classes=(
            ClassSymbol(
                name="UserDatabase",
                qualified_name="UserDatabase",
                line_number=8,
                end_line_number=50,
                methods=(
                    FunctionSymbol(
                        name="get_user",
                        qualified_name="UserDatabase.get_user",
                        line_number=12,
                        end_line_number=28,
                    ),
                ),
            ),
        ),
    )

    test_auth = PythonModuleMap(
        file_path="tests/test_auth.py",
        module_name="tests.test_auth",
        is_test_file=True,
        line_count=40,
        functions=(
            FunctionSymbol(
                name="test_auth_success",
                qualified_name="test_auth_success",
                line_number=5,
                end_line_number=15,
            ),
        ),
    )

    return RepositoryMap(
        repository_url="https://github.com/example/sample-app",
        commit_sha="1234567890abcdef1234567890abcdef12345678",
        file_count=4,
        python_file_count=3,
        non_python_file_paths=("pyproject.toml", "README.md"),
        python_modules=(auth_service, auth_db, test_auth),
        test_file_paths=("tests/test_auth.py",),
        configuration_file_paths=("pyproject.toml",),
    )


@pytest.fixture
def plan_retrieval_result(plan_repo_map: RepositoryMap) -> RetrievalResult:
    """Grounded retrieval result with auth/service.py and auth/database.py."""
    return RetrievalResult(
        query="Authentication token timeout in database lookup",
        strategy_used="combined",
        total_candidates_evaluated=3,
        items=(
            RetrievalItem(
                file_path="src/auth/service.py",
                symbol_name="AuthenticationService.validate_token",
                symbol_type="method",
                start_line=32,
                end_line=55,
                score=7.5,
                reasons=(
                    RetrievalReason(
                        strategy="lexical",
                        signal="symbol_name_match",
                        score_contribution=3.5,
                    ),
                ),
            ),
            RetrievalItem(
                file_path="src/auth/database.py",
                symbol_name="UserDatabase.get_user",
                symbol_type="method",
                start_line=12,
                end_line=28,
                score=4.0,
                reasons=(
                    RetrievalReason(
                        strategy="structural",
                        signal="local_import_dependency",
                        score_contribution=2.0,
                    ),
                ),
            ),
        ),
    )


@pytest.fixture
def planner_input(
    plan_repo_map: RepositoryMap, plan_retrieval_result: RetrievalResult
) -> PlannerInput:
    """Valid PlannerInput contract fixture."""
    return PlannerInput(
        issue=Issue(
            id="issue#42",
            title="User login timeout during token validation",
            body="When validating tokens, database connection times out.",
            repository_url=plan_repo_map.repository_url,
        ),
        repository=Repository(
            url=plan_repo_map.repository_url,
            workspace_path=Path("/tmp/workspaces/sample-app"),
            commit_sha="1234567890abcdef1234567890abcdef12345678",
            default_branch="main",
        ),
        repo_map=plan_repo_map,
        retrieval_result=plan_retrieval_result,
        attempt_number=1,
    )


# ---------------------------------------------------------------------------
# 1. ImplementationStep & ImplementationPlan Domain Model Tests
# ---------------------------------------------------------------------------


class TestPlanningDomainModels:
    def test_create_atomic_step_with_evidence(self) -> None:
        step = ImplementationStep(
            step_id="step-1",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="src/auth/service.py",
            target_symbol="AuthenticationService.validate_token",
            description="Add timeout handling to validate_token method",
            rationale="Prevents unhandled connection timeouts during auth check",
            expected_behavior="Raises AuthenticationTimeoutError on timeout",
            dependencies=(),
            evidence=StepEvidence(
                source=EvidenceSource.RETRIEVED_CONTEXT,
                reference_path="src/auth/service.py",
                reference_symbol="AuthenticationService.validate_token",
                relevance_reason="Contains validate_token signature",
            ),
            verification_requirement="Run tests/test_auth.py",
        )
        assert step.step_id == "step-1"
        assert step.operation == StepOperation.MODIFY_SYMBOL
        assert step.evidence is not None
        assert step.evidence.source == EvidenceSource.RETRIEVED_CONTEXT

    def test_plan_immutability(self) -> None:
        step = ImplementationStep(
            step_id="step-1",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="src/auth/service.py",
            description="Update token validator",
            rationale="Fix timeout bug",
        )
        plan = ImplementationPlan(
            summary="Fix auth timeout",
            rationale="Database connection error",
            steps=(step,),
        )
        with pytest.raises(ValidationError):
            plan.summary = "New Summary"  # type: ignore

    def test_plan_steps_coercion_from_strings_backwards_compatible(self) -> None:
        plan = ImplementationPlan(
            summary="Refactor auth",
            rationale="Improve modularity",
            steps=("Refactor database", "Add unit test"),  # type: ignore
        )
        assert len(plan.steps) == 2
        assert isinstance(plan.steps[0], ImplementationStep)
        assert plan.steps[0].step_id == "step-1"
        assert plan.steps[0].description == "Refactor database"
        assert plan.steps[1].step_id == "step-2"

    def test_plan_json_round_trip(self) -> None:
        step = ImplementationStep(
            step_id="step-1",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="src/auth/service.py",
            target_symbol="AuthenticationService.validate_token",
            description="Add timeout retry loop",
            rationale="Prevent intermittent auth failures",
            evidence=StepEvidence(
                source=EvidenceSource.RETRIEVED_CONTEXT,
                reference_path="src/auth/service.py",
            ),
        )
        original = ImplementationPlan(
            issue_id="issue#42",
            summary="Fix auth timeout",
            rationale="Database pool exhaustion",
            steps=(step,),
            assumptions=("Database pool size >= 5",),
            unresolved_uncertainties=("Exact network latency under peak load",),
        )

        json_str = original.model_dump_json()
        restored = ImplementationPlan.model_validate_json(json_str)

        assert restored.deterministic_dict() == original.deterministic_dict()
        assert restored.steps[0].evidence.source == EvidenceSource.RETRIEVED_CONTEXT


# ---------------------------------------------------------------------------
# 2. Plan Validation Engine Tests
# ---------------------------------------------------------------------------


class TestPlanValidator:
    def test_valid_plan_passes_validation(self, planner_input: PlannerInput) -> None:
        validator = PlanValidator()
        step1 = ImplementationStep(
            step_id="step-1",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="src/auth/database.py",
            target_symbol="UserDatabase.get_user",
            description="Add timeout parameter to get_user",
            rationale="Allows service layer to specify connection deadline",
            evidence=StepEvidence(
                source=EvidenceSource.RETRIEVED_CONTEXT,
                reference_path="src/auth/database.py",
            ),
        )
        step2 = ImplementationStep(
            step_id="step-2",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="src/auth/service.py",
            target_symbol="AuthenticationService.validate_token",
            description="Call get_user with 5 second timeout",
            rationale="Ensures validate_token fails gracefully on slow DB",
            dependencies=("step-1",),
            evidence=StepEvidence(
                source=EvidenceSource.RETRIEVED_CONTEXT,
                reference_path="src/auth/service.py",
            ),
        )
        plan = ImplementationPlan(
            summary="Add query timeout handling",
            rationale="Prevent worker thread starvation during DB outages",
            steps=(step1, step2),
        )

        result = validator.validate(plan, planner_input)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_detect_hallucinated_file(self, planner_input: PlannerInput) -> None:
        validator = PlanValidator()
        step = ImplementationStep(
            step_id="step-1",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="src/auth/non_existent_module.py",  # Hallucinated!
            description="Fix connection leak",
            rationale="Bug in imaginary module",
        )
        plan = ImplementationPlan(
            summary="Fix imaginary file",
            rationale="Module bug",
            steps=(step,),
        )

        result = validator.validate(plan, planner_input)
        assert result.is_valid is False
        assert any(e.error_type == "hallucinated_file" for e in result.errors)

    def test_detect_hallucinated_symbol(self, planner_input: PlannerInput) -> None:
        validator = PlanValidator()
        step = ImplementationStep(
            step_id="step-1",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="src/auth/service.py",
            target_symbol="AuthenticationService.non_existent_method",  # Hallucinated!
            description="Modify missing method",
            rationale="Typo in symbol name",
        )
        plan = ImplementationPlan(
            summary="Fix missing symbol",
            rationale="Bug in method",
            steps=(step,),
        )

        result = validator.validate(plan, planner_input)
        assert result.is_valid is False
        assert any(e.error_type == "hallucinated_symbol" for e in result.errors)

    def test_detect_circular_dependencies(self, planner_input: PlannerInput) -> None:
        validator = PlanValidator()
        step1 = ImplementationStep(
            step_id="step-1",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="src/auth/service.py",
            description="Step 1",
            dependencies=("step-2",),  # 1 depends on 2
        )
        step2 = ImplementationStep(
            step_id="step-2",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="src/auth/database.py",
            description="Step 2",
            dependencies=("step-1",),  # 2 depends on 1 -> CYCLE!
        )
        plan = ImplementationPlan(
            summary="Circular plan",
            rationale="Test cycle",
            steps=(step1, step2),
        )

        result = validator.validate(plan, planner_input)
        assert result.is_valid is False
        assert any(e.error_type == "circular_dependency" for e in result.errors)

    def test_detect_self_dependency(self, planner_input: PlannerInput) -> None:
        validator = PlanValidator()
        step = ImplementationStep(
            step_id="step-1",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="src/auth/service.py",
            description="Self dependent step",
            dependencies=("step-1",),
        )
        plan = ImplementationPlan(
            summary="Self dep plan",
            rationale="Test self dep",
            steps=(step,),
        )

        result = validator.validate(plan, planner_input)
        assert result.is_valid is False
        assert any(e.error_type == "self_dependency" for e in result.errors)

    def test_detect_path_traversal_and_absolute_paths(self, planner_input: PlannerInput) -> None:
        validator = PlanValidator()
        step1 = ImplementationStep(
            step_id="step-1",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="/etc/passwd",  # Absolute path
            description="Modify system file",
        )
        step2 = ImplementationStep(
            step_id="step-2",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="../outside/repo.py",  # Directory traversal
            description="Traverse out of repo",
        )
        plan = ImplementationPlan(
            summary="Malicious path plan",
            rationale="Security test",
            steps=(step1, step2),
        )

        result = validator.validate(plan, planner_input)
        assert result.is_valid is False
        error_types = {e.error_type for e in result.errors}
        assert "absolute_path" in error_types
        assert "directory_traversal" in error_types

    def test_detect_ungrounded_retrieval_evidence(self, planner_input: PlannerInput) -> None:
        validator = PlanValidator()
        step = ImplementationStep(
            step_id="step-1",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="src/auth/service.py",
            description="Update auth service",
            evidence=StepEvidence(
                source=EvidenceSource.RETRIEVED_CONTEXT,
                reference_path="src/billing/service.py",  # Not in RetrievalResult!
            ),
        )
        plan = ImplementationPlan(
            summary="Ungrounded evidence plan",
            rationale="Testing evidence validation",
            steps=(step,),
        )

        result = validator.validate(plan, planner_input)
        assert result.is_valid is False
        assert any(e.error_type == "ungrounded_retrieval_evidence" for e in result.errors)


# ---------------------------------------------------------------------------
# 3. Protocol & Implementation Agent Contract Tests
# ---------------------------------------------------------------------------


class TestPlannerProtocolAndContracts:
    def test_implementation_agent_contract_defaults(self) -> None:
        contract = ImplementationAgentContract()
        assert len(contract.allowed_assumptions) >= 3
        assert len(contract.mandatory_verifications) >= 3
        assert any("topological order" in a for a in contract.allowed_assumptions)
        assert any("syntax and AST" in v for v in contract.mandatory_verifications)

    def test_mock_planner_implementation_satisfies_protocol(
        self, planner_input: PlannerInput
    ) -> None:
        class RuleBasedPlanner:
            def plan(self, p_in: PlannerInput) -> ImplementationPlan:
                return ImplementationPlan(
                    issue_id=p_in.issue.id,
                    summary="Rule-based plan",
                    rationale="Generated from top retrieval item",
                    steps=(
                        ImplementationStep(
                            step_id="step-1",
                            operation=StepOperation.MODIFY_SYMBOL,
                            target_file=p_in.retrieval_result.items[0].file_path,
                            target_symbol=p_in.retrieval_result.items[0].symbol_name,
                            description="Apply fix",
                            rationale="Root cause identified",
                            evidence=StepEvidence(
                                source=EvidenceSource.RETRIEVED_CONTEXT,
                                reference_path=p_in.retrieval_result.items[0].file_path,
                            ),
                        ),
                    ),
                )

        planner = RuleBasedPlanner()
        assert isinstance(planner, PlannerInterface)
        plan = planner.plan(planner_input)
        assert plan.issue_id == planner_input.issue.id
        assert len(plan.steps) == 1


# ---------------------------------------------------------------------------
# 4. Planning Validation Benchmark Harness Tests
# ---------------------------------------------------------------------------


class TestPlanningValidationBenchmark:
    @pytest.fixture
    def benchmark_cases(self, planner_input: PlannerInput) -> list[PlanningBenchmarkTestCase]:
        """Benchmark suite covering valid plans and distinct deliberate fault modes."""
        # 1. Valid plan
        valid_plan = ImplementationPlan(
            summary="Valid plan",
            rationale="Fix auth token validation",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.MODIFY_SYMBOL,
                    target_file="src/auth/service.py",
                    target_symbol="AuthenticationService.validate_token",
                    description="Handle timeout",
                ),
            ),
        )

        # 2. Hallucinated file plan
        hallucinated_file_plan = ImplementationPlan(
            summary="Hallucinated file plan",
            rationale="Bad file path",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.MODIFY_SYMBOL,
                    target_file="src/fake_pkg/missing.py",
                    description="Edit fake file",
                ),
            ),
        )

        # 3. Hallucinated symbol plan
        hallucinated_symbol_plan = ImplementationPlan(
            summary="Hallucinated symbol plan",
            rationale="Bad symbol",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.MODIFY_SYMBOL,
                    target_file="src/auth/service.py",
                    target_symbol="AuthenticationService.fake_method",
                    description="Edit fake method",
                ),
            ),
        )

        # 4. Circular dependency plan
        circular_plan = ImplementationPlan(
            summary="Circular plan",
            rationale="Cycle",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    target_file="src/auth/service.py",
                    description="Step 1",
                    dependencies=("step-2",),
                ),
                ImplementationStep(
                    step_id="step-2",
                    target_file="src/auth/database.py",
                    description="Step 2",
                    dependencies=("step-1",),
                ),
            ),
        )

        # 5. Duplicate step ID plan
        duplicate_id_plan = ImplementationPlan(
            summary="Duplicate ID plan",
            rationale="Dupe ID",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    target_file="src/auth/service.py",
                    description="First step 1",
                ),
                ImplementationStep(
                    step_id="step-1",
                    target_file="src/auth/database.py",
                    description="Second step 1",
                ),
            ),
        )

        return [
            PlanningBenchmarkTestCase(
                case_id="PLAN-VALID-01",
                name="Grounded valid multi-step plan",
                category="valid_plan",
                plan=valid_plan,
                planner_input=planner_input,
                should_be_valid=True,
                expected_error_types=(),
                rationale="Plan references existing file and symbol with no cycle",
            ),
            PlanningBenchmarkTestCase(
                case_id="PLAN-ERR-FILE-01",
                name="Hallucinated file detection",
                category="hallucinated_file",
                plan=hallucinated_file_plan,
                planner_input=planner_input,
                should_be_valid=False,
                expected_error_types=("hallucinated_file",),
                rationale="Target file does not exist in RepositoryMap",
            ),
            PlanningBenchmarkTestCase(
                case_id="PLAN-ERR-SYM-01",
                name="Hallucinated symbol detection",
                category="hallucinated_symbol",
                plan=hallucinated_symbol_plan,
                planner_input=planner_input,
                should_be_valid=False,
                expected_error_types=("hallucinated_symbol",),
                rationale="Target symbol does not exist in target PythonModuleMap",
            ),
            PlanningBenchmarkTestCase(
                case_id="PLAN-ERR-CYCLE-01",
                name="Circular dependency graph detection",
                category="circular_dependency",
                plan=circular_plan,
                planner_input=planner_input,
                should_be_valid=False,
                expected_error_types=("circular_dependency",),
                rationale="Steps form a direct 2-node cycle (step-1 <-> step-2)",
            ),
            PlanningBenchmarkTestCase(
                case_id="PLAN-ERR-DUPE-01",
                name="Duplicate step ID detection",
                category="duplicate_step_id",
                plan=duplicate_id_plan,
                planner_input=planner_input,
                should_be_valid=False,
                expected_error_types=("duplicate_step_id",),
                rationale="Plan contains two steps with identical step_id='step-1'",
            ),
        ]

    def test_run_planning_benchmark(
        self, benchmark_cases: list[PlanningBenchmarkTestCase]
    ) -> None:
        benchmark = PlanningValidationBenchmark()
        report = benchmark.run(benchmark_cases)

        assert report.total_cases == 5
        assert report.correctly_classified == 5
        assert report.accuracy == 1.0
        assert report.false_positives == 0
        assert report.false_negatives == 0
        assert "hallucinated_file" in report.detected_error_types
        assert "hallucinated_symbol" in report.detected_error_types
        assert "circular_dependency" in report.detected_error_types
        assert "duplicate_step_id" in report.detected_error_types


# ---------------------------------------------------------------------------
# 8. Milestone 17 Focused Unit Tests: Pre-Execution AST Syntax Validation
# ---------------------------------------------------------------------------


class TestM17PreExecutionSyntaxValidation:
    """
    Focused verification tests for Milestone 17: Pre-Execution AST Syntax Validation
    of hypothetical post-edit files and additions.
    """

    @pytest.fixture
    def test_workspace(self, tmp_path: Path) -> Path:
        """Create a real temporary workspace with Python source files."""
        src_dir = tmp_path / "src" / "auth"
        src_dir.mkdir(parents=True, exist_ok=True)
        service_file = src_dir / "service.py"
        service_file.write_text(
            "class AuthenticationService:\n"
            "    def validate_token(self, token: str) -> bool:\n"
            "        if not token:\n"
            "            return False\n"
            "        return True\n",
            encoding="utf-8",
        )
        return tmp_path

    @pytest.fixture
    def m17_planner_input(
        self, test_workspace: Path, plan_repo_map: RepositoryMap, plan_retrieval_result: RetrievalResult
    ) -> PlannerInput:
        """Planner input pointed to the real temporary workspace."""
        return PlannerInput(
            issue=Issue(
                id="issue#42",
                title="User login timeout during token validation",
                body="When validating tokens, database connection times out.",
                repository_url=plan_repo_map.repository_url,
            ),
            repository=Repository(
                url=plan_repo_map.repository_url,
                workspace_path=test_workspace,
                commit_sha="1234567890abcdef1234567890abcdef12345678",
                default_branch="main",
            ),
            repo_map=plan_repo_map,
            retrieval_result=plan_retrieval_result,
            attempt_number=1,
        )

    def test_1_complete_valid_add_file_succeeds(self, m17_planner_input: PlannerInput) -> None:
        """1. A complete valid ADD_FILE parses successfully."""
        validator = PlanValidator()
        plan = ImplementationPlan(
            summary="Add new helper module",
            rationale="Provide token hashing helper",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.ADD_FILE,
                    target_file="src/auth/helper.py",
                    description="Create helper module",
                    content="def hash_token(token: str) -> str:\n    return token.strip()\n",
                ),
            ),
        )
        result = validator.validate(plan, m17_planner_input)
        syntax_errors = [e for e in result.errors if e.error_type == "syntax_error"]
        assert len(syntax_errors) == 0

    def test_2_complete_invalid_add_file_rejected(self, m17_planner_input: PlannerInput) -> None:
        """2. A complete invalid ADD_FILE is rejected with a syntax error."""
        validator = PlanValidator()
        plan = ImplementationPlan(
            summary="Add malformed helper module",
            rationale="Testing syntax rejection",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.ADD_FILE,
                    target_file="src/auth/helper.py",
                    description="Create malformed helper module",
                    content="import pytest from click._utils import _Sentinel\n",
                ),
            ),
        )
        result = validator.validate(plan, m17_planner_input)
        assert not result.is_valid
        syntax_errors = [e for e in result.errors if e.error_type == "syntax_error"]
        assert len(syntax_errors) == 1
        assert syntax_errors[0].step_id == "step-1"
        assert syntax_errors[0].field == "content"
        assert "Syntactically invalid Python" in syntax_errors[0].message
        assert "line 1" in syntax_errors[0].message

    def test_3_valid_indented_replacement_fragment_succeeds(
        self, m17_planner_input: PlannerInput
    ) -> None:
        """3. A valid indented replacement fragment succeeds when integrated into surrounding Python."""
        validator = PlanValidator()
        # In isolation, '        return False\n        # extra' cannot stand as module, but in context it is valid
        plan = ImplementationPlan(
            summary="Update token check",
            rationale="Tighten validation check",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.MODIFY_SYMBOL,
                    target_file="src/auth/service.py",
                    target_symbol="AuthenticationService.validate_token",
                    description="Modify token check logic",
                    search_content="        if not token:\n            return False",
                    replace_content="        if not token or len(token) < 5:\n            return False",
                ),
            ),
        )
        result = validator.validate(plan, m17_planner_input)
        syntax_errors = [e for e in result.errors if e.error_type == "syntax_error"]
        assert len(syntax_errors) == 0
        assert result.is_valid

    def test_4_fragment_valid_in_isolation_but_invalid_in_context_rejected(
        self, m17_planner_input: PlannerInput
    ) -> None:
        """4. A replacement that is valid in isolation but creates invalid surrounding syntax is rejected."""
        validator = PlanValidator()
        # 'x = 1' is valid Python in isolation, but with an unmatched unclosed bracket it breaks surrounding AST
        plan = ImplementationPlan(
            summary="Break method syntax",
            rationale="Testing integration syntax error",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.MODIFY_SYMBOL,
                    target_file="src/auth/service.py",
                    target_symbol="AuthenticationService.validate_token",
                    description="Insert unbalanced parenthesis",
                    search_content="        if not token:\n            return False",
                    replace_content="        if not token: (\n            return False",
                ),
            ),
        )
        result = validator.validate(plan, m17_planner_input)
        assert not result.is_valid
        syntax_errors = [e for e in result.errors if e.error_type == "syntax_error"]
        assert len(syntax_errors) == 1
        assert syntax_errors[0].step_id == "step-1"
        assert syntax_errors[0].field == "replace_content"

    def test_5_multiple_sequential_edits_simulated_correctly(
        self, m17_planner_input: PlannerInput
    ) -> None:
        """5. Multiple sequential edits to one file are simulated cumulatively in memory."""
        validator = PlanValidator()
        # Step 1: add a helper method; Step 2: call that helper method
        plan = ImplementationPlan(
            summary="Multi-step refactoring",
            rationale="Split method into helper",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.MODIFY_SYMBOL,
                    target_file="src/auth/service.py",
                    target_symbol="AuthenticationService",
                    description="Add helper method",
                    search_content="    def validate_token(self, token: str) -> bool:",
                    replace_content=(
                        "    def _is_empty(self, token: str) -> bool:\n"
                        "        return not token\n\n"
                        "    def validate_token(self, token: str) -> bool:"
                    ),
                ),
                ImplementationStep(
                    step_id="step-2",
                    operation=StepOperation.MODIFY_SYMBOL,
                    target_file="src/auth/service.py",
                    target_symbol="AuthenticationService.validate_token",
                    dependencies=("step-1",),
                    description="Call helper method",
                    search_content="        if not token:\n            return False",
                    replace_content="        if self._is_empty(token):\n            return False",
                ),
            ),
        )
        result = validator.validate(plan, m17_planner_input)
        syntax_errors = [e for e in result.errors if e.error_type == "syntax_error"]
        assert len(syntax_errors) == 0
        assert result.is_valid

    def test_6_anchor_mismatch_remains_m16_behavior_not_syntax_error(
        self, m17_planner_input: PlannerInput
    ) -> None:
        """6. An anchor mismatch remains an anchor/edit-representation issue rather than becoming a syntax failure."""
        validator = PlanValidator()
        # Non-matching search content
        plan = ImplementationPlan(
            summary="Unmatched anchor test",
            rationale="Verify anchor failure does not become syntax failure",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.MODIFY_SYMBOL,
                    target_file="src/auth/service.py",
                    target_symbol="AuthenticationService.validate_token",
                    description="Unmatched search content",
                    search_content="NON_EXISTENT_ANCHOR_LINE = 12345",
                    replace_content="REPLACEMENT_LINE = 67890",
                ),
            ),
        )
        result = validator.validate(plan, m17_planner_input)
        # Should NOT report syntax_error
        syntax_errors = [e for e in result.errors if e.error_type == "syntax_error"]
        assert len(syntax_errors) == 0

    def test_7_ambiguous_anchor_remains_unchanged(
        self, m17_planner_input: PlannerInput, test_workspace: Path
    ) -> None:
        """7. Ambiguous anchor behavior is not converted to a syntax error."""
        # Create a file with duplicate lines
        dup_file = test_workspace / "src" / "auth" / "service.py"
        dup_file.write_text(
            "def foo():\n    x = 1\ndef bar():\n    x = 1\n",
            encoding="utf-8",
        )
        validator = PlanValidator()
        plan = ImplementationPlan(
            summary="Ambiguous anchor test",
            rationale="Verify ambiguous anchor does not become syntax failure",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.MODIFY_SYMBOL,
                    target_file="src/auth/service.py",
                    description="Ambiguous search content across file",
                    search_content="    x = 1",
                    replace_content="    x = 2",
                ),
            ),
        )
        result = validator.validate(plan, m17_planner_input)
        syntax_errors = [e for e in result.errors if e.error_type == "syntax_error"]
        assert len(syntax_errors) == 0

    def test_8_no_real_workspace_mutation_during_syntax_validation(
        self, m17_planner_input: PlannerInput, test_workspace: Path
    ) -> None:
        """8. Confirm no real workspace files are altered during in-memory candidate construction."""
        service_file = test_workspace / "src" / "auth" / "service.py"
        content_before = service_file.read_text(encoding="utf-8")

        validator = PlanValidator()
        plan = ImplementationPlan(
            summary="Workspace safety check",
            rationale="Verify zero disk side effects during validation",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.MODIFY_SYMBOL,
                    target_file="src/auth/service.py",
                    target_symbol="AuthenticationService.validate_token",
                    description="Modify token check",
                    search_content="        if not token:\n            return False",
                    replace_content="        if not token:\n            return True  # MUTATED",
                ),
            ),
        )
        validator.validate(plan, m17_planner_input)

        content_after = service_file.read_text(encoding="utf-8")
        assert content_before == content_after, "Workspace was mutated during plan validation!"

    def test_9_syntax_diagnostics_contain_line_and_column_information(
        self, m17_planner_input: PlannerInput
    ) -> None:
        """9. Syntax diagnostics contain deterministic line and column details."""
        validator = PlanValidator()
        plan = ImplementationPlan(
            summary="Syntax diagnostic test",
            rationale="Verify line and column diagnostics",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.ADD_FILE,
                    target_file="src/auth/test_syntax.py",
                    description="Emits syntax error at known location",
                    content="def bad_func():\n    return 1 +\n",
                ),
            ),
        )
        result = validator.validate(plan, m17_planner_input)
        assert not result.is_valid
        syntax_errors = [e for e in result.errors if e.error_type == "syntax_error"]
        assert len(syntax_errors) == 1
        err = syntax_errors[0]
        assert "line 2" in err.message
        assert "column" in err.message

    def test_10_syntax_failure_enters_existing_repair_loop_without_changing_budget(
        self, m17_planner_input: PlannerInput
    ) -> None:
        """10. Syntax errors are formatted via existing repair prompt without changing repair loop policy."""
        from autonomous_engineer.agents.prompt_builder import PlannerPromptBuilder

        validator = PlanValidator()
        plan = ImplementationPlan(
            summary="Repair loop formatting test",
            rationale="Check error serialization in build_repair_prompt",
            steps=(
                ImplementationStep(
                    step_id="step-1",
                    operation=StepOperation.ADD_FILE,
                    target_file="src/auth/bad.py",
                    description="Broken syntax",
                    content="class (\n",
                ),
            ),
        )
        val_result = validator.validate(plan, m17_planner_input)
        assert not val_result.is_valid

        builder = PlannerPromptBuilder()
        repair_prompt = builder.build_repair_prompt(
            invalid_plan_str=json.dumps(plan.deterministic_dict()),
            validation_result=val_result,
        )

        assert "=== VALIDATION ERRORS DETECTED ===" in repair_prompt
        assert "[syntax_error] [Step: step-1]" in repair_prompt
        assert "Syntactically invalid Python generated for src/auth/bad.py" in repair_prompt
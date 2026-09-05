"""
tests/unit/test_retrieval.py

Comprehensive tests for context retrieval, tokenization regressions,
distractor handling, determinism, ablation analysis, and multi-category evaluation benchmark.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from autonomous_engineer.domain.models import (
    ClassSymbol,
    ContextBudget,
    FunctionSymbol,
    ImportStatement,
    Issue,
    PythonModuleMap,
    RepositoryMap,
    RetrievalItem,
    RetrievalReason,
    RetrievalResult,
)
from autonomous_engineer.retrieval import (
    CodeTokenizer,
    ContextRetriever,
    DetailedEvaluationReport,
    LexicalRetriever,
    LocalImportResolver,
    RetrievalBenchmarkTestCase,
    RetrievalEvaluator,
    StructuralRetriever,
)


# ---------------------------------------------------------------------------
# Fixture: Comprehensive Synthetic Multi-Package RepositoryMap
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_repo_map() -> RepositoryMap:
    """Create an in-memory RepositoryMap with production modules, tests, configs, and distractors."""
    # 1. Auth Service module (Production implementation)
    auth_service = PythonModuleMap(
        file_path="src/auth/service.py",
        module_name="src.auth.service",
        line_count=120,
        docstring="Coordinates production user authentication, credentials, and token validation.",
        imports=(
            ImportStatement(module="auth.database", names=("UserDatabase",), is_from=True, line_number=3),
            ImportStatement(module="auth.tokens", names=("TokenManager",), is_from=True, line_number=4),
            ImportStatement(module="auth.session", names=("SessionManager",), is_from=True, line_number=5),
        ),
        classes=(
            ClassSymbol(
                name="AuthenticationService",
                qualified_name="AuthenticationService",
                line_number=10,
                end_line_number=70,
                base_classes=("BaseService",),
                docstring="Coordinates login, credential validation, and session verification.",
                methods=(
                    FunctionSymbol(
                        name="authenticate_user",
                        qualified_name="AuthenticationService.authenticate_user",
                        line_number=15,
                        end_line_number=35,
                        parameters=("self", "username", "password"),
                        docstring="Verify user credentials against database.",
                    ),
                    FunctionSymbol(
                        name="validate_token",
                        qualified_name="AuthenticationService.validate_token",
                        line_number=38,
                        end_line_number=60,
                        parameters=("self", "token"),
                        docstring="Validate signed JWT authentication token.",
                    ),
                ),
            ),
        ),
    )

    # 2. Auth Database module (Local dependency)
    auth_db = PythonModuleMap(
        file_path="src/auth/database.py",
        module_name="src.auth.database",
        line_count=80,
        docstring="Database access for user records, connection pool, and credentials lookup.",
        classes=(
            ClassSymbol(
                name="UserDatabase",
                qualified_name="UserDatabase",
                line_number=8,
                end_line_number=50,
                docstring="Manages connection pool and queries for user authentication records.",
                methods=(
                    FunctionSymbol(
                        name="get_user_by_username",
                        qualified_name="UserDatabase.get_user_by_username",
                        line_number=12,
                        end_line_number=28,
                        parameters=("self", "username"),
                        docstring="Fetch user record or raise connection timeout.",
                    ),
                ),
            ),
        ),
    )

    # 3. Auth Tokens module (Token cryptographic signing & errors)
    auth_tokens = PythonModuleMap(
        file_path="src/auth/tokens.py",
        module_name="src.auth.tokens",
        line_count=60,
        docstring="Token generation, cryptographic signing utilities, and TokenExpiredSignatureError definition.",
        classes=(
            ClassSymbol(
                name="TokenManager",
                qualified_name="TokenManager",
                line_number=5,
                end_line_number=40,
                methods=(
                    FunctionSymbol(
                        name="create_token",
                        qualified_name="TokenManager.create_token",
                        line_number=10,
                        end_line_number=25,
                        parameters=("self", "payload"),
                        docstring="Create signed JWT token with expiration timestamp.",
                    ),
                    FunctionSymbol(
                        name="verify_signature",
                        qualified_name="TokenManager.verify_signature",
                        line_number=27,
                        end_line_number=40,
                        parameters=("self", "token"),
                        docstring="Raises TokenExpiredSignatureError: Signature has expired during verification.",
                    ),
                ),
            ),
        ),
    )

    # 4. Auth Session module (Session rotation and expiration)
    auth_session = PythonModuleMap(
        file_path="src/auth/session.py",
        module_name="src.auth.session",
        line_count=75,
        docstring="Manages user session lifetimes, refresh credentials, and token rotation.",
        classes=(
            ClassSymbol(
                name="SessionManager",
                qualified_name="SessionManager",
                line_number=6,
                end_line_number=55,
                docstring="Controls user session state, refresh credentials, and automatic token rotation.",
                methods=(
                    FunctionSymbol(
                        name="refresh_credentials",
                        qualified_name="SessionManager.refresh_credentials",
                        line_number=12,
                        end_line_number=30,
                        parameters=("self", "session_id"),
                        docstring="Refresh credentials when session approaches expiration.",
                    ),
                    FunctionSymbol(
                        name="token_rotation",
                        qualified_name="SessionManager.token_rotation",
                        line_number=32,
                        end_line_number=50,
                        parameters=("self", "user_id"),
                        docstring="Rotate active session tokens.",
                    ),
                ),
            ),
        ),
    )

    # 5. Distractor module: Mock Service
    mock_service = PythonModuleMap(
        file_path="src/auth/mock_service.py",
        module_name="src.auth.mock_service",
        line_count=40,
        docstring="Test mock for authentication service with fake credentials.",
        classes=(
            ClassSymbol(
                name="MockAuthenticationService",
                qualified_name="MockAuthenticationService",
                line_number=5,
                end_line_number=35,
                methods=(
                    FunctionSymbol(
                        name="authenticate_user",
                        qualified_name="MockAuthenticationService.authenticate_user",
                        line_number=10,
                        end_line_number=20,
                        parameters=("self", "username", "password"),
                    ),
                ),
            ),
        ),
    )

    # 6. Billing Service module
    billing_service = PythonModuleMap(
        file_path="src/billing/service.py",
        module_name="src.billing.service",
        line_count=90,
        docstring="Manages customer subscriptions and invoice tax calculation.",
        classes=(
            ClassSymbol(
                name="BillingService",
                qualified_name="BillingService",
                line_number=10,
                end_line_number=65,
                methods=(
                    FunctionSymbol(
                        name="process_invoice",
                        qualified_name="BillingService.process_invoice",
                        line_number=15,
                        end_line_number=40,
                        parameters=("self", "customer_id", "amount"),
                        docstring="Calculate tax and process customer invoice.",
                    ),
                ),
            ),
        ),
    )

    # 7. Test files
    test_auth = PythonModuleMap(
        file_path="tests/test_auth.py",
        module_name="tests.test_auth",
        is_test_file=True,
        line_count=50,
        imports=(
            ImportStatement(module="auth.service", names=("AuthenticationService",), is_from=True, line_number=2),
        ),
        functions=(
            FunctionSymbol(
                name="test_authenticate_user_success",
                qualified_name="test_authenticate_user_success",
                line_number=8,
                end_line_number=20,
            ),
        ),
    )

    test_billing = PythonModuleMap(
        file_path="tests/test_billing.py",
        module_name="tests.test_billing",
        is_test_file=True,
        line_count=45,
        functions=(
            FunctionSymbol(
                name="test_process_invoice",
                qualified_name="test_process_invoice",
                line_number=5,
                end_line_number=18,
            ),
        ),
    )

    return RepositoryMap(
        repository_url="https://github.com/example/enterprise-app",
        commit_sha="abcd1234abcd1234abcd1234abcd1234abcd1234",
        file_count=10,
        python_file_count=7,
        non_python_file_paths=("pyproject.toml", "requirements.txt", "docs/authentication.md"),
        python_modules=(
            auth_service,
            auth_db,
            auth_tokens,
            auth_session,
            mock_service,
            billing_service,
            test_auth,
            test_billing,
        ),
        test_file_paths=("tests/test_auth.py", "tests/test_billing.py"),
        configuration_file_paths=("pyproject.toml", "requirements.txt"),
        has_pyproject_toml=True,
        has_requirements_txt=True,
    )


# ---------------------------------------------------------------------------
# 1. Tokenizer Regression Tests
# ---------------------------------------------------------------------------


class TestCodeTokenizerRegressions:
    def test_camel_and_pascal_case_variations(self) -> None:
        tokenizer = CodeTokenizer()
        assert tokenizer.tokenize_identifier("AuthenticationService") == ("authentication", "service")
        assert tokenizer.tokenize_identifier("authentication_service") == ("authentication", "service")
        assert tokenizer.tokenize_identifier("authentication-service") == ("authentication", "service")
        assert tokenizer.tokenize_identifier("authentication.service") == ("authentication", "service")

    def test_acronym_splitting(self) -> None:
        tokenizer = CodeTokenizer()
        assert tokenizer.tokenize_identifier("HTTPServer") == ("http", "server")
        assert tokenizer.tokenize_identifier("HTTP_server") == ("http", "server")
        assert tokenizer.tokenize_identifier("parseJSONResponse") == ("parse", "json", "response")
        assert tokenizer.tokenize_identifier("parse_json_response") == ("parse", "json", "response")

    def test_stopwords_removal(self) -> None:
        tokenizer = CodeTokenizer()
        tokens = tokenizer.tokenize_text("def authenticate_user(self, username: str) -> None:")
        assert "def" not in tokens
        assert "self" not in tokens
        assert "none" not in tokens
        assert "authenticate" in tokens
        assert "user" in tokens


# ---------------------------------------------------------------------------
# 2. Local Import Resolver Tests
# ---------------------------------------------------------------------------


class TestLocalImportResolver:
    def test_resolve_absolute_local_import(self, synthetic_repo_map: RepositoryMap) -> None:
        resolver = LocalImportResolver(synthetic_repo_map)
        stmt = ImportStatement(module="auth.database", names=("UserDatabase",), is_from=True, line_number=1)
        resolved = resolver.resolve_import("src/auth/service.py", stmt)
        assert resolved == "src/auth/database.py"

    def test_resolve_relative_local_import(self, synthetic_repo_map: RepositoryMap) -> None:
        resolver = LocalImportResolver(synthetic_repo_map)
        stmt = ImportStatement(module="tokens", names=("TokenManager",), is_from=True, level=1, line_number=1)
        resolved = resolver.resolve_import("src/auth/service.py", stmt)
        assert resolved == "src/auth/tokens.py"

    def test_external_stdlib_import_returns_none(self, synthetic_repo_map: RepositoryMap) -> None:
        resolver = LocalImportResolver(synthetic_repo_map)
        stmt = ImportStatement(module="os.path", names=("exists",), is_from=True, line_number=1)
        resolved = resolver.resolve_import("src/auth/service.py", stmt)
        assert resolved is None


# ---------------------------------------------------------------------------
# 3. Lexical Retrieval & Distractor Handling Tests
# ---------------------------------------------------------------------------


class TestLexicalAndDistractorHandling:
    def test_retrieve_production_service_over_mock_distractor(
        self, synthetic_repo_map: RepositoryMap
    ) -> None:
        retriever = LexicalRetriever()
        # Query mentions production authentication handler and credentials
        items = retriever.retrieve("Production authentication handler credentials validation", synthetic_repo_map)

        assert len(items) > 0
        top_item = max(items, key=lambda x: x.score)
        # Production auth/service.py matches docstring, class, and method
        assert top_item.file_path == "src/auth/service.py"

    def test_retrieve_by_exact_error_message(self, synthetic_repo_map: RepositoryMap) -> None:
        retriever = LexicalRetriever()
        items = retriever.retrieve("Raises TokenExpiredSignatureError: Signature has expired during verification", synthetic_repo_map)

        assert len(items) > 0
        top_item = max(items, key=lambda x: x.score)
        assert top_item.file_path == "src/auth/tokens.py"


# ---------------------------------------------------------------------------
# 4. Structural Expansion & Ablation Tests
# ---------------------------------------------------------------------------


class TestStructuralExpansionAndAblation:
    def test_structural_expansion_from_seed(self, synthetic_repo_map: RepositoryMap) -> None:
        structural = StructuralRetriever()
        seed_items = [
            RetrievalItem(
                file_path="src/auth/service.py",
                symbol_name="AuthenticationService",
                symbol_type="class",
                score=5.0,
            )
        ]
        expanded = structural.expand(seed_items, synthetic_repo_map, query="AuthenticationService")
        expanded_files = {it.file_path for it in expanded}

        assert "src/auth/database.py" in expanded_files
        assert "src/auth/tokens.py" in expanded_files
        assert "tests/test_auth.py" in expanded_files

    def test_ablation_strategies_in_context_retriever(
        self, synthetic_repo_map: RepositoryMap
    ) -> None:
        retriever = ContextRetriever()
        query = "AuthenticationService authenticate_user"

        res_lexical = retriever.retrieve(query, synthetic_repo_map, strategy="lexical")
        res_imports = retriever.retrieve(query, synthetic_repo_map, strategy="lexical+imports")
        res_tests = retriever.retrieve(query, synthetic_repo_map, strategy="lexical+tests")
        res_combined = retriever.retrieve(query, synthetic_repo_map, strategy="combined")

        files_lex = {it.file_path for it in res_lexical.items}
        files_imp = {it.file_path for it in res_imports.items}
        files_tst = {it.file_path for it in res_tests.items}
        files_com = {it.file_path for it in res_combined.items}

        assert "src/auth/database.py" in files_imp
        assert "tests/test_auth.py" in files_tst
        assert "src/auth/database.py" in files_com and "tests/test_auth.py" in files_com


# ---------------------------------------------------------------------------
# 5. Determinism & Observability Separation Tests
# ---------------------------------------------------------------------------


class TestDeterminismAndObservability:
    def test_deterministic_content_identity(self, synthetic_repo_map: RepositoryMap) -> None:
        retriever = ContextRetriever()
        query = "User authentication timeout in database"

        res1 = retriever.retrieve(query, synthetic_repo_map)
        res2 = retriever.retrieve(query, synthetic_repo_map)

        # Using the explicit domain method separating deterministic content from runtime metadata
        assert res1.deterministic_dict() == res2.deterministic_dict()


# ---------------------------------------------------------------------------
# 6. JSON Serialization Lossless Round-Trip
# ---------------------------------------------------------------------------


class TestRetrievalSerialization:
    def test_retrieval_result_json_round_trip(self, synthetic_repo_map: RepositoryMap) -> None:
        retriever = ContextRetriever()
        original = retriever.retrieve("Invoice processing in billing service", synthetic_repo_map)

        json_str = original.model_dump_json()
        restored = RetrievalResult.model_validate_json(json_str)

        assert restored.deterministic_dict() == original.deterministic_dict()


# ---------------------------------------------------------------------------
# 7. Comprehensive 8-Category Benchmark Evaluation
# ---------------------------------------------------------------------------


@pytest.fixture
def comprehensive_benchmark(synthetic_repo_map: RepositoryMap) -> list[RetrievalBenchmarkTestCase]:
    """Diverse 8-category benchmark covering exact identifiers, terminology mismatch, errors, and distractors."""
    return [
        # Category A: Exact identifier
        RetrievalBenchmarkTestCase(
            case_id="A-EXACT-ID",
            category="exact_identifier",
            query="AuthenticationService fails when the token database is unavailable.",
            repo_map=synthetic_repo_map,
            primary_relevant_files=("src/auth/service.py",),
            secondary_relevant_files=("src/auth/database.py",),
            description="Direct match against AuthenticationService class",
            rationale="AuthenticationService coordinates DB access and contains the failing call",
        ),
        # Category B: Behavioral issue without implementation identifiers
        RetrievalBenchmarkTestCase(
            case_id="B-BEHAVIORAL",
            category="behavioral_mismatch",
            query="Users are logged out unexpectedly after their session expires.",
            repo_map=synthetic_repo_map,
            primary_relevant_files=("src/auth/session.py",),
            secondary_relevant_files=(),
            description="Issue uses user terms; code uses SessionManager, refresh_credentials, token_rotation",
            rationale="Session management logic resides in session.py",
        ),
        # Category C: Error-message issue
        RetrievalBenchmarkTestCase(
            case_id="C-ERROR-MSG",
            category="error_message",
            query="Raises TokenExpiredSignatureError: Signature has expired during verification",
            repo_map=synthetic_repo_map,
            primary_relevant_files=("src/auth/tokens.py",),
            secondary_relevant_files=(),
            description="Exact exception text in token verify_signature method",
            rationale="TokenExpiredSignatureError is declared and raised in tokens.py",
        ),
        # Category D: Multi-file issue
        RetrievalBenchmarkTestCase(
            case_id="D-MULTI-FILE",
            category="multi_file",
            query="Updating authentication configuration causes token validation to fail.",
            repo_map=synthetic_repo_map,
            primary_relevant_files=("pyproject.toml", "src/auth/service.py", "src/auth/tokens.py"),
            secondary_relevant_files=(),
            description="Interacting config, auth service, and token validation logic",
            rationale="Fix requires config changes and validation adjustments in both auth modules",
        ),
        # Category E: Indirect dependency issue
        RetrievalBenchmarkTestCase(
            case_id="E-INDIRECT-DEP",
            category="indirect_dependency",
            query="Connection pool exhaustion causes login timeouts",
            repo_map=synthetic_repo_map,
            primary_relevant_files=("src/auth/database.py",),
            secondary_relevant_files=("src/auth/service.py",),
            description="Login issue whose root-cause fix is in imported database pool",
            rationale="Database.py manages the connection pool; service.py calls it",
        ),
        # Category F: Test relationship issue
        RetrievalBenchmarkTestCase(
            case_id="F-TEST-REL",
            category="test_relationship",
            query="BillingService invoice tax calculation generates wrong total",
            repo_map=synthetic_repo_map,
            primary_relevant_files=("src/billing/service.py",),
            secondary_relevant_files=("tests/test_billing.py",),
            description="Implementation and associated test file",
            rationale="Planner needs both service implementation and tests for verification",
        ),
        # Category G: Distractor issue
        RetrievalBenchmarkTestCase(
            case_id="G-DISTRACTOR",
            category="distractor",
            query="Production authentication handler fails during credential validation",
            repo_map=synthetic_repo_map,
            primary_relevant_files=("src/auth/service.py",),
            secondary_relevant_files=(),
            distractor_files=("src/auth/mock_service.py", "docs/authentication.md", "src/billing/service.py"),
            description="Real service surrounded by mock service and documentation distractors",
            rationale="Production fix must target src/auth/service.py, not mock or docs",
        ),
        # Category H: Configuration issue
        RetrievalBenchmarkTestCase(
            case_id="H-CONFIG",
            category="configuration",
            query="Missing pyproject dependency specifications and requirements configuration",
            repo_map=synthetic_repo_map,
            primary_relevant_files=("pyproject.toml", "requirements.txt"),
            secondary_relevant_files=(),
            description="Build and dependency config resolution",
            rationale="Dependencies are declared in pyproject.toml and requirements.txt",
        ),
    ]


class TestComprehensiveBenchmark:
    def test_run_benchmark_and_compare_ablations(
        self, comprehensive_benchmark: list[RetrievalBenchmarkTestCase]
    ) -> None:
        retriever = ContextRetriever()
        evaluator = RetrievalEvaluator()

        rep_lexical = evaluator.evaluate_detailed(retriever, comprehensive_benchmark, strategy="lexical")
        rep_imports = evaluator.evaluate_detailed(retriever, comprehensive_benchmark, strategy="lexical+imports")
        rep_tests = evaluator.evaluate_detailed(retriever, comprehensive_benchmark, strategy="lexical+tests")
        rep_config = evaluator.evaluate_detailed(retriever, comprehensive_benchmark, strategy="lexical+config")
        rep_combined = evaluator.evaluate_detailed(retriever, comprehensive_benchmark, strategy="combined")

        assert len(rep_combined.case_results) == 8
        assert rep_combined.metrics.total_test_cases == 8

        # Verify no distractor in top 1 for Category G
        cat_g = next(c for c in rep_combined.case_results if c.category == "distractor")
        assert cat_g.retrieved_files[0] == "src/auth/service.py"
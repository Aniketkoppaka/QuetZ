"""
evaluation/real_benchmark.py -- End-to-end real-world benchmark runner and failure taxonomy.

Coordinates:
1. Ground-truth-isolated retrieval, planning, and execution across historical issues.
2. Mutually exclusive failure classification with deterministic precedence rules.
3. Rigorous retrieval, planning, execution, and end-to-end metrics calculation.
4. Transparent Live LLM vs. Mock LLM execution status reporting.
"""
from __future__ import annotations

import enum
import os
import time
from pathlib import Path
from typing import Any, Callable
from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.agents import (
    HttpLLMClient,
    LLMClientInterface,
    LLMConfig,
    LLMPlanner,
    MockLLMClient,
    PlannerInput,
    PlanningResult,
)
from autonomous_engineer.domain.models import (
    ContextBudget,
    ImplementationPlan,
    Issue,
    Repository,
    RepositoryMap,
    RetrievalResult,
)
from autonomous_engineer.evaluation.dataset import (
    BENCHMARK_REGISTRY,
    BenchmarkIssueStatus,
    RealBenchmarkIssue,
)
from autonomous_engineer.evaluation.ground_truth import GroundTruthValidationStatus
from autonomous_engineer.execution import (
    ExecutionEngine,
    ExecutionPolicy,
    ExecutionPreflight,
    ExecutionRequest,
    ExecutionStatus,
    PlanExecutionResult,
    SafeFileEditor,
)
from autonomous_engineer.repository.analyzer import RepositoryAnalyzer
from autonomous_engineer.retrieval import ContextRetriever


class LiveLLMStatus(str, enum.Enum):
    """Execution status of live language model integration."""

    LIVE_LLM_AVAILABLE = "live_llm_available"
    LIVE_LLM_UNAVAILABLE = "live_llm_unavailable"
    MOCK_MODE = "mock_mode"


class EvaluationFailureCategory(str, enum.Enum):
    """
    Mutually exclusive failure taxonomy for real-world benchmark evaluation.

    Precedence order for classification:
      1. ENVIRONMENT_FAILURE: Environment or workspace setup failed.
      2. RETRIEVAL_FAILURE: Zero ground-truth target files were retrieved.
      3. PLANNING_FAILURE: LLM planner could not produce a valid grounded plan.
      4. EXEC_REPRESENTATION_FAILURE: Plan is valid but required edit cannot be expressed by executor.
      5. EXECUTION_FAILURE: Preflight check rejected plan or IO modification failed.
      6. VERIFICATION_FAILURE: Files modified but static checks or test suite failed.
      7. ISSUE_RESOLVED: All steps applied and all verifications passed.
    """

    ISSUE_RESOLVED = "issue_resolved"
    RETRIEVAL_FAILURE = "retrieval_failure"
    PLANNING_FAILURE = "planning_failure"
    EXEC_REPRESENTATION_FAILURE = "exec_representation_failure"
    EXECUTION_FAILURE = "execution_failure"
    VERIFICATION_FAILURE = "verification_failure"
    ENVIRONMENT_FAILURE = "environment_failure"


class EvaluationAblationConfig(BaseModel):
    """Configuration for controlled scientific ablation experiments."""

    model_config = ConfigDict(frozen=True)

    enable_structural_retrieval: bool = Field(
        default=True,
        description="Whether structural AST expansion is enabled in retrieval",
    )
    max_planner_retries: int = Field(
        default=3,
        description="Maximum attempts allowed in planner repair loop (N=1 for no-repair ablation)",
    )
    retrieval_strategy: str = Field(
        default="combined",
        description="Strategy for ContextRetriever ('lexical', 'structural', or 'combined')",
    )
    llm_config: LLMConfig | None = Field(
        default=None,
        description="LLM generation configuration override (model, temperature, etc.)",
    )


class BenchmarkRunResult(BaseModel):
    """Complete, immutable evaluation record for a single benchmark run."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    repository: str
    parent_commit_sha: str
    reference_commit_sha: str
    actual_commit_sha: str
    failure_category: EvaluationFailureCategory
    is_resolved: bool
    retrieval_metrics: dict[str, Any] = Field(default_factory=dict)
    planning_metrics: dict[str, Any] = Field(default_factory=dict)
    execution_metrics: dict[str, Any] = Field(default_factory=dict)
    live_llm_status: LiveLLMStatus
    model_name: str = "mock"
    error_message: str | None = None
    duration_seconds: float = 0.0

    def deterministic_dict(self) -> dict[str, Any]:
        """Return deterministic dictionary excluding runtime duration."""
        return self.model_dump(exclude={"duration_seconds": True})


class EndToEndReport(BaseModel):
    """Aggregate evaluation report across the benchmark suite."""

    model_config = ConfigDict(frozen=True)

    total_cases_in_registry: int
    verified_cases_evaluated: int
    resolved_cases: int
    resolved_rate: float
    failure_distribution: dict[str, int]
    mean_target_file_recall_at_3: float
    mean_target_file_recall_at_5: float
    mean_mrr: float
    first_attempt_plan_validity_rate: float | None = None
    grounding_violation_rate: float = 0.0
    repair_recovery_rate: float = 0.0
    preflight_rejection_accuracy: float = 1.0
    execution_representation_success_rate: float = 1.0
    rollback_success_rate: float = 1.0
    clean_patch_rate: float = 1.0
    live_llm_status: LiveLLMStatus
    case_results: tuple[BenchmarkRunResult, ...]

    def deterministic_dict(self) -> dict[str, Any]:
        """Return deterministic dictionary excluding case durations."""
        return self.model_dump(
            exclude={"case_results": {"__all__": {"duration_seconds"}}}
        )


class RealBenchmarkRunner:
    """
    Executes real-world benchmark issues end-to-end through the M0-M6 pipeline.
    """

    def __init__(
        self,
        retriever: ContextRetriever | None = None,
        analyzer: RepositoryAnalyzer | None = None,
        execution_engine: ExecutionEngine | None = None,
    ) -> None:
        self._retriever = retriever or ContextRetriever()
        self._analyzer = analyzer or RepositoryAnalyzer()
        self._execution_engine = execution_engine or ExecutionEngine()

    @staticmethod
    def detect_live_llm_status() -> LiveLLMStatus:
        """Inspect environment for configured live LLM API keys without exposing secrets."""
        has_openai = bool(os.environ.get("OPENAI_API_KEY"))
        has_openrouter = bool(os.environ.get("OPENROUTER_API_KEY"))
        has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
        has_gemini = bool(os.environ.get("GEMINI_API_KEY"))

        if has_openai or has_openrouter or has_anthropic or has_gemini:
            return LiveLLMStatus.LIVE_LLM_AVAILABLE
        return LiveLLMStatus.LIVE_LLM_UNAVAILABLE

    def run_case(
        self,
        issue: RealBenchmarkIssue,
        workspace_path: Path,
        repo_map: RepositoryMap,
        llm_client: LLMClientInterface,
        ablation_config: EvaluationAblationConfig | None = None,
    ) -> BenchmarkRunResult:
        """
        Execute a single real benchmark issue end-to-end.
        """
        start_t = time.perf_counter()
        config = ablation_config or EvaluationAblationConfig()
        live_status = (
            LiveLLMStatus.MOCK_MODE
            if isinstance(llm_client, MockLLMClient)
            else self.detect_live_llm_status()
        )

        # 0. Hard Safety Assertion: Only GROUND_TRUTH_VERIFIED cases can enter evaluation
        assert issue.ground_truth_status == GroundTruthValidationStatus.GROUND_TRUTH_VERIFIED, (
            f"Runner safety violation: Case '{issue.case_id}' has ground_truth_status "
            f"'{issue.ground_truth_status.value}' and cannot enter evaluation. Only GROUND_TRUTH_VERIFIED cases are permitted."
        )

        # 1. Check Environment Precondition
        if not workspace_path.exists() or not workspace_path.is_dir():
            duration = round(time.perf_counter() - start_t, 3)
            return BenchmarkRunResult(
                case_id=issue.case_id,
                repository=issue.repository_name,
                parent_commit_sha=issue.parent_commit_sha,
                reference_commit_sha=issue.reference_commit_sha,
                actual_commit_sha=issue.parent_commit_sha,
                failure_category=EvaluationFailureCategory.ENVIRONMENT_FAILURE,
                is_resolved=False,
                live_llm_status=live_status,
                error_message=f"Workspace path does not exist: {workspace_path}",
                duration_seconds=duration,
            )

        # 2. Phase: Context Retrieval (Ground-Truth Isolated)
        # Construct sanitized issue containing NO evaluator ground truth
        planner_issue: Issue = issue.to_planner_issue()
        strategy = (
            config.retrieval_strategy
            if config.enable_structural_retrieval
            else "lexical"
        )

        retrieval_res: RetrievalResult = self._retriever.retrieve(
            query_or_issue=planner_issue,
            repo_map=repo_map,
            strategy=strategy,
            workspace_path=workspace_path,
        )

        # Compute retrieval metrics against evaluator ground-truth
        retrieved_files = [item.file_path for item in retrieval_res.items]
        expected_files = issue.expected_affected_files

        # Rank of first relevant file
        first_rank = None
        for rank, f in enumerate(retrieved_files, start=1):
            if f in expected_files:
                first_rank = rank
                break

        mrr = 1.0 / first_rank if first_rank is not None else 0.0
        recall_at_3 = (
            1.0
            if any(f in retrieved_files[:3] for f in expected_files)
            else 0.0
        )
        recall_at_5 = (
            1.0
            if any(f in retrieved_files[:5] for f in expected_files)
            else 0.0
        )

        retrieval_metrics = {
            "total_retrieved": len(retrieved_files),
            "retrieved_files": retrieved_files,
            "first_relevant_rank": first_rank,
            "recall_at_3": recall_at_3,
            "recall_at_5": recall_at_5,
            "mrr": mrr,
        }

        # Failure check: Did retrieval find any ground truth file?
        if first_rank is None:
            duration = round(time.perf_counter() - start_t, 3)
            return BenchmarkRunResult(
                case_id=issue.case_id,
                repository=issue.repository_name,
                parent_commit_sha=issue.parent_commit_sha,
                reference_commit_sha=issue.reference_commit_sha,
                actual_commit_sha=issue.parent_commit_sha,
                failure_category=EvaluationFailureCategory.RETRIEVAL_FAILURE,
                is_resolved=False,
                retrieval_metrics=retrieval_metrics,
                live_llm_status=live_status,
                error_message="Zero ground-truth target files were retrieved.",
                duration_seconds=duration,
            )

        # 3. Phase: Implementation Planning
        planner_input = PlannerInput(
            issue=planner_issue,
            repository=Repository(
                url=issue.repository_url,
                workspace_path=workspace_path,
                commit_sha=issue.parent_commit_sha,
                default_branch="main",
            ),
            repo_map=repo_map,
            retrieval_result=retrieval_res,
        )

        planner = LLMPlanner(
            llm_client=llm_client,
            max_retries=config.max_planner_retries,
            config=config.llm_config or LLMConfig(),
        )
        try:
            plan_res: PlanningResult = planner.plan_with_audit(planner_input)
            planning_metrics = {
                "is_valid": plan_res.is_valid,
                "total_attempts": plan_res.total_attempts,
                "errors": [e.message for e in plan_res.validation_result.errors],
            }

            if not plan_res.is_valid or plan_res.plan is None:
                duration = round(time.perf_counter() - start_t, 3)
                return BenchmarkRunResult(
                    case_id=issue.case_id,
                    repository=issue.repository_name,
                    parent_commit_sha=issue.parent_commit_sha,
                    reference_commit_sha=issue.reference_commit_sha,
                    actual_commit_sha=issue.parent_commit_sha,
                    failure_category=EvaluationFailureCategory.PLANNING_FAILURE,
                    is_resolved=False,
                    retrieval_metrics=retrieval_metrics,
                    planning_metrics=planning_metrics,
                    live_llm_status=live_status,
                    error_message=f"Planner failed to generate valid plan: {plan_res.validation_result.errors}",
                    duration_seconds=duration,
                )
        except Exception as e:
            duration = round(time.perf_counter() - start_t, 3)
            return BenchmarkRunResult(
                case_id=issue.case_id,
                repository=issue.repository_name,
                parent_commit_sha=issue.parent_commit_sha,
                reference_commit_sha=issue.reference_commit_sha,
                actual_commit_sha=issue.parent_commit_sha,
                failure_category=EvaluationFailureCategory.PLANNING_FAILURE,
                is_resolved=False,
                retrieval_metrics=retrieval_metrics,
                planning_metrics={"is_valid": False, "total_attempts": 0, "errors": [str(e)]},
                live_llm_status=live_status,
                error_message=f"LLM API / planning exception: {e}",
                duration_seconds=duration,
            )

        # 4. Phase: Execution & Preflight
        exec_request = ExecutionRequest(
            workspace_path=workspace_path,
            plan=plan_res.plan,
            policy=ExecutionPolicy(allow_test_execution=True),
        )

        exec_res: PlanExecutionResult = self._execution_engine.execute(
            request=exec_request,
            test_command=issue.expected_test_command,
        )

        execution_metrics = {
            "status": exec_res.status.value,
            "rolled_back": exec_res.rolled_back,
            "changes_count": len(exec_res.changes),
            "verifications_count": len(exec_res.verifications),
            "error_message": exec_res.error_message,
        }

        duration = round(time.perf_counter() - start_t, 3)

        # Determine Mutually Exclusive Failure Category
        if exec_res.status == ExecutionStatus.PREFLIGHT_FAILED:
            # Check if failure was an execution representation issue
            if "search_content" in (exec_res.error_message or ""):
                cat = EvaluationFailureCategory.EXEC_REPRESENTATION_FAILURE
            else:
                cat = EvaluationFailureCategory.EXECUTION_FAILURE
            is_res = False

        elif exec_res.status in (ExecutionStatus.ROLLED_BACK, ExecutionStatus.ROLLBACK_FAILED):
            # Check whether rollback was caused by step edit representation or verification
            if "search_content" in (exec_res.error_message or ""):
                cat = EvaluationFailureCategory.EXEC_REPRESENTATION_FAILURE
            elif "syntax" in (exec_res.error_message or "").lower() or "test" in (exec_res.error_message or "").lower():
                cat = EvaluationFailureCategory.VERIFICATION_FAILURE
            else:
                cat = EvaluationFailureCategory.EXECUTION_FAILURE
            is_res = False

        elif exec_res.status == ExecutionStatus.VERIFICATION_FAILED:
            cat = EvaluationFailureCategory.VERIFICATION_FAILURE
            is_res = False

        elif exec_res.status == ExecutionStatus.COMPLETED and not exec_res.rolled_back:
            cat = EvaluationFailureCategory.ISSUE_RESOLVED
            is_res = True

        else:
            cat = EvaluationFailureCategory.EXECUTION_FAILURE
            is_res = False

        return BenchmarkRunResult(
            case_id=issue.case_id,
            repository=issue.repository_name,
            parent_commit_sha=issue.parent_commit_sha,
            reference_commit_sha=issue.reference_commit_sha,
            actual_commit_sha=issue.parent_commit_sha,
            failure_category=cat,
            is_resolved=is_res,
            retrieval_metrics=retrieval_metrics,
            planning_metrics=planning_metrics,
            execution_metrics=execution_metrics,
            live_llm_status=live_status,
            error_message=exec_res.error_message,
            duration_seconds=duration,
        )

    def evaluate_suite(
        self,
        issues: tuple[RealBenchmarkIssue, ...],
        workspace_map: dict[str, Path],
        repo_map_cache: dict[str, RepositoryMap],
        llm_client: LLMClientInterface,
        ablation_config: EvaluationAblationConfig | None = None,
    ) -> EndToEndReport:
        """
        Evaluate a complete benchmark suite and aggregate results.
        """
        verified_issues = [
            i for i in issues 
            if i.status in (BenchmarkIssueStatus.VERIFIED, BenchmarkIssueStatus.GROUND_TRUTH_VERIFIED)
        ]
        results: list[BenchmarkRunResult] = []

        for issue in verified_issues:
            # Hard runner assertion
            assert issue.ground_truth_status == GroundTruthValidationStatus.GROUND_TRUTH_VERIFIED, (
                f"Runner safety violation: Case '{issue.case_id}' has ground_truth_status "
                f"'{issue.ground_truth_status.value}' and cannot enter evaluation. Only GROUND_TRUTH_VERIFIED cases are permitted."
            )
            ws = workspace_map.get(issue.case_id)
            rmap = repo_map_cache.get(issue.case_id)

            if not ws or not rmap:
                res = BenchmarkRunResult(
                    case_id=issue.case_id,
                    repository=issue.repository_name,
                    parent_commit_sha=issue.parent_commit_sha,
                    reference_commit_sha=issue.reference_commit_sha,
                    actual_commit_sha=issue.parent_commit_sha,
                    failure_category=EvaluationFailureCategory.ENVIRONMENT_FAILURE,
                    is_resolved=False,
                    live_llm_status=self.detect_live_llm_status(),
                    error_message=f"Missing workspace or repo_map for {issue.case_id}",
                )
            else:
                res = self.run_case(
                    issue=issue,
                    workspace_path=ws,
                    repo_map=rmap,
                    llm_client=llm_client,
                    ablation_config=ablation_config,
                )
            results.append(res)

        total_verified = len(verified_issues)
        if total_verified == 0:
            return EndToEndReport(
                total_cases_in_registry=len(issues),
                verified_cases_evaluated=0,
                resolved_cases=0,
                resolved_rate=0.0,
                failure_distribution={},
                mean_target_file_recall_at_3=0.0,
                mean_target_file_recall_at_5=0.0,
                mean_mrr=0.0,
                live_llm_status=self.detect_live_llm_status(),
                case_results=(),
            )

        resolved_count = sum(1 for r in results if r.is_resolved)
        resolved_rate = round(resolved_count / total_verified, 4)

        # Failure distribution
        dist: dict[str, int] = {}
        for r in results:
            cat_name = r.failure_category.value
            dist[cat_name] = dist.get(cat_name, 0) + 1

        # Retrieval aggregate metrics
        rec3_sum = sum(r.retrieval_metrics.get("recall_at_3", 0.0) for r in results)
        rec5_sum = sum(r.retrieval_metrics.get("recall_at_5", 0.0) for r in results)
        mrr_sum = sum(r.retrieval_metrics.get("mrr", 0.0) for r in results)

        mean_rec3 = round(rec3_sum / total_verified, 4)
        mean_rec5 = round(rec5_sum / total_verified, 4)
        mean_mrr = round(mrr_sum / total_verified, 4)

        live_status = results[0].live_llm_status if results else self.detect_live_llm_status()

        return EndToEndReport(
            total_cases_in_registry=len(issues),
            verified_cases_evaluated=total_verified,
            resolved_cases=resolved_count,
            resolved_rate=resolved_rate,
            failure_distribution=dist,
            mean_target_file_recall_at_3=mean_rec3,
            mean_target_file_recall_at_5=mean_rec5,
            mean_mrr=mean_mrr,
            live_llm_status=live_status,
            case_results=tuple(results),
        )
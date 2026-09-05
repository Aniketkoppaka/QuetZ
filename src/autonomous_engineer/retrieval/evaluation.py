"""
retrieval/evaluation.py -- Information Retrieval evaluation harness for code retrieval.

Computes Precision@K, Recall@K, Mean Reciprocal Rank (MRR), and per-case breakdowns
across categorized benchmarks with primary, secondary, and distractor ground truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict, Field, model_validator

from autonomous_engineer.domain.models import RepositoryMap
from autonomous_engineer.retrieval.combined import ContextRetriever


class RetrievalBenchmarkTestCase(BaseModel):
    """A test case in the retrieval evaluation benchmark with structured ground-truth."""

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(default="", description="Unique identifier for benchmark case (e.g. 'AUTH-001')")
    category: str = Field(
        default="general",
        description="Category: 'exact_identifier', 'behavioral_mismatch', 'error_message', "
                    "'multi_file', 'indirect_dependency', 'test_relationship', 'distractor', 'configuration'",
    )
    query: str = Field(description="Issue title / problem description")
    repo_map: RepositoryMap = Field(description="The mapped repository under test")
    primary_relevant_files: tuple[str, ...] = Field(
        default=(),
        description="Primary files directly requiring modification or direct root-cause files",
    )
    secondary_relevant_files: tuple[str, ...] = Field(
        default=(),
        description="Contextually relevant files (associated tests, imported dependencies, config)",
    )
    expected_relevant_files: tuple[str, ...] = Field(
        default=(),
        description="Complete set of relevant files expected in ground truth",
    )
    distractor_files: tuple[str, ...] = Field(
        default=(),
        description="Files with high lexical overlap that are not relevant to solving the issue",
    )
    description: str = Field(default="", description="Optional description of test scenario")
    rationale: str = Field(default="", description="Engineering justification for ground-truth relevance")

    @model_validator(mode="after")
    def populate_expected_relevant_files(self) -> RetrievalBenchmarkTestCase:
        if not self.expected_relevant_files:
            combined = tuple(dict.fromkeys(self.primary_relevant_files + self.secondary_relevant_files))
            object.__setattr__(self, "expected_relevant_files", combined)
        return self


@dataclass(frozen=True)
class CaseEvaluationResult:
    """Evaluation result for an individual benchmark case."""

    case_id: str
    category: str
    query: str
    retrieved_files: tuple[str, ...]
    expected_files: tuple[str, ...]
    distractor_files: tuple[str, ...]
    precision_at_1: float
    precision_at_3: float
    precision_at_5: float
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    reciprocal_rank: float
    distractor_in_top_3: bool


@dataclass(frozen=True)
class RetrievalMetrics:
    """Standard Information Retrieval metrics computed over a benchmark set."""

    precision_at_1: float
    precision_at_3: float
    precision_at_5: float
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float
    total_test_cases: int


@dataclass(frozen=True)
class DetailedEvaluationReport:
    """Comprehensive evaluation report containing aggregate metrics and per-case results."""

    metrics: RetrievalMetrics
    case_results: tuple[CaseEvaluationResult, ...]
    strategy: str


class RetrievalEvaluator:
    """Evaluates context retrieval performance across benchmark queries."""

    def evaluate(
        self,
        retriever: ContextRetriever,
        test_cases: tuple[RetrievalBenchmarkTestCase, ...] | list[RetrievalBenchmarkTestCase],
        strategy: str = "combined",
    ) -> RetrievalMetrics:
        """Run retrieval over test cases and return aggregate RetrievalMetrics."""
        report = self.evaluate_detailed(retriever, test_cases, strategy=strategy)
        return report.metrics

    def evaluate_detailed(
        self,
        retriever: ContextRetriever,
        test_cases: tuple[RetrievalBenchmarkTestCase, ...] | list[RetrievalBenchmarkTestCase],
        strategy: str = "combined",
    ) -> DetailedEvaluationReport:
        """Run retrieval over test cases and return DetailedEvaluationReport."""
        if not test_cases:
            empty_m = RetrievalMetrics(
                precision_at_1=0.0,
                precision_at_3=0.0,
                precision_at_5=0.0,
                recall_at_1=0.0,
                recall_at_3=0.0,
                recall_at_5=0.0,
                mrr=0.0,
                total_test_cases=0,
            )
            return DetailedEvaluationReport(metrics=empty_m, case_results=(), strategy=strategy)

        case_results: list[CaseEvaluationResult] = []
        p1_scores: list[float] = []
        p3_scores: list[float] = []
        p5_scores: list[float] = []
        r1_scores: list[float] = []
        r3_scores: list[float] = []
        r5_scores: list[float] = []
        reciprocal_ranks: list[float] = []

        for tc in test_cases:
            expected_set = set(tc.expected_relevant_files)
            distractor_set = set(tc.distractor_files)
            if not expected_set:
                continue

            result = retriever.retrieve(
                query_or_issue=tc.query,
                repo_map=tc.repo_map,
                strategy=strategy,
            )

            # Deduplicated list of retrieved distinct file paths preserving rank order
            retrieved_files: list[str] = []
            seen: set[str] = set()
            for it in result.items:
                if it.file_path not in seen:
                    seen.add(it.file_path)
                    retrieved_files.append(it.file_path)

            def pk(k: int) -> float:
                top_k = retrieved_files[:k]
                if not top_k:
                    return 0.0
                hits = sum(1 for f in top_k if f in expected_set)
                return hits / float(k)

            def rk(k: int) -> float:
                top_k = retrieved_files[:k]
                if not expected_set:
                    return 0.0
                hits = sum(1 for f in top_k if f in expected_set)
                return hits / float(len(expected_set))

            p1 = pk(1)
            p3 = pk(3)
            p5 = pk(5)
            r1 = rk(1)
            r3 = rk(3)
            r5 = rk(5)

            p1_scores.append(p1)
            p3_scores.append(p3)
            p5_scores.append(p5)
            r1_scores.append(r1)
            r3_scores.append(r3)
            r5_scores.append(r5)

            rr = 0.0
            for rank_idx, f in enumerate(retrieved_files, start=1):
                if f in expected_set:
                    rr = 1.0 / rank_idx
                    break
            reciprocal_ranks.append(rr)

            distractor_hit = any(f in distractor_set for f in retrieved_files[:3])

            case_results.append(
                CaseEvaluationResult(
                    case_id=tc.case_id or tc.query[:20],
                    category=tc.category,
                    query=tc.query,
                    retrieved_files=tuple(retrieved_files),
                    expected_files=tc.expected_relevant_files,
                    distractor_files=tc.distractor_files,
                    precision_at_1=round(p1, 4),
                    precision_at_3=round(p3, 4),
                    precision_at_5=round(p5, 4),
                    recall_at_1=round(r1, 4),
                    recall_at_3=round(r3, 4),
                    recall_at_5=round(r5, 4),
                    reciprocal_rank=round(rr, 4),
                    distractor_in_top_3=distractor_hit,
                )
            )

        n = len(test_cases)
        metrics = RetrievalMetrics(
            precision_at_1=round(sum(p1_scores) / n, 4),
            precision_at_3=round(sum(p3_scores) / n, 4),
            precision_at_5=round(sum(p5_scores) / n, 4),
            recall_at_1=round(sum(r1_scores) / n, 4),
            recall_at_3=round(sum(r3_scores) / n, 4),
            recall_at_5=round(sum(r5_scores) / n, 4),
            mrr=round(sum(reciprocal_ranks) / n, 4),
            total_test_cases=n,
        )

        return DetailedEvaluationReport(
            metrics=metrics,
            case_results=tuple(case_results),
            strategy=strategy,
        )
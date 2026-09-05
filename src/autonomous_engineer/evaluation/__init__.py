"""
evaluation -- Real-world benchmark dataset, live LLM evaluation harness, ground-truth validation, and persistence.

Public API:
  - BenchmarkIssueStatus: Enum of issue registry status (VERIFIED, CANDIDATE, EXCLUDED).
  - RealBenchmarkIssue: Immutable benchmark issue specification with ground-truth isolation.
  - BENCHMARK_REGISTRY: Curated registry of real-world Python repository issues.
  - LiveLLMStatus: Enum capturing live vs. mock LLM execution mode.
  - EvaluationFailureCategory: Mutually exclusive failure taxonomy.
  - EvaluationAblationConfig: Configuration for controlled scientific ablation experiments.
  - BenchmarkRunResult: Detailed per-case run results with metrics and error diagnostics.
  - EndToEndReport: Aggregate evaluation report across benchmark suite.
  - RealBenchmarkRunner: End-to-end evaluation harness.
  - LLMProviderConfig: Configuration contract for live LLM providers.
  - EnvironmentAuditor: Safe environment capability inspector.
  - EvaluationMode: Mode selection (LIVE, MOCK, UNAVAILABLE).
  - BenchmarkRunPersistence: Machine-readable artifact persistence writer.
  - GroundTruthValidationStatus: Evaluator-side ground-truth taxonomy.
  - GroundTruthValidationResult: Evaluator-side result model.
  - GroundTruthValidationReport: Aggregate ground-truth validation report.
  - GroundTruthValidator: Dataset & environment validation engine.
  - BenchmarkEnvironmentAuditor: Host and container runtime capability auditor.
  - BenchmarkEnvironmentStatus: Immutable environment status data model.
  - GroundTruthBenchmarkRunner: Registry SHA integrity and environment runner.
  - GroundTruthArtifactPersistence: Ground-truth run JSON artifact writer.
"""
from __future__ import annotations

from autonomous_engineer.evaluation.config import (
    EnvironmentAuditor,
    EvaluationMode,
    LLMProviderConfig,
)
from autonomous_engineer.evaluation.dataset import (
    BENCHMARK_REGISTRY,
    BenchmarkIssueStatus,
    RealBenchmarkIssue,
)
from autonomous_engineer.evaluation.environment import (
    BenchmarkEnvironmentAuditor,
    BenchmarkEnvironmentStatus,
    GroundTruthArtifactPersistence,
    GroundTruthBenchmarkRunner,
)
from autonomous_engineer.evaluation.ground_truth import (
    GroundTruthValidationReport,
    GroundTruthValidationResult,
    GroundTruthValidationStatus,
    GroundTruthValidator,
)
from autonomous_engineer.evaluation.persistence import BenchmarkRunPersistence
from autonomous_engineer.evaluation.pipeline_eval import (
    BenchmarkEvaluationReport,
    BenchmarkScenario,
    PipelineBenchmarkHarness,
    ScenarioEvaluationResult,
)
from autonomous_engineer.evaluation.real_benchmark import (
    BenchmarkRunResult,
    EndToEndReport,
    EvaluationAblationConfig,
    EvaluationFailureCategory,
    LiveLLMStatus,
    RealBenchmarkRunner,
)

__all__ = [
    "BENCHMARK_REGISTRY",
    "BenchmarkEnvironmentAuditor",
    "BenchmarkEnvironmentStatus",
    "BenchmarkEvaluationReport",
    "BenchmarkIssueStatus",
    "BenchmarkRunPersistence",
    "BenchmarkRunResult",
    "BenchmarkScenario",
    "EndToEndReport",
    "EnvironmentAuditor",
    "EvaluationAblationConfig",
    "EvaluationFailureCategory",
    "EvaluationMode",
    "GroundTruthArtifactPersistence",
    "GroundTruthBenchmarkRunner",
    "GroundTruthValidationReport",
    "GroundTruthValidationResult",
    "GroundTruthValidationStatus",
    "GroundTruthValidator",
    "LLMProviderConfig",
    "LiveLLMStatus",
    "PipelineBenchmarkHarness",
    "RealBenchmarkIssue",
    "RealBenchmarkRunner",
    "ScenarioEvaluationResult",
]
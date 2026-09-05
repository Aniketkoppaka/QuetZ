"""
agents -- Planning and agent protocols for the autonomous software engineer.

Public API:
  - PlannerInput: Formal input contract provided to planning agents.
  - PlannerInterface: Protocol interface for planning agent implementations.
  - ImplementationAgentContract: Assumptions and verification specification.
  - LLMPlanner: Grounded LLM implementation planner with bounded repair loop.
  - PlanningResult, PlanningAuditRecord: Planning execution output and audit trail.
  - LLMClientInterface, LLMConfig, LLMMessage, LLMResponse, MockLLMClient, HttpLLMClient: Provider-neutral LLM client.
  - PlannerPromptBuilder, PLANNER_SYSTEM_PROMPT: Prompt generation and repair prompt builder.
  - PlanValidator, PlanValidationError, PlanValidationResult: Plan validation engine and models.
  - PlanningValidationBenchmark, PlanningBenchmarkTestCase, ValidationBenchmarkReport: Validator benchmark.
  - PlannerBenchmarkHarness, PlannerBenchmarkScenario, PlannerEvaluationReport: Planner benchmark.
"""
from __future__ import annotations

from autonomous_engineer.agents.benchmark import (
    PlannerBenchmarkHarness,
    PlannerBenchmarkScenario,
    PlannerEvaluationReport,
    PlanningBenchmarkTestCase,
    PlanningValidationBenchmark,
    ValidationBenchmarkReport,
)
from autonomous_engineer.agents.llm_client import (
    HttpLLMClient,
    LLMClientInterface,
    LLMConfig,
    LLMMessage,
    LLMResponse,
    MockLLMClient,
)
from autonomous_engineer.agents.planner import (
    LLMPlanner,
    PlanningAuditRecord,
    PlanningResult,
)
from autonomous_engineer.agents.prompt_builder import (
    PLANNER_SYSTEM_PROMPT,
    PlannerPromptBuilder,
)
from autonomous_engineer.agents.protocol import (
    ImplementationAgentContract,
    PlannerInput,
    PlannerInterface,
)
from autonomous_engineer.agents.validator import (
    AbstentionAssessment,
    AbstentionDecision,
    AbstentionEngine,
    PlanValidationError,
    PlanValidationResult,
    PlanValidator,
)

__all__ = [
    "AbstentionAssessment",
    "AbstentionDecision",
    "AbstentionEngine",
    "HttpLLMClient",
    "ImplementationAgentContract",
    "LLMClientInterface",
    "LLMConfig",
    "LLMMessage",
    "LLMPlanner",
    "LLMResponse",
    "MockLLMClient",
    "PLANNER_SYSTEM_PROMPT",
    "PlanValidationError",
    "PlanValidationResult",
    "PlanValidator",
    "PlannerBenchmarkHarness",
    "PlannerBenchmarkScenario",
    "PlannerEvaluationReport",
    "PlannerInput",
    "PlannerInterface",
    "PlannerPromptBuilder",
    "PlanningAuditRecord",
    "PlanningBenchmarkTestCase",
    "PlanningResult",
    "PlanningValidationBenchmark",
    "ValidationBenchmarkReport",
]

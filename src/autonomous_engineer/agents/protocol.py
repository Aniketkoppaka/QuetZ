"""
agents/protocol.py -- Planning agent protocol, input contracts, and agent assumptions.

Defines the formal input and output interface for planning agents and the contract
governing what future implementation agents may assume from an ImplementationPlan.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.domain.models import (
    FailureDetail,
    ImplementationPlan,
    Issue,
    Repository,
    RepositoryMap,
    RetrievalResult,
)


class PlannerInput(BaseModel):
    """
    Formal input contract provided to a planning agent.
    """

    model_config = ConfigDict(frozen=True)

    issue: Issue = Field(description="The GitHub issue to resolve")
    repository: Repository = Field(description="The acquired repository reference")
    repo_map: RepositoryMap = Field(description="Deterministic AST structural repository map")
    retrieval_result: RetrievalResult = Field(
        description="Ranked, budgeted retrieval result containing grounded context",
    )
    attempt_number: int = Field(
        default=1,
        ge=1,
        description="Which repair iteration produced this planning invocation",
    )
    previous_failure: FailureDetail | None = Field(
        default=None,
        description="Details of previous execution or review failure if in repair loop",
    )
    previous_plan: ImplementationPlan | None = Field(
        default=None,
        description="Previous plan that failed execution or review, if in repair loop",
    )

    def deterministic_dict(self) -> dict[str, Any]:
        """Return deterministic dictionary representation of planning input."""
        return self.model_dump(
            exclude={
                "retrieval_result": {"retrieved_at"},
                "repo_map": {"scanned_at"},
                "repository": {"acquired_at"},
            }
        )


class ImplementationAgentContract(BaseModel):
    """
    Explicit specification of what a future coding agent is allowed to assume
    and what it must independently verify before applying changes.
    """

    model_config = ConfigDict(frozen=True)

    allowed_assumptions: tuple[str, ...] = Field(
        default=(
            "Target files exist if step operation is modify/delete/refactor.",
            "Steps must be executed in topological order respecting dependencies.",
            "Each step must satisfy its stated verification_requirement.",
        ),
        description="Facts and behaviors the coding agent may rely on without re-planning.",
    )
    mandatory_verifications: tuple[str, ...] = Field(
        default=(
            "Verify syntax and AST validity before and after applying edits.",
            "Verify that unmodified code in the file is preserved without regressions.",
            "Verify that declared assumptions in the plan hold in actual source code.",
            "Run relevant test suites to confirm issue resolution.",
        ),
        description="Independent checks the coding agent must perform during execution.",
    )


@runtime_checkable
class PlannerInterface(Protocol):
    """Protocol for any planner implementation (deterministic rule-based or future LLM)."""

    def plan(self, planner_input: PlannerInput) -> ImplementationPlan:
        """
        Produce a validated, grounded ImplementationPlan for the given input.

        Args:
            planner_input: Validated PlannerInput contract.

        Returns:
            Validated ImplementationPlan.
        """
        ...
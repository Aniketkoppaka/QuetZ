"""
tools/__init__.py -- Controlled, policy-gated tool infrastructure for ASE.

Phase 2.3: EngineeringSkill / PlaybookRegistry
    Structured declarative playbook definitions that specify per-issue trigger
    heuristics, required capabilities, required verifications, and step-level
    guidance injected into the LLM planner.  Skills are pure data — they carry
    no executable code themselves; all execution is routed through ASE's
    SafeFileEditor / ExecutionEngine / ExecutionPolicy safety layer.

Phase 2.4: PolicyGatedToolRouter
    Audited ToolRequest router.  Every tool invocation is:
      1. Validated against ExecutionPolicy.granted_capabilities (fail-closed).
      2. Validated against ExecutionPolicy.max_risk_level (fail-closed).
      3. Logged into FlightRecorder before the result is returned.

No unrestricted shell execution.  All tool calls respect ASE's capability,
risk-level, and audit invariants.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.execution.models import (
    Capability,
    ExecutionPolicy,
    RiskLevel,
)
from autonomous_engineer.observability import FlightRecorder


# ---------------------------------------------------------------------------
# Phase 2.3 — Engineering Skills / Playbooks
# ---------------------------------------------------------------------------


class EngineeringSkill(BaseModel):
    """
    Declarative description of a reusable engineering playbook.

    A skill is pure *metadata* — it does not contain executable code.
    Its ``step_guidance`` is injected into the LLM planner's prompt to
    constrain how the model structures its ``ImplementationPlan``.

    All fields are immutable (``frozen=True``) so registry entries can be
    safely shared across concurrent sessions.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(
        description="Unique machine-readable skill identifier (snake_case)."
    )
    description: str = Field(
        description="Human-readable summary of what this playbook addresses."
    )
    trigger_patterns: tuple[str, ...] = Field(
        description=(
            "Case-insensitive regex patterns matched against issue text. "
            "At least one must match for the skill to be selected."
        )
    )
    required_capabilities: tuple[Capability, ...] = Field(
        description=(
            "Capabilities that MUST be present in ExecutionPolicy.granted_capabilities "
            "before this skill may be applied."
        )
    )
    required_verifications: tuple[str, ...] = Field(
        default=("syntax_ast",),
        description=(
            "VerificationType string keys that must pass post-execution. "
            "Passed to AbstentionEngine during assessment."
        ),
    )
    max_steps: int = Field(
        default=10,
        ge=1,
        description="Soft upper bound on ImplementationPlan.steps length.",
    )
    step_guidance: str = Field(
        default="",
        description=(
            "Additional planner prompt guidance injected when this skill is active. "
            "Should be concise, declarative, and not reference specific file paths."
        ),
    )

    def matches(self, issue_text: str) -> bool:
        """
        Return True if at least one ``trigger_pattern`` matches *issue_text*.

        Matching is case-insensitive full-string search (``re.search``).
        """
        for pattern in self.trigger_patterns:
            if re.search(pattern, issue_text, re.IGNORECASE):
                return True
        return False

    def capabilities_satisfied_by(self, policy: ExecutionPolicy) -> bool:
        """
        Return True if *policy* grants every capability required by this skill.
        """
        granted = frozenset(policy.granted_capabilities)
        return all(cap in granted for cap in self.required_capabilities)


class PlaybookRegistry:
    """
    Thread-safe registry of :class:`EngineeringSkill` playbooks.

    Skills are stored in insertion order.  ``match()`` returns all skills
    whose trigger patterns match the supplied issue text AND whose required
    capabilities are satisfied by the given policy (or all matching if no
    policy is supplied).
    """

    def __init__(self) -> None:
        self._skills: dict[str, EngineeringSkill] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, skill: EngineeringSkill) -> None:
        """
        Register *skill*.  Raises ``ValueError`` if a skill with the same
        name is already registered.
        """
        if skill.name in self._skills:
            raise ValueError(
                f"A skill named {skill.name!r} is already registered. "
                "Unregister it first or use a different name."
            )
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> None:
        """Remove a skill by name.  No-op if not found."""
        self._skills.pop(name, None)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get(self, name: str) -> EngineeringSkill | None:
        """Return the skill with *name*, or ``None``."""
        return self._skills.get(name)

    @property
    def all_skills(self) -> tuple[EngineeringSkill, ...]:
        """Return all registered skills in insertion order."""
        return tuple(self._skills.values())

    def match(
        self,
        issue_text: str,
        policy: ExecutionPolicy | None = None,
    ) -> list[EngineeringSkill]:
        """
        Return skills whose trigger patterns match *issue_text*.

        If *policy* is provided, only skills whose ``required_capabilities``
        are fully granted by *policy* are included.
        """
        results: list[EngineeringSkill] = []
        for skill in self._skills.values():
            if not skill.matches(issue_text):
                continue
            if policy is not None and not skill.capabilities_satisfied_by(policy):
                continue
            results.append(skill)
        return results


# ---------------------------------------------------------------------------
# Built-in skills
# ---------------------------------------------------------------------------

_PYTHON_BUG_FIX = EngineeringSkill(
    name="python_bug_fix",
    description=(
        "General Python bug fix: correct logic errors, handle exceptions, "
        "fix attribute/type errors, and repair incorrect return values."
    ),
    trigger_patterns=(
        r"\bTraceback\b",
        r"\bAttributeError\b",
        r"\bTypeError\b",
        r"\bValueError\b",
        r"\bKeyError\b",
        r"\bIndexError\b",
        r"\bbug\b",
        r"\bfix\b",
        r"\berror\b",
        r"\bexception\b",
        r"\bcrash\b",
        r"\bfail(s|ed|ure)?\b",
    ),
    required_capabilities=(
        Capability.CAP_READ_REPO,
        Capability.CAP_WRITE_SOURCE,
    ),
    required_verifications=("syntax_ast", "subprocess_test"),
    max_steps=8,
    step_guidance=(
        "Focus only on the minimal change set needed to eliminate the reported "
        "exception or incorrect behaviour.  Do not refactor unrelated code. "
        "Always add or update a targeted regression test as the final step."
    ),
)

_DEPENDENCY_UPGRADE = EngineeringSkill(
    name="dependency_upgrade",
    description=(
        "Upgrade a third-party dependency: update pinned versions, fix "
        "compatibility shims, and verify the import chain is still intact."
    ),
    trigger_patterns=(
        r"\bupgrade\b",
        r"\bupdate\b",
        r"\bdependenc(y|ies)\b",
        r"\brequirements?\b",
        r"\bpyproject\b",
        r"\bsetup\.cfg\b",
        r"\bpip\b",
        r"\bpackage\b",
        r"\bversion\b",
        r"\bcompat(ib(le|ility))?\b",
        r"\bbreaking\s+change\b",
    ),
    required_capabilities=(
        Capability.CAP_READ_REPO,
        Capability.CAP_WRITE_SOURCE,
        Capability.CAP_CREATE_FILE,
    ),
    required_verifications=("syntax_ast", "subprocess_test"),
    max_steps=6,
    step_guidance=(
        "Update version specifiers in the single canonical requirements/pyproject "
        "file.  Add a compatibility shim only if the public API changed.  "
        "Do not change unrelated dependencies in the same step."
    ),
)

_TEST_REPAIR = EngineeringSkill(
    name="test_repair",
    description=(
        "Repair a failing test suite: fix broken assertions, update stale "
        "fixtures, correct mock targets, and restore CI green state."
    ),
    trigger_patterns=(
        r"\btest(s|ing)?\b",
        r"\bpytest\b",
        r"\bunittest\b",
        r"\bfixture\b",
        r"\bassert(ion)?\b",
        r"\bmock\b",
        r"\bCI\b",
        r"\bfailing\s+test\b",
        r"\bbroken\s+test\b",
    ),
    required_capabilities=(
        Capability.CAP_READ_REPO,
        Capability.CAP_WRITE_SOURCE,
        Capability.CAP_RUN_TEST,
    ),
    required_verifications=("syntax_ast", "subprocess_test"),
    max_steps=10,
    step_guidance=(
        "Identify the root cause of each failing test before writing any code. "
        "Update only test files and the minimum production code needed to satisfy "
        "the test contract.  Do not delete tests; prefer fixing them."
    ),
)

# Singleton registry pre-populated with built-in skills.
PLAYBOOK_REGISTRY: PlaybookRegistry = PlaybookRegistry()
PLAYBOOK_REGISTRY.register(_PYTHON_BUG_FIX)
PLAYBOOK_REGISTRY.register(_DEPENDENCY_UPGRADE)
PLAYBOOK_REGISTRY.register(_TEST_REPAIR)


# ---------------------------------------------------------------------------
# Phase 2.4 — Policy-Gated External Tool Framework
# ---------------------------------------------------------------------------

# Ordered risk levels for numeric comparison.
_RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.R0_READ_ONLY: 0,
    RiskLevel.R1_LOCAL_MUTATION: 1,
    RiskLevel.R2_TEST_EXECUTION: 2,
    RiskLevel.R3_GIT_MUTATION: 3,
    RiskLevel.R4_EXTERNAL_COMMUNICATION: 4,
    RiskLevel.R5_PRODUCTION_IMPACT: 5,
}


def _risk_exceeds(requested: RiskLevel, maximum: RiskLevel) -> bool:
    """Return True if *requested* risk is strictly greater than *maximum*."""
    return _RISK_ORDER[requested] > _RISK_ORDER[maximum]


class ToolRequest(BaseModel):
    """
    Immutable record of a single agent tool invocation request.

    Created by the caller before routing through :class:`PolicyGatedToolRouter`.
    The router will validate capability and risk constraints before proceeding.
    """

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique request identifier (UUID4).",
    )
    actor: str = Field(
        description="Logical identity of the requesting component (e.g. 'llm_planner')."
    )
    tool_name: str = Field(
        description="Registered name of the tool being invoked."
    )
    operation: str = Field(
        description="Operation being performed within the tool (e.g. 'read_file')."
    )
    capability_required: Capability = Field(
        description="The single capability that must be granted for this operation."
    )
    risk_level: RiskLevel = Field(
        description="Risk classification of this operation."
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value parameters forwarded to the tool handler.",
    )


class ToolResult(BaseModel):
    """
    Immutable record returned by :class:`PolicyGatedToolRouter` after routing
    a :class:`ToolRequest`.
    """

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(description="Echoed from the originating ToolRequest.")
    success: bool = Field(description="True iff the operation was permitted and completed.")
    output: Any = Field(default=None, description="Tool output on success; None on failure.")
    error: str | None = Field(
        default=None,
        description="Human-readable error message on failure; None on success.",
    )


class PolicyGatedToolRouter:
    """
    Validates and audits every tool invocation against :class:`ExecutionPolicy`.

    Routing is always *fail-closed*: any policy violation immediately returns a
    failed :class:`ToolResult` without invoking the underlying handler.

    All invocations — successes and failures — are recorded in the supplied
    :class:`FlightRecorder` (if provided) for audit purposes.

    **Design invariants**:

    * The router never executes arbitrary shell commands.
    * Handlers are plain Python callables registered via :meth:`register_handler`.
    * A handler that raises is caught; the exception message is recorded and a
      failed ToolResult is returned (fail-closed).
    """

    def __init__(self) -> None:
        # tool_name -> callable(parameters: dict) -> Any
        self._handlers: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def register_handler(
        self,
        tool_name: str,
        handler: Any,
    ) -> None:
        """
        Register *handler* for *tool_name*.

        *handler* must be a callable accepting a single ``dict[str, Any]``
        argument (the ``ToolRequest.parameters``) and returning any value.
        Raises ``ValueError`` if *tool_name* is already registered.
        """
        if tool_name in self._handlers:
            raise ValueError(
                f"Handler for tool {tool_name!r} is already registered."
            )
        self._handlers[tool_name] = handler

    # ------------------------------------------------------------------
    # Core routing
    # ------------------------------------------------------------------

    def route(
        self,
        request: ToolRequest,
        policy: ExecutionPolicy,
        recorder: FlightRecorder | None = None,
    ) -> ToolResult:
        """
        Route *request* through policy checks and invoke the handler.

        Policy checks (in order):
          1. Capability check — ``request.capability_required`` must be in
             ``policy.granted_capabilities``.
          2. Risk level check — ``request.risk_level`` must not exceed
             ``policy.max_risk_level``.
          3. Handler availability — tool must be registered.
          4. Handler invocation (wrapped in try/except).

        All four outcomes are logged to *recorder* when provided.

        Returns
        -------
        ToolResult
            ``success=True``  with ``output`` on success.
            ``success=False`` with ``error`` on any policy or execution failure.
        """
        log_payload: dict[str, Any] = {
            "request_id": request.request_id,
            "actor": request.actor,
            "tool_name": request.tool_name,
            "operation": request.operation,
            "capability_required": request.capability_required.value,
            "risk_level": request.risk_level.value,
        }

        # --- Check 1: Capability ---
        if request.capability_required not in policy.granted_capabilities:
            error_msg = (
                f"Capability {request.capability_required.value!r} is not granted. "
                f"Granted: {[c.value for c in policy.granted_capabilities]}"
            )
            log_payload["outcome"] = "capability_denied"
            log_payload["error"] = error_msg
            if recorder is not None:
                recorder.record("tool_request", "tool_router", log_payload)
            return ToolResult(
                request_id=request.request_id,
                success=False,
                error=error_msg,
            )

        # --- Check 2: Risk level ---
        if _risk_exceeds(request.risk_level, policy.max_risk_level):
            error_msg = (
                f"Risk level {request.risk_level.value!r} exceeds maximum "
                f"allowed {policy.max_risk_level.value!r}."
            )
            log_payload["outcome"] = "risk_denied"
            log_payload["error"] = error_msg
            if recorder is not None:
                recorder.record("tool_request", "tool_router", log_payload)
            return ToolResult(
                request_id=request.request_id,
                success=False,
                error=error_msg,
            )

        # --- Check 3: Handler availability ---
        handler = self._handlers.get(request.tool_name)
        if handler is None:
            error_msg = (
                f"No handler registered for tool {request.tool_name!r}."
            )
            log_payload["outcome"] = "handler_missing"
            log_payload["error"] = error_msg
            if recorder is not None:
                recorder.record("tool_request", "tool_router", log_payload)
            return ToolResult(
                request_id=request.request_id,
                success=False,
                error=error_msg,
            )

        # --- Check 4: Invocation ---
        try:
            output = handler(request.parameters)
            log_payload["outcome"] = "success"
            if recorder is not None:
                recorder.record("tool_request", "tool_router", log_payload)
            return ToolResult(
                request_id=request.request_id,
                success=True,
                output=output,
            )
        except Exception as exc:  # noqa: BLE001
            error_msg = (
                f"Handler for {request.tool_name!r} raised {type(exc).__name__}: {exc}"
            )
            log_payload["outcome"] = "handler_error"
            log_payload["error"] = error_msg
            if recorder is not None:
                recorder.record("tool_request", "tool_router", log_payload)
            return ToolResult(
                request_id=request.request_id,
                success=False,
                error=error_msg,
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Phase 2.3
    "EngineeringSkill",
    "PlaybookRegistry",
    "PLAYBOOK_REGISTRY",
    # Phase 2.4
    "ToolRequest",
    "ToolResult",
    "PolicyGatedToolRouter",
]

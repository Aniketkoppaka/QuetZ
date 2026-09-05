"""
tests/unit/test_tools.py -- Tests for Phase 2.3 (EngineeringSkill / PlaybookRegistry)
                           and Phase 2.4 (PolicyGatedToolRouter).
"""
from __future__ import annotations

import pytest

from autonomous_engineer.execution.models import (
    Capability,
    ExecutionPolicy,
    RiskLevel,
)
from autonomous_engineer.observability import FlightRecorder
from autonomous_engineer.tools import (
    PLAYBOOK_REGISTRY,
    EngineeringSkill,
    PlaybookRegistry,
    PolicyGatedToolRouter,
    ToolRequest,
    ToolResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(
    name: str = "test_skill",
    patterns: tuple[str, ...] = (r"\bbug\b",),
    caps: tuple[Capability, ...] = (Capability.CAP_READ_REPO,),
) -> EngineeringSkill:
    return EngineeringSkill(
        name=name,
        description="A test skill",
        trigger_patterns=patterns,
        required_capabilities=caps,
        required_verifications=("syntax_ast",),
        max_steps=5,
        step_guidance="Test guidance.",
    )


def _make_policy(
    caps: tuple[Capability, ...] = (
        Capability.CAP_READ_REPO,
        Capability.CAP_WRITE_SOURCE,
        Capability.CAP_CREATE_FILE,
        Capability.CAP_RUN_TEST,
    ),
    max_risk: RiskLevel = RiskLevel.R2_TEST_EXECUTION,
) -> ExecutionPolicy:
    return ExecutionPolicy(granted_capabilities=caps, max_risk_level=max_risk)


def _make_request(
    cap: Capability = Capability.CAP_READ_REPO,
    risk: RiskLevel = RiskLevel.R0_READ_ONLY,
    tool: str = "my_tool",
) -> ToolRequest:
    return ToolRequest(
        actor="planner",
        tool_name=tool,
        operation="read",
        capability_required=cap,
        risk_level=risk,
    )


# ---------------------------------------------------------------------------
# Phase 2.3 — EngineeringSkill
# ---------------------------------------------------------------------------


class TestEngineeringSkill:
    def test_matches_on_keyword(self):
        skill = _make_skill(patterns=(r"\bbug\b",))
        assert skill.matches("There is a bug in the parser")

    def test_matches_case_insensitive(self):
        skill = _make_skill(patterns=(r"\bAttributeError\b",))
        assert skill.matches("Got an attributeerror when calling foo")

    def test_no_match_when_no_pattern_fits(self):
        skill = _make_skill(patterns=(r"\bnetwork\b",))
        assert not skill.matches("This is a logic bug in the parser")

    def test_matches_any_pattern(self):
        skill = _make_skill(patterns=(r"\bnetwork\b", r"\bfix\b"))
        assert skill.matches("Need to fix the timeout handler")

    def test_capabilities_satisfied_all_present(self):
        skill = _make_skill(
            caps=(Capability.CAP_READ_REPO, Capability.CAP_WRITE_SOURCE)
        )
        policy = _make_policy(
            caps=(
                Capability.CAP_READ_REPO,
                Capability.CAP_WRITE_SOURCE,
                Capability.CAP_RUN_TEST,
            )
        )
        assert skill.capabilities_satisfied_by(policy)

    def test_capabilities_not_satisfied_when_missing(self):
        skill = _make_skill(caps=(Capability.CAP_DELETE_FILE,))
        policy = _make_policy(
            caps=(Capability.CAP_READ_REPO, Capability.CAP_WRITE_SOURCE)
        )
        assert not skill.capabilities_satisfied_by(policy)

    def test_frozen_model_raises_on_mutation(self):
        skill = _make_skill()
        with pytest.raises(Exception):  # pydantic ValidationError or TypeError
            skill.name = "new_name"  # type: ignore[misc]

    def test_required_verifications_default(self):
        skill = _make_skill()
        assert "syntax_ast" in skill.required_verifications

    def test_max_steps_ge_1(self):
        with pytest.raises(Exception):
            EngineeringSkill(
                name="bad",
                description="bad",
                trigger_patterns=(r"\bbug\b",),
                required_capabilities=(Capability.CAP_READ_REPO,),
                max_steps=0,  # invalid
            )


# ---------------------------------------------------------------------------
# Phase 2.3 — PlaybookRegistry
# ---------------------------------------------------------------------------


class TestPlaybookRegistry:
    def test_register_and_get(self):
        reg = PlaybookRegistry()
        skill = _make_skill(name="alpha")
        reg.register(skill)
        assert reg.get("alpha") is skill

    def test_all_skills_insertion_order(self):
        reg = PlaybookRegistry()
        s1 = _make_skill(name="first")
        s2 = _make_skill(name="second")
        reg.register(s1)
        reg.register(s2)
        names = [s.name for s in reg.all_skills]
        assert names == ["first", "second"]

    def test_duplicate_name_raises(self):
        reg = PlaybookRegistry()
        reg.register(_make_skill(name="dupe"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(_make_skill(name="dupe"))

    def test_unregister_removes_skill(self):
        reg = PlaybookRegistry()
        reg.register(_make_skill(name="to_remove"))
        reg.unregister("to_remove")
        assert reg.get("to_remove") is None
        assert len(reg.all_skills) == 0

    def test_unregister_missing_no_op(self):
        reg = PlaybookRegistry()
        # Should not raise
        reg.unregister("nonexistent")

    def test_match_returns_matching_skills(self):
        reg = PlaybookRegistry()
        bug_skill = _make_skill(name="s1", patterns=(r"\bbug\b",))
        net_skill = _make_skill(name="s2", patterns=(r"\bnetwork\b",))
        reg.register(bug_skill)
        reg.register(net_skill)
        results = reg.match("There is a bug in the code")
        assert len(results) == 1
        assert results[0].name == "s1"

    def test_match_returns_empty_when_no_match(self):
        reg = PlaybookRegistry()
        reg.register(_make_skill(name="s1", patterns=(r"\bnetwork\b",)))
        assert reg.match("Something about a bug") == []

    def test_match_with_policy_filters_missing_capabilities(self):
        reg = PlaybookRegistry()
        skill = _make_skill(
            name="del_skill",
            patterns=(r"\bbug\b",),
            caps=(Capability.CAP_DELETE_FILE,),
        )
        reg.register(skill)
        # Policy without CAP_DELETE_FILE
        policy = _make_policy(caps=(Capability.CAP_READ_REPO,))
        results = reg.match("found a bug", policy=policy)
        assert results == []

    def test_match_with_policy_includes_when_caps_granted(self):
        reg = PlaybookRegistry()
        skill = _make_skill(
            name="s",
            patterns=(r"\bbug\b",),
            caps=(Capability.CAP_READ_REPO,),
        )
        reg.register(skill)
        policy = _make_policy(caps=(Capability.CAP_READ_REPO,))
        results = reg.match("found a bug", policy=policy)
        assert len(results) == 1

    def test_match_without_policy_ignores_capabilities(self):
        reg = PlaybookRegistry()
        skill = _make_skill(
            name="s",
            patterns=(r"\bbug\b",),
            caps=(Capability.CAP_DELETE_FILE,),
        )
        reg.register(skill)
        # No policy: match even without the required capability
        results = reg.match("found a bug")
        assert len(results) == 1

    def test_get_returns_none_for_missing(self):
        reg = PlaybookRegistry()
        assert reg.get("nonexistent") is None


# ---------------------------------------------------------------------------
# Phase 2.3 — Built-in PLAYBOOK_REGISTRY
# ---------------------------------------------------------------------------


class TestBuiltinPlaybookRegistry:
    def test_three_builtin_skills_registered(self):
        names = {s.name for s in PLAYBOOK_REGISTRY.all_skills}
        assert "python_bug_fix" in names
        assert "dependency_upgrade" in names
        assert "test_repair" in names

    def test_python_bug_fix_matches_traceback(self):
        skill = PLAYBOOK_REGISTRY.get("python_bug_fix")
        assert skill is not None
        assert skill.matches("Traceback (most recent call last):")

    def test_dependency_upgrade_matches_requirements(self):
        skill = PLAYBOOK_REGISTRY.get("dependency_upgrade")
        assert skill is not None
        assert skill.matches("Upgrade requirements.txt to use requests 2.32")

    def test_test_repair_matches_pytest(self):
        skill = PLAYBOOK_REGISTRY.get("test_repair")
        assert skill is not None
        assert skill.matches("Fix failing pytest tests in CI")

    def test_builtin_skills_have_step_guidance(self):
        for skill in PLAYBOOK_REGISTRY.all_skills:
            assert skill.step_guidance.strip(), f"{skill.name} has empty step_guidance"


# ---------------------------------------------------------------------------
# Phase 2.4 — PolicyGatedToolRouter (allow path)
# ---------------------------------------------------------------------------


class TestPolicyGatedToolRouterAllow:
    def test_successful_route_returns_success(self):
        router = PolicyGatedToolRouter()
        router.register_handler("echo", lambda p: p.get("value", "ok"))
        req = _make_request(
            cap=Capability.CAP_READ_REPO,
            risk=RiskLevel.R0_READ_ONLY,
            tool="echo",
        )
        policy = _make_policy()
        result = router.route(req, policy)
        assert result.success is True
        assert result.error is None
        assert result.request_id == req.request_id

    def test_handler_output_forwarded(self):
        router = PolicyGatedToolRouter()
        router.register_handler("sum", lambda p: p["a"] + p["b"])
        req = ToolRequest(
            actor="planner",
            tool_name="sum",
            operation="compute",
            capability_required=Capability.CAP_READ_REPO,
            risk_level=RiskLevel.R0_READ_ONLY,
            parameters={"a": 3, "b": 7},
        )
        result = router.route(req, _make_policy())
        assert result.success is True
        assert result.output == 10

    def test_route_at_max_risk_exactly(self):
        router = PolicyGatedToolRouter()
        router.register_handler("t", lambda p: "ok")
        req = _make_request(
            cap=Capability.CAP_RUN_TEST,
            risk=RiskLevel.R2_TEST_EXECUTION,
            tool="t",
        )
        policy = _make_policy(max_risk=RiskLevel.R2_TEST_EXECUTION)
        result = router.route(req, policy)
        assert result.success is True


# ---------------------------------------------------------------------------
# Phase 2.4 — PolicyGatedToolRouter (reject paths)
# ---------------------------------------------------------------------------


class TestPolicyGatedToolRouterRejects:
    def test_rejects_missing_capability(self):
        router = PolicyGatedToolRouter()
        router.register_handler("git_push", lambda p: "pushed")
        req = _make_request(
            cap=Capability.CAP_GIT_COMMIT,
            risk=RiskLevel.R3_GIT_MUTATION,
            tool="git_push",
        )
        # Policy does not grant CAP_GIT_COMMIT
        policy = _make_policy(caps=(Capability.CAP_READ_REPO,))
        result = router.route(req, policy)
        assert result.success is False
        assert result.output is None
        assert "cap_git_commit" in result.error.lower()

    def test_rejects_excessive_risk(self):
        router = PolicyGatedToolRouter()
        router.register_handler("deploy", lambda p: "deployed")
        req = _make_request(
            cap=Capability.CAP_READ_REPO,
            risk=RiskLevel.R5_PRODUCTION_IMPACT,
            tool="deploy",
        )
        policy = _make_policy(max_risk=RiskLevel.R2_TEST_EXECUTION)
        result = router.route(req, policy)
        assert result.success is False
        assert "r5_production_impact" in result.error.lower()

    def test_rejects_unregistered_tool(self):
        router = PolicyGatedToolRouter()
        req = _make_request(cap=Capability.CAP_READ_REPO, risk=RiskLevel.R0_READ_ONLY, tool="ghost")
        result = router.route(req, _make_policy())
        assert result.success is False
        assert "ghost" in result.error

    def test_handler_error_caught_fails_closed(self):
        router = PolicyGatedToolRouter()

        def boom(p):
            raise RuntimeError("Something went wrong")

        router.register_handler("bombtool", boom)
        req = _make_request(cap=Capability.CAP_READ_REPO, risk=RiskLevel.R0_READ_ONLY, tool="bombtool")
        result = router.route(req, _make_policy())
        assert result.success is False
        assert "RuntimeError" in result.error
        assert "Something went wrong" in result.error

    def test_request_id_echoed_on_failure(self):
        router = PolicyGatedToolRouter()
        req = _make_request(cap=Capability.CAP_DELETE_FILE, risk=RiskLevel.R1_LOCAL_MUTATION, tool="del")
        policy = _make_policy(caps=(Capability.CAP_READ_REPO,))
        result = router.route(req, policy)
        assert result.request_id == req.request_id


# ---------------------------------------------------------------------------
# Phase 2.4 — Flight Recorder audit
# ---------------------------------------------------------------------------


class TestToolRouterFlightRecorder:
    def _recorder(self) -> FlightRecorder:
        return FlightRecorder(run_id="test-run")

    def test_successful_route_logged(self):
        router = PolicyGatedToolRouter()
        router.register_handler("echo", lambda p: "ok")
        req = _make_request(cap=Capability.CAP_READ_REPO, risk=RiskLevel.R0_READ_ONLY, tool="echo")
        recorder = self._recorder()
        router.route(req, _make_policy(), recorder=recorder)
        events = recorder.filter_events(event_type="tool_request")
        assert len(events) == 1
        assert events[0].payload["outcome"] == "success"

    def test_capability_denial_logged(self):
        router = PolicyGatedToolRouter()
        req = _make_request(cap=Capability.CAP_DELETE_FILE, risk=RiskLevel.R1_LOCAL_MUTATION, tool="del")
        policy = _make_policy(caps=(Capability.CAP_READ_REPO,))
        recorder = self._recorder()
        router.route(req, policy, recorder=recorder)
        events = recorder.filter_events(event_type="tool_request")
        assert len(events) == 1
        assert events[0].payload["outcome"] == "capability_denied"

    def test_risk_denial_logged(self):
        router = PolicyGatedToolRouter()
        req = _make_request(
            cap=Capability.CAP_READ_REPO,
            risk=RiskLevel.R5_PRODUCTION_IMPACT,
            tool="any",
        )
        recorder = self._recorder()
        router.route(req, _make_policy(max_risk=RiskLevel.R0_READ_ONLY), recorder=recorder)
        events = recorder.filter_events(event_type="tool_request")
        assert events[0].payload["outcome"] == "risk_denied"

    def test_missing_handler_logged(self):
        router = PolicyGatedToolRouter()
        req = _make_request(cap=Capability.CAP_READ_REPO, risk=RiskLevel.R0_READ_ONLY, tool="ghost")
        recorder = self._recorder()
        router.route(req, _make_policy(), recorder=recorder)
        events = recorder.filter_events(event_type="tool_request")
        assert events[0].payload["outcome"] == "handler_missing"

    def test_handler_error_logged(self):
        router = PolicyGatedToolRouter()
        router.register_handler("boom", lambda p: (_ for _ in ()).throw(ValueError("oops")))
        req = _make_request(cap=Capability.CAP_READ_REPO, risk=RiskLevel.R0_READ_ONLY, tool="boom")
        recorder = self._recorder()
        router.route(req, _make_policy(), recorder=recorder)
        events = recorder.filter_events(event_type="tool_request")
        assert events[0].payload["outcome"] == "handler_error"

    def test_no_recorder_does_not_raise(self):
        router = PolicyGatedToolRouter()
        router.register_handler("echo", lambda p: "ok")
        req = _make_request(cap=Capability.CAP_READ_REPO, risk=RiskLevel.R0_READ_ONLY, tool="echo")
        # No recorder; must not raise
        result = router.route(req, _make_policy(), recorder=None)
        assert result.success is True

    def test_multiple_requests_all_logged(self):
        router = PolicyGatedToolRouter()
        router.register_handler("r", lambda p: "ok")
        recorder = self._recorder()
        policy = _make_policy()
        for _ in range(5):
            req = _make_request(cap=Capability.CAP_READ_REPO, risk=RiskLevel.R0_READ_ONLY, tool="r")
            router.route(req, policy, recorder=recorder)
        events = recorder.filter_events(event_type="tool_request", component="tool_router")
        assert len(events) == 5

    def test_component_tag_is_tool_router(self):
        router = PolicyGatedToolRouter()
        router.register_handler("r", lambda p: "ok")
        recorder = self._recorder()
        req = _make_request(cap=Capability.CAP_READ_REPO, risk=RiskLevel.R0_READ_ONLY, tool="r")
        router.route(req, _make_policy(), recorder=recorder)
        events = recorder.filter_events(component="tool_router")
        assert len(events) == 1


# ---------------------------------------------------------------------------
# Phase 2.4 — ToolRequest / ToolResult models
# ---------------------------------------------------------------------------


class TestToolRequestModel:
    def test_request_id_auto_generated(self):
        req1 = _make_request()
        req2 = _make_request()
        assert req1.request_id != req2.request_id

    def test_explicit_request_id_accepted(self):
        req = ToolRequest(
            request_id="fixed-id",
            actor="x",
            tool_name="t",
            operation="o",
            capability_required=Capability.CAP_READ_REPO,
            risk_level=RiskLevel.R0_READ_ONLY,
        )
        assert req.request_id == "fixed-id"

    def test_frozen_prevents_mutation(self):
        req = _make_request()
        with pytest.raises(Exception):
            req.actor = "hacker"  # type: ignore[misc]

    def test_parameters_default_empty(self):
        req = _make_request()
        assert req.parameters == {}


class TestToolResultModel:
    def test_success_result(self):
        result = ToolResult(request_id="abc", success=True, output=42)
        assert result.success is True
        assert result.output == 42
        assert result.error is None

    def test_failure_result(self):
        result = ToolResult(request_id="abc", success=False, error="denied")
        assert result.success is False
        assert result.error == "denied"
        assert result.output is None

    def test_frozen_prevents_mutation(self):
        result = ToolResult(request_id="abc", success=True)
        with pytest.raises(Exception):
            result.success = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Phase 2.4 — Handler registration
# ---------------------------------------------------------------------------


class TestHandlerRegistration:
    def test_duplicate_handler_raises(self):
        router = PolicyGatedToolRouter()
        router.register_handler("t", lambda p: None)
        with pytest.raises(ValueError, match="already registered"):
            router.register_handler("t", lambda p: None)

    def test_multiple_distinct_handlers(self):
        router = PolicyGatedToolRouter()
        router.register_handler("a", lambda p: "A")
        router.register_handler("b", lambda p: "B")
        policy = _make_policy()
        ra = router.route(
            _make_request(cap=Capability.CAP_READ_REPO, risk=RiskLevel.R0_READ_ONLY, tool="a"),
            policy,
        )
        rb = router.route(
            _make_request(cap=Capability.CAP_READ_REPO, risk=RiskLevel.R0_READ_ONLY, tool="b"),
            policy,
        )
        assert ra.output == "A"
        assert rb.output == "B"

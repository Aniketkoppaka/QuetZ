"""
Unit tests for policy engine in config/policy_engine.py.
"""
from autonomous_engineer.config.policy_engine import (
    OrgCompliancePolicy,
    PolicyEngine,
)


def test_clean_patch_passes_policy():
    engine = PolicyEngine()
    result = engine.evaluate_patch(
        files_modified=["src/math_utils.py", "tests/test_math.py"],
        file_contents={"src/math_utils.py": "def f(): return 42"},
    )
    assert result.passed
    assert len(result.violations) == 0
    assert "PASS" in result.to_markdown()


def test_detects_protected_path_violation():
    engine = PolicyEngine()
    result = engine.evaluate_patch(
        files_modified=[".github/workflows/deploy.yml", "src/foo.py"]
    )
    assert not result.passed
    assert any(v.rule_name == "PROTECTED_PATH_MODIFIED" for v in result.violations)
    assert "REJECTED" in result.to_markdown()


def test_detects_banned_import_violation():
    policy = OrgCompliancePolicy(banned_imports=("telnetlib", "pickle"))
    engine = PolicyEngine(policy=policy)
    result = engine.evaluate_patch(
        files_modified=["src/legacy.py"],
        file_contents={"src/legacy.py": "import telnetlib\nimport os\n"},
    )
    assert not result.passed
    assert any(v.rule_name == "BANNED_IMPORT" for v in result.violations)


def test_enforces_required_test_modification():
    policy = OrgCompliancePolicy(require_test_modifications=True)
    engine = PolicyEngine(policy=policy)
    result = engine.evaluate_patch(
        files_modified=["src/core.py"],
        file_contents={"src/core.py": "x = 1"},
    )
    assert not result.passed
    assert any(v.rule_name == "MISSING_TEST_CHANGES" for v in result.violations)


def test_detects_file_ceiling_exceeded():
    policy = OrgCompliancePolicy(max_files_modified_ceiling=2)
    engine = PolicyEngine(policy=policy)
    result = engine.evaluate_patch(
        files_modified=["a.py", "b.py", "c.py"],
    )
    assert not result.passed
    assert any(v.rule_name == "MAX_MODIFIED_FILES_EXCEEDED" for v in result.violations)


def test_detects_lines_changed_ceiling_exceeded():
    policy = OrgCompliancePolicy(max_lines_changed_ceiling=10)
    engine = PolicyEngine(policy=policy)
    large_code = "\n".join([f"line_{i} = {i}" for i in range(20)])
    result = engine.evaluate_patch(
        files_modified=["src/large.py"],
        file_contents={"src/large.py": large_code},
    )
    assert not result.passed
    assert any(v.rule_name == "MAX_LINES_CHANGED_EXCEEDED" for v in result.violations)


def test_detects_js_ts_banned_import():
    policy = OrgCompliancePolicy(banned_imports=("telnet-client", "unsafe-eval"))
    engine = PolicyEngine(policy=policy)
    result = engine.evaluate_patch(
        files_modified=["src/network.ts"],
        file_contents={"src/network.ts": "import { connect } from 'telnet-client';\nexport const x = 1;"},
    )
    assert not result.passed
    assert any(v.rule_name == "BANNED_IMPORT" for v in result.violations)


def test_load_policy_from_json_file(tmp_path):
    import json
    cfg = tmp_path / "enterprise_policy.json"
    cfg.write_text(
        json.dumps({
            "banned_imports": ["eval", "telnetlib"],
            "max_files_modified_ceiling": 5,
            "require_test_modifications": True,
            "network_egress_policy": "BLOCKED"
        }),
        encoding="utf-8"
    )

    policy = OrgCompliancePolicy.from_file(cfg)
    assert "eval" in policy.banned_imports
    assert policy.max_files_modified_ceiling == 5
    assert policy.require_test_modifications is True
    assert policy.network_egress_policy == "BLOCKED"
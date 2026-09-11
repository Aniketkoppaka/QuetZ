"""
Unit tests for .quetz.yaml project-level configuration loader in config/project_config.py.
"""
import json
from autonomous_engineer.config.project_config import QuetzProjectConfig


def test_load_project_config_from_json(tmp_path):
    cfg_file = tmp_path / ".quetz.json"
    cfg_file.write_text(
        json.dumps({
            "version": 1,
            "policy": "custom-enterprise",
            "execution": {
                "test_command": "pytest -m fast",
                "sandbox": "docker",
                "min_confidence": 0.90,
                "enable_mutation_testing": True,
            },
            "banned_imports": ["telnetlib", "eval"],
            "protected_paths": ["release/**"],
        }),
        encoding="utf-8"
    )

    loaded = QuetzProjectConfig.load_from_workspace(tmp_path)
    assert loaded is not None
    assert loaded.policy == "custom-enterprise"
    assert loaded.execution.test_command == "pytest -m fast"
    assert loaded.execution.sandbox == "docker"
    assert loaded.execution.min_confidence == 0.90
    assert loaded.execution.enable_mutation_testing is True
    assert "eval" in loaded.banned_imports
    assert "release/**" in loaded.protected_paths


def test_returns_none_when_no_config(tmp_path):
    assert QuetzProjectConfig.load_from_workspace(tmp_path) is None
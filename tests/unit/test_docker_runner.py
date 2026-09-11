"""
Unit tests for DockerRunner in execution/docker_runner.py.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

from autonomous_engineer.execution.docker_runner import (
    DockerExecutionConfig,
    DockerExecutionResult,
    DockerRunner,
)
from autonomous_engineer.execution.models import ExecutionPolicy
from autonomous_engineer.execution.verifier import ExecutionVerifier


def test_docker_execution_config_defaults():
    cfg = DockerExecutionConfig()
    assert cfg.image_name == "quetz-sandbox:latest"
    assert cfg.network_mode == "none"
    assert cfg.memory_limit == "1024m"
    assert cfg.cpu_limit == "2.0"


def test_docker_runner_build_command(tmp_path):
    cfg = DockerExecutionConfig(
        image_name="test-img:1.0",
        memory_limit="512m",
        cpu_limit="1.5",
        network_mode="none",
    )
    runner = DockerRunner(config=cfg)
    cmd = runner.build_docker_cmd(tmp_path, "pytest -k test_math")

    assert "run" in cmd
    assert "--rm" in cmd
    assert "--network" in cmd
    assert "none" in cmd
    assert "-m" in cmd
    assert "512m" in cmd
    assert "--cpus" in cmd
    assert "1.5" in cmd
    assert f"{tmp_path.resolve()}:/workspace" in cmd
    assert "test-img:1.0" in cmd
    assert cmd[-1] == "pytest -k test_math"


def test_docker_runner_fallback_when_docker_unavailable(tmp_path):
    test_file = tmp_path / "test_simple.py"
    test_file.write_text("def test_ok(): assert 1 == 1\n", encoding="utf-8")

    runner = DockerRunner()
    # Mock Docker as unavailable
    with patch.object(runner, "is_docker_available", return_value=False):
        res = runner.run_command("python -m unittest", workspace=tmp_path, allow_fallback=True)
        assert res.fallback_used is True
        assert res.sandboxed is False


def test_docker_runner_fail_closed_if_fallback_disallowed(tmp_path):
    runner = DockerRunner()
    with patch.object(runner, "is_docker_available", return_value=False):
        res = runner.run_command("pytest", workspace=tmp_path, allow_fallback=False)
        assert res.fallback_used is False
        assert res.passed is False
        assert "Docker daemon unreachable" in (res.error_message or "")


def test_execution_verifier_delegates_to_docker(tmp_path):
    verifier = ExecutionVerifier()
    policy = ExecutionPolicy(
        use_docker_sandbox=True,
        docker_image="quetz-custom:v1",
        allowed_test_commands=("pytest",),
    )

    with patch("autonomous_engineer.execution.docker_runner.DockerRunner.run_command") as mock_run:
        mock_run.return_value = DockerExecutionResult(
            exit_code=0,
            stdout="1 passed in 0.05s",
            stderr="",
            duration_ms=50.0,
            sandboxed=True,
            fallback_used=False,
        )

        res = verifier.verify_tests(tmp_path, policy, command_override="pytest -k test_foo")
        assert res.passed is True
        assert res.exit_code == 0
        assert "1 passed in 0.05s" in res.stdout
        mock_run.assert_called_once()
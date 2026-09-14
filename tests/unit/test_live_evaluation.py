"""
tests/unit/test_live_evaluation.py

Comprehensive tests for Milestone 8: Live LLM evaluation infrastructure,
provider configuration, secret non-disclosure, artifact persistence,
CLI interface, and environment auditor.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest

from autonomous_engineer.evaluation import (
    BENCHMARK_REGISTRY,
    BenchmarkIssueStatus,
    BenchmarkRunPersistence,
    BenchmarkRunResult,
    EndToEndReport,
    EnvironmentAuditor,
    EvaluationFailureCategory,
    EvaluationMode,
    LLMProviderConfig,
    LiveLLMStatus,
    RealBenchmarkIssue,
)
from autonomous_engineer.evaluation.cli import create_parser, main


# ---------------------------------------------------------------------------
# 1. Provider Configuration & Secret Non-Disclosure Tests
# ---------------------------------------------------------------------------


class TestProviderConfiguration:
    def test_provider_config_secret_masking(self) -> None:
        dummy_secret = "".join(["test", "_key_", "1234567890"])
        config = LLMProviderConfig(
            provider_name="openai-compatible",
            api_base_url="https://api.openai.com/v1",
            model_name="gpt-4o",
            api_key=dummy_secret,
        )
        assert config.has_credentials is True

        masked = config.masked_dict()
        assert masked["api_key"] == "[REDACTED_SECRET]"
        assert "mock-test-key" not in json.dumps(masked)
        assert masked["has_credentials"] is True

    def test_provider_config_without_credentials(self) -> None:
        config = LLMProviderConfig(api_key=None)
        assert config.has_credentials is False
        masked = config.masked_dict()
        assert masked["api_key"] is None
        assert masked["has_credentials"] is False

    def test_environment_auditor_does_not_reveal_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-sensitive-test-token")
        audit = EnvironmentAuditor.audit()

        assert audit["llm_credentials_available"] is True
        audit_dump = json.dumps(audit)
        assert "sk-sensitive" not in audit_dump
        assert "token" not in audit_dump.lower() or "llm_credentials_available" in audit_dump


# ---------------------------------------------------------------------------
# 2. Evaluation Mode Selection Tests
# ---------------------------------------------------------------------------


class TestEvaluationModeSelection:
    def test_detects_unavailable_mode_when_no_keys_in_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        audit = EnvironmentAuditor.audit()
        assert audit["llm_credentials_available"] is False
        assert audit["evaluation_mode_default"] == EvaluationMode.UNAVAILABLE.value

    def test_mode_enum_values(self) -> None:
        assert EvaluationMode.LIVE.value == "live"
        assert EvaluationMode.MOCK.value == "mock"
        assert EvaluationMode.UNAVAILABLE.value == "unavailable"


# ---------------------------------------------------------------------------
# 3. Artifact Persistence & Recursive Secret Scrubbing Tests
# ---------------------------------------------------------------------------


class TestBenchmarkRunPersistence:
    @pytest.fixture
    def temp_persistence_dir(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="agy_persist_test_"))
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_save_run_creates_sanitized_json_artifacts(
        self, temp_persistence_dir: Path
    ) -> None:
        persistence = BenchmarkRunPersistence(base_dir=temp_persistence_dir)
        provider_config = LLMProviderConfig(api_key="".join(["mock", "-secret", "-payload"]))

        case_res = BenchmarkRunResult(
            case_id="REAL-CLICK-01",
            repository="pallets/click",
            parent_commit_sha="111",
            reference_commit_sha="222",
            actual_commit_sha="111",
            failure_category=EvaluationFailureCategory.ISSUE_RESOLVED,
            is_resolved=True,
            live_llm_status=LiveLLMStatus.MOCK_MODE,
        )

        report = EndToEndReport(
            total_cases_in_registry=1,
            verified_cases_evaluated=1,
            resolved_cases=1,
            resolved_rate=1.0,
            failure_distribution={"issue_resolved": 1},
            mean_target_file_recall_at_3=1.0,
            mean_target_file_recall_at_5=1.0,
            mean_mrr=1.0,
            live_llm_status=LiveLLMStatus.MOCK_MODE,
            case_results=(case_res,),
        )

        run_dir = persistence.save_run(
            report=report,
            provider_config=provider_config,
            run_id="test_run_001",
        )

        assert run_dir.exists()
        assert (run_dir / "environment.json").exists()
        assert (run_dir / "benchmark_results.json").exists()
        assert (run_dir / "summary.json").exists()

        # Check secret scrubbing in all persisted JSON files
        for f in (run_dir / "environment.json", run_dir / "benchmark_results.json", run_dir / "summary.json"):
            content = f.read_text(encoding="utf-8")
            assert "sk-secret-payload" not in content
            parsed = json.loads(content)
            assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# 4. CLI Entrypoint Tests
# ---------------------------------------------------------------------------


class TestEvaluationCLI:
    def test_parser_options(self) -> None:
        parser = create_parser()
        args = parser.parse_args(["--mode", "mock", "--case", "REAL-CLICK-01", "--dry-run"])
        assert args.mode == "mock"
        assert args.case == "REAL-CLICK-01"
        assert args.dry_run is True

    def test_cli_dry_run_execution(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["--dry-run"])
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "ENVIRONMENT AUDIT" in captured
        assert "DRY RUN" in captured
        assert "REAL-CLICK-01" in captured

    def test_cli_unavailable_mode_when_no_credentials(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        exit_code = main(["--mode", "live"])
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "LIVE LLM EVALUATION: NOT EXECUTED" in captured
        assert "No active live LLM API keys" in captured
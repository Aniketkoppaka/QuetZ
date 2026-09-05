"""
tests/unit/test_ground_truth_environment.py

Comprehensive tests for Milestone 10: Environment feasibility auditor,
commit SHA integrity checks, synthetic SHA detection, and artifact persistence.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
import pytest

from autonomous_engineer.evaluation import (
    BENCHMARK_REGISTRY,
    BenchmarkEnvironmentAuditor,
    BenchmarkEnvironmentStatus,
    BenchmarkIssueStatus,
    GroundTruthArtifactPersistence,
    GroundTruthBenchmarkRunner,
    GroundTruthValidationReport,
    GroundTruthValidationResult,
    GroundTruthValidationStatus,
    RealBenchmarkIssue,
)


# ---------------------------------------------------------------------------
# 1. Environment Feasibility Auditor Tests
# ---------------------------------------------------------------------------


class TestEnvironmentFeasibility:
    def test_auditor_returns_valid_status_structure(self) -> None:
        status = BenchmarkEnvironmentAuditor.audit()
        assert isinstance(status, BenchmarkEnvironmentStatus)
        assert len(status.python_version) > 0
        assert len(status.platform) > 0
        assert isinstance(status.docker_available, bool)
        assert isinstance(status.docker_daemon_running, bool)
        assert isinstance(status.wsl_available, bool)

    def test_deterministic_dict_serialization(self) -> None:
        status = BenchmarkEnvironmentAuditor.audit()
        d = status.deterministic_dict()
        assert "python_version" in d
        assert "docker_available" in d
        assert "docker_daemon_running" in d


# ---------------------------------------------------------------------------
# 2. SHA Integrity & Synthetic Detection Tests
# ---------------------------------------------------------------------------


class TestCommitShaIntegrity:
    def test_detects_synthetic_sha_patterns(self) -> None:
        runner = GroundTruthBenchmarkRunner()
        assert runner.verify_remote_commit_sha("https://github.com/pallets/click", "5e123456789abcdef0123456789abcdef01234567") is False
        assert runner.verify_remote_commit_sha("https://github.com/psf/requests", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef") is False

    def test_classifies_synthetic_sha_as_metadata_inconsistency(self) -> None:
        issue = RealBenchmarkIssue(
            case_id="TEST-SYNTH-01",
            repository_name="pallets/click",
            repository_url="https://github.com/pallets/click",
            parent_commit_sha="5e123456789abcdef0123456789abcdef01234567",
            reference_commit_sha="6f23456789abcdef0123456789abcdef01234568",
            issue_title="Synthetic bug",
            issue_body="Synthetic body",
            expected_affected_files=("src/click/core.py",),
            category="synthetic",
        )
        runner = GroundTruthBenchmarkRunner()
        res = runner.validate_case_integrity(issue)

        assert res.validation_status == GroundTruthValidationStatus.METADATA_INCONSISTENCY
        assert "synthetic" in res.notes.lower()
        assert res.expected_bug_reproduced is False

    def test_validate_all_evaluates_registry_cases(self) -> None:
        runner = GroundTruthBenchmarkRunner()
        report: GroundTruthValidationReport = runner.validate_all(issues=BENCHMARK_REGISTRY)

        assert report.total_cases == 6
        assert len(report.case_results) == 6


# ---------------------------------------------------------------------------
# 3. Ground-Truth Persistence Tests
# ---------------------------------------------------------------------------


class TestGroundTruthPersistence:
    @pytest.fixture
    def temp_persistence_dir(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="agy_gt_persist_"))
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_save_ground_truth_artifacts(self, temp_persistence_dir: Path) -> None:
        persistence = GroundTruthArtifactPersistence(base_dir=temp_persistence_dir)
        env_status = BenchmarkEnvironmentAuditor.audit()

        case_res = GroundTruthValidationResult(
            case_id="REAL-CLICK-01",
            repository_url="https://github.com/pallets/click",
            parent_commit_sha="a2e482348b6f3c1a8d052d9b23b123456789abcd",
            reference_commit_sha="f8c123456789abcdef0123456789abcdef012345",
            reproduction_test_command="pytest tests/test_options.py",
            validation_status=GroundTruthValidationStatus.METADATA_INCONSISTENCY,
            notes="Synthetic SHA detected",
        )

        report = GroundTruthValidationReport(
            total_cases=1,
            validated_cases=0,
            validation_rate=0.0,
            status_distribution={"metadata_inconsistency": 1},
            case_results=(case_res,),
        )

        run_dir = persistence.save_ground_truth_run(
            report=report,
            env_status=env_status,
            run_id="gt_test_run_001",
        )

        assert run_dir.exists()
        assert (run_dir / "environment.json").exists()
        assert (run_dir / "ground_truth_results.json").exists()
        assert (run_dir / "summary.json").exists()

        for fname in ("environment.json", "ground_truth_results.json", "summary.json"):
            parsed = json.loads((run_dir / fname).read_text(encoding="utf-8"))
            assert isinstance(parsed, dict)
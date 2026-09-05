"""
evaluation/environment.py -- Reproducible benchmark environment manager and ground-truth audit runner.

Provides:
1. BenchmarkEnvironmentAuditor: Audits host Python, Git, Docker daemon, WSL, and upstream SHA reachability.
2. GroundTruthBenchmarkRunner: Validates historical benchmark cases with remote SHA and environment checks.
3. GroundTruthArtifactPersistence: Writes machine-readable validation artifacts (environment.json, ground_truth_results.json, summary.json).
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.evaluation.dataset import (
    BenchmarkIssueStatus,
    RealBenchmarkIssue,
)
from autonomous_engineer.evaluation.ground_truth import (
    GroundTruthValidationReport,
    GroundTruthValidationResult,
    GroundTruthValidationStatus,
    GroundTruthValidator,
)


class BenchmarkEnvironmentStatus(BaseModel):
    """Immutable environment feasibility assessment."""

    model_config = ConfigDict(frozen=True)

    python_version: str
    platform: str
    os_name: str
    git_version: str
    pytest_version: str
    docker_available: bool
    docker_daemon_running: bool
    wsl_available: bool
    network_git_remote_working: bool
    notes: str = ""

    def deterministic_dict(self) -> dict[str, Any]:
        return self.model_dump()


class BenchmarkEnvironmentAuditor:
    """Inspects host execution environment and container runtime availability."""

    @classmethod
    def audit(cls) -> BenchmarkEnvironmentStatus:
        git_v = "unavailable"
        if shutil.which("git"):
            try:
                proc = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
                git_v = proc.stdout.strip()
            except Exception:
                git_v = "error"

        pytest_v = "unavailable"
        try:
            import pytest
            pytest_v = getattr(pytest, "__version__", "unknown")
        except ImportError:
            pass

        # Check Docker CLI & Daemon
        docker_cli = bool(shutil.which("docker"))
        docker_daemon = False
        if docker_cli:
            try:
                proc = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
                docker_daemon = (proc.returncode == 0)
            except Exception:
                docker_daemon = False

        # Check WSL
        wsl_avail = False
        if shutil.which("wsl"):
            try:
                proc = subprocess.run(["wsl", "--status"], capture_output=True, text=True, timeout=5)
                wsl_avail = (proc.returncode == 0)
            except Exception:
                wsl_avail = False

        # Check Git Remote Network
        git_network = False
        if shutil.which("git"):
            try:
                proc = subprocess.run(
                    ["git", "ls-remote", "https://github.com/pallets/click.git", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                git_network = (proc.returncode == 0)
            except Exception:
                git_network = False

        notes = []
        if not docker_daemon:
            notes.append("Docker daemon is not running.")
        if not wsl_avail:
            notes.append("WSL is not installed/enabled.")
        if not git_network:
            notes.append("Git remote network query failed.")

        return BenchmarkEnvironmentStatus(
            python_version=sys.version.split()[0],
            platform=platform.platform(),
            os_name=os.name,
            git_version=git_v,
            pytest_version=pytest_v,
            docker_available=docker_cli,
            docker_daemon_running=docker_daemon,
            wsl_available=wsl_avail,
            network_git_remote_working=git_network,
            notes="; ".join(notes) if notes else "All runtime capabilities available.",
        )


class GroundTruthBenchmarkRunner:
    """
    Executes ground-truth validation across benchmark issues, verifying commit SHA existence.
    """

    def __init__(self, validator: GroundTruthValidator | None = None) -> None:
        self._validator = validator or GroundTruthValidator()

    @staticmethod
    def verify_remote_commit_sha(repo_url: str, commit_sha: str) -> bool:
        """
        Check whether a commit SHA or ref exists in the remote Git repository.
        Synthetic placeholder SHAs (e.g. 5e123456789abcdef...) return False.
        """
        if not shutil.which("git") or not commit_sha:
            return False
        # Synthetic check: repeated sequence or standard mock patterns
        if "123456789abcdef" in commit_sha.lower() or "deadbeef" in commit_sha.lower():
            return False
        try:
            proc = subprocess.run(
                ["git", "ls-remote", repo_url, commit_sha],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # If commit SHA is directly referenced or matched
            return (proc.returncode == 0 and commit_sha in proc.stdout)
        except Exception:
            return False

    def validate_case_integrity(
        self,
        issue: RealBenchmarkIssue,
        workspace_path: Path | None = None,
    ) -> GroundTruthValidationResult:
        """
        Verify case metadata integrity, checking whether parent/reference SHAs are synthetic or real.
        """
        # 1. Check for synthetic / non-existent SHA patterns
        parent_sha = issue.parent_commit_sha
        ref_sha = issue.reference_commit_sha

        is_synthetic_parent = ("123456789abcdef" in parent_sha.lower() or "deadbeef" in parent_sha.lower() or parent_sha.startswith("11111111"))
        is_synthetic_ref = ("123456789abcdef" in ref_sha.lower() or "feedface" in ref_sha.lower() or ref_sha.startswith("22222222"))

        if is_synthetic_parent or is_synthetic_ref:
            return GroundTruthValidationResult(
                case_id=issue.case_id,
                repository_url=issue.repository_url,
                parent_commit_sha=parent_sha,
                reference_commit_sha=ref_sha,
                reproduction_test_command=issue.expected_test_command,
                validation_status=GroundTruthValidationStatus.METADATA_INCONSISTENCY,
                expected_affected_files=issue.expected_affected_files,
                notes=(
                    f"Dataset Integrity Defect: Case {issue.case_id} contains synthetic placeholder "
                    f"commit SHAs (parent={parent_sha[:12]}, ref={ref_sha[:12]}) that do not exist in upstream Git history."
                ),
            )

        # 2. If valid SHAs, delegate to standard GroundTruthValidator
        return self._validator.validate_case(issue=issue, workspace_path=workspace_path)

    def validate_all(
        self,
        issues: tuple[RealBenchmarkIssue, ...] | None = None,
        workspace_map: dict[str, Path] | None = None,
    ) -> GroundTruthValidationReport:
        """
        Run ground-truth validation across all verified issues in registry.
        """
        if issues is None:
            from autonomous_engineer.evaluation.dataset import BENCHMARK_REGISTRY
            issues = BENCHMARK_REGISTRY

        verified_issues = [
            i for i in issues 
            if i.status in (BenchmarkIssueStatus.VERIFIED, BenchmarkIssueStatus.GROUND_TRUTH_VERIFIED)
        ]
        results: list[GroundTruthValidationResult] = []
        ws_map = workspace_map or {}

        for issue in verified_issues:
            res = self.validate_case_integrity(issue, ws_map.get(issue.case_id))
            results.append(res)

        total = len(verified_issues)
        validated_count = sum(1 for r in results if r.validation_status == GroundTruthValidationStatus.VALIDATED)
        val_rate = round(validated_count / total, 4) if total > 0 else 0.0

        dist: dict[str, int] = {}
        for r in results:
            k = r.validation_status.value
            dist[k] = dist.get(k, 0) + 1

        return GroundTruthValidationReport(
            total_cases=total,
            validated_cases=validated_count,
            validation_rate=val_rate,
            status_distribution=dist,
            case_results=tuple(results),
        )


class GroundTruthArtifactPersistence:
    """Writes machine-readable ground-truth evaluation artifacts to disk."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or (Path(__file__).parent.parent.parent.parent / "evaluation" / "runs")

    def save_ground_truth_run(
        self,
        report: GroundTruthValidationReport,
        env_status: BenchmarkEnvironmentStatus,
        run_id: str | None = None,
    ) -> Path:
        active_id = run_id or f"gt_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        run_dir = self.base_dir / active_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # 1. environment.json
        env_data = {
            "run_id": active_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": env_status.deterministic_dict(),
        }
        (run_dir / "environment.json").write_text(json.dumps(env_data, indent=2), encoding="utf-8")

        # 2. ground_truth_results.json
        results_data = {
            "run_id": active_id,
            "cases": [c.deterministic_dict() for c in report.case_results],
        }
        (run_dir / "ground_truth_results.json").write_text(json.dumps(results_data, indent=2), encoding="utf-8")

        # 3. summary.json
        summary_data = {
            "run_id": active_id,
            "summary": report.deterministic_dict(),
        }
        (run_dir / "summary.json").write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

        return run_dir
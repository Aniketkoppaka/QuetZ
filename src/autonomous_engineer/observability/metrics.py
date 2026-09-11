"""
observability/metrics.py -- KPI Metrics & Telemetry Collection for QuetZ.

Tracks and computes key performance and trust metrics:
- Resolution Rate & Formal Abstention Rate (epistemic humility)
- Average Mutation Score & Mutants Killed
- Verification Confidence Score Distribution
- SAST Security Clean Pass Rate
- 4-Tier Anchor Usage Distribution
- Average Duration (Time-to-Fix)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class RunMetricRecord(BaseModel):
    """Execution telemetry record for a single workflow run."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    issue_id: str
    status: str  # "COMPLETED", "ABSTAINED", "FAILED"
    duration_seconds: float
    confidence_score: float = 0.0
    mutation_score: float | None = None
    blast_radius_score: float | None = None
    sast_passed: bool = True
    policy_passed: bool = True
    anchor_tiers_used: tuple[int, ...] = ()
    timestamp: datetime = Field(default_factory=_utcnow)


class MetricsSummary(BaseModel):
    """Aggregated KPI metrics across multiple runs."""

    model_config = ConfigDict(frozen=True)

    total_runs: int = 0
    completed_runs: int = 0
    abstained_runs: int = 0
    failed_runs: int = 0
    resolution_rate_pct: float = 0.0
    abstention_rate_pct: float = 0.0
    average_confidence_score: float = 0.0
    average_mutation_score: float = 0.0
    average_duration_seconds: float = 0.0
    sast_clean_pass_rate_pct: float = 100.0
    policy_clean_pass_rate_pct: float = 100.0
    anchor_tier_counts: dict[str, int] = Field(default_factory=dict)


class MetricsCollector:
    """Collects and summarizes execution metrics in-memory or persisted via JSONL."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path
        self._records: list[RunMetricRecord] = []
        if self.storage_path and self.storage_path.exists():
            self._load_records()

    def _load_records(self) -> None:
        try:
            for line in self.storage_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    data = json.loads(line)
                    self._records.append(RunMetricRecord(**data))
        except Exception:
            pass

    def record(self, record: RunMetricRecord) -> None:
        self._records.append(record)
        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with self.storage_path.open("a", encoding="utf-8") as f:
                f.write(record.model_dump_json() + "\n")

    @property
    def records(self) -> tuple[RunMetricRecord, ...]:
        return tuple(self._records)

    def summarize(self) -> MetricsSummary:
        total = len(self._records)
        if total == 0:
            return MetricsSummary()

        completed = sum(1 for r in self._records if r.status == "COMPLETED")
        abstained = sum(1 for r in self._records if r.status == "ABSTAINED")
        failed = sum(1 for r in self._records if r.status == "FAILED")

        res_rate = (completed / total) * 100.0
        abs_rate = (abstained / total) * 100.0

        avg_conf = sum(r.confidence_score for r in self._records) / total
        avg_dur = sum(r.duration_seconds for r in self._records) / total

        mut_scores = [r.mutation_score for r in self._records if r.mutation_score is not None]
        avg_mut = (sum(mut_scores) / len(mut_scores)) if mut_scores else 0.0

        sast_passes = sum(1 for r in self._records if r.sast_passed)
        sast_rate = (sast_passes / total) * 100.0

        policy_passes = sum(1 for r in self._records if r.policy_passed)
        policy_rate = (policy_passes / total) * 100.0

        tier_counts = {"tier_1": 0, "tier_2": 0, "tier_3": 0, "tier_4": 0}
        for r in self._records:
            for tier in r.anchor_tiers_used:
                key = f"tier_{tier}"
                if key in tier_counts:
                    tier_counts[key] += 1

        return MetricsSummary(
            total_runs=total,
            completed_runs=completed,
            abstained_runs=abstained,
            failed_runs=failed,
            resolution_rate_pct=round(res_rate, 2),
            abstention_rate_pct=round(abs_rate, 2),
            average_confidence_score=round(avg_conf, 3),
            average_mutation_score=round(avg_mut, 3),
            average_duration_seconds=round(avg_dur, 2),
            sast_clean_pass_rate_pct=round(sast_rate, 2),
            policy_clean_pass_rate_pct=round(policy_rate, 2),
            anchor_tier_counts=tier_counts,
        )
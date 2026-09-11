"""
Unit tests for KPI metrics engine in observability/metrics.py.
"""
from autonomous_engineer.observability.metrics import (
    MetricsCollector,
    RunMetricRecord,
)


def test_empty_metrics_collector():
    collector = MetricsCollector()
    summary = collector.summarize()
    assert summary.total_runs == 0
    assert summary.resolution_rate_pct == 0.0


def test_metrics_collector_summarizes_outcomes():
    collector = MetricsCollector()

    # 1. Successful run
    collector.record(
        RunMetricRecord(
            run_id="run-1",
            issue_id="ISSUE-1",
            status="COMPLETED",
            duration_seconds=20.0,
            confidence_score=0.95,
            mutation_score=0.90,
            sast_passed=True,
            policy_passed=True,
            anchor_tiers_used=(1, 2),
        )
    )

    # 2. Abstained run (epistemic humility)
    collector.record(
        RunMetricRecord(
            run_id="run-2",
            issue_id="ISSUE-2",
            status="ABSTAINED",
            duration_seconds=10.0,
            confidence_score=0.50,
            mutation_score=None,
            sast_passed=True,
            policy_passed=True,
            anchor_tiers_used=(3,),
        )
    )

    # 3. Failed run
    collector.record(
        RunMetricRecord(
            run_id="run-3",
            issue_id="ISSUE-3",
            status="FAILED",
            duration_seconds=30.0,
            confidence_score=0.30,
            mutation_score=0.40,
            sast_passed=False,
            policy_passed=True,
            anchor_tiers_used=(4,),
        )
    )

    summary = collector.summarize()
    assert summary.total_runs == 3
    assert summary.completed_runs == 1
    assert summary.abstained_runs == 1
    assert summary.failed_runs == 1
    assert summary.resolution_rate_pct == 33.33
    assert summary.abstention_rate_pct == 33.33
    assert summary.average_confidence_score == 0.583
    assert summary.average_mutation_score == 0.65  # (0.90 + 0.40) / 2
    assert summary.average_duration_seconds == 20.0
    assert summary.sast_clean_pass_rate_pct == 66.67
    assert summary.anchor_tier_counts["tier_1"] == 1
    assert summary.anchor_tier_counts["tier_2"] == 1
    assert summary.anchor_tier_counts["tier_3"] == 1
    assert summary.anchor_tier_counts["tier_4"] == 1


def test_metrics_collector_jsonl_persistence(tmp_path):
    log_file = tmp_path / "metrics.jsonl"
    c1 = MetricsCollector(storage_path=log_file)
    c1.record(
        RunMetricRecord(
            run_id="run-persisted",
            issue_id="ISSUE-P",
            status="COMPLETED",
            duration_seconds=15.0,
            confidence_score=0.99,
        )
    )
    assert log_file.exists()

    # Reload in a new collector instance
    c2 = MetricsCollector(storage_path=log_file)
    assert len(c2.records) == 1
    assert c2.records[0].run_id == "run-persisted"
    summary = c2.summarize()
    assert summary.total_runs == 1
    assert summary.resolution_rate_pct == 100.0
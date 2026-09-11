"""
Unit tests for new CLI commands in cli.py:
- scan-security
- scan-licenses
- metrics
- feedback
"""
from autonomous_engineer.cli import main
from autonomous_engineer.observability.metrics import MetricsCollector, RunMetricRecord


def test_cli_scan_security_clean(tmp_path, capsys):
    f = tmp_path / "clean.py"
    f.write_text("def ok(): return 42\n", encoding="utf-8")
    exit_code = main(["scan-security", str(f)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "SAST Security Audit: PASS" in captured.out


def test_cli_scan_security_vulnerable(tmp_path, capsys):
    f = tmp_path / "vuln.py"
    f.write_text("import subprocess\nsubprocess.Popen('ls', shell=True)\n", encoding="utf-8")
    exit_code = main(["scan-security", str(f)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "SAST Security Audit: FAILED" in captured.out


def test_cli_scan_licenses_clean(tmp_path, capsys):
    f = tmp_path / "requirements.txt"
    f.write_text("click>=8.0\nrequests>=2.31.0\n", encoding="utf-8")
    exit_code = main(["scan-licenses", str(f)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Supply-Chain & License Compliance: PASS" in captured.out


def test_cli_scan_licenses_copyleft(tmp_path, capsys):
    f = tmp_path / "requirements.txt"
    f.write_text("gpl-module==1.0\n", encoding="utf-8")
    exit_code = main(["scan-licenses", str(f)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Supply-Chain & License Compliance: REJECTED" in captured.out


def test_cli_metrics_display(tmp_path, capsys):
    log_file = tmp_path / "metrics.jsonl"
    c = MetricsCollector(storage_path=log_file)
    c.record(
        RunMetricRecord(
            run_id="run-cli",
            issue_id="ISSUE-C",
            status="COMPLETED",
            duration_seconds=12.4,
            confidence_score=0.96,
            mutation_score=0.90,
            anchor_tiers_used=(1,),
        )
    )

    exit_code = main(["metrics", "--file", str(log_file)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Total Workflow Runs:        1" in captured.out
    assert "Resolution Rate:            100.0%" in captured.out


def test_cli_feedback_adaptation(tmp_path, capsys):
    fb_file = tmp_path / "fb.jsonl"
    exit_code = main([
        "feedback",
        "--pr-id", "PR-101",
        "--issue-id", "ISSUE-101",
        "--outcome", "REJECTED_OR_ABANDONED",
        "--confidence", "0.85",
        "--files", "src/auth.py",
        "--file", str(fb_file),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Recorded Review Outcome: [REJECTED_OR_ABANDONED]" in captured.out
    assert "w_verification:" in captured.out


def test_cli_export_audit_json(tmp_path):
    out_file = tmp_path / "audit_report.json"
    exit_code = main(["export-audit", "--path", str(tmp_path), "--output", str(out_file)])
    assert exit_code == 0
    assert out_file.exists()
    import json
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert "report_id" in data
    assert "compliance_status" in data
    assert data["compliance_status"] == "COMPLIANT"
    assert "security_sast" in data
    assert "supply_chain_licenses" in data
    assert "bayesian_calibrated_weights" in data


def test_cli_export_audit_markdown(tmp_path):
    out_file = tmp_path / "audit_report.md"
    exit_code = main(["export-audit", "--path", str(tmp_path), "--output", str(out_file)])
    assert exit_code == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "Enterprise Compliance & Security Audit Report" in content
    assert "Static Application Security Testing" in content
    assert "Supply-Chain License Compliance" in content
"""
Unit tests for LicenseScanner in verification/license_scan.py.
"""
from autonomous_engineer.verification.license_scan import (
    LicenseCategory,
    LicenseScanner,
)


def test_permissive_dependencies_pass():
    scanner = LicenseScanner()
    reqs = """
click>=8.0.0
requests==2.31.0
pydantic>=2.0
"""
    findings = scanner.scan_requirements_txt(reqs)
    assert len(findings) == 0


def test_detects_copyleft_gpl_in_requirements():
    scanner = LicenseScanner()
    reqs = """
requests==2.31.0
pygpl==1.0.0
readline>=8.0
"""
    findings = scanner.scan_requirements_txt(reqs)
    assert len(findings) == 2
    assert all(f.category == LicenseCategory.COPYLEFT for f in findings)
    assert any("pygpl" in f.package_name for f in findings)
    assert any("readline" in f.package_name for f in findings)


def test_scan_pyproject_toml():
    scanner = LicenseScanner()
    pyproject_text = """
[project]
name = "my-app"
dependencies = [
    "click>=8.0",
    "agpl-service>=1.2.0"
]
"""
    findings = scanner.scan_pyproject_toml(pyproject_text)
    assert len(findings) == 1
    assert findings[0].package_name == "agpl-service"
    assert findings[0].detected_license == "AGPL-3.0"
    assert findings[0].blocking is True


def test_scan_workspace_generates_report(tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("fastapi>=0.100.0\npytest>=7.0.0\n", encoding="utf-8")

    scanner = LicenseScanner()
    report = scanner.scan_workspace(tmp_path)
    assert report.passed is True
    assert len(report.findings) == 0
    assert "fastapi" in report.packages_checked
    assert "pytest" in report.packages_checked
    assert "Supply-Chain & License Compliance: PASS" in report.to_markdown()


def test_scan_workspace_fails_closed_on_copyleft(tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("gpl-module==1.0\n", encoding="utf-8")

    scanner = LicenseScanner()
    report = scanner.scan_workspace(tmp_path)
    assert report.passed is False
    assert len(report.findings) == 1
    assert "Supply-Chain & License Compliance: REJECTED" in report.to_markdown()
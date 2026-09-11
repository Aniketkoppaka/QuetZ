"""
Unit tests for SAST security scanner in verification/security_scan.py.
"""
from autonomous_engineer.verification.security_scan import (
    ASTSecurityScanner,
    SecuritySeverity,
)


def test_clean_code_passes_sast_scan():
    code = """
def add(a: int, b: int) -> int:
    return a + b
"""
    scanner = ASTSecurityScanner()
    findings = scanner.scan_source(code)
    assert len(findings) == 0


def test_detects_dangerous_eval_and_exec():
    code = """
def run_dynamic(user_input):
    eval(user_input)
    exec("print('hello')")
"""
    scanner = ASTSecurityScanner()
    findings = scanner.scan_source(code)
    assert len(findings) == 2
    assert all(f.severity == SecuritySeverity.CRITICAL for f in findings)
    assert any("eval" in f.message for f in findings)
    assert any("exec" in f.message for f in findings)


def test_detects_subprocess_shell_true():
    code = """
import subprocess

def run_cmd(cmd):
    subprocess.Popen(cmd, shell=True)
"""
    scanner = ASTSecurityScanner()
    findings = scanner.scan_source(code)
    assert len(findings) == 1
    assert findings[0].severity == SecuritySeverity.CRITICAL
    assert "shell=True" in findings[0].message


def test_detects_insecure_pickle_and_yaml():
    code = """
import pickle
import yaml

def load_data(raw):
    d1 = pickle.loads(raw)
    d2 = yaml.unsafe_load(raw)
    d3 = yaml.load(raw)
    return d1, d2, d3
"""
    scanner = ASTSecurityScanner()
    findings = scanner.scan_source(code)
    assert len(findings) == 3
    assert all(f.severity == SecuritySeverity.HIGH for f in findings)


def test_detects_hardcoded_secrets():
    code = """
API_KEY = "sk-live-1234567890abcdef123456"
"""
    scanner = ASTSecurityScanner()
    findings = scanner.scan_source(code)
    assert len(findings) == 1
    assert findings[0].severity == SecuritySeverity.CRITICAL
    assert "hardcoded" in findings[0].message.lower()


def test_detects_ssl_verify_disabled():
    code = """
import requests

def fetch(url):
    return requests.get(url, verify=False)
"""
    scanner = ASTSecurityScanner()
    findings = scanner.scan_source(code)
    assert len(findings) == 1
    assert findings[0].severity == SecuritySeverity.HIGH
    assert "verify=False" in findings[0].message


def test_scan_files_report(tmp_path):
    f_clean = tmp_path / "clean.py"
    f_clean.write_text("def ok(): return 1\n", encoding="utf-8")

    f_vuln = tmp_path / "vuln.py"
    f_vuln.write_text("import subprocess\nsubprocess.run('ls', shell=True)\n", encoding="utf-8")

    scanner = ASTSecurityScanner()
    report = scanner.scan_files([f_clean, f_vuln])
    assert not report.passed
    assert report.critical_count == 1
    assert "SAST Security Audit: FAILED" in report.to_markdown()
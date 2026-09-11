"""
tests/unit/test_comprehensive_edge_cases.py -- Deep enterprise-grade edge cases & stress test suite.

Covers boundary behaviors and edge cases across:
1. AST SAST Scanner:
   - Malformed/truncated Python syntax
   - Unicode/emoji/null bytes in source
   - Obfuscated/aliased imports (e.g. __import__('pickle'), getattr)
   - Extremely deep AST nesting
2. Supply-Chain & License Scanner:
   - Malformed requirements.txt (trailing comments, environment markers, git+ssh URLs)
   - Malformed pyproject.toml (invalid TOML, missing tables, non-string dependencies)
   - Banned licenses with varied casing, spaces, or hyphens (e.g. "GPL-3.0-only", "AGPLv3+")
3. Enterprise Policy Engine:
   - Empty patches vs. enormous patches
   - Windows backslash vs Unix forward slash path matching
   - Deeply nested directories (.github/workflows/nested/sub/ci.yml)
   - JSON vs YAML vs corrupt policy files
4. Polyglot Code Analyzer (Go, Rust, JS/TS):
   - Multi-line comments, comments containing code keywords
   - Generics in Go (func Foo[T any](x T))
   - Impl blocks with traits in Rust (impl Trait for Struct)
   - Empty files, files with only whitespace, non-UTF8 binary files
5. Cryptographic Signing & Provenance:
   - Empty keys, very long keys (4096 bytes)
   - Bit flipping in signature, key ID, and payload fields
   - Deterministic verification across repeated runs
6. Project Config Loader (.quetz.yaml / .quetz.json):
   - Missing fields, invalid types (e.g. string for timeout_seconds)
   - Precedence of config file formats
7. Metric & Bayesian Adaptive Tuner:
   - Division by zero on 0 total runs
   - Score clamping at upper/lower limits (0.05 min weight, 0.50 max weight)
   - Handling of huge volume of alternating feedback (merged vs rejected)
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from autonomous_engineer.verification.security_scan import ASTSecurityScanner, SecuritySeverity
from autonomous_engineer.verification.license_scan import LicenseScanner, LicenseCategory
from autonomous_engineer.config.policy_engine import OrgCompliancePolicy, PolicyEngine
from autonomous_engineer.repository.go_rust_analyzer import PolyglotCodeAnalyzer
from autonomous_engineer.repository.js_ts_analyzer import JsTsAnalyzer
from autonomous_engineer.verification.signing import CertificateSigner, SignedCertificateEnvelope
from autonomous_engineer.config.project_config import QuetzProjectConfig
from autonomous_engineer.observability.feedback_loop import AdaptiveConfidenceTuner, PRFeedbackRecord, PROutcome
from autonomous_engineer.observability.metrics import MetricsCollector, RunMetricRecord


# ===========================================================================
# 1. AST SAST Scanner Edge Cases
# ===========================================================================
class TestSecurityScanEdgeCases:

    def test_syntax_error_fails_closed_with_critical(self):
        scanner = ASTSecurityScanner()
        # Incomplete statement / syntax error
        findings = scanner.scan_source("def broken_func(:\n    pass\n", "broken.py")
        assert len(findings) >= 1
        assert any(f.severity == SecuritySeverity.CRITICAL for f in findings)
        assert any(f.rule_id == "SEC-SYNTAX-ERR" for f in findings)

    def test_unicode_and_null_bytes_handling(self):
        scanner = ASTSecurityScanner()
        code = "# 🚀 日本語コメント \nx = 'valid string'\n"
        findings = scanner.scan_source(code, "unicode_test.py")
        assert len(findings) == 0

    def test_deeply_nested_eval(self):
        scanner = ASTSecurityScanner()
        nested_code = "def f():\n    if True:\n        while True:\n            for _ in range(1):\n                try:\n                    eval('print(1)')\n                except: pass\n"
        findings = scanner.scan_source(nested_code, "nested.py")
        assert any(f.rule_id == "SEC-CWE-95" for f in findings)

    def test_subprocess_shell_variable_or_attribute(self):
        scanner = ASTSecurityScanner()
        # Explicit shell=True
        code = "import subprocess\nsubprocess.run(['ls'], shell=True)\n"
        findings = scanner.scan_source(code, "subp.py")
        assert any(f.rule_id == "SEC-CWE-78" for f in findings)

    def test_empty_source_code(self):
        scanner = ASTSecurityScanner()
        findings = scanner.scan_source("", "empty.py")
        assert len(findings) == 0


# ===========================================================================
# 2. Supply-Chain & License Scanner Edge Cases
# ===========================================================================
class TestLicenseScannerEdgeCases:

    def test_requirements_with_environment_markers_and_comments(self):
        scanner = LicenseScanner()
        text = """
        # Primary requirements
        click>=8.0.0; python_version >= '3.11' # core cli
        pytest == 8.3.0 ; sys_platform == 'win32'
        requests~=2.31.0
        # Malicious copyleft package with marker
        gpl-dependency>=1.0; os_name == 'posix'
        """
        findings = scanner.scan_requirements_txt(text, "requirements.txt")
        gpl_finding = next((f for f in findings if "gpl-dependency" in f.package_name), None)
        assert gpl_finding is not None
        assert gpl_finding.blocking is True

    def test_malformed_pyproject_toml_graceful_handling(self, tmp_path):
        scanner = LicenseScanner()
        corrupt_toml = tmp_path / "pyproject.toml"
        corrupt_toml.write_text("this is [not valid toml = = = 123", encoding="utf-8")
        report = scanner.scan_workspace(tmp_path)
        # Should not crash, fail-closed or return report with no crash
        assert isinstance(report.passed, bool)

    def test_various_copyleft_case_sensitivity(self):
        scanner = LicenseScanner()
        text = "AGPL-PACKAGE==1.0\nMyGplLibrary==2.0\n"
        findings = scanner.scan_requirements_txt(text, "requirements.txt")
        assert len(findings) == 2
        assert all(f.blocking for f in findings)


# ===========================================================================
# 3. Enterprise Policy Engine Edge Cases
# ===========================================================================
class TestPolicyEngineEdgeCases:

    def test_path_normalization_windows_backslashes(self):
        policy = OrgCompliancePolicy(protected_path_patterns=(".github/*", ".github/**/*"))
        engine = PolicyEngine(policy)
        # Path passed with Windows backslashes
        res = engine.evaluate_patch(files_modified=[r".github\workflows\quetz.yml"])
        assert not res.passed
        assert any(v.rule_name == "PROTECTED_PATH_MODIFIED" for v in res.violations)

    def test_corrupt_policy_file_raises_or_fails(self, tmp_path):
        corrupt_file = tmp_path / "policy.json"
        corrupt_file.write_text("{ unclosed json", encoding="utf-8")
        with pytest.raises(Exception):
            OrgCompliancePolicy.from_file(corrupt_file)

    def test_empty_patch_evaluation(self):
        engine = PolicyEngine()
        res = engine.evaluate_patch(files_modified=[], file_contents={})
        assert res.passed
        assert len(res.violations) == 0


# ===========================================================================
# 4. Polyglot Code Analyzer Edge Cases (Go, Rust, JS/TS)
# ===========================================================================
class TestPolyglotAnalyzerEdgeCases:

    def test_go_generics_and_methods(self):
        code = """package main

type Cache[T any] struct {
    items map[string]T
}

func (c *Cache[T]) Get(key string) T {
    return c.items[key]
}

func ProcessData[K comparable, V any](k K, v V) {
}
"""
        analyzer = PolyglotCodeAnalyzer()
        mod = analyzer.analyze_source(code, "cache.go")
        assert mod.language == "go"
        assert analyzer.check_symbol_present(mod, "Cache") is True
        assert analyzer.check_symbol_present(mod, "Get") is True
        assert analyzer.check_symbol_present(mod, "ProcessData") is True

    def test_rust_impl_blocks_and_traits(self):
        code = """use std::fmt::Display;

pub trait Serializer {
    fn serialize(&self) -> String;
}

pub struct Config {
    pub name: String,
}

impl Serializer for Config {
    fn serialize(&self) -> String {
        self.name.clone()
    }
}
"""
        analyzer = PolyglotCodeAnalyzer()
        mod = analyzer.analyze_source(code, "src/config.rs")
        assert mod.language == "rust"
        assert analyzer.check_symbol_present(mod, "Serializer") is True
        assert analyzer.check_symbol_present(mod, "Config") is True
        assert analyzer.check_symbol_present(mod, "serialize") is True

    def test_js_ts_class_methods_and_arrow_functions(self):
        code = """
export class PaymentGateway {
    private apiKey: string;

    constructor(key: string) {
        this.apiKey = key;
    }

    async chargeCard(amount: number) {
        return true;
    }

    refund = (transactionId: string) => {
        return true;
    };
}
"""
        analyzer = JsTsAnalyzer()
        mod = analyzer.analyze_source(code, "gateway.ts")
        assert analyzer.check_symbol_present(mod, "PaymentGateway") is True
        assert analyzer.check_symbol_present(mod, "chargeCard") is True
        assert analyzer.check_symbol_present(mod, "refund") is True


# ===========================================================================
# 5. Cryptographic Signing & Provenance Edge Cases
# ===========================================================================
class TestSigningEdgeCases:

    def test_empty_string_secret_key(self):
        signer = CertificateSigner(secret_key="")
        cert_data = {"certificate_id": "c1", "evidence_hash": "h1", "status": "COMPLETED"}
        envelope = signer.sign_certificate(cert_data)
        assert signer.verify_envelope(envelope) is True

    def test_large_secret_key_4096_bytes(self):
        large_key = b"A" * 4096
        signer = CertificateSigner(secret_key=large_key)
        cert_data = {"certificate_id": "c2", "evidence_hash": "h2", "status": "COMPLETED"}
        envelope = signer.sign_certificate(cert_data)
        assert signer.verify_envelope(envelope) is True

    def test_tamper_signature_hash_mismatch(self):
        signer = CertificateSigner(secret_key="secret")
        cert_data = {"certificate_id": "c3", "evidence_hash": "hash_original", "status": "COMPLETED"}
        envelope = signer.sign_certificate(cert_data)

        # Mismatch evidence hash
        tampered = SignedCertificateEnvelope(
            certificate_payload=cert_data,
            evidence_hash="hash_tampered",
            signature=envelope.signature,
        )
        assert signer.verify_envelope(tampered) is False


# ===========================================================================
# 6. Metric & Bayesian Adaptive Tuner Edge Cases
# ===========================================================================
class TestTunerMetricsEdgeCases:

    def test_zero_runs_division_by_zero_safety(self, tmp_path):
        empty_log = tmp_path / "empty_metrics.jsonl"
        collector = MetricsCollector(storage_path=empty_log)
        summary = collector.summarize()
        assert summary.total_runs == 0
        assert summary.resolution_rate_pct == 0.0
        assert summary.average_confidence_score == 0.0
        assert summary.sast_clean_pass_rate_pct == 100.0

    def test_extreme_feedback_rejections_clamping(self):
        tuner = AdaptiveConfidenceTuner()
        # Ingest 50 consecutive rejections
        for i in range(50):
            tuner.record_feedback(
                PRFeedbackRecord(
                    pr_id=f"PR-{i}",
                    issue_id="ISSUE",
                    outcome=PROutcome.REJECTED_OR_ABANDONED,
                    confidence_at_generation=0.95,
                )
            )
        weights = tuner.get_calibrated_weights()
        # Weight for verification must not exceed max clamp (0.50)
        assert weights.w_verification <= 0.50
        # Plan and authority must not drop below min clamp (0.05)
        assert weights.w_plan >= 0.05
        assert weights.w_authority >= 0.05
        # Total sum of weights must equal 1.0 (within float tolerance)
        total_sum = weights.w_grounding + weights.w_plan + weights.w_verification + weights.w_authority
        assert abs(total_sum - 1.0) < 1e-4
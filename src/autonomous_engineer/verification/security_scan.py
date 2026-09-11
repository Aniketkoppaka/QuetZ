"""
verification/security_scan.py -- In-Pipeline SAST & Security Verification Gate for QuetZ.

Performs deterministic AST analysis on modified source files to catch OWASP/CWE vulnerabilities:
- CWE-94 / CWE-95: Unsafe eval() / exec()
- CWE-78: Shell injection via subprocess (e.g. shell=True)
- CWE-502: Insecure deserialization (pickle, marshal, unsafe yaml)
- CWE-798: Hardcoded credentials or private keys
- CWE-295: Disabled SSL/TLS verification (verify=False)

Fails closed if high or critical severity issues are introduced.
"""
from __future__ import annotations

import ast
import re
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SecuritySeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SecurityFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    cwe_id: str
    message: str
    file_path: str
    line_number: int
    severity: SecuritySeverity
    snippet: str = ""


class SecurityScanReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    findings: tuple[SecurityFinding, ...] = Field(default=())
    scanned_files: tuple[str, ...] = Field(default=())
    passed: bool = True

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SecuritySeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SecuritySeverity.HIGH)

    def to_markdown(self) -> str:
        if not self.findings:
            return (
                "### 🛡️ SAST Security Audit: PASS\n"
                f"- Scanned `{len(self.scanned_files)}` modified file(s).\n"
                "- No OWASP or high-severity vulnerabilities introduced.\n"
            )

        status_emoji = "❌" if not self.passed else "⚠️"
        lines = [
            f"### {status_emoji} SAST Security Audit: {'FAILED' if not self.passed else 'WARNING'}",
            f"- Scanned `{len(self.scanned_files)}` file(s), found `{len(self.findings)}` issue(s).",
            f"- **Critical**: {self.critical_count} | **High**: {self.high_count}",
            "",
            "| Rule | Severity | Location | Issue |",
            "| :--- | :---: | :--- | :--- |",
        ]
        for f in self.findings:
            lines.append(
                f"| `{f.rule_id}` ({f.cwe_id}) | `{f.severity.value}` | `{f.file_path}:{f.line_number}` | {f.message} |"
            )
        return "\n".join(lines)


_CREDENTIAL_PATTERNS = [
    (re.compile(r"""(?i)(?:api_key|apikey|secret_key|private_key|auth_token)\s*=\s*['"][A-Za-z0-9_\-]{16,}['"]"""), "Possible hardcoded API/Secret key"),
    (re.compile(r"""-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"""), "Hardcoded private key block"),
]


class _SecurityASTVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str, source_lines: list[str]) -> None:
        self.file_path = file_path
        self.source_lines = source_lines
        self.findings: list[SecurityFinding] = []

    def _get_snippet(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""

    def visit_Call(self, node: ast.Call) -> None:
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name in ("eval", "exec"):
            self.findings.append(
                SecurityFinding(
                    rule_id="SEC-CWE-95",
                    cwe_id="CWE-95",
                    message=f"Use of potentially dangerous dynamic execution `{func_name}()`",
                    file_path=self.file_path,
                    line_number=node.lineno,
                    severity=SecuritySeverity.CRITICAL,
                    snippet=self._get_snippet(node.lineno),
                )
            )

        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        self.findings.append(
                            SecurityFinding(
                                rule_id="SEC-CWE-78",
                                cwe_id="CWE-78",
                                message="subprocess call with `shell=True` allows potential command injection",
                                file_path=self.file_path,
                                line_number=node.lineno,
                                severity=SecuritySeverity.CRITICAL,
                                snippet=self._get_snippet(node.lineno),
                            )
                        )

            if isinstance(node.func.value, ast.Name) and node.func.value.id in ("pickle", "_pickle", "marshal"):
                if node.func.attr in ("load", "loads"):
                    self.findings.append(
                        SecurityFinding(
                            rule_id="SEC-CWE-502",
                            cwe_id="CWE-502",
                            message=f"Insecure deserialization using `{node.func.value.id}.{node.func.attr}()`",
                            file_path=self.file_path,
                            line_number=node.lineno,
                            severity=SecuritySeverity.HIGH,
                            snippet=self._get_snippet(node.lineno),
                        )
                    )

            if isinstance(node.func.value, ast.Name) and node.func.value.id == "yaml":
                if node.func.attr == "unsafe_load":
                    self.findings.append(
                        SecurityFinding(
                            rule_id="SEC-CWE-502-YAML",
                            cwe_id="CWE-502",
                            message="Use of unsafe YAML loader `yaml.unsafe_load()`",
                            file_path=self.file_path,
                            line_number=node.lineno,
                            severity=SecuritySeverity.HIGH,
                            snippet=self._get_snippet(node.lineno),
                        )
                    )
                elif node.func.attr == "load":
                    has_loader = any(kw.arg == "Loader" for kw in node.keywords)
                    if not has_loader:
                        self.findings.append(
                            SecurityFinding(
                                rule_id="SEC-CWE-502-YAML",
                                cwe_id="CWE-502",
                                message="`yaml.load()` called without specifying a safe Loader",
                                file_path=self.file_path,
                                line_number=node.lineno,
                                severity=SecuritySeverity.HIGH,
                                snippet=self._get_snippet(node.lineno),
                            )
                        )

        for kw in node.keywords:
            if kw.arg == "verify" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                self.findings.append(
                    SecurityFinding(
                        rule_id="SEC-CWE-295",
                        cwe_id="CWE-295",
                        message="SSL/TLS certificate verification explicitly disabled (`verify=False`)",
                        file_path=self.file_path,
                        line_number=node.lineno,
                        severity=SecuritySeverity.HIGH,
                        snippet=self._get_snippet(node.lineno),
                    )
                )

        self.generic_visit(node)


class ASTSecurityScanner:
    def scan_source(self, code: str, file_path: str = "<string>") -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        # Strip UTF-8 byte order mark if present
        if code.startswith("\ufeff"):
            code = code.lstrip("\ufeff")
        source_lines = code.splitlines()

        for line_idx, line in enumerate(source_lines, start=1):
            for pattern, msg in _CREDENTIAL_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        SecurityFinding(
                            rule_id="SEC-CWE-798",
                            cwe_id="CWE-798",
                            message=msg,
                            file_path=file_path,
                            line_number=line_idx,
                            severity=SecuritySeverity.CRITICAL,
                            snippet=line.strip(),
                        )
                    )

        try:
            tree = ast.parse(code, filename=file_path)
        except SyntaxError as e:
            findings.append(
                SecurityFinding(
                    rule_id="SEC-SYNTAX-ERR",
                    cwe_id="CWE-20",
                    message=f"Syntax error during AST security analysis: {e}",
                    file_path=file_path,
                    line_number=e.lineno or 1,
                    severity=SecuritySeverity.CRITICAL,
                )
            )
            return findings

        visitor = _SecurityASTVisitor(file_path, source_lines)
        visitor.visit(tree)
        findings.extend(visitor.findings)
        return findings

    def scan_files(self, file_paths: list[str | Path]) -> SecurityScanReport:
        all_findings: list[SecurityFinding] = []
        scanned: list[str] = []

        for p in file_paths:
            path = Path(p)
            if not path.exists() or not path.is_file() or path.suffix != ".py":
                continue
            scanned.append(str(path))
            try:
                content = path.read_text(encoding="utf-8-sig")
                findings = self.scan_source(content, file_path=str(path))
                all_findings.extend(findings)
            except Exception as exc:
                all_findings.append(
                    SecurityFinding(
                        rule_id="SEC-READ-ERR",
                        cwe_id="CWE-20",
                        message=f"Failed to read file for SAST scan: {exc}",
                        file_path=str(path),
                        line_number=1,
                        severity=SecuritySeverity.HIGH,
                    )
                )

        has_blocking_issues = any(
            f.severity in (SecuritySeverity.CRITICAL, SecuritySeverity.HIGH) for f in all_findings
        )

        return SecurityScanReport(
            findings=tuple(all_findings),
            scanned_files=tuple(scanned),
            passed=not has_blocking_issues,
        )
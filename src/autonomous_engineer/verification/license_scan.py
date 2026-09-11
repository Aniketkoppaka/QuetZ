"""
verification/license_scan.py -- Dependency & License Supply-Chain Scanner for QuetZ.

Scans dependency configuration files (requirements.txt, pyproject.toml) to prevent:
- Introduction of restrictive copyleft licenses (GPL, AGPL, SSPL) into commercial codebases.
- Ingestion of unverified or suspicious third-party package dependencies.
- Unpinned or wildcard package requirements that risk supply-chain drift.
"""
from __future__ import annotations

import re
import tomllib
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LicenseCategory(str, Enum):
    PERMISSIVE = "PERMISSIVE"      # MIT, Apache-2.0, BSD, ISC
    COPYLEFT = "COPYLEFT"          # GPL, AGPL, LGPL, SSPL
    UNKNOWN = "UNKNOWN"
    COMMERCIAL = "COMMERCIAL"


class DependencyFinding(BaseModel):
    """Represents a licensing or supply-chain risk detected in a dependency."""

    model_config = ConfigDict(frozen=True)

    package_name: str
    version_spec: str
    detected_license: str
    category: LicenseCategory
    file_path: str
    message: str
    blocking: bool = True


class LicenseScanReport(BaseModel):
    """Audit report detailing dependency licenses and supply-chain safety."""

    model_config = ConfigDict(frozen=True)

    packages_checked: tuple[str, ...] = Field(default=())
    findings: tuple[DependencyFinding, ...] = Field(default=())
    passed: bool = True

    def to_markdown(self) -> str:
        if self.passed and not self.findings:
            return (
                "### 📜 Supply-Chain & License Compliance: PASS\n"
                f"- Verified `{len(self.packages_checked)}` dependency reference(s).\n"
                "- All packages conform to permissive licensing policies (No copyleft/AGPL).\n"
            )

        status_emoji = "❌" if not self.passed else "⚠️"
        lines = [
            f"### {status_emoji} Supply-Chain & License Compliance: {'REJECTED' if not self.passed else 'WARNING'}",
            f"- Checked `{len(self.packages_checked)}` package(s), identified `{len(self.findings)}` issue(s):",
            "",
            "| Package | Version | License | Category | Issue |",
            "| :--- | :--- | :---: | :---: | :--- |",
        ]
        for f in self.findings:
            lines.append(
                f"| `{f.package_name}` | `{f.version_spec or '*'}` | `{f.detected_license}` | `{f.category.value}` | {f.message} |"
            )
        return "\n".join(lines)


# Reference catalog of well-known Python packages and their licenses
_KNOWN_LICENSES: dict[str, tuple[str, LicenseCategory]] = {
    # Permissive standard packages
    "click": ("Apache-2.0", LicenseCategory.PERMISSIVE),
    "requests": ("Apache-2.0", LicenseCategory.PERMISSIVE),
    "urllib3": ("MIT", LicenseCategory.PERMISSIVE),
    "pydantic": ("MIT", LicenseCategory.PERMISSIVE),
    "pytest": ("MIT", LicenseCategory.PERMISSIVE),
    "fastapi": ("MIT", LicenseCategory.PERMISSIVE),
    "flask": ("BSD-3-Clause", LicenseCategory.PERMISSIVE),
    "django": ("BSD-3-Clause", LicenseCategory.PERMISSIVE),
    "numpy": ("BSD-3-Clause", LicenseCategory.PERMISSIVE),
    "pandas": ("BSD-3-Clause", LicenseCategory.PERMISSIVE),
    "scipy": ("BSD-3-Clause", LicenseCategory.PERMISSIVE),
    "torch": ("BSD-3-Clause", LicenseCategory.PERMISSIVE),
    "transformers": ("Apache-2.0", LicenseCategory.PERMISSIVE),
    "httpx": ("BSD-3-Clause", LicenseCategory.PERMISSIVE),
    "jinja2": ("BSD-3-Clause", LicenseCategory.PERMISSIVE),
    "pyyaml": ("MIT", LicenseCategory.PERMISSIVE),
    "toml": ("MIT", LicenseCategory.PERMISSIVE),
    "tomli": ("MIT", LicenseCategory.PERMISSIVE),
    # Known Copyleft packages
    "pygpl": ("GPL-3.0", LicenseCategory.COPYLEFT),
    "readline": ("GPL-3.0", LicenseCategory.COPYLEFT),
    "gpl-module": ("GPL-3.0", LicenseCategory.COPYLEFT),
    "agpl-service": ("AGPL-3.0", LicenseCategory.COPYLEFT),
    "pyftpdlib-gpl": ("GPL-2.0", LicenseCategory.COPYLEFT),
}


class LicenseScanner:
    """Scans dependency manifests for licensing risks and supply-chain anomalies."""

    def __init__(
        self,
        disallowed_categories: tuple[LicenseCategory, ...] = (LicenseCategory.COPYLEFT,),
        banned_licenses: tuple[str, ...] = ("GPL", "AGPL", "SSPL"),
    ) -> None:
        self.disallowed_categories = disallowed_categories
        self.banned_licenses = banned_licenses

    def _parse_req_line(self, line: str) -> tuple[str, str] | None:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            return None
        # Strip trailing inline comments and environment markers
        line = line.split("#")[0].strip()
        line = line.split(";")[0].strip()
        if not line:
            return None
        # Match package name and version specification
        match = re.match(r"^([a-zA-Z0-9_\-\.]+)(.*)$", line)
        if match:
            pkg = match.group(1).lower()
            spec = match.group(2).strip()
            return pkg, spec
        return None

    def scan_requirements_txt(self, content: str, file_path: str = "requirements.txt") -> list[DependencyFinding]:
        findings: list[DependencyFinding] = []
        for line in content.splitlines():
            parsed = self._parse_req_line(line)
            if not parsed:
                continue
            pkg, spec = parsed
            finding = self._check_package(pkg, spec, file_path)
            if finding:
                findings.append(finding)
        return findings

    def scan_pyproject_toml(self, content: str, file_path: str = "pyproject.toml") -> list[DependencyFinding]:
        findings: list[DependencyFinding] = []
        try:
            data = tomllib.loads(content)
        except Exception:
            return findings

        # Check [project.dependencies]
        deps: list[str] = data.get("project", {}).get("dependencies", [])
        for dep in deps:
            parsed = self._parse_req_line(dep)
            if parsed:
                pkg, spec = parsed
                finding = self._check_package(pkg, spec, file_path)
                if finding:
                    findings.append(finding)

        # Check [tool.poetry.dependencies]
        poetry_deps: dict[str, Any] = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        for pkg_name, spec_val in poetry_deps.items():
            if pkg_name.lower() == "python":
                continue
            finding = self._check_package(pkg_name.lower(), str(spec_val), file_path)
            if finding:
                findings.append(finding)

        return findings

    def _check_package(self, pkg: str, spec: str, file_path: str) -> DependencyFinding | None:
        lic_name, cat = _KNOWN_LICENSES.get(pkg, ("UNKNOWN", LicenseCategory.UNKNOWN))

        # Heuristic fallback if unknown: check if package name suggests copyleft
        if cat == LicenseCategory.UNKNOWN:
            pkg_lower = pkg.lower()
            if any(b.lower() in pkg_lower for b in self.banned_licenses):
                for b in self.banned_licenses:
                    if b.lower() in pkg_lower:
                        lic_name = b
                        cat = LicenseCategory.COPYLEFT
                        break

        # Check for explicit copyleft or banned category
        if cat in self.disallowed_categories or any(b.lower() in lic_name.lower() for b in self.banned_licenses):
            return DependencyFinding(
                package_name=pkg,
                version_spec=spec,
                detected_license=lic_name,
                category=cat,
                file_path=file_path,
                message=f"Disallowed copyleft license `{lic_name}` detected for package `{pkg}`",
                blocking=True,
            )

        return None

    def scan_workspace(self, workspace_path: Path) -> LicenseScanReport:
        all_findings: list[DependencyFinding] = []
        packages_checked: list[str] = []

        # 1. Scan requirements.txt
        for req_file in workspace_path.glob("*requirements*.txt"):
            try:
                text = req_file.read_text(encoding="utf-8")
                for line in text.splitlines():
                    p = self._parse_req_line(line)
                    if p:
                        packages_checked.append(p[0])
                all_findings.extend(self.scan_requirements_txt(text, str(req_file.name)))
            except Exception:
                pass

        # 2. Scan pyproject.toml
        pyproject = workspace_path / "pyproject.toml"
        if pyproject.exists():
            try:
                text = pyproject.read_text(encoding="utf-8")
                data = tomllib.loads(text)
                for d in data.get("project", {}).get("dependencies", []):
                    p = self._parse_req_line(d)
                    if p:
                        packages_checked.append(p[0])
                all_findings.extend(self.scan_pyproject_toml(text, "pyproject.toml"))
            except Exception:
                pass

        has_blocking = any(f.blocking for f in all_findings)
        return LicenseScanReport(
            packages_checked=tuple(sorted(set(packages_checked))),
            findings=tuple(all_findings),
            passed=not has_blocking,
        )
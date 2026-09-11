"""
config/policy_engine.py -- Enterprise Policy & Compliance Rules Engine for QuetZ.

Enforces configurable enterprise governance constraints on autonomous patch generation:
- Banned Modules/Imports (e.g. telnetlib, ftplib, pickle)
- Protected Path Patterns (e.g. .github/**, migrations/**, Dockerfile)
- Required Test Invariants (e.g. requires test files modified if source files touched)
"""
from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PolicyViolation(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_name: str
    message: str
    file_path: str
    blocking: bool = True


class OrgCompliancePolicy(BaseModel):
    """Declarative enterprise compliance rules for autonomous coding runs."""

    model_config = ConfigDict(frozen=True)

    banned_imports: tuple[str, ...] = Field(default=("telnetlib", "ftplib"))
    protected_path_patterns: tuple[str, ...] = Field(
        default=(".github/*", ".github/**/*", "migrations/*", "migrations/**/*", "Dockerfile*")
    )
    require_test_modifications: bool = Field(default=False)
    max_files_modified_ceiling: int = Field(default=25)
    max_lines_changed_ceiling: int | None = Field(default=500)
    allowed_licenses: tuple[str, ...] = Field(default=("MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC"))
    require_clean_sast: bool = Field(default=True)
    network_egress_policy: str = Field(default="BLOCKED")  # BLOCKED or ALLOWED

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrgCompliancePolicy:
        """Construct OrgCompliancePolicy from dictionary, converting lists to tuples."""
        kwargs: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, list):
                kwargs[k] = tuple(v)
            else:
                kwargs[k] = v
        return cls(**kwargs)

    @classmethod
    def from_file(cls, path: Path | str) -> OrgCompliancePolicy:
        """Load OrgCompliancePolicy from a JSON or YAML configuration file."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Policy file not found: {p}")

        content = p.read_text(encoding="utf-8")
        if p.suffix in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore
                data = yaml.safe_load(content) or {}
            except ImportError:
                # Fallback simple parser for basic yaml key: list values if pyyaml not installed
                import json
                try:
                    data = json.loads(content)
                except Exception:
                    data = {}
        else:
            import json
            data = json.loads(content)

        return cls.from_dict(data)


class PolicyCheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool
    violations: tuple[PolicyViolation, ...] = Field(default=())
    policy_name: str = "OrgCompliancePolicy"

    def to_markdown(self) -> str:
        if self.passed:
            return (
                "### 📜 Enterprise Policy & Governance: PASS\n"
                "- All organizational compliance rules and path protections satisfied.\n"
            )

        lines = [
            "### ❌ Enterprise Policy & Governance: REJECTED",
            f"- Identified `{len(self.violations)}` compliance violation(s):",
            "",
            "| Rule | File | Message |",
            "| :--- | :--- | :--- |",
        ]
        for v in self.violations:
            lines.append(f"| `{v.rule_name}` | `{v.file_path}` | {v.message} |")
        return "\n".join(lines)


class PolicyEngine:
    """Evaluates patch proposals against enterprise compliance rules."""

    def __init__(self, policy: OrgCompliancePolicy | None = None) -> None:
        self.policy = policy or OrgCompliancePolicy()

    def evaluate_patch(
        self,
        files_modified: list[str] | tuple[str, ...],
        file_contents: dict[str, str] | None = None,
    ) -> PolicyCheckResult:
        violations: list[PolicyViolation] = []

        # 1. Check maximum files modified ceiling
        if len(files_modified) > self.policy.max_files_modified_ceiling:
            violations.append(
                PolicyViolation(
                    rule_name="MAX_MODIFIED_FILES_EXCEEDED",
                    message=(
                        f"Patch touches {len(files_modified)} files, exceeding policy limit of "
                        f"{self.policy.max_files_modified_ceiling}"
                    ),
                    file_path="<global>",
                )
            )

        # 2. Check protected paths
        for fpath in files_modified:
            norm_path = fpath.replace("\\", "/")
            for pattern in self.policy.protected_path_patterns:
                if fnmatch.fnmatch(norm_path, pattern):
                    violations.append(
                        PolicyViolation(
                            rule_name="PROTECTED_PATH_MODIFIED",
                            message=f"File matches protected path pattern '{pattern}'",
                            file_path=fpath,
                        )
                    )

        # 3. Check test modifications if required
        if self.policy.require_test_modifications and files_modified:
            has_tests = any("test" in f.lower() for f in files_modified)
            if not has_tests:
                violations.append(
                    PolicyViolation(
                        rule_name="MISSING_TEST_CHANGES",
                        message="Policy requires at least one test file to be added or modified in the patch",
                        file_path="<global>",
                    )
                )

        # 4. Check banned imports in modified file contents
        if file_contents:
            import ast

            total_lines_changed = 0
            for fpath, code in file_contents.items():
                total_lines_changed += len(code.splitlines())

                # Python AST imports check
                if fpath.endswith(".py"):
                    try:
                        tree = ast.parse(code, filename=fpath)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    if alias.name in self.policy.banned_imports:
                                        violations.append(
                                            PolicyViolation(
                                                rule_name="BANNED_IMPORT",
                                                message=f"Direct import of banned module '{alias.name}' detected",
                                                file_path=fpath,
                                            )
                                        )
                            elif isinstance(node, ast.ImportFrom):
                                if node.module and node.module in self.policy.banned_imports:
                                    violations.append(
                                        PolicyViolation(
                                            rule_name="BANNED_IMPORT",
                                            message=f"Import from banned module '{node.module}' detected",
                                            file_path=fpath,
                                        )
                                    )
                    except SyntaxError:
                        pass

                # JavaScript / TypeScript imports check
                elif fpath.endswith((".js", ".jsx", ".ts", ".tsx")):
                    from autonomous_engineer.repository.js_ts_analyzer import JsTsAnalyzer
                    js_analyzer = JsTsAnalyzer()
                    mod_map = js_analyzer.analyze_source(code, fpath)
                    for imp in mod_map.imports:
                        if imp in self.policy.banned_imports:
                            violations.append(
                                PolicyViolation(
                                    rule_name="BANNED_IMPORT",
                                    message=f"Import of banned module/package '{imp}' detected in JS/TS",
                                    file_path=fpath,
                                )
                            )

            if self.policy.max_lines_changed_ceiling is not None and total_lines_changed > self.policy.max_lines_changed_ceiling:
                violations.append(
                    PolicyViolation(
                        rule_name="MAX_LINES_CHANGED_EXCEEDED",
                        message=(
                            f"Total modified lines ({total_lines_changed}) exceeds policy ceiling of "
                            f"{self.policy.max_lines_changed_ceiling}"
                        ),
                        file_path="<global>",
                    )
                )

        has_blocking = any(v.blocking for v in violations)
        return PolicyCheckResult(
            passed=not has_blocking,
            violations=tuple(violations),
        )
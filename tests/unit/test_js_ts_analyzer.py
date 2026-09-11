"""
Unit tests for JsTsAnalyzer in repository/js_ts_analyzer.py and JS/TS configs in file_scanner.py.
"""
from autonomous_engineer.execution.models import ExecutionPolicy
from autonomous_engineer.repository.file_scanner import FileScanner
from autonomous_engineer.repository.js_ts_analyzer import JsTsAnalyzer


def test_js_ts_analyzer_parses_functions_and_classes():
    code = """
import { useState, useEffect } from 'react';
import axios from 'axios';

export async function fetchData(url: string): Promise<any> {
    const response = await axios.get(url);
    return response.data;
}

export const processPayload = (payload: any) => {
    return { ok: true, payload };
};

export class ClientManager {
    constructor() {}
}
"""
    analyzer = JsTsAnalyzer()
    res = analyzer.analyze_source(code, "src/api/client.ts")

    assert res.is_typescript is True
    assert res.is_test_file is False

    # Check imports
    assert "react" in res.imports
    assert "axios" in res.imports

    # Check functions
    fn_names = [f.name for f in res.functions]
    assert "fetchData" in fn_names
    assert "processPayload" in fn_names

    fetch_fn = next(f for f in res.functions if f.name == "fetchData")
    assert fetch_fn.is_async is True
    assert fetch_fn.is_export is True
    assert "url" in fetch_fn.parameters

    # Check classes
    class_names = [c.name for c in res.classes]
    assert "ClientManager" in class_names

    # Check exports
    assert "fetchData" in res.exports
    assert "processPayload" in res.exports
    assert "ClientManager" in res.exports


def test_js_ts_analyzer_detects_test_files():
    analyzer = JsTsAnalyzer()
    assert analyzer.is_test_file("src/__tests__/client.test.ts") is True
    assert analyzer.is_test_file("tests/component.spec.jsx") is True
    assert analyzer.is_test_file("src/utils.js") is False


def test_file_scanner_identifies_js_ts_configs():
    scanner = FileScanner()
    assert scanner.is_config_file("package.json") is True
    assert scanner.is_config_file("tsconfig.json") is True
    assert scanner.is_config_file("jest.config.js") is True
    assert scanner.is_config_file("vite.config.ts") is True


def test_execution_policy_allows_npm_and_jest():
    policy = ExecutionPolicy()
    assert any("npm test" in cmd for cmd in policy.allowed_test_commands)
    assert any("jest" in cmd for cmd in policy.allowed_test_commands)
    assert any("vitest" in cmd for cmd in policy.allowed_test_commands)


def test_js_ts_analyzer_methods_and_symbols():
    code = """
export interface UserSession {
    token: string;
}

export class AuthController {
    public async login(creds: any) {
        return true;
    }

    logout() {
        return false;
    }
}
"""
    analyzer = JsTsAnalyzer()
    mod = analyzer.analyze_source(code, "src/auth/controller.ts")
    assert "UserSession" in mod.exports
    assert "AuthController" in mod.exports

    auth_cls = next(c for c in mod.classes if c.name == "AuthController")
    assert "login" in auth_cls.methods
    assert "logout" in auth_cls.methods

    # Check symbol presence helper
    assert analyzer.check_symbol_present(mod, "AuthController") is True
    assert analyzer.check_symbol_present(mod, "login") is True
    assert analyzer.check_symbol_present(mod, "AuthController.logout") is True
    assert analyzer.check_symbol_present(mod, "nonExistentMethod") is False


def test_execution_verifier_verifies_js_ts_file(tmp_path):
    from autonomous_engineer.domain.models import ImplementationStep, StepOperation
    from autonomous_engineer.execution.models import FileChangeRecord
    from autonomous_engineer.execution.verifier import ExecutionVerifier

    ts_file = tmp_path / "index.ts"
    ts_file.write_text("export function computeHash(data: string) { return 42; }", encoding="utf-8")

    verifier = ExecutionVerifier()
    changes = (
        FileChangeRecord(
            file_path="index.ts",
            operation=StepOperation.MODIFY_SYMBOL,
            lines_added=1,
            lines_removed=0,
            content_hash_after="abc123",
        ),
    )
    steps = (
        ImplementationStep(
            step_id="step-1",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="index.ts",
            target_symbol="computeHash",
            description="Add computeHash function",
        ),
    )

    results = verifier.verify_static(tmp_path, changes, steps)
    assert len(results) == 2  # SYNTAX_AST + SYMBOL_EXISTENCE
    assert all(r.passed for r in results)
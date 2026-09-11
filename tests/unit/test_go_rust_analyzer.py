"""
Unit tests for Go and Rust structural code analysis in repository/go_rust_analyzer.py.
"""
from autonomous_engineer.domain.models import ImplementationStep, StepOperation
from autonomous_engineer.execution.models import FileChangeRecord
from autonomous_engineer.execution.verifier import ExecutionVerifier
from autonomous_engineer.repository.go_rust_analyzer import PolyglotCodeAnalyzer


def test_go_code_analysis():
    go_code = '''package service

import "net/http"
import "fmt"

type ServerConfig struct {
    Port int
}

func HandleRequest(w http.ResponseWriter, r *http.Request) {
    fmt.Fprintf(w, "OK")
}
'''
    analyzer = PolyglotCodeAnalyzer()
    mod = analyzer.analyze_source(go_code, "pkg/server/handler.go")

    assert mod.language == "go"
    assert mod.is_test_file is False
    assert "net/http" in mod.imports

    sym_names = [s.name for s in mod.symbols]
    assert "ServerConfig" in sym_names
    assert "HandleRequest" in sym_names

    assert analyzer.check_symbol_present(mod, "HandleRequest") is True
    assert analyzer.check_symbol_present(mod, "ServerConfig") is True
    assert analyzer.check_symbol_present(mod, "NonExistent") is False


def test_rust_code_analysis():
    rust_code = '''use std::sync::Arc;

pub struct AuthToken {
    pub value: String,
}

pub async fn verify_token(token: &str) -> bool {
    !token.is_empty()
}
'''
    analyzer = PolyglotCodeAnalyzer()
    mod = analyzer.analyze_source(rust_code, "src/auth/token.rs")

    assert mod.language == "rust"
    assert mod.is_test_file is False
    assert "std::sync::Arc" in mod.imports

    sym_names = [s.name for s in mod.symbols]
    assert "AuthToken" in sym_names
    assert "verify_token" in sym_names

    assert analyzer.check_symbol_present(mod, "verify_token") is True
    assert analyzer.check_symbol_present(mod, "AuthToken") is True


def test_execution_verifier_polyglot(tmp_path):
    go_file = tmp_path / "main.go"
    go_file.write_text('package main\n\nfunc RunApp() {}\n', encoding="utf-8")

    verifier = ExecutionVerifier()
    changes = (
        FileChangeRecord(
            file_path="main.go",
            operation=StepOperation.MODIFY_SYMBOL,
            lines_added=1,
            lines_removed=0,
            content_hash_after="12345",
        ),
    )
    steps = (
        ImplementationStep(
            step_id="step-1",
            operation=StepOperation.MODIFY_SYMBOL,
            target_file="main.go",
            target_symbol="RunApp",
            description="Add RunApp entry point",
        ),
    )

    results = verifier.verify_static(tmp_path, changes, steps)
    assert len(results) == 2
    assert all(r.passed for r in results)
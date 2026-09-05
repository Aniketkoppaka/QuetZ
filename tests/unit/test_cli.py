"""
tests/unit/test_cli.py -- Tests for ASE Production CLI.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from autonomous_engineer.cli import build_parser, cmd_audit, cmd_skills, main


class TestCli:
    def test_parser_builds(self):
        parser = build_parser()
        args = parser.parse_args(["skills"])
        assert args.command == "skills"

    def test_skills_command_executes_cleanly(self, capsys):
        rc = cmd_skills()
        assert rc == 0
        captured = capsys.readouterr()
        assert "Declarative Engineering Playbook Registry" in captured.out
        assert "python_bug_fix" in captured.out

    def test_audit_command_executes_cleanly(self, capsys):
        rc = cmd_audit()
        assert rc == 0
        captured = capsys.readouterr()
        assert "System Environment & Security Policy Audit" in captured.out
        assert "Default Granted Capabilities" in captured.out

    def test_main_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "autonomous-engineer" in captured.out

    def test_main_skills(self, capsys):
        rc = main(["skills"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Total Registered Skills" in captured.out

    def test_run_parser_flags(self):
        parser = build_parser()
        args = parser.parse_args([
            "run",
            "--repo", "test/repo",
            "--title", "Fix bug",
            "--body", "Description",
            "--open-pr",
            "--mutation-testing",
            "--require-reproduction",
        ])
        assert args.command == "run"
        assert args.repo == "test/repo"
        assert args.open_pr is True
        assert args.mutation_testing is True
        assert args.require_reproduction is True

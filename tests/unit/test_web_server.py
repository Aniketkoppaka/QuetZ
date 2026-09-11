"""
tests/unit/test_web_server.py -- Tests for ASE Control Console Web Server and API endpoints.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
import pytest

from autonomous_engineer.web.server import (
    ASEConsoleHandler,
    get_mock_runs,
    get_system_summary,
    get_agents_hierarchy,
    _SESSIONS,
    STATIC_DIR,
)
import socketserver


class TestWebServerDataModels:
    """Test data providers for the ASE Control Console."""

    def test_system_summary_structure(self) -> None:
        summary = get_system_summary()
        assert summary["status"] == "OPERATIONAL"
        assert summary["active_policy"] == "Strict-Fail-Closed-v2"
        assert "coordinator" in summary["model_orchestration"]
        assert summary["stats"]["verified_completed"] > 0
        assert summary["security_policy"]["fail_closed_enabled"] is True

    def test_mock_runs_differentiators(self) -> None:
        runs = get_mock_runs()
        assert len(runs) >= 3

        # First run: completed with high confidence and mutation score
        r1 = runs[0]
        assert r1["status"] == "COMPLETED"
        assert "dag_plan" in r1
        assert len(r1["dag_plan"]["steps"]) == 2
        assert "anchor_tier" in r1["dag_plan"]["steps"][0]
        assert "TIER 1" in r1["dag_plan"]["steps"][0]["anchor_tier"]

        # Diffs inspection
        assert len(r1["diffs"]) > 0
        assert "TIER 1" in r1["diffs"][0]["anchor_tier"]
        assert "hunks" in r1["diffs"][0]

        # Reproduction check
        assert r1["reproduction"]["status"] == "CONFIRMED_REPRODUCED"
        assert r1["reproduction"]["pre_patch_exit_code"] == 1
        assert r1["reproduction"]["post_patch_exit_code"] == 0

        # Mutation check
        assert r1["mutation_report"]["score"] > 0.8
        assert len(r1["mutation_report"]["operators"]) > 0

        # Certificate check
        assert r1["certificate"]["static_ast_passed"] is True
        assert r1["certificate"]["reproduction_verified"] is True
        assert r1["certificate"]["rolled_back"] is False
        assert len(r1["certificate"]["evidence_hash"]) == 64

        # Third run: failure with rollback
        r3 = runs[2]
        assert r3["status"] == "FAILED"
        assert r3["certificate"]["rolled_back"] is True
        assert r3["dag_plan"]["steps"][0]["status"] == "ROLLED_BACK"

    def test_agents_hierarchy(self) -> None:
        agents = get_agents_hierarchy()
        assert len(agents) == 6
        roles = [a["role"] for a in agents]
        assert any("Coordinator" in r for r in roles)
        assert any("Reviewer" in r for r in roles)
        assert any("Verifier" in r for r in roles)

    def test_sessions_seeded(self) -> None:
        assert len(_SESSIONS) >= 3
        sess = _SESSIONS["sess-click-2419"]
        assert len(sess["messages"]) >= 4
        # Verify cards embedded inside messages
        has_cards = any(len(m.get("cards", [])) > 0 for m in sess["messages"])
        assert has_cards is True

    def test_static_files_exist(self) -> None:
        assert (STATIC_DIR / "index.html").is_file()
        assert (STATIC_DIR / "style.css").is_file()
        assert (STATIC_DIR / "app.js").is_file()


class TestWebServerHttpEndpoints:
    """Test actual HTTP requests against an active console server thread."""

    @classmethod
    @pytest.fixture(scope="class")
    def test_server(cls):
        # Pick an ephemeral test port
        socketserver.TCPServer.allow_reuse_address = True
        httpd = socketserver.TCPServer(("127.0.0.1", 0), ASEConsoleHandler)
        port = httpd.server_address[1]
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        base_url = f"http://127.0.0.1:{port}"
        time.sleep(0.05)
        yield base_url
        httpd.shutdown()
        httpd.server_close()

    def test_get_index_html(self, test_server: str) -> None:
        req = urllib.request.urlopen(f"{test_server}/")
        assert req.status == 200
        assert "text/html" in req.headers.get("Content-Type", "")
        content = req.read().decode("utf-8")
        assert "QuetZ // Autonomous Software Engineer Chat Console" in content
        assert "ENGINEERING SESSIONS" in content

    def test_get_style_css(self, test_server: str) -> None:
        req = urllib.request.urlopen(f"{test_server}/style.css")
        assert req.status == 200
        assert "text/css" in req.headers.get("Content-Type", "")
        content = req.read().decode("utf-8")
        assert "--accent-green: #39FF88" in content

    def test_get_app_js(self, test_server: str) -> None:
        req = urllib.request.urlopen(f"{test_server}/app.js")
        assert req.status == 200
        content = req.read().decode("utf-8")
        assert "QuetZ Chat Control Console Client Application" in content

    def test_api_sessions_list(self, test_server: str) -> None:
        req = urllib.request.urlopen(f"{test_server}/api/sessions")
        assert req.status == 200
        sessions = json.loads(req.read().decode("utf-8"))
        assert len(sessions) >= 3
        assert sessions[0]["session_id"] == "sess-click-2419"

    def test_api_session_detail(self, test_server: str) -> None:
        req = urllib.request.urlopen(f"{test_server}/api/sessions/sess-click-2419")
        assert req.status == 200
        session = json.loads(req.read().decode("utf-8"))
        assert session["session_id"] == "sess-click-2419"
        assert len(session["messages"]) >= 4
        assert session["messages"][1]["cards"][0]["type"] == "reproduction_proof"

    def test_api_post_message(self, test_server: str) -> None:
        post_data = json.dumps({"text": "Please verify mutation tests"}).encode("utf-8")
        req = urllib.request.Request(
            f"{test_server}/api/sessions/sess-click-2419/messages",
            data=post_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 201
            reply = json.loads(resp.read().decode("utf-8"))
            assert reply["sender"] == "agent"
            assert len(reply["cards"]) > 0
            assert reply["cards"][0]["type"] == "mutation_report"

    def test_api_post_new_session(self, test_server: str) -> None:
        post_data = json.dumps({"title": "Test Custom Issue", "repo": "test/repo"}).encode("utf-8")
        req = urllib.request.Request(
            f"{test_server}/api/sessions",
            data=post_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 201
            new_sess = json.loads(resp.read().decode("utf-8"))
            assert "sess-" in new_sess["session_id"]
            assert new_sess["title"] == "Test Custom Issue"

    def test_api_session_not_found(self, test_server: str) -> None:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{test_server}/api/sessions/sess-does-not-exist")
        assert exc_info.value.code == 404

    def test_api_runs_legacy(self, test_server: str) -> None:
        req = urllib.request.urlopen(f"{test_server}/api/runs")
        assert req.status == 200
        runs = json.loads(req.read().decode("utf-8"))
        assert len(runs) >= 3

    def test_api_metrics(self, test_server: str) -> None:
        req = urllib.request.urlopen(f"{test_server}/api/metrics")
        assert req.status == 200
        data = json.loads(req.read().decode("utf-8"))
        assert data["total_runs"] == 2
        assert data["completed_runs"] == 2
        assert data["resolution_rate_pct"] == 100.0
        assert data["sast_clean_pass_rate_pct"] == 100.0
        assert "tier_1" in data["anchor_tier_counts"]

    def test_api_feedback_get(self, test_server: str) -> None:
        req = urllib.request.urlopen(f"{test_server}/api/feedback")
        assert req.status == 200
        data = json.loads(req.read().decode("utf-8"))
        assert "calibrated_weights" in data
        assert "w_verification" in data["calibrated_weights"]
        assert "w_grounding" in data["calibrated_weights"]
        assert "total_feedback_count" in data

    def test_api_feedback_post_and_calibrate(self, test_server: str) -> None:
        payload = json.dumps({
            "pr_id": "PR-TEST-101",
            "issue_id": "ISSUE-101",
            "outcome": "MERGED_AS_IS",
            "confidence": 0.95,
            "comments": "Great clean verified patch"
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{test_server}/api/feedback",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 201
            res = json.loads(resp.read().decode("utf-8"))
            assert res["status"] == "RECORDED"
            assert res["outcome"] == "MERGED_AS_IS"
            assert "updated_weights" in res
            assert res["updated_weights"]["w_verification"] > 0



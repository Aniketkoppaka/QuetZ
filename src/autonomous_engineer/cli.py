"""
autonomous_engineer/cli.py -- Production CLI and Developer Interface for ASE.

Commands:
  - run: Execute end-to-end autonomous resolution on a repository with an issue.
  - verify: Run independent verification and mutation testing on an existing patch/workspace.
  - audit: Audit local environment, Git capabilities, and tool allowlists.
  - skills: Inspect registered engineering skills and trigger patterns.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from autonomous_engineer.domain.models import Issue, Repository
from autonomous_engineer.domain.states import WorkflowPhase
from autonomous_engineer.execution.models import Capability, ExecutionPolicy
from autonomous_engineer.github import GitHubPRBot
from autonomous_engineer.orchestration.pipeline import (
    AutonomousPipeline,
    PipelineConfig,
    PipelineExecutionSummary,
)
from autonomous_engineer.repository.acquisition import GitAcquisitionService
from autonomous_engineer.repository.analyzer import RepositoryAnalyzer
from autonomous_engineer.repository.models import RepositoryReference
from autonomous_engineer.tools import PLAYBOOK_REGISTRY
from autonomous_engineer.verification.reproduction import ReproductionCandidate


def build_parser() -> argparse.ArgumentParser:
    """Build root CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="autonomous-engineer",
        description="QuetZ (Autonomous Software Engineer) - Production-Grade Fail-Closed Agentic Harness",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run autonomous engineering cycle on an issue")
    run_parser.add_argument("--repo", required=True, help="Repository URL, path, or reference")
    run_parser.add_argument("--issue-id", default="local/issue#1", help="Unique issue ID")
    run_parser.add_argument("--title", required=True, help="Issue title")
    run_parser.add_argument("--body", required=True, help="Detailed problem description")
    run_parser.add_argument("--branch", default="main", help="Target git branch")
    run_parser.add_argument("--reproduce-cmd", default=None, help="Test command to establish reproduction (e.g. pytest -k test_foo)")
    run_parser.add_argument("--reproduce-pattern", default=None, help="Expected error regex signature in reproduction failure")
    run_parser.add_argument("--require-reproduction", action="store_true", help="Fail-closed if candidate test passes pre-patch")
    run_parser.add_argument("--mutation-testing", action="store_true", help="Run AST mutation assertion strength checks")
    run_parser.add_argument("--open-pr", action="store_true", help="Generate GitHub PR payload and branch with VerificationCertificate")
    run_parser.add_argument("--out-dir", default=None, help="Optional output directory for artifacts")

    # Command: skills
    subparsers.add_parser("skills", help="List registered engineering playbooks and triggers")

    # Command: audit
    subparsers.add_parser("audit", help="Audit local environment, git availability, and security policies")

    # Command: ui (Control Console)
    ui_parser = subparsers.add_parser("ui", help="Launch the QuetZ Engineering Control Console")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    ui_parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")

    return parser


def cmd_skills() -> int:
    """Display registered engineering playbooks and triggers."""
    print("=" * 70)
    print("QuetZ Declarative Engineering Playbook Registry")
    print("=" * 70)
    skills = PLAYBOOK_REGISTRY.all_skills
    for skill in skills:
        print(f"\n[Skill: {skill.name}]")
        print(f"  Description: {skill.description}")
        print(f"  Required Capabilities: {[c.value for c in skill.required_capabilities]}")
        print(f"  Triggers ({len(skill.trigger_patterns)}): {list(skill.trigger_patterns[:4])}...")
        print(f"  Guidance: {skill.step_guidance[:100]}...")
    print(f"\nTotal Registered Skills: {len(skills)}")
    return 0


def cmd_audit() -> int:
    """Audit local execution capabilities."""
    print("=" * 70)
    print("QuetZ System Environment & Security Policy Audit")
    print("=" * 70)
    policy = ExecutionPolicy()
    print(f"Default Granted Capabilities: {[c.value for c in policy.granted_capabilities]}")
    print(f"Max Risk Ceiling: {policy.max_risk_level.value}")
    print(f"Test Execution Allowed: {policy.allow_test_execution}")
    print(f"Auto-Rollback On Failure: {policy.auto_rollback_on_failure}")
    print(f"Allowed Test Runners: {policy.allowed_test_commands}")
    print("Security Invariants: Fail-closed, pure-syntactic AST analysis, zero code execution during parsing.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Execute autonomous resolution run."""
    print("=" * 70)
    print("QuetZ (Autonomous Software Engineer) - Starting Workflow Run")
    print("=" * 70)
    print(f"Target Repository: {args.repo}")
    print(f"Issue: [{args.issue_id}] {args.title}")

    issue = Issue(
        id=args.issue_id,
        title=args.title,
        body=args.body,
        repository_url=args.repo,
        base_branch=args.branch,
    )

    repro_candidate: ReproductionCandidate | None = None
    if args.reproduce_cmd:
        repro_candidate = ReproductionCandidate(
            test_command=args.reproduce_cmd,
            expected_failure_pattern=args.reproduce_pattern,
            description=f"CLI reproduction test for {args.issue_id}",
        )
        print(f"Reproduction Candidate: `{repro_candidate.build_command_line()}`")

    policy = ExecutionPolicy()
    if args.open_pr:
        policy = policy.with_capability(Capability.CAP_OPEN_PR)

    cfg = PipelineConfig(
        require_reproduction=args.require_reproduction,
        run_mutation_testing=args.mutation_testing,
        execution_policy=policy,
    )

    # Acquire and analyze repo
    workspace_path = Path(args.repo).resolve() if Path(args.repo).exists() else Path.cwd()
    repo = Repository(
        url=args.repo,
        workspace_path=workspace_path,
        commit_sha="local_head",
        branch=args.branch,
    )

    print("\n[Phase: MAPPING] Syntactically parsing repository into AST structural map...")
    analyzer = RepositoryAnalyzer()
    repo_map = analyzer.analyze(repo)
    print(f"  Inventoried {repo_map.file_count} files ({repo_map.python_file_count} Python modules).")

    # Match skills
    matched = PLAYBOOK_REGISTRY.match(f"{issue.title}\n{issue.body}", policy=cfg.execution_policy)
    print(f"  Matched Engineering Playbooks: {[s.name for s in matched] or 'None (General Workflow)'}")

    # Initialize LLM planner if API credentials are present
    planner = None
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        from autonomous_engineer.agents.llm_client import HttpLLMClient, LLMConfig
        from autonomous_engineer.agents.planner import LLMPlanner
        model_name = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
        print(f"  Live LLM Provider: OpenRouter ({model_name})")
        client = HttpLLMClient(api_base_url="https://openrouter.ai/api/v1", api_key=openrouter_key)
        planner_cfg = LLMConfig(model=model_name, temperature=0.0)
        planner = LLMPlanner(llm_client=client, config=planner_cfg)

    pipeline = AutonomousPipeline(planner=planner)
    print("\n[Phase: EXECUTING] Routing through fail-closed verification pipeline...")

    # Define hook or print active plan if generated
    summary = pipeline.run(
        issue=issue,
        repository=repo,
        repository_map=repo_map,
        plan=None,
        config=cfg,
        reproduction_candidate=repro_candidate,
    )

    print("\n" + "=" * 70)
    print("Execution Outcome Summary")
    print("=" * 70)
    print(f"Final Phase: {summary.final_phase.value.upper()}")
    print(f"Job Status:  {summary.status.value.upper()}")
    print(f"Duration:    {summary.duration_seconds}s")
    if summary.error_message:
        print(f"Diagnostics: {summary.error_message}")

    if summary.certificate:
        print("\n" + summary.certificate.to_markdown())
    if summary.reproduction_evidence:
        print("\n" + summary.reproduction_evidence.to_markdown())
    if summary.mutation_report:
        print("\n" + summary.mutation_report.to_markdown())
    if summary.impact_report:
        print(f"\nBlast Radius Analysis: {summary.impact_report.summary()}")

    if args.open_pr and summary.final_phase == WorkflowPhase.COMPLETED:
        bot = GitHubPRBot()
        pr_payload = bot.generate_pr_payload(issue=issue, summary=summary, policy=policy)
        print("\n" + "=" * 70)
        print("GitHub PR Delivery Payload Generated")
        print("=" * 70)
        print(f"Target Branch: {pr_payload.branch_name} -> {pr_payload.base_branch}")
        print(f"PR Title:      {pr_payload.title}")
        print(f"Commit Msg:    {pr_payload.commit_message}")
        print(f"Files Changed: {list(pr_payload.files_changed)}")
        if args.out_dir:
            out_path = Path(args.out_dir) / "pr_payload.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(pr_payload.model_dump_json(indent=2), encoding="utf-8")
            print(f"Saved PR payload to: {out_path}")

    return 0 if summary.final_phase == WorkflowPhase.COMPLETED else 1


def cmd_ui(args: argparse.Namespace) -> int:
    """Launch the QuetZ Engineering Control Console web server."""
    from autonomous_engineer.web.server import run_server
    run_server(host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "skills":
        return cmd_skills()
    elif args.command == "audit":
        return cmd_audit()
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "ui":
        return cmd_ui(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())

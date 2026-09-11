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

# Ensure standard output can print Unicode characters safely across all platforms
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
    run_parser.add_argument(
        "--provider",
        default=None,
        choices=["openrouter", "openai", "anthropic", "ollama", "groq", "deepseek", "mistral", "gemini", "custom"],
        help="LLM Provider backend (default: auto-detected from environment variables)",
    )
    run_parser.add_argument("--api-base", default=None, help="Custom LLM API Base URL (e.g. http://localhost:11434/v1 for Ollama)")
    run_parser.add_argument("--model", default=None, help="Target LLM model name")
    run_parser.add_argument("--out-dir", default=None, help="Optional output directory for artifacts")

    # Command: skills
    subparsers.add_parser("skills", help="List registered engineering playbooks and triggers")

    # Command: audit
    subparsers.add_parser("audit", help="Audit local environment, git availability, and security policies")

    # Command: ui (Control Console)
    ui_parser = subparsers.add_parser("ui", help="Launch the QuetZ Engineering Control Console")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    ui_parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")

    # Command: scan-security
    sec_parser = subparsers.add_parser("scan-security", help="Run AST static application security scan (SAST)")
    sec_parser.add_argument("paths", nargs="*", default=["."], help="Paths to files or directories to scan (default: .)")

    # Command: scan-licenses
    lic_parser = subparsers.add_parser("scan-licenses", help="Scan dependencies for copyleft/prohibited licenses")
    lic_parser.add_argument("path", nargs="?", default=".", help="Workspace path or manifest file to scan (default: .)")

    # Command: metrics
    met_parser = subparsers.add_parser("metrics", help="Display aggregated KPI telemetry and trust metrics")
    met_parser.add_argument("--file", default=None, help="Optional path to metrics.jsonl telemetry store")

    # Command: feedback
    fb_parser = subparsers.add_parser("feedback", help="Record human review outcome to adapt confidence weights")
    fb_parser.add_argument("--pr-id", required=True, help="Pull Request ID or reference")
    fb_parser.add_argument("--issue-id", required=True, help="Associated Issue ID")
    fb_parser.add_argument(
        "--outcome",
        required=True,
        choices=["MERGED_AS_IS", "MERGED_WITH_EDITS", "REJECTED_OR_ABANDONED"],
        help="Human review outcome",
    )
    fb_parser.add_argument("--confidence", type=float, default=0.90, help="Original confidence score at generation")
    fb_parser.add_argument("--files", nargs="*", default=[], help="Files touched in the PR")
    fb_parser.add_argument("--file", default=None, help="Optional path to feedback.jsonl persistence store")

    # Command: export-audit
    audit_exp_parser = subparsers.add_parser("export-audit", help="Export comprehensive enterprise compliance and security report")
    audit_exp_parser.add_argument("--output", "-o", default=None, help="Output file path (default: stdout, or .json/.md based on extension)")
    audit_exp_parser.add_argument("--policy", default=None, help="Optional path to custom enterprise policy YAML/JSON file")
    audit_exp_parser.add_argument("--path", default=".", help="Workspace path to audit (default: .)")

    # Command: sign-cert
    sign_parser = subparsers.add_parser("sign-cert", help="Sign a VerificationCertificate using cryptographic keys")
    sign_parser.add_argument("cert_file", help="Path to VerificationCertificate JSON file")
    sign_parser.add_argument("--output", "-o", default=None, help="Output path for signed envelope JSON")
    sign_parser.add_argument("--key", default=None, help="Optional secret key (or env QUETZ_SIGNING_KEY)")

    # Command: verify-cert
    verify_parser = subparsers.add_parser("verify-cert", help="Verify cryptographic signature and integrity of a signed certificate envelope")
    verify_parser.add_argument("envelope_file", help="Path to signed certificate envelope JSON file")
    verify_parser.add_argument("--key", default=None, help="Optional secret key (or env QUETZ_SIGNING_KEY)")

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

    # Initialize LLM planner if credentials or local endpoints are specified
    planner = None
    provider = (args.provider or "").lower()
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    mistral_key = os.environ.get("MISTRAL_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    api_base: str | None = args.api_base
    api_key: str = ""
    model_name: str | None = args.model

    from autonomous_engineer.agents.llm_client import HttpLLMClient, LLMConfig, LLMProviderProfile
    from autonomous_engineer.agents.planner import LLMPlanner

    # 1. Ollama (Local)
    if provider == "ollama" or (api_base and "11434" in api_base):
        api_base = api_base or LLMProviderProfile.DEFAULT_ENDPOINTS["ollama"]
        model_name = model_name or LLMProviderProfile.DEFAULT_MODELS["ollama"]
        api_key = "ollama"
        provider = "ollama"
        print(f"  Live LLM Provider: Local Ollama ({model_name} @ {api_base})")
    # 2. Anthropic
    elif provider == "anthropic" or (not provider and anthropic_key and not (openrouter_key or openai_key)):
        api_base = api_base or LLMProviderProfile.DEFAULT_ENDPOINTS["anthropic"]
        api_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY", "")
        model_name = model_name or LLMProviderProfile.DEFAULT_MODELS["anthropic"]
        provider = "anthropic"
        print(f"  Live LLM Provider: Anthropic ({model_name})")
    # 3. Groq (Ultra-Low Latency Inference)
    elif provider == "groq" or (not provider and groq_key and not (openrouter_key or openai_key)):
        api_base = api_base or LLMProviderProfile.DEFAULT_ENDPOINTS["groq"]
        api_key = groq_key or os.environ.get("GROQ_API_KEY", "")
        model_name = model_name or LLMProviderProfile.DEFAULT_MODELS["groq"]
        provider = "groq"
        print(f"  Live LLM Provider: Groq Fast LPU ({model_name})")
    # 4. DeepSeek
    elif provider == "deepseek" or (not provider and deepseek_key and not (openrouter_key or openai_key)):
        api_base = api_base or LLMProviderProfile.DEFAULT_ENDPOINTS["deepseek"]
        api_key = deepseek_key or os.environ.get("DEEPSEEK_API_KEY", "")
        model_name = model_name or LLMProviderProfile.DEFAULT_MODELS["deepseek"]
        provider = "deepseek"
        print(f"  Live LLM Provider: DeepSeek ({model_name})")
    # 5. Mistral AI
    elif provider == "mistral" or (not provider and mistral_key and not (openrouter_key or openai_key)):
        api_base = api_base or LLMProviderProfile.DEFAULT_ENDPOINTS["mistral"]
        api_key = mistral_key or os.environ.get("MISTRAL_API_KEY", "")
        model_name = model_name or LLMProviderProfile.DEFAULT_MODELS["mistral"]
        provider = "mistral"
        print(f"  Live LLM Provider: Mistral AI ({model_name})")
    # 6. Google Gemini
    elif provider == "gemini" or (not provider and gemini_key and not (openrouter_key or openai_key)):
        api_base = api_base or LLMProviderProfile.DEFAULT_ENDPOINTS["gemini"]
        api_key = gemini_key or os.environ.get("GEMINI_API_KEY", "")
        model_name = model_name or LLMProviderProfile.DEFAULT_MODELS["gemini"]
        provider = "gemini"
        print(f"  Live LLM Provider: Google Gemini ({model_name})")
    # 7. OpenAI
    elif provider == "openai" or (not provider and openai_key and not openrouter_key):
        api_base = api_base or LLMProviderProfile.DEFAULT_ENDPOINTS["openai"]
        api_key = openai_key or ""
        model_name = model_name or LLMProviderProfile.DEFAULT_MODELS["openai"]
        provider = "openai"
        print(f"  Live LLM Provider: OpenAI ({model_name})")
    # 8. OpenRouter (Multi-Model Gateway)
    elif openrouter_key or provider == "openrouter":
        api_base = api_base or LLMProviderProfile.DEFAULT_ENDPOINTS["openrouter"]
        api_key = openrouter_key or ""
        model_name = model_name or os.environ.get("OPENROUTER_MODEL", LLMProviderProfile.DEFAULT_MODELS["openrouter"])
        provider = "openrouter"
        print(f"  Live LLM Provider: OpenRouter ({model_name})")

    if api_base:
        client = HttpLLMClient(api_base_url=api_base, api_key=api_key, provider=provider)
        planner_cfg = LLMConfig(model=model_name or "default", temperature=0.0)
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

    if (args.open_pr or args.submit_pr) and summary.final_phase == WorkflowPhase.COMPLETED:
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

        if args.submit_pr:
            gh_token = os.environ.get("GITHUB_TOKEN")
            if not gh_token:
                print("Warning: --submit-pr specified but GITHUB_TOKEN environment variable is missing.")
            else:
                repo_parts = args.repo.rstrip("/").split("/")
                if len(repo_parts) >= 2:
                    owner, rname = repo_parts[-2], repo_parts[-1].replace(".git", "")
                    print(f"Submitting PR to GitHub: {owner}/{rname}...")
                    res = bot.submit_pull_request(repo_owner=owner, repo_name=rname, payload=pr_payload, github_token=gh_token)
                    if res.get("success"):
                        print(f"✓ Pull Request Created Successfully: {res.get('html_url')}")
                    else:
                        print(f"✕ Pull Request Submission Failed: {res.get('error')}")

    return 0 if summary.final_phase == WorkflowPhase.COMPLETED else 1


def cmd_ui(args: argparse.Namespace) -> int:
    """Launch the QuetZ Engineering Control Console web server."""
    from autonomous_engineer.web.server import run_server
    run_server(host=args.host, port=args.port)
    return 0


def cmd_scan_security(args: argparse.Namespace) -> int:
    """Execute static application security scan (SAST) on target files or paths."""
    from autonomous_engineer.verification.security_scan import ASTSecurityScanner
    print("=" * 70)
    print("QuetZ AST Static Application Security Scanner (SAST)")
    print("=" * 70)

    scanner = ASTSecurityScanner()
    target_paths: list[Path] = []
    for p_str in args.paths:
        p = Path(p_str)
        if p.is_file() and p.suffix == ".py":
            target_paths.append(p)
        elif p.is_dir():
            target_paths.extend(p.glob("**/*.py"))

    # Remove duplicates and exclusions
    cleaned_paths = sorted(
        set(p for p in target_paths if not any(ign in str(p) for ign in (".git", ".pytest_cache", ".venv", "venv")))
    )
    print(f"Scanning {len(cleaned_paths)} Python module(s)...")

    report = scanner.scan_files(cleaned_paths)
    print("\n" + report.to_markdown())
    return 0 if report.passed else 1


def cmd_scan_licenses(args: argparse.Namespace) -> int:
    """Execute supply-chain and copyleft license check."""
    from autonomous_engineer.verification.license_scan import LicenseScanner
    print("=" * 70)
    print("QuetZ Supply-Chain & License Compliance Scanner")
    print("=" * 70)

    scanner = LicenseScanner()
    target_path = Path(args.path)

    if target_path.is_file():
        text = target_path.read_text(encoding="utf-8")
        if target_path.name.endswith(".toml"):
            findings = scanner.scan_pyproject_toml(text, target_path.name)
        else:
            findings = scanner.scan_requirements_txt(text, target_path.name)
        from autonomous_engineer.verification.license_scan import LicenseScanReport
        report = LicenseScanReport(
            packages_checked=tuple(f.package_name for f in findings),
            findings=tuple(findings),
            passed=not any(f.blocking for f in findings),
        )
    else:
        report = scanner.scan_workspace(target_path)

    print("\n" + report.to_markdown())
    return 0 if report.passed else 1


def cmd_metrics(args: argparse.Namespace) -> int:
    """Display aggregated KPI telemetry summary."""
    from autonomous_engineer.observability.metrics import MetricsCollector
    print("=" * 70)
    print("QuetZ Autonomous Engineering KPI & Trust Metrics Dashboard")
    print("=" * 70)

    storage = Path(args.file) if args.file else None
    collector = MetricsCollector(storage_path=storage)
    summary = collector.summarize()

    print(f"Total Workflow Runs:        {summary.total_runs}")
    print(f"Completed Runs (PR Opened): {summary.completed_runs}")
    print(f"Abstained Runs:             {summary.abstained_runs}")
    print(f"Failed Runs:                {summary.failed_runs}")
    print(f"Resolution Rate:            {summary.resolution_rate_pct}%")
    print(f"Epistemic Abstention Rate:  {summary.abstention_rate_pct}%")
    print(f"Average Confidence Score:   {summary.average_confidence_score:.3f}")
    print(f"Average Mutation Kill Rate: {summary.average_mutation_score:.3f}")
    print(f"Average Time-to-Fix:        {summary.average_duration_seconds}s")
    print(f"SAST Clean Pass Rate:       {summary.sast_clean_pass_rate_pct}%")
    print(f"Anchor Tiers Used:          {summary.anchor_tier_counts}")
    return 0


def cmd_feedback(args: argparse.Namespace) -> int:
    """Ingest human review feedback and display adapted confidence weights."""
    from autonomous_engineer.observability.feedback_loop import (
        AdaptiveConfidenceTuner,
        PRFeedbackRecord,
        PROutcome,
    )
    print("=" * 70)
    print("QuetZ Adaptive Confidence Tuner (Feedback Ingestion)")
    print("=" * 70)

    storage = Path(args.file) if args.file else None
    tuner = AdaptiveConfidenceTuner(persistence_file=storage)

    record = PRFeedbackRecord(
        pr_id=args.pr_id,
        issue_id=args.issue_id,
        outcome=PROutcome(args.outcome),
        confidence_at_generation=args.confidence,
        files_touched=tuple(args.files),
    )
    tuner.record_feedback(record)
    new_weights = tuner.get_calibrated_weights()

    print(f"Recorded Review Outcome: [{record.outcome.value}] for PR {record.pr_id}")
    print("\nUpdated Mathematical Confidence Weights:")
    print(f"  w_grounding:    {new_weights.w_grounding:.3f}")
    print(f"  w_plan:         {new_weights.w_plan:.3f}")
    print(f"  w_verification: {new_weights.w_verification:.3f}")
    print(f"  w_authority:    {new_weights.w_authority:.3f}")
    return 0


def cmd_export_audit(args: argparse.Namespace) -> int:
    """Generate comprehensive SOC2/ISO enterprise audit report for security, compliance, and metrics."""
    import json
    from datetime import datetime, timezone
    from autonomous_engineer.config.policy_engine import OrgCompliancePolicy, PolicyEngine
    from autonomous_engineer.verification.security_scan import ASTSecurityScanner
    from autonomous_engineer.verification.license_scan import LicenseScanner
    from autonomous_engineer.observability.metrics import MetricsCollector
    from autonomous_engineer.observability.feedback_loop import AdaptiveConfidenceTuner

    target_dir = Path(args.path)

    # 1. SAST Scan (scan production code, ignoring tests and virtual environments)
    sec_scanner = ASTSecurityScanner()
    python_files = [
        p for p in target_dir.glob("**/*.py")
        if not any(ign in str(p).replace("\\", "/") for ign in (".git", ".venv", "venv", "__pycache__", "/tests/", "tests/"))
    ]
    sec_report = sec_scanner.scan_files(python_files)

    # 2. License Scan
    lic_scanner = LicenseScanner()
    lic_report = lic_scanner.scan_workspace(target_dir)

    # 3. Policy Engine Evaluation
    if args.policy:
        policy = OrgCompliancePolicy.from_file(args.policy)
    else:
        policy = OrgCompliancePolicy()
    policy_engine = PolicyEngine(policy)
    file_paths = [str(p.relative_to(target_dir)) for p in python_files[:20]]
    policy_res = policy_engine.evaluate_patch(files_modified=file_paths)

    # 4. Metrics & Bayesian Weights
    tuner = AdaptiveConfidenceTuner()
    weights = tuner.get_calibrated_weights()

    copyleft_pkgs = [f.package_name for f in lic_report.findings if f.blocking]

    report_data = {
        "report_id": f"AUDIT-{int(time.time())}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace": str(target_dir.resolve()),
        "security_sast": {
            "passed": sec_report.passed,
            "total_findings": len(sec_report.findings),
            "critical_count": sec_report.critical_count,
            "high_count": sec_report.high_count,
            "files_scanned": len(sec_report.scanned_files),
            "findings": [f.model_dump(mode="json") for f in sec_report.findings],
        },
        "supply_chain_licenses": {
            "compliant": lic_report.passed,
            "packages_audited": len(lic_report.packages_checked),
            "copyleft_found": copyleft_pkgs,
        },
        "enterprise_governance": {
            "passed": policy_res.passed,
            "violations": [v.model_dump(mode="json") for v in policy_res.violations],
            "banned_imports": list(policy.banned_imports),
            "network_egress_policy": policy.network_egress_policy,
        },
        "bayesian_calibrated_weights": weights.model_dump(mode="json"),
        "compliance_status": "COMPLIANT" if (sec_report.passed and lic_report.passed and policy_res.passed) else "NON_COMPLIANT",
    }

    output_content = ""
    if args.output and args.output.endswith(".json"):
        output_content = json.dumps(report_data, indent=2)
    elif args.output and (args.output.endswith(".md") or args.output.endswith(".markdown")):
        lines = [
            f"# Enterprise Compliance & Security Audit Report ({report_data['report_id']})",
            f"**Generated**: `{report_data['timestamp']}` | **Status**: `{report_data['compliance_status']}`\n",
            "## 1. Static Application Security Testing (SAST)",
            f"- Status: {'✓ PASSED' if sec_report.passed else '✕ FAILED'}",
            f"- Files Scanned: {len(sec_report.scanned_files)}",
            f"- Critical / High Findings: {sec_report.critical_count + sec_report.high_count}\n",
            "## 2. Supply-Chain License Compliance",
            f"- Status: {'✓ COMPLIANT' if lic_report.passed else '✕ NON-COMPLIANT'}",
            f"- Prohibited/Copyleft Packages: {len(copyleft_pkgs)}\n",
            "## 3. Organizational Governance & Safety Boundaries",
            f"- Policy Pass: {'✓ YES' if policy_res.passed else '✕ VIOLATIONS'}",
            f"- Network Egress Mode: `{policy.network_egress_policy}`\n",
            "## 4. Calibrated Confidence Scoring Distribution",
            f"- Grounding Evidence: `{weights.w_grounding:.3f}`",
            f"- Plan Determinism: `{weights.w_plan:.3f}`",
            f"- Multi-Test Verification: `{weights.w_verification:.3f}`",
            f"- Reviewer Authority: `{weights.w_authority:.3f}`",
        ]
        output_content = "\n".join(lines)
    else:
        output_content = json.dumps(report_data, indent=2)

    if args.output:
        Path(args.output).write_text(output_content, encoding="utf-8")
        print(f"Exported audit report to: {args.output}")
    else:
        print(output_content)

    return 0 if report_data["compliance_status"] == "COMPLIANT" else 1


def cmd_sign_cert(args: argparse.Namespace) -> int:
    """Sign a VerificationCertificate JSON file using HMAC-SHA256."""
    import json
    from autonomous_engineer.verification.signing import CertificateSigner

    cert_path = Path(args.cert_file)
    if not cert_path.exists():
        print(f"Error: Certificate file not found: {cert_path}")
        return 1

    cert_data = json.loads(cert_path.read_text(encoding="utf-8"))
    key = args.key or os.environ.get("QUETZ_SIGNING_KEY")
    signer = CertificateSigner(secret_key=key)
    envelope = signer.sign_certificate(cert_data)

    env_json = envelope.model_dump_json(indent=2)
    if args.output:
        Path(args.output).write_text(env_json, encoding="utf-8")
        print(f"Signed certificate written to: {args.output}")
    else:
        print(env_json)
    return 0


def cmd_verify_cert(args: argparse.Namespace) -> int:
    """Verify cryptographic signature and integrity of a signed certificate envelope."""
    import json
    from autonomous_engineer.verification.signing import CertificateSigner, SignedCertificateEnvelope

    env_path = Path(args.envelope_file)
    if not env_path.exists():
        print(f"Error: Envelope file not found: {env_path}")
        return 1

    env_data = json.loads(env_path.read_text(encoding="utf-8"))
    envelope = SignedCertificateEnvelope(**env_data)

    key = args.key or os.environ.get("QUETZ_SIGNING_KEY")
    signer = CertificateSigner(secret_key=key)
    is_valid = signer.verify_envelope(envelope)

    if is_valid:
        cert = envelope.certificate_payload
        print("=" * 70)
        print("✓ CRYPTOGRAPHIC VERIFICATION SUCCESSFUL")
        print("=" * 70)
        print(f"Certificate ID: {cert.get('certificate_id')}")
        print(f"Algorithm:      {envelope.signature_algorithm}")
        print(f"Evidence Hash:  {envelope.evidence_hash}")
        print(f"Status:         {cert.get('status')}")
        print(f"Confidence:     {cert.get('confidence_score')}")
        print("Signature:      VALID (Unmodified Artifact)")
        return 0
    else:
        print("=" * 70)
        print("✕ CRYPTOGRAPHIC VERIFICATION FAILED (TAMPER DETECTED / KEY MISMATCH)")
        print("=" * 70)
        return 1


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
    elif args.command == "scan-security":
        return cmd_scan_security(args)
    elif args.command == "scan-licenses":
        return cmd_scan_licenses(args)
    elif args.command == "metrics":
        return cmd_metrics(args)
    elif args.command == "feedback":
        return cmd_feedback(args)
    elif args.command == "export-audit":
        return cmd_export_audit(args)
    elif args.command == "sign-cert":
        return cmd_sign_cert(args)
    elif args.command == "verify-cert":
        return cmd_verify_cert(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())

"""
evaluation/cli.py -- Command-Line Interface for executing real-world benchmarks.

Usage:
  python -m autonomous_engineer.evaluation.cli --mode mock
  python -m autonomous_engineer.evaluation.cli --mode live --case REAL-CLICK-01
  python -m autonomous_engineer.evaluation.cli --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from autonomous_engineer.agents.llm_client import HttpLLMClient, LLMConfig, MockLLMClient
from autonomous_engineer.evaluation.config import EnvironmentAuditor, EvaluationMode, LLMProviderConfig
from autonomous_engineer.evaluation.dataset import BENCHMARK_REGISTRY, BenchmarkIssueStatus
from autonomous_engineer.evaluation.ground_truth import GroundTruthValidationStatus
from autonomous_engineer.evaluation.persistence import BenchmarkRunPersistence
from autonomous_engineer.evaluation.real_benchmark import (
    EvaluationAblationConfig,
    LiveLLMStatus,
    RealBenchmarkRunner,
)


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Autonomous Software Engineer Real-World Evaluation Harness (Milestone 8)",
    )
    parser.add_argument(
        "--mode",
        choices=["live", "mock", "unavailable"],
        default=None,
        help="Evaluation execution mode (defaults to auto-detection from environment)",
    )
    parser.add_argument(
        "--case",
        type=str,
        default=None,
        help="Filter execution to a specific benchmark case ID (e.g. REAL-CLICK-01)",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Filter execution to a specific problem category (e.g. exact_identifier)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory path to save run artifacts",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Audit environment and validate dataset entries without executing LLM/plans",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum planner repair loop retries",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI execution entrypoint."""
    parser = create_parser()
    args = parser.parse_args(argv)

    print("================================================================================")
    print("       AUTONOMOUS SOFTWARE ENGINEER -- REAL-WORLD EVALUATION HARNESS")
    print("================================================================================")

    # 1. Environment Audit
    audit_data = EnvironmentAuditor.audit()
    print("\n--- ENVIRONMENT AUDIT ---")
    print(f"Python Version:       {audit_data['python_version']}")
    print(f"Platform:             {audit_data['platform']}")
    print(f"Git Version:          {audit_data['git_version']}")
    print(f"Pytest Version:       {audit_data['pytest_version']}")
    print(f"Network Available:    {audit_data['network_available']}")
    print(f"LLM Provider:         {audit_data['llm_provider']}")
    print(f"LLM Model:            {audit_data['llm_model']}")
    print(f"Credentials Status:   {'AVAILABLE' if audit_data['llm_credentials_available'] else 'NOT CONFIGURED'}")

    provider_config = LLMProviderConfig.from_env()

    # Determine mode
    if args.mode:
        selected_mode = EvaluationMode(args.mode)
    else:
        selected_mode = EvaluationMode.LIVE if provider_config.has_credentials else EvaluationMode.UNAVAILABLE

    print(f"Selected Mode:        {selected_mode.value.upper()}")

    # 2. Dry-Run / Unavailable Handling
    if args.dry_run:
        print("\n[DRY RUN] Environment validated. Verified dataset cases in registry:")
        for idx, item in enumerate(BENCHMARK_REGISTRY, start=1):
            status_str = f"[{item.status.value.upper()}]"
            print(f"  {idx:2d}. {status_str:<12} {item.case_id:<18} ({item.repository_name}) - {item.issue_title[:45]}...")
        print("\nDry run complete. Exiting cleanly.")
        return 0

    if selected_mode == EvaluationMode.UNAVAILABLE or (selected_mode == EvaluationMode.LIVE and not provider_config.has_credentials):
        print("\n================================================================================")
        print("LIVE LLM EVALUATION: NOT EXECUTED")
        print("REASON: No active live LLM API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY)")
        print("        are configured in the execution environment.")
        print("================================================================================")
        return 0

    active_cases = [
        c for c in BENCHMARK_REGISTRY
        if c.status in (BenchmarkIssueStatus.VERIFIED, BenchmarkIssueStatus.GROUND_TRUTH_VERIFIED)
        and c.ground_truth_status == GroundTruthValidationStatus.GROUND_TRUTH_VERIFIED
    ]
    if args.case:
        active_cases = [c for c in active_cases if c.case_id == args.case]
        if not active_cases:
            print(f"\nError: Case ID {args.case!r} not found in verified registry.")
            return 1
    if args.category:
        active_cases = [c for c in active_cases if c.category == args.category]
        if not active_cases:
            print(f"\nError: No verified cases match category {args.category!r}.")
            return 1

    print(f"\nRunning benchmark on {len(active_cases)} verified case(s)...")

    # 4. Client Selection
    if selected_mode == EvaluationMode.LIVE:
        client = HttpLLMClient(
            api_base_url=provider_config.api_base_url,
            api_key=provider_config.api_key or "",
        )
        llm_config = LLMConfig(
            model=provider_config.model_name,
            temperature=provider_config.temperature,
            max_tokens=provider_config.max_tokens,
            timeout_seconds=provider_config.timeout_seconds,
        )
    else:
        # Mock mode fallback
        client = MockLLMClient(responses=['{"summary": "Mock evaluation plan"}'])
        llm_config = None

    runner = RealBenchmarkRunner()
    ablation_config = EvaluationAblationConfig(max_planner_retries=args.max_retries, llm_config=llm_config)

    # Execute evaluation suite
    report = runner.evaluate_suite(
        issues=tuple(active_cases),
        workspace_map={},
        repo_map_cache={},
        llm_client=client,
        ablation_config=ablation_config,
    )

    # 5. Persist Run Artifacts
    persistence = BenchmarkRunPersistence(base_dir=Path(args.output_dir) if args.output_dir else None)
    run_dir = persistence.save_run(report=report, provider_config=provider_config)
    print(f"\nRun artifacts saved to: {run_dir}")

    # 6. Print Summary
    print("\n--- BENCHMARK RESULTS SUMMARY ---")
    print(f"Total Evaluated:      {report.verified_cases_evaluated}")
    print(f"Resolved Cases:       {report.resolved_cases}")
    print(f"Resolved Rate:        {report.resolved_rate * 100:.1f}%")
    print(f"Failure Distribution: {report.failure_distribution}")
    print(f"Mean Target Recall@3: {report.mean_target_file_recall_at_3 * 100:.1f}%")
    print(f"Mean MRR:             {report.mean_mrr:.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
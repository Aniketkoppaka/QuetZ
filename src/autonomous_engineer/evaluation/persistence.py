"""
evaluation/persistence.py -- Machine-readable benchmark run persistence and artifact writer.

Saves benchmark results to evaluation/runs/<run_id>/ with:
1. environment.json (sanitized runtime metadata)
2. benchmark_results.json (detailed per-case traces and classifications)
3. summary.json (aggregate metrics)

Strict invariant: All persisted JSON files are scrubbed of any secret credentials.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autonomous_engineer.evaluation.config import EnvironmentAuditor, LLMProviderConfig
from autonomous_engineer.evaluation.real_benchmark import BenchmarkRunResult, EndToEndReport


def _scrub_secrets(obj: Any) -> Any:
    """Recursively scrub any key or value resembling an API key or auth header."""
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if any(term in k_lower for term in ("api_key", "authorization", "secret", "token", "password")):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = _scrub_secrets(v)
        return cleaned
    elif isinstance(obj, (list, tuple)):
        return [_scrub_secrets(item) for item in obj]
    elif isinstance(obj, str):
        if obj.startswith("sk-") or "Bearer " in obj:
            return "[REDACTED]"
        return obj
    return obj


class BenchmarkRunPersistence:
    """Persists machine-readable evaluation run artifacts."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or (Path(__file__).parent.parent.parent.parent / "evaluation" / "runs")

    def save_run(
        self,
        report: EndToEndReport,
        provider_config: LLMProviderConfig,
        run_id: str | None = None,
    ) -> Path:
        """
        Save environment, benchmark results, and summary to a dedicated run directory.

        Args:
            report: The EndToEndReport to persist.
            provider_config: Provider configuration (will be masked).
            run_id: Optional run ID (generated if not provided).

        Returns:
            Path to the created run directory.
        """
        active_run_id = run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        run_dir = self.base_dir / active_run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # 1. Environment Metadata
        env_data = {
            "run_id": active_run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": EnvironmentAuditor.audit(),
            "provider_config": provider_config.masked_dict(),
        }
        (run_dir / "environment.json").write_text(
            json.dumps(_scrub_secrets(env_data), indent=2),
            encoding="utf-8",
        )

        # 2. Detailed Per-Case Results
        results_data = {
            "run_id": active_run_id,
            "cases": [r.deterministic_dict() for r in report.case_results],
        }
        (run_dir / "benchmark_results.json").write_text(
            json.dumps(_scrub_secrets(results_data), indent=2),
            encoding="utf-8",
        )

        # 3. Summary Aggregate Report
        summary_data = {
            "run_id": active_run_id,
            "summary": report.deterministic_dict(),
        }
        (run_dir / "summary.json").write_text(
            json.dumps(_scrub_secrets(summary_data), indent=2),
            encoding="utf-8",
        )

        return run_dir
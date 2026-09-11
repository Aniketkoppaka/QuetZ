"""
Structured logging, tracing, execution flight recorder, KPI metrics, and adaptive feedback tuning.

Public API:
  - FlightEvent: Immutable event record in an agent's flight trajectory.
  - FlightRecorder: In-memory and file-backed trajectory flight recorder.
  - RunMetricRecord: Telemetry record for a workflow run.
  - MetricsSummary: Aggregated KPI summary (resolution rate, mutation score, etc.).
  - MetricsCollector: Metrics aggregator and JSONL persistence engine.
  - AdaptiveConfidenceTuner: Self-calibrating confidence tuning engine.
  - ConfidenceWeights: Mathematical weights for confidence calculation.
  - PRFeedbackRecord: Human review feedback record.
  - PROutcome: Enum of PR review dispositions.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.observability.feedback_loop import (
    AdaptiveConfidenceTuner,
    ConfidenceWeights,
    PRFeedbackRecord,
    PROutcome,
)
from autonomous_engineer.observability.metrics import (
    MetricsCollector,
    MetricsSummary,
    RunMetricRecord,
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class FlightEvent(BaseModel):
    """
    Immutable audit event in an agent's flight log.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=_utcnow)
    run_id: str = Field(description="Workflow or run identifier")
    event_type: str = Field(description="Event classification (transition, evidence, plan, mutation, verification, failure)")
    component: str = Field(description="Subsystem emitting event")
    payload: dict[str, Any] = Field(default_factory=dict, description="Structured event payload")

    def to_jsonl(self) -> str:
        """Serialize event to single-line JSON."""
        return json.dumps(
            {
                "event_id": self.event_id,
                "timestamp": self.timestamp.isoformat(),
                "run_id": self.run_id,
                "event_type": self.event_type,
                "component": self.component,
                "payload": self.payload,
            }
        )


class FlightRecorder:
    """
    In-memory and file-backed flight recorder for autonomous runs.
    """

    def __init__(self, run_id: str, log_file: Path | None = None) -> None:
        self._run_id = run_id
        self._log_file = log_file
        self._events: list[FlightEvent] = []

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def events(self) -> tuple[FlightEvent, ...]:
        return tuple(self._events)

    def record(self, event_type: str, component: str, payload: dict[str, Any] | None = None) -> FlightEvent:
        """
        Record a new flight event synchronously and append to log file if configured.
        """
        event = FlightEvent(
            run_id=self._run_id,
            event_type=event_type,
            component=component,
            payload=payload or {},
        )
        self._events.append(event)
        if self._log_file is not None:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            with self._log_file.open("a", encoding="utf-8") as f:
                f.write(event.to_jsonl() + "\n")
        return event

    def filter_events(self, event_type: str | None = None, component: str | None = None) -> list[FlightEvent]:
        """Query recorded events by type or component."""
        res = self._events
        if event_type:
            res = [e for e in res if e.event_type == event_type]
        if component:
            res = [e for e in res if e.component == component]
        return res


__all__ = [
    "AdaptiveConfidenceTuner",
    "ConfidenceWeights",
    "FlightEvent",
    "FlightRecorder",
    "MetricsCollector",
    "MetricsSummary",
    "PRFeedbackRecord",
    "PROutcome",
    "RunMetricRecord",
]
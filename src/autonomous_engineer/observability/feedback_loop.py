"""
observability/feedback_loop.py -- Adaptive Feedback Loop & Dynamic Confidence Tuning for QuetZ.

Tracks human review outcomes of autonomous pull requests:
- MERGED_AS_IS: Patch was accepted without modification.
- MERGED_WITH_EDITS: Developer accepted patch but revised parts of it.
- REJECTED_OR_ABANDONED: Patch was rejected, closed, or reverted.

Dynamically tunes verification weights in the confidence formula:
    Confidence = w_grounding * S_grounding + w_plan * S_plan + w_verification * S_verification + w_authority * S_authority
And maintains module penalty scores to increase epistemic humility in fragile codebase areas.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class PROutcome(str, Enum):
    MERGED_AS_IS = "MERGED_AS_IS"
    MERGED_WITH_EDITS = "MERGED_WITH_EDITS"
    REJECTED_OR_ABANDONED = "REJECTED_OR_ABANDONED"


class PRFeedbackRecord(BaseModel):
    """Immutable record of human review outcome on an autonomous PR."""

    model_config = ConfigDict(frozen=True)

    pr_id: str
    issue_id: str
    outcome: PROutcome
    confidence_at_generation: float
    files_touched: tuple[str, ...] = Field(default=())
    human_comments: str = ""
    timestamp: datetime = Field(default_factory=_utcnow)


class ConfidenceWeights(BaseModel):
    """Calibrated weight distribution for multi-dimensional confidence scoring."""

    model_config = ConfigDict(frozen=True)

    w_grounding: float = 0.30
    w_plan: float = 0.25
    w_verification: float = 0.35
    w_authority: float = 0.10

    def compute_score(
        self,
        s_grounding: float,
        s_plan: float,
        s_verification: float,
        s_authority: float,
    ) -> float:
        raw = (
            self.w_grounding * s_grounding
            + self.w_plan * s_plan
            + self.w_verification * s_verification
            + self.w_authority * s_authority
        )
        return max(0.0, min(1.0, round(raw, 4)))


class AdaptiveConfidenceTuner:
    """Ingests PR outcomes and tunes confidence parameters and module risk penalties."""

    def __init__(self, persistence_file: Path | None = None) -> None:
        self.persistence_file = persistence_file
        self._records: list[PRFeedbackRecord] = []
        self._module_rejections: dict[str, int] = {}
        if self.persistence_file and self.persistence_file.exists():
            self._load()

    def _load(self) -> None:
        try:
            for line in self.persistence_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = PRFeedbackRecord(**json.loads(line))
                    self._records.append(rec)
                    if rec.outcome == PROutcome.REJECTED_OR_ABANDONED:
                        for f in rec.files_touched:
                            self._module_rejections[f] = self._module_rejections.get(f, 0) + 1
        except Exception:
            pass

    def record_feedback(self, feedback: PRFeedbackRecord) -> None:
        self._records.append(feedback)
        if feedback.outcome == PROutcome.REJECTED_OR_ABANDONED:
            for f in feedback.files_touched:
                self._module_rejections[f] = self._module_rejections.get(f, 0) + 1

        if self.persistence_file:
            self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
            with self.persistence_file.open("a", encoding="utf-8") as f:
                f.write(feedback.model_dump_json() + "\n")

    @property
    def feedback_records(self) -> tuple[PRFeedbackRecord, ...]:
        return tuple(self._records)

    def get_module_penalty(self, file_path: str) -> float:
        """Calculate confidence penalty for frequently rejected modules."""
        rejections = self._module_rejections.get(file_path, 0)
        # Cap penalty at 0.20 reduction in confidence
        return round(min(0.20, rejections * 0.05), 4)

    def get_calibrated_weights(self) -> ConfidenceWeights:
        """
        Dynamically adjust weights based on PR review history:
        If PRs are frequently rejected, shift weight heavily into rigorous verification.
        """
        if not self._records:
            return ConfidenceWeights()

        total = len(self._records)
        rejected = sum(1 for r in self._records if r.outcome == PROutcome.REJECTED_OR_ABANDONED)
        rejection_rate = rejected / total

        # Shift up to +0.15 weight into verification if rejection rate is high
        boost = min(0.15, rejection_rate * 0.20)
        new_w_verif = round(0.35 + boost, 3)
        new_w_plan = round(0.25 - (boost * 0.6), 3)
        new_w_ground = round(0.30 - (boost * 0.4), 3)

        return ConfidenceWeights(
            w_grounding=new_w_ground,
            w_plan=new_w_plan,
            w_verification=new_w_verif,
            w_authority=0.10,
        )
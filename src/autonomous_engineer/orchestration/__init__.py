"""
orchestration -- Persistent asynchronous job and session engine for autonomous software engineering.

Public API:
  - JobStatus: Lifecycle states of an ASE Job.
  - JobBudget: Resource and execution boundaries (tokens, retries, seconds).
  - JobCheckpoint: Disk-serializable checkpoint snapshot.
  - ASEJob: Core job abstraction wrapping WorkflowRun with persistence, pause/resume.
  - ASEJobManager: Session manager coordinating active and checkpointed jobs.
"""
from __future__ import annotations

import enum
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.domain.models import Issue
from autonomous_engineer.domain.states import WorkflowPhase, WorkflowRun


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class JobStatus(str, enum.Enum):
    """Lifecycle states of an asynchronous ASE job."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABSTAINED = "abstained"
    ABANDONED = "abandoned"


class JobBudget(BaseModel):
    """Resource and execution boundaries governing an ASE job."""

    model_config = ConfigDict(frozen=True)

    max_repair_iterations: int = Field(default=3, ge=1)
    max_total_tokens: int = Field(default=100_000, ge=1_000)
    max_wall_clock_seconds: float = Field(default=600.0, ge=10.0)
    tokens_consumed: int = Field(default=0, ge=0)


class JobCheckpoint(BaseModel):
    """Immutable checkpoint representation of an active or paused job."""

    model_config = ConfigDict(frozen=True)

    checkpoint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    phase: WorkflowPhase
    status: JobStatus
    workflow_run_json: str
    budget: JobBudget
    created_at: datetime = Field(default_factory=_utcnow)


class ASEJob:
    """
    Persistent asynchronous job and session abstraction for autonomous tasks.
    Manages task lifecycle, pause/resume, checkpointing, and budget enforcement.
    """

    def __init__(
        self,
        job_id: str,
        run: WorkflowRun,
        budget: JobBudget | None = None,
        status: JobStatus = JobStatus.PENDING,
    ) -> None:
        self._job_id = job_id
        self._run = run
        self._budget = budget or JobBudget()
        self._status = status
        self._checkpoints: list[JobCheckpoint] = []

    @property
    def job_id(self) -> str:
        return self._job_id

    @property
    def run(self) -> WorkflowRun:
        return self._run

    @property
    def status(self) -> JobStatus:
        return self._status

    @property
    def budget(self) -> JobBudget:
        return self._budget

    @property
    def checkpoints(self) -> tuple[JobCheckpoint, ...]:
        return tuple(self._checkpoints)

    def transition_workflow(
        self,
        to_phase: WorkflowPhase,
        triggered_by: str,
        reason: str = "",
        tokens_used: int = 0,
        **updates: Any,
    ) -> WorkflowRun:
        """Advance workflow run state while enforcing budget boundaries."""
        new_tokens = self._budget.tokens_consumed + tokens_used
        if new_tokens > self._budget.max_total_tokens:
            self._status = JobStatus.ABANDONED
            raise ValueError(
                f"Job {self._job_id} exceeded token budget: {new_tokens} > {self._budget.max_total_tokens}"
            )

        self._budget = JobBudget(
            max_repair_iterations=self._budget.max_repair_iterations,
            max_total_tokens=self._budget.max_total_tokens,
            max_wall_clock_seconds=self._budget.max_wall_clock_seconds,
            tokens_consumed=new_tokens,
        )

        self._run = self._run.transition(to_phase, triggered_by, reason=reason, **updates)

        if self._run.phase == WorkflowPhase.COMPLETED:
            self._status = JobStatus.COMPLETED
        elif self._run.phase == WorkflowPhase.ABSTAINED:
            self._status = JobStatus.ABSTAINED
        elif self._run.phase == WorkflowPhase.FAILED:
            self._status = JobStatus.FAILED
        elif self._run.phase == WorkflowPhase.ABANDONED:
            self._status = JobStatus.ABANDONED
        else:
            self._status = JobStatus.RUNNING

        return self._run

    def pause(self) -> JobCheckpoint:
        """Pause running job and generate a checkpoint snapshot."""
        self._status = JobStatus.PAUSED
        return self.save_checkpoint()

    def resume(self) -> None:
        """Resume paused job."""
        if self._status != JobStatus.PAUSED:
            raise ValueError(f"Cannot resume job with status {self._status.value}")
        self._status = JobStatus.RUNNING

    def save_checkpoint(self) -> JobCheckpoint:
        """Generate and save an immutable checkpoint."""
        ckpt = JobCheckpoint(
            job_id=self._job_id,
            phase=self._run.phase,
            status=self._status,
            workflow_run_json=self._run.model_dump_json(),
            budget=self._budget,
        )
        self._checkpoints.append(ckpt)
        return ckpt

    @classmethod
    def restore_from_checkpoint(cls, checkpoint: JobCheckpoint) -> "ASEJob":
        """Restore an ASEJob from a serialized checkpoint."""
        run = WorkflowRun.model_validate_json(checkpoint.workflow_run_json)
        job = cls(
            job_id=checkpoint.job_id,
            run=run,
            budget=checkpoint.budget,
            status=checkpoint.status,
        )
        job._checkpoints.append(checkpoint)
        return job


class ASEJobManager:
    """Session coordinator managing active and disk-persisted jobs."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self._storage_dir = storage_dir
        self._jobs: dict[str, ASEJob] = {}

    def create_job(
        self,
        task_id: str,
        issue: Issue,
        budget: JobBudget | None = None,
        job_id: str | None = None,
    ) -> ASEJob:
        """Create a new job initialized with fresh WorkflowRun."""
        jid = job_id or str(uuid.uuid4())
        run = WorkflowRun(run_id=f"run-{jid[:8]}", task_id=task_id, issue=issue)
        job = ASEJob(job_id=jid, run=run, budget=budget)
        self._jobs[jid] = job
        return job

    def get_job(self, job_id: str) -> ASEJob | None:
        return self._jobs.get(job_id)

    def persist_checkpoint(self, job_id: str) -> Path:
        """Save job checkpoint directly to disk."""
        if not self._storage_dir:
            raise ValueError("No storage_dir configured for ASEJobManager.")
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found.")

        ckpt = job.save_checkpoint()
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        ckpt_file = self._storage_dir / f"{job_id}.json"
        ckpt_file.write_text(ckpt.model_dump_json(indent=2), encoding="utf-8")
        return ckpt_file

    def load_checkpoint(self, checkpoint_path: Path) -> ASEJob:
        """Load job checkpoint from disk and register as active session."""
        data = checkpoint_path.read_text(encoding="utf-8")
        ckpt = JobCheckpoint.model_validate_json(data)
        job = ASEJob.restore_from_checkpoint(ckpt)
        self._jobs[job.job_id] = job
        return job


__all__ = [
    "ASEJob",
    "ASEJobManager",
    "JobBudget",
    "JobCheckpoint",
    "JobStatus",
]

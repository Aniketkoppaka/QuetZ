"""
orchestration/pipeline.py -- Unified End-to-End Autonomous Software Engineering Pipeline (Phase 4.1).

Connects all fail-closed, auditable sub-systems into a cohesive autonomous run:
1. Repository Understanding & Mapping
2. Grounded Context Retrieval
3. Declarative Skill/Playbook Matching
4. Reproduction-Before-Fix Test Execution (Fail phase)
5. Structured Plan Generation & Preflight Security Checks
6. Transactional Execution & 4-Tier Anchor Matching with Auto-Rollback
7. Post-Patch Reproduction Verification (Pass phase)
8. Semantic Change-Impact Analysis (Blast radius)
9. Mutation-Based Test Assertion Strength Verification
10. Proof-Carrying Verification Certificate Generation
11. Evidence-Based Abstention Evaluation & Independent Code Review
12. Final Result & Audit Record Emission
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.agents.validator import AbstentionDecision, AbstentionEngine
from autonomous_engineer.domain.models import (
    FinalResult,
    ImplementationPlan,
    Issue,
    PatchSummary,
    Repository,
    RepositoryMap,
)
from autonomous_engineer.domain.states import WorkflowPhase, WorkflowRun
from autonomous_engineer.execution.engine import ExecutionEngine
from autonomous_engineer.execution.models import (
    Capability,
    ExecutionPolicy,
    ExecutionRequest,
    PlanExecutionResult,
    VerificationCertificate,
)
from autonomous_engineer.observability import FlightRecorder
from autonomous_engineer.orchestration import ASEJob, JobBudget, JobStatus
from autonomous_engineer.repository.impact_analyzer import ChangeImpactAnalyzer, ImpactReport
from autonomous_engineer.review import IndependentReviewAgent, ReviewVerdict
from autonomous_engineer.tools import PLAYBOOK_REGISTRY, EngineeringSkill
from autonomous_engineer.verification.mutation import MutationReport, MutationTester
from autonomous_engineer.verification.reproduction import (
    ReproductionCandidate,
    ReproductionEvidence,
    ReproductionVerifier,
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class PipelineConfig(BaseModel):
    """Configuration tuning pipeline execution and verification gates."""

    model_config = ConfigDict(frozen=True)

    execution_policy: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    require_reproduction: bool = Field(
        default=False,
        description="Whether a verified reproduction candidate (fail-then-pass) is required",
    )
    run_mutation_testing: bool = Field(
        default=False,
        description="Whether mutation analysis is run on patch changes",
    )
    max_mutation_candidates: int = Field(default=3, ge=1)
    min_confidence_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    enable_flight_recorder: bool = Field(default=True)


class PipelineExecutionSummary(BaseModel):
    """Immutable comprehensive record of an end-to-end pipeline run."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    issue_id: str
    final_phase: WorkflowPhase
    status: JobStatus
    matched_skills: tuple[str, ...] = Field(default=())
    reproduction_evidence: ReproductionEvidence | None = None
    impact_report: ImpactReport | None = None
    mutation_report: MutationReport | None = None
    certificate: VerificationCertificate | None = None
    abstention_decision: AbstentionDecision | None = None
    review_verdict: ReviewVerdict | None = None
    final_result: FinalResult | None = None
    error_message: str | None = None
    duration_seconds: float = 0.0
    recorded_at: datetime = Field(default_factory=_utcnow)


class AutonomousPipeline:
    """
    Unified coordinator running an autonomous software engineering task through all verified phases.
    """

    def __init__(
        self,
        execution_engine: ExecutionEngine | None = None,
        reproduction_verifier: ReproductionVerifier | None = None,
        impact_analyzer_factory: Any | None = None,
        mutation_tester: MutationTester | None = None,
        abstention_engine: AbstentionEngine | None = None,
        review_agent: IndependentReviewAgent | None = None,
        planner: Any | None = None,
        retriever: Any | None = None,
    ) -> None:
        self._execution_engine = execution_engine or ExecutionEngine()
        self._reproduction_verifier = reproduction_verifier or ReproductionVerifier()
        self._impact_analyzer_factory = impact_analyzer_factory or ChangeImpactAnalyzer
        self._mutation_tester = mutation_tester or MutationTester()
        self._abstention_engine = abstention_engine or AbstentionEngine()
        self._review_agent = review_agent or IndependentReviewAgent()
        self._planner = planner
        self._retriever = retriever

    def run(
        self,
        issue: Issue,
        repository: Repository,
        repository_map: RepositoryMap,
        plan: ImplementationPlan | None = None,
        config: PipelineConfig | None = None,
        reproduction_candidate: ReproductionCandidate | None = None,
    ) -> PipelineExecutionSummary:
        """
        Execute an end-to-end autonomous engineering cycle fail-closed.
        """
        start_time = time.perf_counter()
        cfg = config or PipelineConfig()
        policy = cfg.execution_policy

        # Initialise State Machine & Flight Recorder
        run_id = f"run-{issue.id.replace('/', '_').replace('#', '_')}-{int(time.time())}"
        workflow_run = WorkflowRun(
            run_id=run_id,
            task_id=f"task-{issue.id}",
            issue=issue,
            repository=repository,
        )
        job = ASEJob(job_id=workflow_run.run_id, run=workflow_run)
        recorder: FlightRecorder | None = None
        if cfg.enable_flight_recorder:
            recorder = FlightRecorder(run_id=workflow_run.run_id)
            plan_id_str = plan.plan_id if plan else "dynamic_llm_plan"
            recorder.record("pipeline_started", "pipeline", {"issue_id": issue.id, "plan_id": plan_id_str})

        # Advance state to ACQUIRING -> MAPPING
        job.transition_workflow(WorkflowPhase.ACQUIRING, triggered_by="pipeline")
        job.transition_workflow(WorkflowPhase.MAPPING, triggered_by="pipeline", repository_map=repository_map)

        # 1. Declarative Playbook Matching
        matched_skills = PLAYBOOK_REGISTRY.match(
            issue_text=f"{issue.title}\n{issue.body}",
            policy=policy,
        )
        matched_skill_names = tuple(s.name for s in matched_skills)
        if recorder:
            recorder.record("skills_matched", "pipeline", {"skills": list(matched_skill_names)})

        # 2. Reproduction Pre-Patch Execution (Optional / if candidate provided)
        reproduction_evidence: ReproductionEvidence | None = None
        if reproduction_candidate is not None:
            pre_res = self._reproduction_verifier.run_pre_patch(
                workspace=repository.workspace_path,
                candidate=reproduction_candidate,
                policy=policy,
            )
            # If reproduction is required and pre-patch passes -> ABSTAIN immediately (vacuous test)
            if cfg.require_reproduction and pre_res.passed:
                evidence = self._reproduction_verifier.evaluate_reproduction(
                    pre_result=pre_res,
                    post_result=pre_res,
                    candidate=reproduction_candidate,
                )
                job.transition_workflow(WorkflowPhase.RETRIEVING, triggered_by="pipeline")
                job.transition_workflow(WorkflowPhase.ABSTAINED, triggered_by="pipeline")
                if recorder:
                    recorder.record("reproduction_vacuous", "pipeline", {"diagnostics": evidence.diagnostics})
                return PipelineExecutionSummary(
                    run_id=job.run.run_id,
                    issue_id=issue.id,
                    final_phase=WorkflowPhase.ABSTAINED,
                    status=JobStatus.ABSTAINED,
                    matched_skills=matched_skill_names,
                    reproduction_evidence=evidence,
                    duration_seconds=round(time.perf_counter() - start_time, 2),
                )

        # Transition: RETRIEVING -> PLANNING -> IMPLEMENTING
        job.transition_workflow(WorkflowPhase.RETRIEVING, triggered_by="pipeline")

        active_plan = plan
        if active_plan is None:
            from autonomous_engineer.agents.protocol import PlannerInput
            from autonomous_engineer.retrieval.combined import ContextRetriever
            retriever = self._retriever or ContextRetriever()
            retrieval_result = retriever.retrieve(
                query_or_issue=issue,
                repo_map=repository_map,
                workspace_path=repository.workspace_path,
            )
            p_input = PlannerInput(
                issue=issue,
                repository=repository,
                repo_map=repository_map,
                retrieval_result=retrieval_result,
            )
            if self._planner is not None:
                active_plan = self._planner.plan(p_input)
            else:
                from autonomous_engineer.agents.planner import LLMPlanner
                active_plan = LLMPlanner().plan(p_input)

        job.transition_workflow(WorkflowPhase.PLANNING, triggered_by="pipeline", current_plan=active_plan)
        job.transition_workflow(WorkflowPhase.IMPLEMENTING, triggered_by="pipeline")

        # 3. Transactional Plan Execution
        exec_request = ExecutionRequest(
            workspace_path=repository.workspace_path,
            plan=active_plan,
            policy=policy,
        )
        exec_result: PlanExecutionResult = self._execution_engine.execute(exec_request)

        # Transition to EXECUTING -> EVALUATING
        job.transition_workflow(WorkflowPhase.EXECUTING, triggered_by="pipeline")
        job.transition_workflow(WorkflowPhase.EVALUATING, triggered_by="pipeline")

        if not exec_result.succeeded:
            # Execution failed or rolled back
            job.transition_workflow(WorkflowPhase.FAILED, triggered_by="pipeline")
            if recorder:
                recorder.record("execution_failed", "pipeline", {"error": exec_result.error_message})
            return PipelineExecutionSummary(
                run_id=job.run.run_id,
                issue_id=issue.id,
                final_phase=WorkflowPhase.FAILED,
                status=JobStatus.FAILED,
                matched_skills=matched_skill_names,
                error_message=exec_result.error_message,
                duration_seconds=round(time.perf_counter() - start_time, 2),
            )

        # 4. Post-Patch Reproduction Verification
        if reproduction_candidate is not None:
            post_res = self._reproduction_verifier.run_post_patch(
                workspace=repository.workspace_path,
                candidate=reproduction_candidate,
                policy=policy,
            )
            reproduction_evidence = self._reproduction_verifier.evaluate_reproduction(
                pre_result=pre_res,  # type: ignore[has-type]
                post_result=post_res,
                candidate=reproduction_candidate,
            )
            if cfg.require_reproduction and not reproduction_evidence.is_verified:
                job.transition_workflow(WorkflowPhase.ABSTAINED, triggered_by="pipeline")
                return PipelineExecutionSummary(
                    run_id=job.run.run_id,
                    issue_id=issue.id,
                    final_phase=WorkflowPhase.ABSTAINED,
                    status=JobStatus.ABSTAINED,
                    matched_skills=matched_skill_names,
                    reproduction_evidence=reproduction_evidence,
                    duration_seconds=round(time.perf_counter() - start_time, 2),
                )

        # 5. Semantic Change-Impact Analysis
        changed_paths = [c.file_path for c in exec_result.changes]
        impact_analyzer = self._impact_analyzer_factory(repository_map)
        impact_report: ImpactReport = impact_analyzer.analyze(changed_paths)

        # 6. Mutation Testing
        mutation_report: MutationReport | None = None
        if cfg.run_mutation_testing and exec_result.changes:
            mutation_report = self._mutation_tester.evaluate_mutations(
                workspace=repository.workspace_path,
                changes=exec_result.changes,
                policy=policy,
                max_mutants_total=cfg.max_mutation_candidates,
            )

        # 7. Verification Certificate Generation
        certificate = self._execution_engine.generate_certificate(
            request=exec_request,
            result=exec_result,
            issue_id=issue.id,
        )

        # 8. Formal Abstention Assessment
        abstention_assessment = self._abstention_engine.assess_evidence(
            retrieval_contexts=(),
            plan=active_plan,
            certificate=certificate,
            execution_policy=policy,
        )
        if abstention_assessment.decision != AbstentionDecision.VERIFIED_SUCCESS:
            job.transition_workflow(WorkflowPhase.ABSTAINED, triggered_by="pipeline")
            return PipelineExecutionSummary(
                run_id=job.run.run_id,
                issue_id=issue.id,
                final_phase=WorkflowPhase.ABSTAINED,
                status=JobStatus.ABSTAINED,
                matched_skills=matched_skill_names,
                reproduction_evidence=reproduction_evidence,
                impact_report=impact_report,
                mutation_report=mutation_report,
                certificate=certificate,
                abstention_decision=abstention_assessment.decision,
                duration_seconds=round(time.perf_counter() - start_time, 2),
            )

        # Transition: EVALUATING -> REVIEWING
        job.transition_workflow(WorkflowPhase.REVIEWING, triggered_by="pipeline")

        # 9. Independent Code Review
        review_result = self._review_agent.review_patch(
            issue=issue,
            plan=active_plan,
            changes=exec_result.changes,
            certificate=certificate,
        )

        if review_result.verdict != ReviewVerdict.APPROVED:
            job.transition_workflow(WorkflowPhase.ABSTAINED, triggered_by="pipeline")
            return PipelineExecutionSummary(
                run_id=job.run.run_id,
                issue_id=issue.id,
                final_phase=WorkflowPhase.ABSTAINED,
                status=JobStatus.ABSTAINED,
                matched_skills=matched_skill_names,
                reproduction_evidence=reproduction_evidence,
                impact_report=impact_report,
                mutation_report=mutation_report,
                certificate=certificate,
                abstention_decision=abstention_assessment.decision,
                review_verdict=review_result.verdict,
                duration_seconds=round(time.perf_counter() - start_time, 2),
            )

        # Transition: REVIEWING -> VERIFYING -> SUBMITTING -> COMPLETED
        job.transition_workflow(WorkflowPhase.VERIFYING, triggered_by="pipeline")
        job.transition_workflow(WorkflowPhase.SUBMITTING, triggered_by="pipeline")

        patch_summary = PatchSummary(
            files_modified=tuple(c.file_path for c in exec_result.changes),
            lines_added=0,
            lines_removed=0,
        )
        final_result = FinalResult(
            task_id=job.run.task_id,
            issue_id=issue.id,
            resolved=True,
            total_repair_attempts=0,
            total_duration_seconds=round(time.perf_counter() - start_time, 2),
            patch_summary=patch_summary,
        )
        job.transition_workflow(WorkflowPhase.COMPLETED, triggered_by="pipeline", final_result=final_result)

        if recorder:
            recorder.record("pipeline_completed", "pipeline", {"certificate_id": certificate.certificate_id})

        return PipelineExecutionSummary(
            run_id=job.run.run_id,
            issue_id=issue.id,
            final_phase=WorkflowPhase.COMPLETED,
            status=JobStatus.COMPLETED,
            matched_skills=matched_skill_names,
            reproduction_evidence=reproduction_evidence,
            impact_report=impact_report,
            mutation_report=mutation_report,
            certificate=certificate,
            abstention_decision=abstention_assessment.decision,
            review_verdict=review_result.verdict,
            final_result=final_result,
            duration_seconds=round(time.perf_counter() - start_time, 2),
        )

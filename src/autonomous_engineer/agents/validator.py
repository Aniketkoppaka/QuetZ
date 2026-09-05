"""
agents/validator.py -- Plan validation and hallucination detection engine.

Validates ImplementationPlan instances against PlannerInput to ensure:
1. Direct Acyclic Graph (DAG) dependency integrity and no cycles.
2. Step ID uniqueness and non-empty action definitions.
3. Path safety and canonical repo-relative POSIX formatting.
4. Hallucination prevention: verifies all target files and symbols exist in RepositoryMap.
5. Evidence grounding: validates provenance links against RetrievalResult and RepositoryMap.
"""
from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from autonomous_engineer.agents.protocol import PlannerInput
from autonomous_engineer.execution.file_editor import _resolve_edit
from autonomous_engineer.domain.models import (
    EvidenceSource,
    ImplementationPlan,
    ImplementationStep,
    PythonModuleMap,
    RepositoryMap,
    RetrievalResult,
    StepOperation,
)


class PlanValidationError(BaseModel):
    """Structured record of a single plan validation violation."""

    model_config = ConfigDict(frozen=True)

    step_id: str | None = Field(default=None, description="Step ID where violation occurred, if step-specific")
    field: str = Field(description="Field name associated with error")
    error_type: str = Field(description="Machine-readable error type identifier")
    message: str = Field(description="Human-readable explanation of the validation error")


class PlanValidationResult(BaseModel):
    """Aggregated result of a plan validation inspection."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool = Field(description="True if plan satisfies all planning invariants")
    errors: tuple[PlanValidationError, ...] = Field(
        default=(),
        description="List of validation errors preventing plan acceptance",
    )
    warnings: tuple[str, ...] = Field(
        default=(),
        description="Non-fatal warnings regarding the plan",
    )


class PlanValidator:
    """Validates ImplementationPlan instances against PlannerInput contracts."""

    def validate(
        self,
        plan: ImplementationPlan,
        planner_input: PlannerInput,
    ) -> PlanValidationResult:
        """
        Perform comprehensive deterministic validation on an ImplementationPlan.

        Args:
            plan: The ImplementationPlan to validate.
            planner_input: The PlannerInput contract grounding the plan.

        Returns:
            PlanValidationResult with all detected violations.
        """
        errors: list[PlanValidationError] = []
        warnings: list[str] = []

        # 1. Basic Plan Requirements
        if not plan.summary.strip():
            errors.append(
                PlanValidationError(
                    step_id=None,
                    field="summary",
                    error_type="empty_summary",
                    message="Plan summary cannot be empty.",
                )
            )

        if not plan.rationale.strip():
            errors.append(
                PlanValidationError(
                    step_id=None,
                    field="rationale",
                    error_type="empty_rationale",
                    message="Plan rationale cannot be empty.",
                )
            )

        if not plan.steps:
            errors.append(
                PlanValidationError(
                    step_id=None,
                    field="steps",
                    error_type="empty_steps",
                    message="Plan must contain at least one implementation step.",
                )
            )
            return PlanValidationResult(is_valid=False, errors=tuple(errors), warnings=tuple(warnings))

        # 2. Step ID Uniqueness
        seen_step_ids: set[str] = set()
        step_by_id: dict[str, ImplementationStep] = {}

        for step in plan.steps:
            if not step.step_id.strip():
                errors.append(
                    PlanValidationError(
                        step_id=step.step_id,
                        field="step_id",
                        error_type="empty_step_id",
                        message="Step ID cannot be empty.",
                    )
                )
            elif step.step_id in seen_step_ids:
                errors.append(
                    PlanValidationError(
                        step_id=step.step_id,
                        field="step_id",
                        error_type="duplicate_step_id",
                        message=f"Duplicate step ID {step.step_id!r} found in plan.",
                    )
                )
            else:
                seen_step_ids.add(step.step_id)
                step_by_id[step.step_id] = step

        # 3. Dependency Graph & Cycle Detection (DAG validation)
        self._validate_dependencies(plan.steps, seen_step_ids, errors)

        # 4. Repository & Retrieval Indexing for Grounding
        known_files, module_symbols, config_files = self._index_repository(planner_input.repo_map)
        retrieved_paths = {it.file_path for it in planner_input.retrieval_result.items}

        # 5. Step-Level Validation (Paths, Hallucinations, Evidence)
        for step in plan.steps:
            self._validate_step(
                step=step,
                known_files=known_files,
                module_symbols=module_symbols,
                config_files=config_files,
                retrieved_paths=retrieved_paths,
                repo_map=planner_input.repo_map,
                errors=errors,
                warnings=warnings,
            )

        # 6. Pre-Execution Syntactic AST Validation (M17 Intervention)
        workspace_path = (
            planner_input.repository.workspace_path
            if planner_input.repository and planner_input.repository.workspace_path
            else None
        )
        self._validate_python_syntax(plan=plan, workspace_path=workspace_path, errors=errors)

        is_valid = len(errors) == 0
        return PlanValidationResult(
            is_valid=is_valid,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def _validate_dependencies(
        self,
        steps: tuple[ImplementationStep, ...],
        known_step_ids: set[str],
        errors: list[PlanValidationError],
    ) -> None:
        """Validate that step dependencies form a valid Directed Acyclic Graph (DAG)."""
        adj: dict[str, list[str]] = {}

        for step in steps:
            adj[step.step_id] = []
            for dep in step.dependencies:
                if dep == step.step_id:
                    errors.append(
                        PlanValidationError(
                            step_id=step.step_id,
                            field="dependencies",
                            error_type="self_dependency",
                            message=f"Step {step.step_id!r} cannot depend on itself.",
                        )
                    )
                elif dep not in known_step_ids:
                    errors.append(
                        PlanValidationError(
                            step_id=step.step_id,
                            field="dependencies",
                            error_type="unknown_dependency",
                            message=f"Step {step.step_id!r} references unknown dependency {dep!r}.",
                        )
                    )
                else:
                    adj[step.step_id].append(dep)

        # Cycle detection using DFS coloring (0 = unvisited, 1 = visiting, 2 = visited)
        visited: dict[str, int] = {s.step_id: 0 for s in steps}
        path: list[str] = []

        def dfs(node: str) -> bool:
            visited[node] = 1
            path.append(node)
            for neighbor in adj.get(node, []):
                if visited.get(neighbor) == 1:
                    cycle_str = " -> ".join(path + [neighbor])
                    errors.append(
                        PlanValidationError(
                            step_id=node,
                            field="dependencies",
                            error_type="circular_dependency",
                            message=f"Circular dependency detected: {cycle_str}",
                        )
                    )
                    return True
                elif visited.get(neighbor) == 0:
                    if dfs(neighbor):
                        return True
            path.pop()
            visited[node] = 2
            return False

        for step in steps:
            if visited[step.step_id] == 0:
                dfs(step.step_id)

    def _index_repository(
        self, repo_map: RepositoryMap
    ) -> tuple[set[str], dict[str, set[str]], set[str]]:
        """Build fast lookup sets for repository files and symbols."""
        known_files: set[str] = set()
        module_symbols: dict[str, set[str]] = {}
        config_files: set[str] = set(repo_map.configuration_file_paths)

        known_files.update(repo_map.non_python_file_paths)
        known_files.update(repo_map.test_file_paths)
        known_files.update(repo_map.configuration_file_paths)

        for mod in repo_map.python_modules:
            known_files.add(mod.file_path)
            symbols: set[str] = set()

            for func in mod.functions:
                symbols.add(func.name)
                symbols.add(func.qualified_name)

            for cls in mod.classes:
                symbols.add(cls.name)
                symbols.add(cls.qualified_name)
                for m in cls.methods:
                    symbols.add(m.name)
                    symbols.add(m.qualified_name)
                for nest in cls.nested_classes:
                    symbols.add(nest.name)
                    symbols.add(nest.qualified_name)

            module_symbols[mod.file_path] = symbols

        return known_files, module_symbols, config_files

    def _validate_step(
        self,
        step: ImplementationStep,
        known_files: set[str],
        module_symbols: dict[str, set[str]],
        config_files: set[str],
        retrieved_paths: set[str],
        repo_map: RepositoryMap,
        errors: list[PlanValidationError],
        warnings: list[str],
    ) -> None:
        """Validate a single implementation step against grounding and schema rules."""
        # Action description check
        if not step.description.strip():
            errors.append(
                PlanValidationError(
                    step_id=step.step_id,
                    field="description",
                    error_type="empty_description",
                    message=f"Step {step.step_id!r} has an empty description.",
                )
            )

        # Path Safety Checks
        target = step.target_file.strip()
        if not target and step.operation not in (StepOperation.UPDATE_CONFIGURATION,):
            errors.append(
                PlanValidationError(
                    step_id=step.step_id,
                    field="target_file",
                    error_type="empty_target_file",
                    message=f"Step {step.step_id!r} specifies an empty target file path.",
                )
            )
            return

        if "\\" in target:
            errors.append(
                PlanValidationError(
                    step_id=step.step_id,
                    field="target_file",
                    error_type="invalid_path_separators",
                    message=f"Path {target!r} contains backslashes; must use POSIX forward slashes.",
                )
            )

        pure_path = PurePosixPath(target)
        if pure_path.is_absolute():
            errors.append(
                PlanValidationError(
                    step_id=step.step_id,
                    field="target_file",
                    error_type="absolute_path",
                    message=f"Path {target!r} must be repo-relative, not absolute.",
                )
            )

        if ".." in pure_path.parts:
            errors.append(
                PlanValidationError(
                    step_id=step.step_id,
                    field="target_file",
                    error_type="directory_traversal",
                    message=f"Path {target!r} contains directory traversal '..'.",
                )
            )

        # Hallucination Detection: Target File
        is_creating_file = step.operation in (StepOperation.ADD_FILE, StepOperation.ADD_TEST)

        if is_creating_file:
            if target in known_files:
                warnings.append(
                    f"Step {step.step_id!r} uses {step.operation.value} for existing file {target!r}."
                )
        else:
            if target not in known_files:
                errors.append(
                    PlanValidationError(
                        step_id=step.step_id,
                        field="target_file",
                        error_type="hallucinated_file",
                        message=(
                            f"Step {step.step_id!r} references non-existent file {target!r} "
                            f"for operation {step.operation.value!r}."
                        ),
                    )
                )

        # Hallucination Detection: Target Symbol
        if step.target_symbol and target in module_symbols:
            known_syms = module_symbols[target]
            sym = step.target_symbol.strip()
            if (
                step.operation in (StepOperation.MODIFY_SYMBOL, StepOperation.DELETE_SYMBOL)
                and sym not in known_syms
            ):
                errors.append(
                    PlanValidationError(
                        step_id=step.step_id,
                        field="target_symbol",
                        error_type="hallucinated_symbol",
                        message=(
                            f"Step {step.step_id!r} references non-existent symbol {sym!r} "
                            f"in file {target!r}."
                        ),
                    )
                )

        # Evidence Grounding Validation
        if step.evidence is not None:
            ev = step.evidence
            if ev.source == EvidenceSource.RETRIEVED_CONTEXT:
                if ev.reference_path not in retrieved_paths:
                    errors.append(
                        PlanValidationError(
                            step_id=step.step_id,
                            field="evidence",
                            error_type="ungrounded_retrieval_evidence",
                            message=(
                                f"Step {step.step_id!r} claims RETRIEVED_CONTEXT evidence from "
                                f"{ev.reference_path!r}, but it was not present in RetrievalResult."
                            ),
                        )
                    )
            elif ev.source == EvidenceSource.REPOSITORY_MAP:
                if ev.reference_path not in known_files:
                    errors.append(
                        PlanValidationError(
                            step_id=step.step_id,
                            field="evidence",
                            error_type="ungrounded_repository_evidence",
                            message=(
                                f"Step {step.step_id!r} claims REPOSITORY_MAP evidence from "
                                f"{ev.reference_path!r}, but it does not exist in RepositoryMap."
                            ),
                        )
                    )
            elif ev.source == EvidenceSource.UNSUPPORTED:
                errors.append(
                    PlanValidationError(
                        step_id=step.step_id,
                        field="evidence",
                        error_type="unsupported_evidence",
                        message=f"Step {step.step_id!r} is flagged with UNSUPPORTED evidence.",
                    )
                )

    def _validate_python_syntax(
        self,
        plan: ImplementationPlan,
        workspace_path: Path | None,
        errors: list[PlanValidationError],
    ) -> None:
        """
        Validate that model-generated additions and replacements yield syntactically valid Python.
        Simulates edits purely in memory using existing _resolve_edit() semantics without modifying disk.
        """
        # Group steps by target Python file to simulate sequential edits
        file_steps: dict[str, list[ImplementationStep]] = {}
        for step in plan.steps:
            target = step.target_file.strip()
            if target.endswith(".py"):
                file_steps.setdefault(target, []).append(step)

        for rel_path, steps in file_steps.items():
            # In-memory candidate representation
            simulated_text: str | None = None

            for step in steps:
                if step.operation in (StepOperation.ADD_FILE, StepOperation.ADD_TEST):
                    # For new files, step.content represents the complete module
                    simulated_text = step.content if step.content is not None else ""
                    try:
                        ast.parse(simulated_text, filename=rel_path)
                    except SyntaxError as e:
                        errors.append(
                            PlanValidationError(
                                step_id=step.step_id,
                                field="content",
                                error_type="syntax_error",
                                message=(
                                    f"Syntactically invalid Python generated for {rel_path}: "
                                    f"line {e.lineno}, column {e.offset}: {e.msg}. "
                                    f"Text: {e.text.strip() if e.text else ''}"
                                ),
                            )
                        )
                elif step.operation == StepOperation.DELETE_FILE:
                    simulated_text = None
                else:
                    # Modification operations (MODIFY_SYMBOL, REFACTOR_FILE, etc.)
                    if simulated_text is None:
                        # Load starting base text from authentic workspace if available
                        if workspace_path is not None:
                            target_file_path = (workspace_path / rel_path).resolve()
                            if target_file_path.exists():
                                simulated_text = target_file_path.read_text(encoding="utf-8", errors="replace")

                    if simulated_text is not None and step.search_content is not None:
                        replacement = step.replace_content if step.replace_content is not None else ""
                        try:
                            # Apply in-memory hypothetical resolution using existing M15 matcher
                            new_text, _ = _resolve_edit(
                                current_text=simulated_text,
                                search_content=step.search_content,
                                replace_content=replacement,
                                target_symbol=step.target_symbol,
                                step_id=step.step_id,
                                rel_path=rel_path,
                            )
                            # Update in-memory candidate text for subsequent steps on this file
                            simulated_text = new_text

                            # Perform AST validation on the resulting complete Python module
                            ast.parse(simulated_text, filename=rel_path)
                        except SyntaxError as e:
                            errors.append(
                                PlanValidationError(
                                    step_id=step.step_id,
                                    field="replace_content",
                                    error_type="syntax_error",
                                    message=(
                                        f"Syntactically invalid Python generated for {rel_path}: "
                                        f"line {e.lineno}, column {e.offset}: {e.msg}. "
                                        f"Text: {e.text.strip() if e.text else ''}"
                                    ),
                                )
                            )
                        except Exception:
                            # Anchor mismatches or ambiguity are NOT syntax errors;
                            # fail closed at execution time, preserving M16 baseline behavior.
                            pass


import enum


class AbstentionDecision(str, enum.Enum):
    """
    Formal verdict from the evidence-based confidence and abstention engine.
    """

    VERIFIED_SUCCESS = "verified_success"
    LIKELY_SUCCESS = "likely_success"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNVERIFIED_BEHAVIOR = "unverified_behavior"
    UNAUTHORIZED_CHANGE = "unauthorized_change"


class AbstentionAssessment(BaseModel):
    """
    Formal evidence-based assessment result deciding whether to accept a patch or abstain.
    """

    model_config = ConfigDict(frozen=True)

    decision: AbstentionDecision = Field(description="Formal abstention/acceptance verdict")
    should_abstain: bool = Field(description="True if system must formally abstain rather than produce patch")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence score across all evidence dimensions")
    reasons: tuple[str, ...] = Field(default=(), description="Explanations justifying the decision")
    evidence_dimensions: dict[str, float] = Field(
        default_factory=dict,
        description="Individual dimension scores (retrieval_grounding, verification_pass, plan_validity)",
    )


class AbstentionEngine:
    """
    Formal evidence-based confidence and abstention engine.

    Determines whether a proposed solution has sufficient verifiable evidence to be
    accepted, or whether ASE must formally abstain to prevent producing falsely confident patches.
    """

    def __init__(self, confidence_threshold: float = 0.65) -> None:
        self._confidence_threshold = confidence_threshold

    def assess_evidence(
        self,
        planner_input: PlannerInput | None = None,
        plan_validation: PlanValidationResult | None = None,
        verification_passed: bool = False,
        unauthorized_detected: bool = False,
        plan: Any = None,
        certificate: Any = None,
        execution_policy: Any = None,
        **kwargs: Any,
    ) -> AbstentionAssessment:
        """
        Evaluate multi-dimensional evidence and decide whether to proceed or abstain.
        Supports both planner-input based assessment and certificate-based assessment.
        """
        reasons: list[str] = []
        dim_scores: dict[str, float] = {}

        # If called from pipeline with certificate
        if certificate is not None:
            verification_passed = bool(certificate.static_ast_passed and certificate.test_verification_passed)
            unauthorized_detected = bool(certificate.unauthorized_modifications_detected)
            dim_scores["retrieval_grounding"] = 1.0
            dim_scores["plan_validity"] = 1.0 if not certificate.rolled_back else 0.0
            dim_scores["verification_pass"] = 1.0 if verification_passed else 0.0
            dim_scores["authority"] = 0.0 if unauthorized_detected else 1.0
            overall_confidence = float(certificate.confidence_score)
            if unauthorized_detected:
                return AbstentionAssessment(
                    decision=AbstentionDecision.UNAUTHORIZED_CHANGE,
                    should_abstain=True,
                    confidence_score=round(overall_confidence, 2),
                    reasons=("Unauthorized mutations outside plan authority detected.",),
                    evidence_dimensions=dim_scores,
                )
            if not verification_passed:
                return AbstentionAssessment(
                    decision=AbstentionDecision.UNVERIFIED_BEHAVIOR,
                    should_abstain=True,
                    confidence_score=round(overall_confidence, 2),
                    reasons=("Verification checks did not pass cleanly.",),
                    evidence_dimensions=dim_scores,
                )
            if overall_confidence < self._confidence_threshold:
                return AbstentionAssessment(
                    decision=AbstentionDecision.INSUFFICIENT_EVIDENCE,
                    should_abstain=True,
                    confidence_score=round(overall_confidence, 2),
                    reasons=("Certificate confidence below threshold.",),
                    evidence_dimensions=dim_scores,
                )
            decision = (
                AbstentionDecision.VERIFIED_SUCCESS
                if overall_confidence >= 0.85
                else AbstentionDecision.LIKELY_SUCCESS
            )
            return AbstentionAssessment(
                decision=decision,
                should_abstain=False,
                confidence_score=round(overall_confidence, 2),
                reasons=("Verified success certified.",),
                evidence_dimensions=dim_scores,
            )

        # 1. Retrieval & Context Grounding dimension
        retrieval_count = len(planner_input.retrieval_result.items)
        if retrieval_count == 0:
            grounding_score = 0.0
            reasons.append("Zero grounded context retrieved from repository.")
        elif retrieval_count < 2:
            grounding_score = 0.5
            reasons.append("Sparse grounded context retrieved (fewer than 2 files/symbols).")
        else:
            grounding_score = 1.0
        dim_scores["retrieval_grounding"] = grounding_score

        # 2. Plan Validation & DAG integrity dimension
        if plan_validation is not None:
            if not plan_validation.is_valid:
                plan_score = 0.0
                reasons.append(f"Plan validation failed with {len(plan_validation.errors)} errors.")
            elif len(plan_validation.warnings) > 2:
                plan_score = 0.7
                reasons.append("Plan passed validation but generated multiple warnings.")
            else:
                plan_score = 1.0
        else:
            plan_score = 0.5
        dim_scores["plan_validity"] = plan_score

        # 3. Dynamic/Static Verification dimension
        if verification_passed:
            verification_score = 1.0
        else:
            verification_score = 0.0
            reasons.append("Verification checks (AST syntax or dynamic tests) did not pass.")
        dim_scores["verification_pass"] = verification_score

        # 4. Unauthorized modification check
        if unauthorized_detected:
            dim_scores["authority"] = 0.0
            reasons.append("Unauthorized mutations outside plan authority were detected.")
        else:
            dim_scores["authority"] = 1.0

        # Weighted aggregate confidence score
        # 30% Grounding, 25% Plan Validity, 35% Verification, 10% Authority
        overall_confidence = (
            0.30 * dim_scores["retrieval_grounding"]
            + 0.25 * dim_scores["plan_validity"]
            + 0.35 * dim_scores["verification_pass"]
            + 0.10 * dim_scores["authority"]
        )

        if unauthorized_detected:
            return AbstentionAssessment(
                decision=AbstentionDecision.UNAUTHORIZED_CHANGE,
                should_abstain=True,
                confidence_score=round(overall_confidence, 2),
                reasons=tuple(reasons),
                evidence_dimensions=dim_scores,
            )

        if not verification_passed:
            return AbstentionAssessment(
                decision=AbstentionDecision.UNVERIFIED_BEHAVIOR,
                should_abstain=True,
                confidence_score=round(overall_confidence, 2),
                reasons=tuple(reasons),
                evidence_dimensions=dim_scores,
            )

        if overall_confidence < self._confidence_threshold:
            return AbstentionAssessment(
                decision=AbstentionDecision.INSUFFICIENT_EVIDENCE,
                should_abstain=True,
                confidence_score=round(overall_confidence, 2),
                reasons=tuple(reasons),
                evidence_dimensions=dim_scores,
            )

        decision = (
            AbstentionDecision.VERIFIED_SUCCESS
            if overall_confidence >= 0.85
            else AbstentionDecision.LIKELY_SUCCESS
        )

        return AbstentionAssessment(
            decision=decision,
            should_abstain=False,
            confidence_score=round(overall_confidence, 2),
            reasons=tuple(reasons),
            evidence_dimensions=dim_scores,
        )
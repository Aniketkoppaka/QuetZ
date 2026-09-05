"""
agents/prompt_builder.py -- Grounded prompt generation and repair prompt builder.

Constructs structured, constraint-enforcing prompts that ground the LLM planner in:
1. Retrieved code excerpts and match reasons.
2. Verified RepositoryMap files and symbols.
3. Strict evidence provenance requirements (preventing hallucinated facts).
4. Direct Acyclic Graph (DAG) dependency instructions.
"""
from __future__ import annotations

import json
from autonomous_engineer.agents.protocol import PlannerInput
from autonomous_engineer.agents.validator import PlanValidationResult
from autonomous_engineer.domain.models import ImplementationPlan


PLANNER_SYSTEM_PROMPT = r"""You are an expert Autonomous Software Engineer planning agent.
Your sole responsibility is to formulate a structured, step-by-step ImplementationPlan to resolve a software engineering issue.

CRITICAL PLANNING RULES:
1. STRICT GROUNDING & NO HALLUCINATIONS:
   - You may ONLY modify, delete, or refactor files and symbols that exist in the provided Repository Map or Retrieved Context.
   - Do NOT invent or assume the existence of files, modules, classes, or functions that are not explicitly documented in the prompt.
   - For new files, explicitly use the operation 'add_file' or 'add_test'.

2. PROVENANCE & EVIDENCE REQUIREMENTS:
   - Every implementation step must specify an 'evidence' block grounding the step.
   - Allowed evidence sources:
     * 'retrieved_context': For files/symbols present in the retrieved evidence list.
     * 'repository_map': For files/symbols documented in the repository map.
     * 'new_file': For files being created from scratch.
     * 'explicit_assumption': For logical hypotheses where context is incomplete.
   - NEVER claim 'unsupported' evidence.

3. ATOMIC STEPS & DAG DEPENDENCIES:
   - Break changes down into atomic, unambiguous steps (e.g. modify method X, add test Y).
   - Assign each step a unique 'step_id' (e.g. 'step-1', 'step-2').
   - Specify 'dependencies' as a list of prerequisite step IDs. Dependencies must form a Directed Acyclic Graph (no circular dependencies, no self-dependencies).

4. UNCERTAINTY & INCOMPLETE CONTEXT:
   - If the retrieved context is insufficient or ambiguous, declare explicit hypotheses in 'assumptions' or known unknowns in 'unresolved_uncertainties'. Do not fabricate certainty.

5. VERBATIM SEARCH ANCHOR PRECISION:
   - When specifying 'search_content' for modification steps, copy the lines EXACTLY as they appear in the retrieved context.
   - Include 2-5 surrounding lines to ensure uniqueness across the file.
   - Separate multiple lines in 'search_content' with '\\n' (e.g. "def divide(a: float, b: float) -> float:\\n    return a / b" or include the docstring if present). Do NOT concatenate multiple lines together without '\\n'.
   - Do NOT edit or invent comments, variable names, or type annotations in 'search_content'.
   - If modifying an existing symbol, always specify 'target_symbol' (e.g. 'ClassName.method_name' or 'function_name') to guarantee anchor disambiguation.

6. CODE SYNTAX & INDENTATION INTEGRITY:
   - Every replacement block ('replace_content') or new file ('content') must be syntactically valid Python when inserted into the file.
   - PRESERVE MULTI-LINE INDENTATION WITH '\n': In JSON strings, use '\\n' between separate statements and include exact indentation (e.g. 4 spaces, 8 spaces). Do NOT collapse statements onto a single line without newlines.
   - If replacing within an indented block or function, indent each line in 'replace_content' to match the surrounding block.

7. EXAMPLE STEP FORMAT:
   {
     "step_id": "step-1",
     "target_file": "math_ops.py",
     "operation": "modify_symbol",
     "target_symbol": "divide",
     "search_content": "    return a / b",
     "replace_content": "    if b == 0:\n        return 0.0\n    return a / b",
     "description": "Handle zero division by returning 0.0",
     "evidence": {
       "source": "retrieved_context",
       "reference_path": "math_ops.py"
     }
   }

8. OUTPUT FORMAT:
   - You must output valid, strictly conforming JSON matching the ImplementationPlan schema.
   - Do NOT include markdown commentary or code blocks outside the JSON payload.
"""


def compact_diagnostic(err: PlanValidationError) -> str:
    """
    Deterministically transform a verbose PlanValidationError into a compact representation.

    Preserves essential information:
    - step ID (if present)
    - error type
    - affected field
    - location info (file, line, column)
    - substantive error message
    Normalizes multi-line whitespace into single-line format while preserving all substantive tokens.
    """
    msg = err.message.strip()
    # Collapse multi-line whitespace into single line
    msg_single_line = " ".join(msg.split())

    step_part = f" [Step: {err.step_id}]" if err.step_id else ""
    return f"[{err.error_type}]{step_part} (Field: {err.field}): {msg_single_line}"


def compact_plan_representation(invalid_plan_str: str, max_chars: int = 1200) -> str:
    """
    Deterministically produce a compact structural representation of the previous rejected plan.

    Extracts high-level summary, affected files, and step outlines (id, operation, target_file)
    while eliding massive duplicate file contents / replace contents that consume thousands of tokens.
    Falls back to bounded head-truncation if invalid_plan_str cannot be parsed as JSON.
    """
    cleaned = invalid_plan_str.strip()
    if not cleaned:
        return "(empty plan)"

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            summary = data.get("summary", "")
            steps = data.get("steps", [])
            step_summaries: list[str] = []
            if isinstance(steps, list):
                for s in steps:
                    if isinstance(s, dict):
                        sid = s.get("step_id", "unknown")
                        op = s.get("operation", "unknown")
                        target = s.get("target_file", "")
                        step_summaries.append(f"  - {sid}: {op} -> {target}")
                    else:
                        step_summaries.append(f"  - {str(s)[:60]}")

            lines = [
                "Compact Structure of Rejected Plan:",
                f"Summary: {summary}",
                f"Steps Count: {len(steps)}",
            ]
            if step_summaries:
                lines.append("Step Outlines:")
                lines.extend(step_summaries)
            return "\n".join(lines)
    except Exception:
        pass

    # Non-JSON or truncated JSON: provide bounded excerpt
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars] + f"\n... [truncated {len(cleaned) - max_chars} chars of rejected raw output] ..."


class PlannerPromptBuilder:
    """Constructs grounded system, user, and repair prompts for planning agents."""

    def __init__(self, system_prompt: str = PLANNER_SYSTEM_PROMPT) -> None:
        self._system_prompt = system_prompt

    def build_system_prompt(self) -> str:
        """Return the core system prompt enforcing planning constraints."""
        schema_json = json.dumps(ImplementationPlan.model_json_schema(), indent=2)
        return f"{self._system_prompt}\n\nREQUIRED JSON SCHEMA:\n{schema_json}"

    def build_user_prompt(self, planner_input: PlannerInput) -> str:
        """
        Build the full context prompt grounding the planner in issue and repository facts.
        """
        sections: list[str] = []

        # 1. Issue Specification
        issue = planner_input.issue
        sections.append(
            f"=== ISSUE DESCRIPTION ===\n"
            f"Issue ID: {issue.id}\n"
            f"Title: {issue.title}\n\n"
            f"Description:\n{issue.body or '(No description provided)'}"
        )

        # 2. Historical Repository Grounding
        repo_map = planner_input.repo_map
        sections.append(
            f"=== HISTORICAL REPOSITORY GROUNDING (CHECKED-OUT PARENT COMMIT) ===\n"
            f"Repository: {planner_input.repository.url}\n"
            f"Checked-Out Commit SHA: {planner_input.repository.commit_sha}\n"
            f"Parent Workspace Tree: {repo_map.file_count} total files ({repo_map.python_file_count} Python source files)\n"
            f"Discovered Test Files in Parent Tree: {', '.join(repo_map.test_file_paths) or 'None'}\n"
            f"Discovered Configuration Files in Parent Tree: {', '.join(repo_map.configuration_file_paths) or 'None'}"
        )

        # 3. Structural Module Index
        if repo_map.python_modules:
            mod_lines = ["=== REPOSITORY PYTHON MODULES & KNOWN SYMBOLS ==="]
            for mod in repo_map.python_modules[:15]:  # Bounded module preview
                classes = [c.name for c in mod.classes]
                funcs = [f.name for f in mod.functions]
                symbols_desc = []
                if classes:
                    symbols_desc.append(f"Classes: {', '.join(classes)}")
                if funcs:
                    symbols_desc.append(f"Functions: {', '.join(funcs)}")
                desc_str = f" ({'; '.join(symbols_desc)})" if symbols_desc else ""
                mod_lines.append(f"- {mod.file_path}{desc_str}")
            sections.append("\n".join(mod_lines))

        # 4. Retrieved Grounded Context
        retrieval = planner_input.retrieval_result
        if retrieval.items:
            ret_lines = [
                f"=== RETRIEVED GROUNDED EVIDENCE (Ranked by Relevance) ===\n"
                f"Query Evaluated: {retrieval.query}\n"
            ]
            for idx, item in enumerate(retrieval.items, start=1):
                reasons_str = "; ".join(r.description for r in item.reasons) if item.reasons else "Score match"
                sym_str = f" | Symbol: {item.symbol_name}" if item.symbol_name else ""
                line_str = f" (Lines {item.start_line}-{item.end_line})" if item.start_line else ""
                ret_lines.append(
                    f"[{idx}] File: {item.file_path}{sym_str}{line_str} [Score: {item.score:.2f}]\n"
                    f"    Relevance: {reasons_str}"
                )
                if item.content:
                    ret_lines.append(f"    Excerpt:\n```python\n{item.content}\n```")
            sections.append("\n".join(ret_lines))
        else:
            sections.append("=== RETRIEVED GROUNDED EVIDENCE ===\n(No high-confidence context items retrieved)")

        # 5. Repair / Attempt History
        if planner_input.attempt_number > 1 or planner_input.previous_failure:
            repair_lines = [f"=== REPAIR CONTEXT (Iteration {planner_input.attempt_number}) ==="]
            if planner_input.previous_failure:
                repair_lines.append(
                    f"Previous Failure Category: {planner_input.previous_failure.category.value}\n"
                    f"Failure Reason: {planner_input.previous_failure.reason}\n"
                    f"Failure Details:\n{planner_input.previous_failure.message}"
                )
            if planner_input.previous_plan:
                repair_lines.append(
                    f"Previous Plan Summary: {planner_input.previous_plan.summary}\n"
                    f"Previous Affected Files: {', '.join(planner_input.previous_plan.affected_files)}"
                )
            sections.append("\n".join(repair_lines))

        sections.append(
            "Formulate a complete, grounded, atomic ImplementationPlan JSON object addressing this issue."
        )

        return "\n\n".join(sections)

    def build_repair_prompt(
        self,
        invalid_plan_str: str,
        validation_result: PlanValidationResult,
    ) -> str:
        """
        Build a focused repair prompt detailing exact validation errors to correct.
        Uses deterministic diagnostic context compaction (M18) for errors while
        preserving the previous rejected plan JSON payload as working-memory scaffold (M19).
        """
        error_lines = [
            "Your previous implementation plan was REJECTED by the PlanValidator.",
            "You must produce a revised, corrected ImplementationPlan JSON object that resolves all errors below:\n",
            "=== VALIDATION ERRORS DETECTED ===",
        ]

        for idx, err in enumerate(validation_result.errors, start=1):
            compact_err = compact_diagnostic(err)
            error_lines.append(f"{idx}. {compact_err}")

        if validation_result.warnings:
            error_lines.append("\n=== WARNINGS ===")
            for warn in validation_result.warnings:
                clean_warn = " ".join(warn.strip().split())
                error_lines.append(f"- {clean_warn}")

        error_lines.append("\n=== PREVIOUS REJECTED PLAN (JSON PAYLOAD) ===")
        error_lines.append(invalid_plan_str.strip())
        error_lines.append(
            "\nProduce a revised, strictly valid ImplementationPlan JSON object that resolves every error listed above."
        )
        has_syntax_err = any(e.error_type == "syntax_error" for e in validation_result.errors)
        if has_syntax_err:
            error_lines.append(
                "CRITICAL INDENTATION FIX: If you had a syntax_error, ensure statements in 'replace_content' or 'content' are separated by newline characters (\\n) and indented with spaces to form valid Python. Do NOT collapse statements into a single line."
            )

        return "\n".join(error_lines)
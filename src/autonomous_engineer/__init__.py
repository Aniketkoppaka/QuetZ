"""
autonomous_engineer -- Autonomous Software Engineering Agent.

This package is the top-level namespace for the autonomous-software-engineer
project.  It resolves GitHub issues end-to-end: understanding the repository,
planning and implementing changes, executing tests in a sandboxed environment,
and producing a verified patch or pull request.

Status: Milestone 7 -- domain model, workflow state machine, repository acquisition, AST mapping, context retrieval, grounded LLM planning, plan validation, atomic implementation execution, multi-tier verification, automatic rollback, real-world benchmark dataset, and end-to-end evaluation harness implemented.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
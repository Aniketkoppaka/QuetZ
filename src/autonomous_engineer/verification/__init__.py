"""
verification -- Advanced verification and confidence evidence generation for ASE.

Includes:
  - ReproductionVerifier: Reproduction-before-fix (Fail-then-pass) test verification.
"""
from __future__ import annotations

from autonomous_engineer.verification.mutation import (
    AstMutantGenerator,
    MutantDefinition,
    MutantStatus,
    MutantTestResult,
    MutationOperatorType,
    MutationReport,
    MutationTester,
)
from autonomous_engineer.verification.reproduction import (
    ReproductionCandidate,
    ReproductionEvidence,
    ReproductionStatus,
    ReproductionVerifier,
)

__all__ = [
    "AstMutantGenerator",
    "MutantDefinition",
    "MutantStatus",
    "MutantTestResult",
    "MutationOperatorType",
    "MutationReport",
    "MutationTester",
    "ReproductionCandidate",
    "ReproductionEvidence",
    "ReproductionStatus",
    "ReproductionVerifier",
]

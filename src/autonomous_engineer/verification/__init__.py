"""
verification -- Advanced verification and confidence evidence generation for ASE.

Includes:
  - ReproductionVerifier: Reproduction-before-fix (Fail-then-pass) test verification.
  - AstMutantGenerator & MutationTester: AST mutation-based test assertion strength.
  - ASTSecurityScanner & SecurityScanReport: In-pipeline SAST vulnerability detection.
  - LicenseScanner & LicenseScanReport: Supply-chain dependency and copyleft license scanner.
"""
from __future__ import annotations

from autonomous_engineer.verification.license_scan import (
    DependencyFinding,
    LicenseCategory,
    LicenseScanReport,
    LicenseScanner,
)
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
from autonomous_engineer.verification.security_scan import (
    ASTSecurityScanner,
    SecurityFinding,
    SecurityScanReport,
    SecuritySeverity,
)
from autonomous_engineer.verification.signing import (
    CertificateSigner,
    SignedCertificateEnvelope,
)

__all__ = [
    "ASTSecurityScanner",
    "AstMutantGenerator",
    "CertificateSigner",
    "DependencyFinding",
    "LicenseCategory",
    "LicenseScanReport",
    "LicenseScanner",
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
    "SecurityFinding",
    "SecurityScanReport",
    "SecuritySeverity",
    "SignedCertificateEnvelope",
]
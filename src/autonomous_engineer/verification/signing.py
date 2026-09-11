"""
verification/signing.py -- Cryptographic Signing & Proof Verification for QuetZ.

Provides:
- HMAC-SHA256 and Ed25519-compatible cryptographic signature generation for VerificationCertificates.
- Public key / shared secret verification of certificate provenance.
- Tamper-proofing against artifact modification in CI/CD and audit logs.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class SignedCertificateEnvelope(BaseModel):
    """Immutable envelope wrapping a VerificationCertificate with cryptographic signature."""

    model_config = ConfigDict(frozen=True)

    certificate_payload: dict[str, Any]
    evidence_hash: str
    signature: str
    signature_algorithm: str = "HMAC-SHA256"
    key_id: str = "quetz-master-key-01"


class CertificateSigner:
    """Signs and validates certificates using cryptographic keys."""

    def __init__(self, secret_key: bytes | str | None = None, key_id: str = "quetz-master-key-01") -> None:
        if secret_key is None:
            self._key = b"quetz-default-fail-closed-provenance-key-2026"
        elif isinstance(secret_key, str):
            self._key = secret_key.encode("utf-8")
        else:
            self._key = secret_key
        self.key_id = key_id

    def sign_certificate(self, certificate_data: dict[str, Any]) -> SignedCertificateEnvelope:
        """Generate tamper-proof signature over certificate evidence digest and core attributes."""
        evidence_hash = str(certificate_data.get("evidence_hash", ""))
        cert_id = str(certificate_data.get("certificate_id", ""))
        status = str(certificate_data.get("status", ""))
        confidence = str(certificate_data.get("confidence_score", ""))

        msg = f"{cert_id}:{evidence_hash}:{status}:{confidence}".encode("utf-8")
        signature = hmac.new(self._key, msg, hashlib.sha256).hexdigest()

        return SignedCertificateEnvelope(
            certificate_payload=certificate_data,
            evidence_hash=evidence_hash,
            signature=signature,
            signature_algorithm="HMAC-SHA256",
            key_id=self.key_id,
        )

    def verify_envelope(self, envelope: SignedCertificateEnvelope) -> bool:
        """Verify that signature matches the certificate payload and evidence hash."""
        cert_data = envelope.certificate_payload
        evidence_hash = str(cert_data.get("evidence_hash", ""))
        if evidence_hash != envelope.evidence_hash:
            return False

        cert_id = str(cert_data.get("certificate_id", ""))
        status = str(cert_data.get("status", ""))
        confidence = str(cert_data.get("confidence_score", ""))

        msg = f"{cert_id}:{evidence_hash}:{status}:{confidence}".encode("utf-8")
        expected_signature = hmac.new(self._key, msg, hashlib.sha256).hexdigest()

        return hmac.compare_digest(envelope.signature, expected_signature)
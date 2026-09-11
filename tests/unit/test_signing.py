"""
Unit tests for cryptographic certificate signing and verification in verification/signing.py.
"""
import json
from autonomous_engineer.cli import main
from autonomous_engineer.verification.signing import CertificateSigner, SignedCertificateEnvelope


def test_certificate_signing_and_verification_roundtrip():
    cert_data = {
        "certificate_id": "cert-12345",
        "evidence_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "status": "COMPLETED",
        "confidence_score": 0.98,
        "static_ast_passed": True,
        "test_verification_passed": True,
    }

    signer = CertificateSigner(secret_key=b"secret-passphrase-test")
    envelope = signer.sign_certificate(cert_data)

    assert envelope.evidence_hash == cert_data["evidence_hash"]
    assert len(envelope.signature) == 64
    assert signer.verify_envelope(envelope) is True


def test_signature_fails_on_payload_tampering():
    cert_data = {
        "certificate_id": "cert-tamper",
        "evidence_hash": "aaaabbbbcccc111122223333",
        "status": "COMPLETED",
        "confidence_score": 0.95,
    }

    signer = CertificateSigner(secret_key=b"test-key")
    envelope = signer.sign_certificate(cert_data)

    # Tamper with confidence score
    tampered_data = dict(envelope.certificate_payload)
    tampered_data["confidence_score"] = 0.99
    tampered_envelope = SignedCertificateEnvelope(
        certificate_payload=tampered_data,
        evidence_hash=envelope.evidence_hash,
        signature=envelope.signature,
    )

    assert signer.verify_envelope(tampered_envelope) is False


def test_cli_sign_and_verify_commands(tmp_path, capsys):
    cert_file = tmp_path / "cert.json"
    cert_data = {
        "certificate_id": "cert-cli-test",
        "evidence_hash": "111122223333444455556666",
        "status": "COMPLETED",
        "confidence_score": 0.96,
    }
    cert_file.write_text(json.dumps(cert_data), encoding="utf-8")

    env_file = tmp_path / "cert.signed.json"

    # 1. Sign CLI
    exit_code_sign = main(["sign-cert", str(cert_file), "--output", str(env_file), "--key", "my-test-key"])
    assert exit_code_sign == 0
    assert env_file.exists()

    # 2. Verify CLI
    exit_code_verify = main(["verify-cert", str(env_file), "--key", "my-test-key"])
    captured = capsys.readouterr()
    assert exit_code_verify == 0
    assert "✓ CRYPTOGRAPHIC VERIFICATION SUCCESSFUL" in captured.out

    # 3. Verify CLI with wrong key
    exit_code_wrong = main(["verify-cert", str(env_file), "--key", "wrong-key"])
    assert exit_code_wrong == 1
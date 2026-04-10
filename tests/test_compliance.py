"""
Brain_Scape — Compliance Layer Tests

Tests for RBAC, encryption, audit logging, and consent management.
"""

import pytest
from compliance.rbac import RBACManager, PERMISSIONS
from compliance.encryption import EncryptionManager
from compliance.audit_logger import AuditLogger
from compliance.consent_manager import ConsentManager


class TestRBAC:
    """Test role-based access control."""

    def setup_method(self):
        self.rbac = RBACManager(secret_key="test-secret-key-for-testing-only")

    def test_create_access_token(self):
        """Should create a valid JWT access token."""
        token = self.rbac.create_access_token(
            user_id="user-123", role="clinician", institution="inst-456"
        )
        assert token is not None
        assert isinstance(token, str)

    def test_validate_valid_token(self):
        """Should validate a token that was just created."""
        token = self.rbac.create_access_token(
            user_id="user-123", role="clinician"
        )
        payload = self.rbac.validate_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["role"] == "clinician"

    def test_validate_expired_token(self):
        """Should reject expired tokens."""
        # Create a token that expires immediately
        rbac = RBACManager(secret_key="test-key", access_token_expire_minutes=-1)
        token = rbac.create_access_token(user_id="user-123", role="clinician")
        payload = rbac.validate_token(token)
        assert payload is None

    def test_validate_invalid_token(self):
        """Should reject invalid tokens."""
        payload = self.rbac.validate_token("invalid-token")
        assert payload is None

    def test_clinician_permissions(self):
        """Clinicians should have broad access."""
        allowed, reason = self.rbac.check_permission("clinician", "GET /mesh/{scan_id}")
        assert allowed

        allowed, reason = self.rbac.check_permission("clinician", "POST /annotate")
        assert allowed

    def test_researcher_permissions(self):
        """Researchers should have limited access."""
        allowed, reason = self.rbac.check_permission("researcher", "GET /mesh/{scan_id}")
        assert allowed  # Anonymized access

        allowed, reason = self.rbac.check_permission("researcher", "POST /annotate")
        assert not allowed  # No annotation access

    def test_patient_permissions(self):
        """Patients should have restricted access."""
        allowed, reason = self.rbac.check_permission("patient", "GET /mesh/{scan_id}")
        assert allowed  # Own scans only (scope checked separately)

        allowed, reason = self.rbac.check_permission("patient", "POST /annotate")
        assert not allowed

    def test_unknown_role(self):
        """Unknown roles should have no permissions."""
        allowed, reason = self.rbac.check_permission("admin", "GET /mesh/{scan_id}")
        assert not allowed

    def test_endpoint_matching(self):
        """Endpoint pattern matching should work with path parameters."""
        assert RBACManager._endpoint_matches("GET /mesh/{scan_id}", "GET /mesh/abc-123")
        assert not RBACManager._endpoint_matches("GET /mesh/{scan_id}", "GET /report/abc-123")


class TestEncryption:
    """Test encryption at rest."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypting and decrypting should return original data."""
        manager = EncryptionManager(encryption_key="test-encryption-key-for-testing")
        plaintext = b"This is sensitive patient data that must be encrypted."

        ciphertext = manager.encrypt(plaintext)
        assert ciphertext != plaintext

        decrypted = manager.decrypt(ciphertext)
        assert decrypted == plaintext

    def test_different_keys_produce_different_ciphertext(self):
        """Different encryption keys should produce different ciphertext."""
        manager1 = EncryptionManager(encryption_key="key-one")
        manager2 = EncryptionManager(encryption_key="key-two")

        plaintext = b"Same data, different keys"
        cipher1 = manager1.encrypt(plaintext)
        cipher2 = manager2.encrypt(plaintext)

        assert cipher1 != cipher2

    def test_generate_key(self):
        """Generated keys should be unique and valid."""
        key1 = EncryptionManager.generate_key()
        key2 = EncryptionManager.generate_key()

        assert key1 != key2
        assert isinstance(key1, str)
        assert len(key1) > 0


class TestAuditLogger:
    """Test append-only audit logging."""

    def test_log_event(self, tmp_path):
        """Should log an audit event."""
        logger = AuditLogger(storage="file", log_dir=str(tmp_path))

        event = logger.log(
            user_id="user-123",
            role="clinician",
            action="GET /report/scan-456",
            resource_id="scan-456",
            outcome="ALLOWED",
        )

        assert event["user_id"] == "user-123"
        assert event["role"] == "clinician"
        assert event["action"] == "GET /report/scan-456"
        assert event["outcome"] == "ALLOWED"

    def test_log_denied_access(self, tmp_path):
        """Should log denied access attempts."""
        logger = AuditLogger(storage="file", log_dir=str(tmp_path))

        event = logger.log(
            user_id="user-789",
            role="patient",
            action="POST /annotate",
            outcome="DENIED",
        )

        assert event["outcome"] == "DENIED"

    def test_query_logs(self, tmp_path):
        """Should be able to query audit logs."""
        logger = AuditLogger(storage="file", log_dir=str(tmp_path))

        logger.log(user_id="user-1", role="clinician", action="GET /mesh/scan-1", outcome="ALLOWED")
        logger.log(user_id="user-2", role="patient", action="POST /annotate", outcome="DENIED")

        # Query by user
        results = logger.query(user_id="user-1")
        assert len(results) == 1

        # Query by outcome
        results = logger.query(outcome="DENIED")
        assert len(results) == 1


class TestConsentManager:
    """Test consent management."""

    def setup_method(self):
        self.consent = ConsentManager(
            storage="file",
            storage_path="/tmp/brainscape_test_consent",
        )

    def test_grant_consent(self):
        """Should grant consent for a feature."""
        result = self.consent.grant_consent(
            patient_id="patient-1",
            feature="longitudinal_analysis",
            granted_by="patient-1",
        )
        assert result["status"] == "granted"
        assert result["feature"] == "longitudinal_analysis"

    def test_revoke_consent(self):
        """Should revoke consent for a feature."""
        self.consent.grant_consent("patient-2", "research_contribution", "patient-2")
        result = self.consent.revoke_consent(
            patient_id="patient-2",
            feature="research_contribution",
            revoked_by="patient-2",
        )
        assert result["status"] == "revoked"

    def test_check_consent_opt_in(self):
        """Opt-in features should require explicit consent."""
        # Without consent
        assert not self.consent.check_consent("patient-new", "research_contribution")

        # With consent
        self.consent.grant_consent("patient-new", "research_contribution", "patient-new")
        assert self.consent.check_consent("patient-new", "research_contribution")

    def test_check_consent_opt_out(self):
        """Opt-out features should be allowed by default."""
        assert self.consent.check_consent("patient-3", "data_sharing")

    def test_require_consent_raises(self):
        """require_consent should raise PermissionError if not granted."""
        with pytest.raises(PermissionError):
            self.consent.require_consent("patient-4", "longitudinal_analysis")

    def test_unknown_feature(self):
        """Should raise ValueError for unknown features."""
        with pytest.raises(ValueError):
            self.consent.grant_consent("patient-5", "nonexistent_feature", "patient-5")
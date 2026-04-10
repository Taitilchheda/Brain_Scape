"""
Brain_Scape — Consent Manager

Tracks patient consent decisions. Certain features (longitudinal analysis,
research contribution) require explicit consent. The system enforces this
programmatically, not just as a policy document.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from compliance.audit_logger import AuditLogger


class ConsentManager:
    """
    Manages patient consent for data processing features.

    Enforces that certain pipeline features require explicit consent
    before they can be used with a patient's data.
    """

    # Features that require explicit consent
    CONSENT_REQUIRED_FEATURES = {
        "longitudinal_analysis": {
            "description": "Compare multiple scans over time to track changes",
            "default": False,
        },
        "research_contribution": {
            "description": "Allow anonymized data to contribute to research datasets",
            "default": False,
        },
        "data_sharing": {
            "description": "Share scan results with referred clinicians",
            "default": True,  # Opt-out
        },
        "ai_training": {
            "description": "Allow anonymized data to be used for model improvement",
            "default": False,
        },
    }

    def __init__(
        self,
        storage: str = "file",
        storage_path: str = "data/consent",
        audit_logger: Optional[AuditLogger] = None,
    ):
        self.storage = storage
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.audit = audit_logger or AuditLogger(storage="file")

    def grant_consent(
        self,
        patient_id: str,
        feature: str,
        granted_by: str,
        ip_address: Optional[str] = None,
    ) -> dict:
        """
        Grant consent for a feature.

        Args:
            patient_id: UUID of the patient.
            feature: Feature name (must be in CONSENT_REQUIRED_FEATURES).
            granted_by: UUID of the user granting consent.
            ip_address: Client IP for audit.

        Returns:
            Consent record dict.
        """
        if feature not in self.CONSENT_REQUIRED_FEATURES:
            raise ValueError(f"Unknown feature: {feature}")

        record = {
            "consent_id": str(uuid.uuid4()),
            "patient_id": patient_id,
            "feature": feature,
            "status": "granted",
            "granted_by": granted_by,
            "granted_at": datetime.now(timezone.utc).isoformat(),
            "revoked_at": None,
        }

        self._save_consent(record)

        # Audit log
        self.audit.log(
            user_id=granted_by,
            role="patient",
            action=f"CONSENT_GRANTED:{feature}",
            resource_id=patient_id,
            outcome="ALLOWED",
            ip_address=ip_address,
        )

        return record

    def revoke_consent(
        self,
        patient_id: str,
        feature: str,
        revoked_by: str,
        ip_address: Optional[str] = None,
    ) -> dict:
        """Revoke consent for a feature."""
        if feature not in self.CONSENT_REQUIRED_FEATURES:
            raise ValueError(f"Unknown feature: {feature}")

        record = {
            "consent_id": str(uuid.uuid4()),
            "patient_id": patient_id,
            "feature": feature,
            "status": "revoked",
            "granted_by": None,
            "granted_at": None,
            "revoked_by": revoked_by,
            "revoked_at": datetime.now(timezone.utc).isoformat(),
        }

        self._save_consent(record)

        self.audit.log(
            user_id=revoked_by,
            role="patient",
            action=f"CONSENT_REVOKED:{feature}",
            resource_id=patient_id,
            outcome="ALLOWED",
            ip_address=ip_address,
        )

        return record

    def check_consent(self, patient_id: str, feature: str) -> bool:
        """
        Check if consent has been granted for a feature.

        Args:
            patient_id: UUID of the patient.
            feature: Feature to check.

        Returns:
            True if consent is granted, False otherwise.
        """
        if feature not in self.CONSENT_REQUIRED_FEATURES:
            # Non-consent features are allowed by default
            return True

        # Check for opt-out features (default=True)
        feature_config = self.CONSENT_REQUIRED_FEATURES[feature]
        if feature_config["default"] is True:
            # Opt-out: allowed unless explicitly revoked
            latest = self._get_latest_consent(patient_id, feature)
            if latest and latest["status"] == "revoked":
                return False
            return True
        else:
            # Opt-in: requires explicit grant
            latest = self._get_latest_consent(patient_id, feature)
            if latest and latest["status"] == "granted":
                return True
            return False

    def require_consent(self, patient_id: str, feature: str) -> None:
        """
        Raise an error if consent has not been granted.

        Call this at the start of features that require consent.
        """
        if not self.check_consent(patient_id, feature):
            raise PermissionError(
                f"Consent not granted for feature '{feature}' "
                f"for patient {patient_id}. Consent must be explicitly granted "
                f"before this feature can be used."
            )

    def _save_consent(self, record: dict) -> None:
        """Save a consent record."""
        consent_file = self.storage_path / f"{record['patient_id']}.jsonl"
        with open(consent_file, "a") as f:
            f.write(json.dumps(record) + "\n")

    def _get_latest_consent(
        self, patient_id: str, feature: str
    ) -> Optional[dict]:
        """Get the most recent consent record for a patient/feature."""
        consent_file = self.storage_path / f"{patient_id}.jsonl"

        if not consent_file.exists():
            return None

        latest = None
        with open(consent_file) as f:
            for line in f:
                record = json.loads(line.strip())
                if record.get("feature") == feature:
                    latest = record

        return latest
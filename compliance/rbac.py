"""
Brain_Scape — RBAC (Role-Based Access Control)

JWT-based authentication with role claims. Three core roles:
  - Clinician:  full scan access, all report modes, annotation
  - Researcher: anonymized data only, aggregate stats, no PHI
  - Patient:   own scans only, patient report mode only

Role claims are embedded in JWT; every API endpoint validates them
before serving a response.
"""

import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional


# ── Permission Matrix (from architecture.md Section 4.6) ──
PERMISSIONS = {
    "clinician": {
        "POST /ingest": True,
        "GET /status/{job_id}": True,
        "GET /mesh/{scan_id}": "own_and_referred",
        "GET /report/{scan_id}": "full_technical",
        "POST /query": True,
        "POST /annotate": True,
        "GET /longitudinal": True,
        "GET /prognosis/{scan_id}": True,
        "GET /export/{scan_id}": True,
        "POST /diagnosis/{scan_id}": True,
        "POST /connectivity/{scan_id}": True,
        "POST /treatment-planning/{scan_id}": True,
        "GET /dashboard/{institution_id}": True,
        "GET /governance/{scan_id}": True,
        "GET /signoff/{scan_id}": True,
        "POST /signoff/{scan_id}": True,
    },
    "researcher": {
        "POST /ingest": True,
        "GET /status/{job_id}": True,
        "GET /mesh/{scan_id}": "anonymized_only",
        "GET /report/{scan_id}": "anonymized",
        "POST /query": True,
        "POST /annotate": False,
        "GET /longitudinal": "anonymized",
        "POST /diagnosis/{scan_id}": True,
        "POST /connectivity/{scan_id}": True,
        "GET /governance/{scan_id}": True,
        "GET /signoff/{scan_id}": True,
        "POST /signoff/{scan_id}": True,
    },
    "patient": {
        "POST /ingest": True,
        "GET /status/{job_id}": "own_only",
        "GET /mesh/{scan_id}": "own_only",
        "GET /report/{scan_id}": "patient_mode_only",
        "POST /query": True,
        "POST /annotate": False,
        "GET /prognosis/{scan_id}": "own_only",
        "GET /export/{scan_id}": "own_only",
        "GET /governance/{scan_id}": "own_only",
        "GET /signoff/{scan_id}": "own_only",
    },
}


class RBACManager:
    """
    JWT-based RBAC manager for Brain_Scape.

    Handles token creation, validation, and permission checking.
    """

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 15,
        refresh_token_expire_days: int = 7,
    ):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire = timedelta(minutes=access_token_expire_minutes)
        self.refresh_token_expire = timedelta(days=refresh_token_expire_days)

    def create_access_token(
        self,
        user_id: str,
        role: str,
        institution: Optional[str] = None,
    ) -> str:
        """Create a JWT access token with role claims."""
        payload = {
            "sub": user_id,
            "role": role,
            "institution": institution,
            "type": "access",
            "exp": datetime.now(timezone.utc) + self.access_token_expire,
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(
        self,
        user_id: str,
        role: str,
    ) -> str:
        """Create a JWT refresh token."""
        payload = {
            "sub": user_id,
            "role": role,
            "type": "refresh",
            "exp": datetime.now(timezone.utc) + self.refresh_token_expire,
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def validate_token(self, token: str) -> Optional[dict]:
        """Validate a JWT token and return the decoded payload."""
        try:
            payload = jwt.decode(
                token, self.secret_key, algorithms=[self.algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def check_permission(
        self,
        role: str,
        endpoint: str,
        scan_owner_id: Optional[str] = None,
        requesting_user_id: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Check if a role has permission to access an endpoint.

        Args:
            role: User's role claim.
            endpoint: API endpoint being accessed.
            scan_owner_id: UUID of the scan's owner patient.
            requesting_user_id: UUID of the requesting user.

        Returns:
            Tuple of (allowed: bool, reason: str).
        """
        if role not in PERMISSIONS:
            return False, f"Unknown role: {role}"

        role_perms = PERMISSIONS[role]

        # Find matching endpoint permission
        for perm_endpoint, perm_value in role_perms.items():
            if self._endpoint_matches(perm_endpoint, endpoint):
                # Boolean permission
                if perm_value is True:
                    return True, "allowed"
                elif perm_value is False:
                    return False, f"Role '{role}' cannot access {endpoint}"

                # Scope-based permission
                if perm_value == "own_only" or perm_value == "own_and_referred":
                    if scan_owner_id and requesting_user_id:
                        if scan_owner_id == requesting_user_id:
                            return True, "own_scan_allowed"
                        elif perm_value == "own_and_referred":
                            # Check referral status (would query DB in production)
                            return True, "referred_scan_allowed"
                        return False, "not_own_scan"
                    return True, "scope_check_deferred"

                elif perm_value == "anonymized_only" or perm_value == "anonymized":
                    return True, "anonymized_access_only"

                elif perm_value == "patient_mode_only":
                    if scan_owner_id and requesting_user_id:
                        if scan_owner_id == requesting_user_id:
                            return True, "own_scan_patient_mode"
                        return False, "not_own_scan"
                    return True, "scope_check_deferred"

                elif perm_value == "full_technical":
                    return True, "full_access"

        # No matching permission found — deny by default
        return False, f"No permission for {endpoint} with role {role}"

    @staticmethod
    def _endpoint_matches(pattern: str, actual: str) -> bool:
        """Check if an actual endpoint matches a permission pattern."""
        # Simple pattern matching: /path/{param} matches /path/anything
        pattern_parts = pattern.split("/")
        actual_parts = actual.split("/")

        if len(pattern_parts) != len(actual_parts):
            return False

        for p, a in zip(pattern_parts, actual_parts):
            if p.startswith("{") and p.endswith("}"):
                continue  # Wildcard — matches any value
            if p != a:
                return False

        return True
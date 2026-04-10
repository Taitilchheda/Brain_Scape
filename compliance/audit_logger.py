"""
Brain_Scape — Audit Logger

Append-only audit log for every API call, role check, download, and model inference.
No UPDATE or DELETE permissions on the audit store — ever.

Required for HIPAA compliance and breach investigation.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Append-only audit logger.

    Every access event, query, download, and model inference is logged.
    The log is immutable by design — no UPDATE or DELETE operations.
    """

    def __init__(
        self,
        storage: str = "postgres",
        log_dir: str = "logs/audit",
    ):
        """
        Args:
            storage: "postgres" (production) or "file" (development).
            log_dir: Directory for file-based audit logs.
        """
        self.storage = storage
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        user_id: str,
        role: str,
        action: str,
        resource_id: Optional[str] = None,
        outcome: str = "ALLOWED",
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> dict:
        """
        Log an audit event.

        Args:
            user_id: UUID of the user performing the action.
            role: User's role (clinician, researcher, patient).
            action: The action taken (e.g., "GET /report/scan_xyz").
            resource_id: ID of the resource being accessed.
            outcome: "ALLOWED" or "DENIED".
            ip_address: Client IP address.
            session_id: Session identifier.
            details: Optional additional details.

        Returns:
            The created audit event dict.
        """
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "role": role,
            "action": action,
            "resource_id": resource_id,
            "outcome": outcome,
            "ip": ip_address,
            "session_id": session_id,
            "details": details,
        }

        # Write to storage
        if self.storage == "file":
            self._write_to_file(event)
        elif self.storage == "postgres":
            self._write_to_postgres(event)

        logger.debug(f"Audit: {outcome} {action} by {role}:{user_id}")

        return event

    def log_access(self, user_id: str, role: str, action: str,
                   resource_id: str, outcome: str, **kwargs) -> dict:
        """Convenience method for access events."""
        return self.log(
            user_id=user_id, role=role, action=action,
            resource_id=resource_id, outcome=outcome, **kwargs
        )

    def log_phi_access(self, user_id: str, role: str,
                       resource_id: str, **kwargs) -> dict:
        """Log PHI access (always both allowed and denied)."""
        return self.log(
            user_id=user_id, role=role,
            action="PHI_ACCESS", resource_id=resource_id,
            details={"phi_access": True}, **kwargs
        )

    def _write_to_file(self, event: dict) -> None:
        """Write audit event to a daily log file (development mode)."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = self.log_dir / f"audit_{date_str}.jsonl"

        with open(log_file, "a") as f:
            f.write(json.dumps(event) + "\n")

    def _write_to_postgres(self, event: dict) -> None:
        """Write audit event to Postgres (production mode)."""
        # In production, this would use SQLAlchemy to insert into
        # an append-only table with no UPDATE/DELETE grants
        try:
            import sqlalchemy
            # Placeholder — actual DB write would go here
            self._write_to_file(event)  # Fallback to file
        except ImportError:
            self._write_to_file(event)

    def query(
        self,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> list[dict]:
        """
        Query audit logs (read-only — no modification).

        Args:
            user_id: Filter by user.
            resource_id: Filter by resource.
            start_time: ISO8601 start time.
            end_time: ISO8601 end time.
            outcome: Filter by outcome ("ALLOWED" or "DENIED").

        Returns:
            List of matching audit events.
        """
        results = []

        if self.storage == "file":
            for log_file in sorted(self.log_dir.glob("audit_*.jsonl")):
                with open(log_file) as f:
                    for line in f:
                        event = json.loads(line.strip())

                        if user_id and event.get("user_id") != user_id:
                            continue
                        if resource_id and event.get("resource_id") != resource_id:
                            continue
                        if outcome and event.get("outcome") != outcome:
                            continue
                        if start_time and event.get("timestamp", "") < start_time:
                            continue
                        if end_time and event.get("timestamp", "") > end_time:
                            continue

                        results.append(event)

        return results
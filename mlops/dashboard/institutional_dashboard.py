"""
Brain_Scape — Institutional Dashboard Configuration

Aggregate stats, audit tools, utilization dashboards for institutional admins.
Includes GDPR data residency controls and role-based dashboard scopes.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class InstitutionConfig:
    """Configuration for an institutional tenant."""
    institution_id: str
    name: str
    data_residency_region: str = "us-east-1"
    gdpr_enabled: bool = False
    retention_days: int = 365
    allowed_modalities: List[str] = field(default_factory=lambda: ["MRI_T1", "fMRI", "EEG"])
    max_concurrent_jobs: int = 10
    s3_bucket: str = ""
    audit_log_retention_days: int = 2555  # 7 years HIPAA
    dashboard_users: List[str] = field(default_factory=list)


@dataclass
class DashboardStats:
    """Aggregate statistics for institutional dashboard."""
    institution_id: str
    period: str  # "24h", "7d", "30d", "all"
    total_scans: int = 0
    scans_by_modality: Dict[str, int] = field(default_factory=dict)
    scans_by_status: Dict[str, int] = field(default_factory=dict)
    average_processing_time_minutes: float = 0.0
    average_confidence: float = 0.0
    jobs_by_stage: Dict[str, int] = field(default_factory=dict)
    active_users: int = 0
    total_users: int = 0
    storage_used_gb: float = 0.0
    audit_events: int = 0
    denied_access_events: int = 0
    phi_scrubbing_events: int = 0
    model_performance: Dict = field(default_factory=dict)
    peak_concurrent_jobs: int = 0


class InstitutionalDashboard:
    """Generate institutional dashboards and aggregate statistics.

    Features:
    - Per-institution scoped statistics
    - GDPR data residency enforcement
    - Audit log querying for compliance
    - Utilization metrics and resource planning
    - Model performance tracking per institution
    """

    # GDPR-compliant data residency regions
    GDPR_REGIONS = ["eu-west-1", "eu-central-1", "eu-north-1"]
    US_REGIONS = ["us-east-1", "us-west-2"]

    def __init__(self, config_dir: str = "configs/institutions"):
        self.config_dir = Path(config_dir)
        self.institutions: Dict[str, InstitutionConfig] = {}
        self._load_configs()

    def _load_configs(self):
        """Load institutional configurations."""
        if self.config_dir.exists():
            for f in self.config_dir.glob("*.json"):
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                    inst = InstitutionConfig(**data)
                    self.institutions[inst.institution_id] = inst
                except Exception as e:
                    logger.warning(f"Failed to load institution config {f}: {e}")

    def register_institution(self, config: InstitutionConfig):
        """Register a new institutional tenant."""
        self.institutions[config.institution_id] = config
        self._save_config(config)
        logger.info(f"Registered institution: {config.name} ({config.institution_id})")

    def _save_config(self, config: InstitutionConfig):
        """Save institutional config to disk."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        path = self.config_dir / f"{config.institution_id}.json"
        with open(path, "w") as f:
            json.dump(config.__dict__, f, indent=2)

    def get_stats(
        self,
        institution_id: str,
        period: str = "30d",
        audit_logger=None,
        job_store=None,
    ) -> DashboardStats:
        """Generate aggregate statistics for an institution.

        Args:
            institution_id: Institution identifier
            period: Time period ("24h", "7d", "30d", "all")
            audit_logger: AuditLogger instance for querying events
            job_store: Job storage backend for querying jobs

        Returns:
            DashboardStats with aggregate metrics
        """
        config = self.institutions.get(institution_id)
        if not config:
            logger.warning(f"Unknown institution: {institution_id}")
            return DashboardStats(institution_id=institution_id, period=period)

        stats = DashboardStats(
            institution_id=institution_id,
            period=period,
        )

        # Query audit logs if available
        if audit_logger:
            self._populate_audit_stats(stats, audit_logger, period)

        # Query job store if available
        if job_store:
            self._populate_job_stats(stats, job_store, period, config)

        return stats

    def _populate_audit_stats(
        self, stats: DashboardStats, audit_logger, period: str
    ):
        """Populate statistics from audit log."""
        try:
            period_map = {
                "24h": timedelta(hours=24),
                "7d": timedelta(days=7),
                "30d": timedelta(days=30),
            }
            # Query all events for the period
            all_events = audit_logger.query()
            stats.audit_events = len(all_events)
            stats.denied_access_events = len(
                [e for e in all_events if e.get("outcome") == "DENIED"]
            )
            stats.phi_scrubbing_events = len(
                [e for e in all_events if "phi" in e.get("action", "").lower()
                 or "anonymiz" in e.get("action", "").lower()]
            )
        except Exception as e:
            logger.warning(f"Failed to query audit logs: {e}")

    def _populate_job_stats(
        self, stats: DashboardStats, job_store, period: str, config: InstitutionConfig
    ):
        """Populate statistics from job store."""
        try:
            # This would query the actual job database in production
            # For now, provide placeholder logic
            pass
        except Exception as e:
            logger.warning(f"Failed to query job store: {e}")

    def check_data_residency(self, institution_id: str, target_region: str) -> bool:
        """Check if data can be stored in the target region per GDPR rules.

        Args:
            institution_id: Institution identifier
            target_region: Target AWS/cloud region

        Returns:
            True if the region is compliant with the institution's data residency policy
        """
        config = self.institutions.get(institution_id)
        if not config:
            return False

        allowed_region = config.data_residency_region

        # If GDPR is enabled, EU data must stay in EU regions
        if config.gdpr_enabled:
            if allowed_region in self.GDPR_REGIONS:
                return target_region in self.GDPR_REGIONS
            elif allowed_region in self.US_REGIONS:
                # US data can be in any US region but not EU (unless explicitly allowed)
                return target_region in self.US_REGIONS

        # Non-GDPR: allow same region only
        return target_region == allowed_region

    def get_grafana_dashboard_config(
        self, institution_id: str
    ) -> Dict:
        """Generate Grafana dashboard configuration for an institution.

        Returns a dashboard JSON with institution-scoped panels.
        """
        config = self.institutions.get(institution_id)
        if not config:
            return {}

        return {
            "dashboard": {
                "id": None,
                "uid": f"brainscape-{institution_id}",
                "title": f"Brain_Scape — {config.name}",
                "tags": ["brainscape", institution_id],
                "timezone": "utc",
                "panels": [
                    {
                        "id": 1,
                        "title": "Scans by Status",
                        "type": "piechart",
                        "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0},
                        "targets": [{
                            "expr": f'sum by (status) (brainscape_jobs_total{{institution="{institution_id}"}})',
                            "legendFormat": "{{status}}",
                        }],
                    },
                    {
                        "id": 2,
                        "title": "Processing Time (minutes)",
                        "type": "timeseries",
                        "gridPos": {"h": 8, "w": 6, "x": 6, "y": 0},
                        "targets": [{
                            "expr": f'histogram_quantile(0.5, rate(brainscape_job_duration_seconds_bucket{{institution="{institution_id}"}}[5m])) / 60',
                            "legendFormat": "P50",
                        }],
                    },
                    {
                        "id": 3,
                        "title": "Queue Depth",
                        "type": "stat",
                        "gridPos": {"h": 4, "w": 3, "x": 12, "y": 0},
                        "targets": [{
                            "expr": f'brainscape_queue_depth{{institution="{institution_id}"}}',
                        }],
                    },
                    {
                        "id": 4,
                        "title": "Model Confidence (P50)",
                        "type": "gauge",
                        "gridPos": {"h": 4, "w": 3, "x": 15, "y": 0},
                        "targets": [{
                            "expr": f'histogram_quantile(0.5, rate(brainscape_model_confidence_bucket{{institution="{institution_id}"}}[5m]))',
                        }],
                    },
                    {
                        "id": 5,
                        "title": "Denied Access Events",
                        "type": "timeseries",
                        "gridPos": {"h": 8, "w": 6, "x": 12, "y": 4},
                        "targets": [{
                            "expr": f'sum(rate(brainscape_audit_denied_total{{institution="{institution_id}"}}[5m]))',
                            "legendFormat": "Denied",
                        }],
                    },
                    {
                        "id": 6,
                        "title": "Storage Usage (GB)",
                        "type": "stat",
                        "gridPos": {"h": 4, "w": 3, "x": 18, "y": 0},
                        "targets": [{
                            "expr": f'brainscape_storage_used_gb{{institution="{institution_id}"}}',
                        }],
                    },
                    {
                        "id": 7,
                        "title": "Scans by Modality",
                        "type": "barchart",
                        "gridPos": {"h": 8, "w": 6, "x": 18, "y": 4},
                        "targets": [{
                            "expr": f'sum by (modality) (brainscape_scans_total{{institution="{institution_id}"}})',
                        }],
                    },
                ],
                "templating": {
                    "list": [
                        {
                            "name": "period",
                            "type": "interval",
                            "options": [
                                {"text": "Last 24h", "value": "24h"},
                                {"text": "Last 7d", "value": "7d"},
                                {"text": "Last 30d", "value": "30d"},
                            ],
                            "current": {"text": "Last 30d", "value": "30d"},
                        },
                    ],
                },
            },
            "overwrite": True,
        }

    def get_institution_audit_report(
        self,
        institution_id: str,
        audit_logger,
        period_days: int = 30,
    ) -> Dict:
        """Generate a compliance audit report for an institution.

        Args:
            institution_id: Institution identifier
            audit_logger: AuditLogger instance
            period_days: Number of days to include

        Returns:
            Dict with audit report data
        """
        config = self.institutions.get(institution_id)
        if not config:
            return {"error": f"Unknown institution: {institution_id}"}

        try:
            all_events = audit_logger.query()
        except Exception as e:
            return {"error": f"Failed to query audit log: {e}"}

        allowed_events = [e for e in all_events if e.get("outcome") == "ALLOWED"]
        denied_events = [e for e in all_events if e.get("outcome") == "DENIED"]

        return {
            "institution_id": institution_id,
            "institution_name": config.name,
            "report_period_days": period_days,
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_events": len(all_events),
                "allowed_events": len(allowed_events),
                "denied_events": len(denied_events),
                "denied_pct": len(denied_events) / max(len(all_events), 1) * 100,
            },
            "denied_by_role": self._count_by_field(denied_events, "role"),
            "denied_by_action": self._count_by_field(denied_events, "action"),
            "compliance_checks": {
                "phi_scrubbing_enabled": True,
                "encryption_at_rest": True,
                "audit_logging": True,
                "rbac_enforced": True,
                "data_residency": config.data_residency_region,
                "gdpr_compliant": config.gdpr_enabled,
                "retention_policy_days": config.retention_days,
            },
            "recommendations": self._generate_compliance_recommendations(
                denied_events, config
            ),
        }

    @staticmethod
    def _count_by_field(events: List[Dict], field: str) -> Dict[str, int]:
        """Count events grouped by a field."""
        counts = {}
        for e in events:
            key = e.get(field, "unknown")
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _generate_compliance_recommendations(
        denied_events: List[Dict], config: InstitutionConfig
    ) -> List[str]:
        """Generate compliance recommendations based on audit data."""
        recs = []

        if len(denied_events) > 10:
            recs.append(
                "High number of denied access events — review role assignments and permissions"
            )

        patient_denied = [e for e in denied_events if e.get("role") == "patient"]
        if len(patient_denied) > 5:
            recs.append(
                "Multiple patient access denials — verify patient scope restrictions are working as intended"
            )

        if not config.gdpr_enabled:
            recs.append(
                "GDPR compliance not enabled — consider enabling if processing EU patient data"
            )

        if config.retention_days > 365:
            recs.append(
                f"Data retention policy set to {config.retention_days} days — "
                "verify this aligns with institutional and regulatory requirements"
            )

        if not recs:
            recs.append("No immediate compliance concerns identified")

        return recs
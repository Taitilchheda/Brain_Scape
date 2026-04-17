"""
Brain_Scape - Clinical Governance Engine

Computes configurable clinical governance metadata for each case:
- provenance and runtime lineage
- safety gates for automation eligibility
- uncertainty and escalation tiering
- evidence cards and sign-off requirements
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - fallback for minimal environments
    yaml = None


logger = logging.getLogger(__name__)


DEFAULT_GOVERNANCE_CONFIG: dict[str, Any] = {
    "governance": {
        "schema_version": "1.0.0",
        "review": {
            "auto_report_min_confidence": 0.82,
            "second_read_min_confidence": 0.72,
            "min_scan_quality_for_auto": ["good", "excellent"],
            "block_auto_if_synthetic_fallback": True,
            "severe_region_escalation_threshold": 1,
            "flagged_region_escalation_threshold": 4,
            "high_risk_requires_escalation": True,
        },
        "uncertainty": {
            "high_confidence_threshold": 0.90,
            "moderate_confidence_threshold": 0.75,
            "caution_threshold": 0.78,
        },
        "evidence": {
            "max_cards": 5,
            "min_region_severity": 2,
            "min_region_confidence": 0.5,
        },
        "escalation": {
            "tiers": {
                "urgent": {
                    "notify_roles": ["stroke_neurology", "neurosurgery"],
                    "expected_review_minutes": 30,
                },
                "priority": {
                    "notify_roles": ["attending_neurology"],
                    "expected_review_minutes": 180,
                },
                "routine": {
                    "notify_roles": ["assigned_clinician"],
                    "expected_review_minutes": 1440,
                },
            }
        },
        "signoff": {
            "default_required_roles": ["clinician"],
            "second_reader_role": "second_clinician",
            "require_second_read_on": ["requires_second_read", "urgent_escalation"],
        },
        "messaging": {
            "clinician_notice": "AI findings are decision support and require clinician validation.",
            "patient_notice": "Your care team reviews these AI findings before final decisions are made.",
        },
    }
}


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class ClinicalGovernanceEngine:
    """Config-driven clinical governance evaluator."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path
        self._config = self._load_config(config_path)

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    def reload(self) -> dict[str, Any]:
        self._config = self._load_config(self.config_path)
        return self._config

    def evaluate(
        self,
        analysis_payload: dict[str, Any],
        runtime_context: Optional[dict[str, Any]] = None,
        signoff_history: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        payload = copy.deepcopy(analysis_payload or {})
        runtime = copy.deepcopy(runtime_context or {})
        history = list(signoff_history or [])

        governance_cfg = self._config.get("governance", {})
        review_cfg = governance_cfg.get("review", {})
        uncertainty_cfg = governance_cfg.get("uncertainty", {})
        evidence_cfg = governance_cfg.get("evidence", {})
        messaging_cfg = governance_cfg.get("messaging", {})

        metrics = payload.get("metrics") or self._derive_metrics(payload.get("damage_summary", []))

        confidence = _safe_float(payload.get("overall_confidence"), 0.0)
        scan_quality = str(payload.get("scan_quality") or "unknown").lower()
        risk_band = str(payload.get("risk_band") or "low").lower()
        source_kind = str(runtime.get("source_kind") or self._infer_source_kind(payload))
        synthetic_fallback = bool(runtime.get("synthetic_fallback", False))

        safety_gates = self._build_safety_gates(
            confidence=confidence,
            scan_quality=scan_quality,
            synthetic_fallback=synthetic_fallback,
            metrics=metrics,
            review_cfg=review_cfg,
        )
        automation_eligible = all(gate.get("status") == "pass" for gate in safety_gates)

        decision_tier = self._select_decision_tier(
            confidence=confidence,
            risk_band=risk_band,
            metrics=metrics,
            automation_eligible=automation_eligible,
            review_cfg=review_cfg,
            safety_gates=safety_gates,
        )
        escalation = self._build_escalation(decision_tier)
        uncertainty = self._build_uncertainty(
            confidence=confidence,
            synthetic_fallback=synthetic_fallback,
            uncertainty_cfg=uncertainty_cfg,
        )
        evidence_cards = self._build_evidence_cards(
            payload.get("damage_summary", []),
            evidence_cfg=evidence_cfg,
        )

        required_roles = self._required_signoff_roles(decision_tier)
        latest_signoff = history[-1] if history else None
        review_state = self._derive_review_state(decision_tier, latest_signoff)

        provenance = {
            "source_kind": source_kind,
            "source_upload": payload.get("source_upload"),
            "source_nifti": runtime.get("source_nifti") or payload.get("source_nifti_path") or payload.get("source_upload_path"),
            "synthetic_fallback": synthetic_fallback,
            "mesh_quality": runtime.get("mesh_quality"),
            "volume_resolution": runtime.get("volume_resolution") or runtime.get("resolution_profile"),
            "analysis_mode": payload.get("analysis_mode") or "baseline",
            "runtime_updated_at": runtime.get("updated_at"),
            "schema_version": governance_cfg.get("schema_version", "1.0.0"),
        }

        return {
            "schema_version": governance_cfg.get("schema_version", "1.0.0"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "decision_tier": decision_tier,
            "review_state": review_state,
            "automation_eligible": automation_eligible,
            "required_signoff_roles": required_roles,
            "risk_band": risk_band,
            "metrics": metrics,
            "safety_gates": safety_gates,
            "escalation": escalation,
            "uncertainty": uncertainty,
            "evidence_cards": evidence_cards,
            "provenance": provenance,
            "messaging": {
                "clinician_notice": messaging_cfg.get("clinician_notice", ""),
                "patient_notice": messaging_cfg.get("patient_notice", ""),
            },
            "latest_signoff": latest_signoff,
            "signoff_count": len(history),
        }

    def _load_config(self, config_path: Optional[Path]) -> dict[str, Any]:
        base = copy.deepcopy(DEFAULT_GOVERNANCE_CONFIG)
        if not config_path:
            return base

        path = Path(config_path)
        if not path.exists():
            logger.warning("Clinical governance config not found at %s. Using defaults.", path)
            return base

        if yaml is None:
            logger.warning("PyYAML unavailable. Using default clinical governance configuration.")
            return base

        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            if not isinstance(loaded, dict):
                logger.warning("Clinical governance config is not a mapping. Using defaults.")
                return base
            return _deep_merge(base, loaded)
        except Exception as exc:
            logger.warning("Failed to load clinical governance config: %s", exc)
            return base

    @staticmethod
    def _infer_source_kind(payload: dict[str, Any]) -> str:
        scan_id = str(payload.get("scan_id") or "")
        patient_id = str(payload.get("patient_id") or "")
        if scan_id.startswith("demo-") or patient_id.startswith("demo-"):
            return "demo"
        if payload.get("source_upload") or payload.get("source_upload_path"):
            return "uploaded"
        return "persisted"

    @staticmethod
    def _derive_metrics(regions: list[dict[str, Any]]) -> dict[str, Any]:
        severe = sum(1 for region in regions if int(region.get("severity_level", 0)) >= 4)
        moderate = sum(1 for region in regions if int(region.get("severity_level", 0)) == 3)
        mild = sum(1 for region in regions if int(region.get("severity_level", 0)) == 2)
        flagged = severe + moderate + mild
        triage_score = round((severe * 3.5) + (moderate * 2.2) + (mild * 1.1), 2)
        return {
            "flagged_regions": flagged,
            "severe_regions": severe,
            "moderate_regions": moderate,
            "mild_regions": mild,
            "triage_score": triage_score,
        }

    @staticmethod
    def _status_from_score(score: float, pass_min: float, warn_min: float) -> str:
        if score >= pass_min:
            return "pass"
        if score >= warn_min:
            return "warn"
        return "fail"

    def _build_safety_gates(
        self,
        confidence: float,
        scan_quality: str,
        synthetic_fallback: bool,
        metrics: dict[str, Any],
        review_cfg: dict[str, Any],
    ) -> list[dict[str, Any]]:
        auto_min = _safe_float(review_cfg.get("auto_report_min_confidence"), 0.82)
        second_min = _safe_float(review_cfg.get("second_read_min_confidence"), 0.72)
        quality_allow = {
            str(value).strip().lower()
            for value in review_cfg.get("min_scan_quality_for_auto", [])
            if str(value).strip()
        }
        block_auto_on_synth = bool(review_cfg.get("block_auto_if_synthetic_fallback", True))

        confidence_status = self._status_from_score(confidence, auto_min, second_min)
        quality_status = "pass" if not quality_allow or scan_quality in quality_allow else "warn"

        synthetic_status = "pass"
        if synthetic_fallback and block_auto_on_synth:
            synthetic_status = "fail"
        elif synthetic_fallback:
            synthetic_status = "warn"

        flagged_regions = int(metrics.get("flagged_regions", 0))
        severe_regions = int(metrics.get("severe_regions", 0))
        finding_status = "pass"
        if severe_regions > 0:
            finding_status = "warn"
        if flagged_regions >= int(review_cfg.get("flagged_region_escalation_threshold", 4)):
            finding_status = "warn"

        return [
            {
                "name": "confidence",
                "status": confidence_status,
                "detail": f"Overall confidence {round(confidence * 100)}% (auto >= {round(auto_min * 100)}%).",
            },
            {
                "name": "scan_quality",
                "status": quality_status,
                "detail": f"Scan quality '{scan_quality}' evaluated against automation allow-list.",
            },
            {
                "name": "synthetic_fallback",
                "status": synthetic_status,
                "detail": "Synthetic fallback detected in runtime pipeline." if synthetic_fallback else "Native volumetric source available.",
            },
            {
                "name": "finding_burden",
                "status": finding_status,
                "detail": f"Flagged regions: {flagged_regions}; severe regions: {severe_regions}.",
            },
        ]

    def _select_decision_tier(
        self,
        confidence: float,
        risk_band: str,
        metrics: dict[str, Any],
        automation_eligible: bool,
        review_cfg: dict[str, Any],
        safety_gates: list[dict[str, Any]],
    ) -> str:
        severe_regions = int(metrics.get("severe_regions", 0))
        flagged_regions = int(metrics.get("flagged_regions", 0))
        auto_min = _safe_float(review_cfg.get("auto_report_min_confidence"), 0.82)
        second_min = _safe_float(review_cfg.get("second_read_min_confidence"), 0.72)
        severe_threshold = int(review_cfg.get("severe_region_escalation_threshold", 1))
        flagged_threshold = int(review_cfg.get("flagged_region_escalation_threshold", 4))
        high_risk_requires_escalation = bool(review_cfg.get("high_risk_requires_escalation", True))

        has_failed_gate = any(gate.get("status") == "fail" for gate in safety_gates)

        needs_escalation = False
        if high_risk_requires_escalation and risk_band == "high":
            needs_escalation = True
        if severe_regions >= severe_threshold:
            needs_escalation = True
        if flagged_regions >= flagged_threshold and confidence < auto_min:
            needs_escalation = True

        if needs_escalation and (confidence < second_min or has_failed_gate):
            return "urgent_escalation"

        if needs_escalation:
            return "requires_clinician_review"

        if not automation_eligible or has_failed_gate:
            return "requires_second_read"

        return "auto_report_allowed"

    def _build_escalation(self, decision_tier: str) -> dict[str, Any]:
        tiers_cfg = (
            self._config
            .get("governance", {})
            .get("escalation", {})
            .get("tiers", {})
        )

        if decision_tier == "urgent_escalation":
            level = "urgent"
        elif decision_tier in {"requires_clinician_review", "requires_second_read"}:
            level = "priority"
        else:
            level = "routine"

        tier_cfg = tiers_cfg.get(level, {})
        return {
            "level": level,
            "notify_roles": list(tier_cfg.get("notify_roles", [])),
            "expected_review_minutes": int(tier_cfg.get("expected_review_minutes", 1440)),
        }

    def _build_uncertainty(
        self,
        confidence: float,
        synthetic_fallback: bool,
        uncertainty_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        high_thr = _safe_float(uncertainty_cfg.get("high_confidence_threshold"), 0.90)
        moderate_thr = _safe_float(uncertainty_cfg.get("moderate_confidence_threshold"), 0.75)
        caution_thr = _safe_float(uncertainty_cfg.get("caution_threshold"), 0.78)

        if confidence >= high_thr:
            band = "high"
        elif confidence >= moderate_thr:
            band = "moderate"
        else:
            band = "low"

        caution = confidence < caution_thr or synthetic_fallback
        return {
            "confidence": confidence,
            "band": band,
            "caution": caution,
            "message": (
                "Findings should be treated as high-uncertainty and require direct clinician verification."
                if caution
                else "Confidence profile is within routine review bounds."
            ),
        }

    def _build_evidence_cards(
        self,
        regions: list[dict[str, Any]],
        evidence_cfg: dict[str, Any],
    ) -> list[dict[str, Any]]:
        min_severity = int(evidence_cfg.get("min_region_severity", 2))
        min_confidence = _safe_float(evidence_cfg.get("min_region_confidence"), 0.5)
        max_cards = int(evidence_cfg.get("max_cards", 5))

        filtered = []
        for region in regions:
            severity_level = int(region.get("severity_level", 0))
            confidence = _safe_float(region.get("confidence"), 0.0)
            if severity_level < min_severity or confidence < min_confidence:
                continue
            filtered.append(region)

        filtered.sort(
            key=lambda item: (
                int(item.get("severity_level", 0)),
                _safe_float(item.get("confidence"), 0.0),
                _safe_float(item.get("volume_mm3"), 0.0),
            ),
            reverse=True,
        )

        cards = []
        for region in filtered[:max_cards]:
            confidence = _safe_float(region.get("confidence"), 0.0)
            severity_label = str(region.get("severity_label") or "UNKNOWN")
            region_name = str(region.get("anatomical_name") or region.get("atlas_id") or "Unknown")
            cards.append(
                {
                    "region": region_name,
                    "severity_label": severity_label,
                    "severity_level": int(region.get("severity_level", 0)),
                    "confidence": confidence,
                    "confidence_pct": round(confidence * 100),
                    "volume_mm3": _safe_float(region.get("volume_mm3"), 0.0),
                    "pct_region": _safe_float(region.get("pct_region"), _safe_float(region.get("volume_pct_of_region"), 0.0)),
                    "statement": f"{region_name}: {severity_label} involvement at {round(confidence * 100)}% confidence.",
                }
            )
        return cards

    def _required_signoff_roles(self, decision_tier: str) -> list[str]:
        signoff_cfg = self._config.get("governance", {}).get("signoff", {})
        roles = list(signoff_cfg.get("default_required_roles", ["clinician"]))
        second_read_required = decision_tier in set(signoff_cfg.get("require_second_read_on", []))
        if second_read_required:
            second_role = str(signoff_cfg.get("second_reader_role") or "second_clinician")
            if second_role and second_role not in roles:
                roles.append(second_role)
        return roles

    @staticmethod
    def _derive_review_state(decision_tier: str, latest_signoff: Optional[dict[str, Any]]) -> str:
        if latest_signoff:
            decision = str(latest_signoff.get("decision") or "").lower()
            if decision == "approve":
                return "approved"
            if decision == "requires_second_read":
                return "pending_second_read"
            if decision == "escalate":
                return "escalated"
            return "review_recorded"

        if decision_tier == "auto_report_allowed":
            return "awaiting_primary_signoff"
        if decision_tier == "requires_second_read":
            return "second_read_required"
        if decision_tier == "requires_clinician_review":
            return "clinician_review_required"
        if decision_tier == "urgent_escalation":
            return "urgent_review_required"
        return "review_pending"

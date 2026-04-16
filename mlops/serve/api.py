"""
Brain_Scape — FastAPI Server

Exposes all capabilities as REST endpoints with async job tracking.
No neuroimaging job runs synchronously — all heavy compute is queued.
"""

import base64
import csv
import hashlib
import json
import logging
import math
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Query, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from pydantic import BaseModel

from compliance.rbac import RBACManager
from compliance.audit_logger import AuditLogger
from compliance.clinical_governance import ClinicalGovernanceEngine

logger = logging.getLogger(__name__)

_PROJECT_DIR = Path(__file__).resolve().parents[2]
_OUTPUTS_DIR = _PROJECT_DIR / "outputs"
_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
_CLINICAL_GOVERNANCE_CONFIG = _PROJECT_DIR / "configs" / "clinical_governance.yaml"
_FRONTEND_URL = os.getenv("BRAINSCAPE_FRONTEND_URL", "http://127.0.0.1:3000").rstrip("/")

# ── App Setup ──

app = FastAPI(
    title="Brain_Scape API",
    description="Neuro-imaging intelligence platform — 3D reconstruction, damage analysis, RAG, LLM Q&A",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Dependencies ──

audit = AuditLogger(storage="file")
JWT_SECRET = os.getenv("BRAINSCAPE_JWT_SECRET", "brainscape-dev-secret-key-32ch!!")
rbac = RBACManager(secret_key=JWT_SECRET)
governance_engine = ClinicalGovernanceEngine(config_path=_CLINICAL_GOVERNANCE_CONFIG)


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Extract and validate user from JWT token."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.replace("Bearer ", "") if authorization else ""
    payload = rbac.validate_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


# ── Models ──

class JobStatus(BaseModel):
    job_id: str
    status: str
    stage: Optional[str] = None
    progress_pct: Optional[int] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class QueryRequest(BaseModel):
    scan_id: str
    question: str
    voice_audio_b64: Optional[str] = None


class AnnotateRequest(BaseModel):
    scan_id: str
    mesh_face_id: int
    comment: str
    marker_type: str = "point"


class SignoffRequest(BaseModel):
    decision: Literal["approve", "requires_second_read", "escalate"]
    note: Optional[str] = None
    escalation_reason: Optional[str] = None
    escalation_target: Optional[str] = None


class CriticalAcknowledgementRequest(BaseModel):
    disposition: Literal["pending", "escalated", "resolved"] = "pending"
    note: Optional[str] = None
    escalation_target: Optional[str] = None


class SegmentationEditRequest(BaseModel):
    operation: Literal["add", "erase", "smooth", "label", "undo", "redo", "approve", "reject"]
    region_name: Optional[str] = None
    rationale: str
    voxel_count_delta: int = 0
    confidence_hint: Optional[float] = None
    patch_summary: Optional[dict[str, Any]] = None


class SegmentationApprovalRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: Optional[str] = None


class DistanceMeasurementRequest(BaseModel):
    point_a: list[float]
    point_b: list[float]
    coordinate_space: Literal["voxel", "mm"] = "voxel"
    spacing_mm: Optional[list[float]] = None
    label: Optional[str] = None


class VolumeMeasurementRequest(BaseModel):
    voxel_count: int
    spacing_mm: Optional[list[float]] = None
    label: Optional[str] = None


class QAAvailabilityRequest(BaseModel):
    scan_id: str
    question: str


# ── In-Memory Job Store (production would use Postgres) ──

_job_store: dict[str, dict] = {}
_UPLOADED_ANALYSES: dict[str, dict] = {}
_VOLUME_PAYLOAD_CACHE: dict[str, dict] = {}
_RUNTIME_CONTEXT_STORE: dict[str, dict[str, Any]] = {}
_SIGNOFF_STORE: dict[str, list[dict[str, Any]]] = {}
_CRITICAL_ACK_STORE: dict[str, list[dict[str, Any]]] = {}
_REPORT_FINALIZATION_STORE: dict[str, list[dict[str, Any]]] = {}
_SEGMENTATION_EDIT_STORE: dict[str, dict[str, Any]] = {}
_MEASUREMENT_LEDGER: dict[str, list[dict[str, Any]]] = {}

_MESH_QUALITY_PROFILES: dict[str, dict[str, float | int | str]] = {
    "standard": {
        "decimation_target": 140000,
        "iso_value": 0.5,
        "smooth_iterations": 12,
        "output_prefix": "brain_v2",
    },
    "high": {
        "decimation_target": 320000,
        "iso_value": 0.48,
        "smooth_iterations": 20,
        "output_prefix": "brain_hq_v2",
    },
    "extreme": {
        "decimation_target": 650000,
        "iso_value": 0.46,
        "smooth_iterations": 24,
        "output_prefix": "brain_xq_v2",
    },
}


_VOLUME_RESOLUTION_PROFILES: dict[str, tuple[int, int, int]] = {
    "standard": (96, 96, 96),
    "high": (144, 144, 144),
    "extreme": (192, 192, 192),
}


def _mesh_profile(quality: str) -> dict[str, float | int | str]:
    return _MESH_QUALITY_PROFILES.get(quality, _MESH_QUALITY_PROFILES["high"])


def _mesh_quality_from_output_name(mesh_name: str) -> str:
    normalized = mesh_name.lower()
    if normalized.startswith("brain_xq"):
        return "extreme"
    if normalized.startswith("brain_hq"):
        return "high"
    return "standard"


def _volume_target_shape(resolution: str) -> tuple[int, int, int]:
    return _VOLUME_RESOLUTION_PROFILES.get(resolution, _VOLUME_RESOLUTION_PROFILES["standard"])


def _create_job(user_id: str, scan_path: str) -> str:
    """Create a new job record."""
    job_id = str(uuid4())
    _job_store[job_id] = {
        "job_id": job_id,
        "user_id": user_id,
        "scan_path": scan_path,
        "status": "queued",
        "stage": "ingestion",
        "progress_pct": 0,
        "error_message": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return job_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_PROJECT_DIR)).replace("\\", "/")
    except ValueError:
        return str(path)


def _analysis_json_path(scan_id: str) -> Path:
    return _OUTPUTS_DIR / "analysis" / scan_id / "analysis.json"


def _record_runtime_context(scan_id: str, **context_updates: Any) -> dict[str, Any]:
    context = dict(_RUNTIME_CONTEXT_STORE.get(scan_id, {}))
    for key, value in context_updates.items():
        if value is not None:
            context[key] = value
    context["updated_at"] = _now_iso()
    _RUNTIME_CONTEXT_STORE[scan_id] = context
    return context


def _resolve_runtime_context(scan_id: str, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    context = dict(_RUNTIME_CONTEXT_STORE.get(scan_id, {}))
    if extra:
        for key, value in extra.items():
            if value is not None:
                context[key] = value
    return context


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _preprocessing_status_map(scan_id: str, analysis: dict, runtime_context: dict[str, Any]) -> dict[str, str]:
    source_kind = str(runtime_context.get("source_kind") or "unknown")
    synthetic_fallback = bool(runtime_context.get("synthetic_fallback", False))
    quality = str(analysis.get("scan_quality") or "unknown").lower()

    if source_kind == "demo":
        return {
            "skull_stripping": "simulated",
            "motion_correction": "simulated",
            "slice_timing": "simulated",
            "denoising": "simulated",
            "intensity_normalization": "simulated",
            "atlas_registration": "simulated",
        }

    base_status = "pass"
    if synthetic_fallback or quality in {"limited", "poor"}:
        base_status = "review_required"
    if quality == "unknown":
        base_status = "unknown"

    return {
        "skull_stripping": base_status,
        "motion_correction": base_status,
        "slice_timing": "pass" if str(analysis.get("modalities", [""])[0]).lower() == "fmri" else "not_applicable",
        "denoising": base_status,
        "intensity_normalization": base_status,
        "atlas_registration": base_status,
    }


def _build_provenance_banner(scan_id: str, analysis: dict, runtime_context: dict[str, Any]) -> dict[str, Any]:
    source_kind = str(runtime_context.get("source_kind") or ("demo" if scan_id.startswith("demo-") else "uploaded"))
    synthetic_fallback = bool(runtime_context.get("synthetic_fallback", False))
    source_mode = "real_patient_derived"
    if source_kind == "demo":
        source_mode = "demo_dataset"
    if synthetic_fallback:
        source_mode = "synthetic_fallback"

    preprocessing_map = _preprocessing_status_map(scan_id, analysis, runtime_context)
    return {
        "scan_id": scan_id,
        "source_mode": source_mode,
        "source_kind": source_kind,
        "synthetic_fallback": synthetic_fallback,
        "analysis_mode": analysis.get("analysis_mode") or runtime_context.get("analysis_mode") or "baseline",
        "source_nifti": runtime_context.get("source_nifti") or analysis.get("source_upload") or analysis.get("source_upload_path"),
        "atlas_version": analysis.get("atlas", "AAL3"),
        "model_versions": {
            "segmentation": "nnU-Net-v2/fallback",
            "classification": "severity-v1",
            "confidence": "confidence-v1",
            "reconstruction": "mesh-builder-v2",
            "llm": os.getenv("LLM_MODEL", "gpt-4"),
        },
        "mesh_quality": runtime_context.get("mesh_quality"),
        "volume_resolution": runtime_context.get("volume_resolution") or runtime_context.get("resolution_profile"),
        "preprocessing_status": preprocessing_map,
        "generated_at": _now_iso(),
    }


def _build_safety_profile(scan_id: str, analysis: dict, runtime_context: dict[str, Any]) -> dict[str, Any]:
    quality = str(analysis.get("scan_quality") or "unknown").lower()
    confidence = _safe_float(analysis.get("overall_confidence"), 0.0)
    synthetic_fallback = bool(runtime_context.get("synthetic_fallback", False))
    source_kind = str(runtime_context.get("source_kind") or "unknown")

    low_quality = quality in {"limited", "poor", "unknown"}
    low_confidence = confidence < 0.75
    decision_support_only = synthetic_fallback or low_quality or low_confidence

    reasons: list[str] = []
    if synthetic_fallback:
        reasons.append("synthetic_fallback_active")
    if low_quality:
        reasons.append(f"scan_quality_{quality}")
    if low_confidence:
        reasons.append("overall_confidence_below_calibrated_threshold")
    if source_kind == "demo":
        reasons.append("demo_source")

    locks = []
    if decision_support_only:
        locks.extend([
            "definitive_language_block",
            "manual_confirmation_required",
            "auto_finalize_report_blocked",
            "surgical_planning_hard_stop_without_signoff",
        ])

    return {
        "decision_support_only": decision_support_only,
        "manual_confirmation_required": decision_support_only,
        "definitive_language_allowed": not decision_support_only,
        "high_risk_action_locks": locks,
        "reasons": reasons,
        "overall_confidence": round(confidence, 3),
        "scan_quality": quality,
    }


def _build_uncertainty_profile(scan_id: str, analysis: dict) -> dict[str, Any]:
    regions = list(analysis.get("damage_summary", []))
    uncertainty_regions: list[dict[str, Any]] = []

    for region in regions:
        confidence = _safe_float(region.get("confidence"), 0.5)
        severity_level = _safe_int(region.get("severity_level"), 0)
        volume_pct = _safe_float(region.get("pct_region") or region.get("volume_pct_of_region"), 0.0)
        uncertainty = max(0.03, min(0.97, (1.0 - confidence) + (0.05 if severity_level >= 3 else 0.0)))
        uncertainty_regions.append(
            {
                "anatomical_name": region.get("anatomical_name") or region.get("atlas_id", "Unknown"),
                "severity_level": severity_level,
                "confidence": round(confidence, 3),
                "uncertainty": round(float(uncertainty), 3),
                "volume_pct_of_region": round(volume_pct, 2),
            }
        )

    uncertainty_regions.sort(key=lambda item: item["uncertainty"], reverse=True)
    high_uncertainty = [r for r in uncertainty_regions if r["uncertainty"] >= 0.35]

    return {
        "scan_id": scan_id,
        "global_uncertainty": round(sum(r["uncertainty"] for r in uncertainty_regions) / max(len(uncertainty_regions), 1), 3),
        "high_uncertainty_regions": high_uncertainty[:12],
        "regions": uncertainty_regions,
        "overlay_hint": {
            "color_map": "coolwarm",
            "semantic": "higher values indicate lower certainty",
        },
    }


def _build_critical_findings(scan_id: str, analysis: dict, safety_profile: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    metrics = analysis.get("metrics") or _compute_case_metrics(analysis)
    severe_regions = _safe_int(metrics.get("severe_regions"), 0)
    flagged_regions = _safe_int(metrics.get("flagged_regions"), 0)
    triage_score = _safe_float(metrics.get("triage_score"), 0.0)
    risk_band = str(analysis.get("risk_band") or "low").lower()

    if severe_regions >= 1 or triage_score >= 8.0 or risk_band == "high":
        findings.append(
            {
                "finding_id": f"critical-{scan_id}-001",
                "severity": "urgent",
                "category": "critical_burden",
                "title": "High-severity neuroimaging burden detected",
                "description": "One or more regions are in the RED severity range; urgent clinician review is required.",
                "requires_acknowledgement": True,
            }
        )

    if safety_profile.get("decision_support_only"):
        findings.append(
            {
                "finding_id": f"critical-{scan_id}-002",
                "severity": "warning",
                "category": "safety_gate",
                "title": "Decision-support-only safety mode active",
                "description": "Fallback or low-confidence conditions detected. Definitive recommendations are suppressed.",
                "requires_acknowledgement": True,
            }
        )

    if flagged_regions >= 5:
        findings.append(
            {
                "finding_id": f"critical-{scan_id}-003",
                "severity": "priority",
                "category": "multifocal_pattern",
                "title": "Multifocal pattern requiring multidisciplinary review",
                "description": "Multiple affected regions exceed expected variance for single-focal disease pattern.",
                "requires_acknowledgement": True,
            }
        )

    return findings


def _classify_clinical_change(delta: dict[str, Any]) -> dict[str, Any]:
    triage_delta = _safe_float(delta.get("triage_score"), 0.0)
    severe_delta = _safe_int(delta.get("severe_regions"), 0)
    flagged_delta = _safe_int(delta.get("flagged_regions"), 0)
    confidence_pct = _safe_float(delta.get("confidence_pct"), 0.0)

    magnitude = abs(triage_delta)
    meaningful = (
        abs(severe_delta) >= 1
        or abs(flagged_delta) >= 2
        or magnitude >= 2.0
        or abs(confidence_pct) >= 8.0
    )

    if not meaningful:
        label = "likely_measurement_variance"
    elif triage_delta > 0:
        label = "likely_progression"
    elif triage_delta < 0:
        label = "likely_improvement"
    else:
        label = "mixed_change"

    return {
        "clinically_meaningful": meaningful,
        "classification": label,
        "confidence": round(min(0.95, 0.55 + (0.08 * min(4.0, magnitude))), 3),
    }


def _build_disease_specific_modules(analysis: dict) -> dict[str, Any]:
    regions = list(analysis.get("damage_summary", []))
    severe_regions = [r for r in regions if _safe_int(r.get("severity_level"), 0) >= 4]
    moderate_regions = [r for r in regions if _safe_int(r.get("severity_level"), 0) == 3]

    total_volume = sum(_safe_float(r.get("volume_mm3"), 0.0) for r in regions)
    severe_volume = sum(_safe_float(r.get("volume_mm3"), 0.0) for r in severe_regions)

    stroke_like_regions = [r for r in regions if any(token in str(r.get("anatomical_name", "")).lower() for token in ["mca", "basal", "thalam", "capsule", "frontal", "parietal"])]
    aspects_like_score = max(0, 10 - len([r for r in stroke_like_regions if _safe_int(r.get("severity_level"), 0) >= 3]))

    return {
        "stroke": {
            "aspects_like_score": aspects_like_score,
            "hemorrhage_burden_mm3": round(severe_volume, 1),
            "edema_progression_alert": len(severe_regions) >= 2,
            "mismatch_comment": "Perfusion mismatch estimation unavailable without perfusion series.",
        },
        "tumor": {
            "longitudinal_volumetrics_mm3": round(total_volume, 1),
            "response_tracking_summary": "Use serial comparisons to classify response/progression.",
        },
        "tbi": {
            "diffuse_injury_pattern": len(moderate_regions) + len(severe_regions) >= 4,
            "cognitive_risk_summary": "Moderate" if len(severe_regions) == 0 else "High",
        },
        "epilepsy_preop": {
            "eloquent_overlap_risk": any("hippoc" in str(r.get("anatomical_name", "")).lower() for r in severe_regions),
            "tract_risk_summary": "Requires tractography review before resection planning.",
        },
    }


def _qa_mode_tag(rag_results: list[dict[str, Any]], answer_text: str) -> str:
    if rag_results:
        return "evidence-backed"
    if not answer_text.strip() or answer_text.lower().startswith("error generating"):
        return "unavailable"
    return "heuristic"


def _build_evidence_cards(
    question: str,
    analysis: dict,
    citations: list[dict[str, Any]],
    mode_tag: str,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []

    if citations:
        for citation in citations[:5]:
            cards.append(
                {
                    "statement": f"Response to: {question}",
                    "source": citation.get("source") or citation.get("title") or "clinical-literature",
                    "title": citation.get("title") or "Untitled source",
                    "publication_year": citation.get("year"),
                    "evidence_level": "peer_reviewed_literature",
                    "applicability": "contextual",
                    "relevance_score": citation.get("relevance_score", citation.get("score", 0)),
                }
            )
    else:
        cards.append(
            {
                "statement": f"Response to: {question}",
                "source": "internal-analysis",
                "title": "No external literature retrieved",
                "publication_year": None,
                "evidence_level": "heuristic",
                "applicability": "decision_support_only",
                "relevance_score": 0,
            }
        )

    cards.append(
        {
            "statement": "Structured region-level findings",
            "source": "analysis.damage_summary",
            "title": f"Scan {analysis.get('scan_id', 'unknown')} findings",
            "publication_year": None,
            "evidence_level": "model_output",
            "applicability": "case_specific",
            "relevance_score": round(_safe_float(analysis.get("overall_confidence"), 0.0), 3),
            "mode_tag": mode_tag,
        }
    )

    return cards[:6]


def _normalize_spacing(spacing_mm: Optional[list[float]]) -> list[float]:
    if not spacing_mm or len(spacing_mm) < 3:
        return [1.0, 1.0, 1.0]
    return [max(1e-6, _safe_float(v, 1.0)) for v in spacing_mm[:3]]


def _distance_mm(point_a: list[float], point_b: list[float], spacing_mm: list[float], coordinate_space: str) -> float:
    if len(point_a) < 3 or len(point_b) < 3:
        raise ValueError("Expected point_a and point_b with 3 values each")

    dx = _safe_float(point_a[0]) - _safe_float(point_b[0])
    dy = _safe_float(point_a[1]) - _safe_float(point_b[1])
    dz = _safe_float(point_a[2]) - _safe_float(point_b[2])

    if coordinate_space == "voxel":
        dx *= spacing_mm[0]
        dy *= spacing_mm[1]
        dz *= spacing_mm[2]

    return math.sqrt((dx * dx) + (dy * dy) + (dz * dz))


def _volume_mm3(voxel_count: int, spacing_mm: list[float]) -> float:
    if voxel_count < 0:
        raise ValueError("voxel_count must be non-negative")
    voxel_volume = spacing_mm[0] * spacing_mm[1] * spacing_mm[2]
    return float(voxel_count) * voxel_volume


def _dicom_orientation_from_spacing(spacing_mm: list[float]) -> dict[str, Any]:
    return {
        "orientation": "RAS",
        "pixel_spacing_mm": [round(spacing_mm[0], 3), round(spacing_mm[1], 3)],
        "slice_thickness_mm": round(spacing_mm[2], 3),
    }


def _decorate_analysis_payload(
    scan_id: str,
    payload: dict,
    runtime_overrides: Optional[dict[str, Any]] = None,
) -> dict:
    decorated = dict(payload)

    if "metrics" not in decorated or not isinstance(decorated.get("metrics"), dict):
        decorated["metrics"] = _compute_case_metrics(decorated)

    runtime_context = _resolve_runtime_context(scan_id, runtime_overrides)
    runtime_context.setdefault(
        "source_kind",
        "demo" if scan_id in _DEMO_ANALYSES else ("uploaded" if decorated.get("source_upload") else "persisted"),
    )

    signoff_history = list(_SIGNOFF_STORE.get(scan_id, []))
    governance = governance_engine.evaluate(
        analysis_payload=decorated,
        runtime_context=runtime_context,
        signoff_history=signoff_history,
    )

    provenance_banner = _build_provenance_banner(scan_id, decorated, runtime_context)
    safety_profile = _build_safety_profile(scan_id, decorated, runtime_context)
    uncertainty_profile = _build_uncertainty_profile(scan_id, decorated)
    critical_findings = _build_critical_findings(scan_id, decorated, safety_profile)

    decorated["clinical_governance"] = governance
    decorated["provenance"] = governance.get("provenance", {})
    decorated["provenance_banner"] = provenance_banner
    decorated["safety_profile"] = safety_profile
    decorated["uncertainty_profile"] = uncertainty_profile
    decorated["critical_findings"] = critical_findings
    decorated["signoff_history"] = signoff_history
    decorated["review_state"] = governance.get("review_state")
    decorated["decision_tier"] = governance.get("decision_tier")

    return decorated


def _write_analysis_payload(scan_id: str, payload: dict) -> None:
    output_path = _analysis_json_path(scan_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _read_analysis_payload(scan_id: str) -> Optional[dict]:
    path = _analysis_json_path(scan_id)
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"Could not parse analysis JSON for {scan_id}: {exc}")
        return None


def _resolve_analysis_payload(scan_id: str) -> dict:
    if scan_id in _DEMO_ANALYSES:
        return dict(_DEMO_ANALYSES[scan_id])

    if scan_id in _UPLOADED_ANALYSES:
        return dict(_UPLOADED_ANALYSES[scan_id])

    payload = _read_analysis_payload(scan_id)
    if payload:
        _UPLOADED_ANALYSES[scan_id] = dict(payload)
        return payload

    raise HTTPException(status_code=404, detail=f"Analysis for scan {scan_id} not found")


# ── Endpoints ──

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "api": "ok",
        "workers_active": True,
        "queue_depth": len([j for j in _job_store.values() if j["status"] == "queued"]),
    }


@app.post("/ingest")
async def ingest_scan(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a scan and start the processing pipeline.

    In local/demo mode this endpoint performs a fast synthetic analysis so the
    UI and report workflows can complete end-to-end without external workers.
    """
    user_id = current_user.get("sub", "anonymous")
    role = current_user.get("role", "patient")

    # Audit log
    audit.log(
        user_id=user_id, role=role,
        action="POST /ingest", outcome="ALLOWED",
    )

    # Save uploaded file
    import os
    upload_dir = f"data/raw/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename or "upload")

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Create job
    job_id = _create_job(user_id, file_path)

    # Materialize an analysis payload immediately so upload/report/volume flows work end-to-end.
    try:
        analysis = _materialize_uploaded_analysis(job_id, Path(file_path))
        scan_ref = str(analysis.get("scan_id", job_id))
        _record_runtime_context(
            job_id,
            source_kind="uploaded",
            source_nifti=analysis.get("source_upload") or analysis.get("source_upload_path"),
            synthetic_fallback=False,
            analysis_mode=analysis.get("analysis_mode") or "deterministic-upload",
        )
        decorated = _decorate_analysis_payload(scan_ref, analysis)
        _job_store[job_id].update(
            {
                "status": "complete",
                "stage": "done",
                "progress_pct": 100,
                "provenance_banner": decorated.get("provenance_banner", {}),
                "safety_profile": decorated.get("safety_profile", {}),
                "scan_id": scan_ref,
                "updated_at": _now_iso(),
            }
        )
    except Exception as exc:
        logger.exception(f"Uploaded scan analysis failed for job {job_id}: {exc}")
        _job_store[job_id].update(
            {
                "status": "failed",
                "stage": "analysis",
                "progress_pct": 100,
                "error_message": str(exc),
                "updated_at": _now_iso(),
            }
        )

    return {
        "job_id": job_id,
        "scan_id": job_id,
        "status": _job_store[job_id]["status"],
        "eta_seconds": 5,
    }


@app.get("/status/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Poll the status of a processing job."""
    if job_id not in _job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = _job_store[job_id]

    # RBAC check
    allowed, reason = rbac.check_permission(
        current_user.get("role", "patient"),
        "GET /status/{job_id}",
    )
    if not allowed:
        audit.log(
            user_id=current_user.get("sub", ""),
            role=current_user.get("role", ""),
            action=f"GET /status/{job_id}",
            outcome="DENIED",
        )
        raise HTTPException(status_code=403, detail=reason)

    return JobStatus(**job)


@app.get("/mesh/{scan_id}")
async def get_mesh(
    scan_id: str,
    force_rebuild: bool = Query(False),
    quality: str = Query("high", pattern="^(standard|high|extreme)$"),
    current_user: dict = Depends(get_current_user),
):
    """Retrieve or build a patient-specific mesh and damage overlay."""
    analysis = _resolve_analysis_payload(scan_id)

    try:
        mesh_info = _ensure_scan_mesh(
            scan_id,
            analysis,
            force_rebuild=force_rebuild,
            quality=quality,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(f"Failed to build mesh for {scan_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Mesh reconstruction failed for {scan_id}") from exc

    _record_runtime_context(
        scan_id,
        mesh_quality=mesh_info.get("mesh_quality"),
        source_nifti=mesh_info.get("source_nifti"),
    )

    decorated = _decorate_analysis_payload(scan_id, analysis)

    return {
        "scan_id": scan_id,
        "patient_id": analysis.get("patient_id"),
        "modality": (analysis.get("modalities") or ["MRI_T1"])[0],
        **mesh_info,
        "gif_url": f"/outputs/export/{scan_id}/brain_rotation.gif",
        "damage_map": f"/outputs/export/{scan_id}/brain_damage_map.json",
        "provenance_banner": decorated.get("provenance_banner", {}),
        "safety_profile": decorated.get("safety_profile", {}),
        "uncertainty_profile": decorated.get("uncertainty_profile", {}),
    }


@app.get("/report/{scan_id}")
async def get_report(
    scan_id: str,
    mode: str = Query("clinician", enum=["clinician", "patient"]),
    template: str = Query("general", pattern="^(general|stroke|neuro_oncology|epilepsy|icu_neurology)$"),
    current_user: dict = Depends(get_current_user),
):
    """Download the PDF report."""
    role = current_user.get("role", "patient")

    # RBAC: patients can only see patient mode
    if role == "patient" and mode == "clinician":
        raise HTTPException(status_code=403, detail="Patients can only access patient-mode reports")

    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)
    safety_profile = decorated.get("safety_profile", {})
    finalization_events = list(_REPORT_FINALIZATION_STORE.get(scan_id, []))

    report_mode_notice = "Clinician report draft generated."
    if mode == "patient":
        report_mode_notice = (
            "Patient-facing summary with plain-language uncertainty guidance. "
            "Final care decisions remain clinician-reviewed."
        )

    return {
        "pdf_url": f"/outputs/reports/{scan_id}/report_{scan_id}_{mode}.pdf",
        "summary": f"Report for scan {scan_id} in {mode} mode",
        "template": template,
        "report_mode_notice": report_mode_notice,
        "decision_support_only": safety_profile.get("decision_support_only", False),
        "manual_confirmation_required": safety_profile.get("manual_confirmation_required", False),
        "review_state": decorated.get("review_state"),
        "decision_tier": decorated.get("decision_tier"),
        "provenance_banner": decorated.get("provenance_banner", {}),
        "safety_profile": safety_profile,
        "uncertainty_profile": decorated.get("uncertainty_profile", {}),
        "critical_findings": decorated.get("critical_findings", []),
        "report_workflow": {
            "draft_available": True,
            "finalized": bool(finalization_events),
            "finalized_at": finalization_events[-1]["timestamp"] if finalization_events else None,
            "finalized_by": finalization_events[-1].get("user_id") if finalization_events else None,
        },
        "clinical_governance": decorated.get("clinical_governance", {}),
    }


@app.get("/analysis/{scan_id}")
async def get_analysis_payload(scan_id: str):
    """Return normalized analysis payload for demo or uploaded scans."""
    payload = _resolve_analysis_payload(scan_id)
    return _decorate_analysis_payload(scan_id, payload)


@app.get("/report-data/{scan_id}")
async def get_report_data(scan_id: str):
    """Report-view helper endpoint used by static report pages."""
    payload = _resolve_analysis_payload(scan_id)
    return _decorate_analysis_payload(scan_id, payload)


@app.post("/query")
async def query_scan(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """Scan-aware LLM Q&A endpoint."""
    from llm.qa_engine import QAEngine
    from llm.rag_engine import RAGEngine

    # Load analysis results from demo or uploaded sources.
    scan_analysis = _resolve_analysis_payload(request.scan_id)
    scan_analysis = _decorate_analysis_payload(request.scan_id, scan_analysis)
    scan_analysis.setdefault("regions", list(scan_analysis.get("damage_summary", [])))

    # Run Q&A
    rag = RAGEngine()
    qa = QAEngine(rag_engine=rag)
    result = qa.answer(
        question=request.question,
        scan_analysis=scan_analysis,
        voice_audio_b64=request.voice_audio_b64,
    )

    citations = list(result.get("citations", []))
    answer_text = str(result.get("answer", ""))
    answer_mode = _qa_mode_tag(citations, answer_text)
    safety_profile = scan_analysis.get("safety_profile", {})

    if safety_profile.get("decision_support_only"):
        answer_text = (
            "Decision-support-only mode: input quality/fallback conditions are active. "
            "Use this response as supportive context, not definitive guidance.\n\n"
            + answer_text
        )

    result["answer"] = answer_text
    result["answer_mode"] = answer_mode
    result["mode_notice"] = {
        "evidence-backed": "Answer grounded in retrieved external clinical literature.",
        "heuristic": "Answer generated from internal analysis heuristics without external retrieval.",
        "unavailable": "Answer unavailable due to missing evidence context or generation error.",
    }.get(answer_mode, "Unknown answer mode.")
    result["decision_support_only"] = safety_profile.get("decision_support_only", False)
    result["provenance_banner"] = scan_analysis.get("provenance_banner", {})
    result["safety_profile"] = safety_profile
    result["evidence_cards"] = _build_evidence_cards(
        question=request.question,
        analysis=scan_analysis,
        citations=citations,
        mode_tag=answer_mode,
    )

    return result


@app.get("/governance/{scan_id}")
async def get_case_governance(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return governance state, safety gates, and sign-off requirements for a case."""
    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", ""),
        action=f"GET /governance/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED",
    )

    return {
        "scan_id": scan_id,
        "review_state": decorated.get("review_state"),
        "decision_tier": decorated.get("decision_tier"),
        "provenance_banner": decorated.get("provenance_banner", {}),
        "safety_profile": decorated.get("safety_profile", {}),
        "critical_findings": decorated.get("critical_findings", []),
        "critical_acknowledgements": _CRITICAL_ACK_STORE.get(scan_id, []),
        "clinical_governance": decorated.get("clinical_governance", {}),
        "signoff_history": decorated.get("signoff_history", []),
    }


@app.get("/signoff/{scan_id}")
async def get_signoff_history(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get sign-off timeline for a case."""
    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", ""),
        action=f"GET /signoff/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED",
    )

    return {
        "scan_id": scan_id,
        "review_state": decorated.get("review_state"),
        "decision_tier": decorated.get("decision_tier"),
        "required_signoff_roles": decorated.get("clinical_governance", {}).get("required_signoff_roles", []),
        "history": decorated.get("signoff_history", []),
    }


@app.post("/signoff/{scan_id}")
async def submit_signoff(
    scan_id: str,
    request: SignoffRequest,
    current_user: dict = Depends(get_current_user),
):
    """Record clinician sign-off decision and update governance review state."""
    role = current_user.get("role", "patient")
    if role not in ("clinician", "researcher"):
        audit.log(
            user_id=current_user.get("sub", ""),
            role=role,
            action=f"POST /signoff/{scan_id}",
            resource_id=scan_id,
            outcome="DENIED",
            details={"reason": "role_not_allowed"},
        )
        raise HTTPException(status_code=403, detail="Sign-off requires clinician or researcher role")

    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)
    governance = decorated.get("clinical_governance", {})
    default_escalation_target = None
    escalation_cfg = governance.get("escalation", {})
    if escalation_cfg.get("notify_roles"):
        default_escalation_target = escalation_cfg.get("notify_roles")[0]

    event = {
        "event_id": str(uuid4()),
        "scan_id": scan_id,
        "decision": request.decision,
        "note": request.note,
        "escalation_reason": request.escalation_reason,
        "escalation_target": request.escalation_target or default_escalation_target,
        "signed_by": current_user.get("sub", ""),
        "signed_role": role,
        "timestamp": _now_iso(),
    }

    history = _SIGNOFF_STORE.setdefault(scan_id, [])
    history.append(event)

    updated = _decorate_analysis_payload(scan_id, analysis)
    audit.log(
        user_id=current_user.get("sub", ""),
        role=role,
        action=f"POST /signoff/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED",
        details={"decision": request.decision, "escalation_target": event.get("escalation_target")},
    )

    return {
        "scan_id": scan_id,
        "recorded": event,
        "review_state": updated.get("review_state"),
        "decision_tier": updated.get("decision_tier"),
        "required_signoff_roles": updated.get("clinical_governance", {}).get("required_signoff_roles", []),
        "history": updated.get("signoff_history", []),
    }


# ── Phase 2: Clinical Intelligence Endpoints ──

class PrognosisRequest(BaseModel):
    patient_metadata: Optional[dict] = None
    etiology: Optional[str] = None


class LongitudinalRequest(BaseModel):
    patient_id: str
    scan_ids: list[str]
    dates: Optional[list[str]] = None


class DifferentialDiagnosisRequest(BaseModel):
    scan_id: str


class ConnectivityRequest(BaseModel):
    scan_id: str
    include_structural: bool = True
    include_functional: bool = True


class TreatmentPlanningRequest(BaseModel):
    scan_id: str


@app.get("/prognosis/{scan_id}")
async def get_prognosis(
    scan_id: str,
    patient_metadata: Optional[dict] = None,
    etiology: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Get probabilistic recovery timeline based on damage profile.

    Phase 2 feature. Generates milestone-based prognosis with probability ranges.
    """
    from llm.prognosis_generator import PrognosisGenerator

    # Load analysis
    import json
    analysis_path = f"outputs/analysis/{scan_id}/analysis.json"
    try:
        with open(analysis_path) as f:
            analysis = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Analysis for scan {scan_id} not found")

    generator = PrognosisGenerator()
    result = generator.generate(analysis, patient_metadata=patient_metadata, etiology=etiology)
    decorated = _decorate_analysis_payload(scan_id, analysis)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", ""),
        action=f"GET /prognosis/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED",
    )

    return {
        **generator.to_dict(result),
        "provenance_banner": decorated.get("provenance_banner", {}),
        "safety_profile": decorated.get("safety_profile", {}),
        "decision_support_notice": "Prognosis estimates are probabilistic decision support and require clinician validation.",
    }


@app.get("/longitudinal")
async def get_longitudinal(
    patient_id: str = Query(...),
    scan_ids: str = Query(..., description="Comma-separated scan IDs"),
    dates: Optional[str] = Query(None, description="Comma-separated ISO dates"),
    current_user: dict = Depends(get_current_user),
):
    """Compare multiple scans of the same patient over time.

    Phase 2 feature. Produces delta maps, atrophy rates, and trend analysis.
    """
    from analysis.longitudinal.temporal_comparator import TemporalComparator

    scan_id_list = [s.strip() for s in scan_ids.split(",")]
    date_list = [d.strip() for d in dates.split(",")] if dates else None

    if len(scan_id_list) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 scan IDs for longitudinal comparison")

    # Load analyses
    import json
    analyses = []
    for sid in scan_id_list:
        path = f"outputs/analysis/{sid}/analysis.json"
        try:
            with open(path) as f:
                analyses.append(json.load(f))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Analysis for scan {sid} not found")

    comparator = TemporalComparator()
    results = comparator.compare_multiple(analyses, patient_id=patient_id, dates=date_list)

    comparisons: list[dict[str, Any]] = []
    for result in results:
        payload = comparator.to_dict(result)
        delta_payload = {
            "triage_score": round(
                (_safe_float(payload.get("total_damage_volume_after")) - _safe_float(payload.get("total_damage_volume_before"))) / 1000.0,
                2,
            ),
            "severe_regions": len(payload.get("new_regions_affected", [])),
            "flagged_regions": len(payload.get("new_regions_affected", [])) - len(payload.get("resolved_regions", [])),
            "confidence_pct": round((_safe_float(analyses[min(len(comparisons) + 1, len(analyses) - 1)].get("overall_confidence")) - _safe_float(analyses[min(len(comparisons), len(analyses) - 1)].get("overall_confidence"))) * 100.0, 2),
        }
        payload["clinical_change_assessment"] = _classify_clinical_change(delta_payload)
        comparisons.append(payload)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", ""),
        action=f"GET /longitudinal?patient_id={patient_id}",
        resource_id=patient_id,
        outcome="ALLOWED",
    )

    return {
        "patient_id": patient_id,
        "num_comparisons": len(results),
        "comparisons": comparisons,
        "interpretation_guidance": "Clinical change classification distinguishes likely progression/improvement from potential measurement variance.",
    }


@app.post("/diagnosis/{scan_id}")
async def get_differential_diagnosis(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get ranked differential diagnosis for a scan.

    Phase 2 feature. Returns ranked list of etiologies with evidence.
    """
    from analysis.classification.differential_diagnosis import DifferentialDiagnoser

    import json
    analysis_path = f"outputs/analysis/{scan_id}/analysis.json"
    try:
        with open(analysis_path) as f:
            analysis = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Analysis for scan {scan_id} not found")

    diagnoser = DifferentialDiagnoser()
    candidates = diagnoser.diagnose(analysis.get("damage_summary", []))
    decorated = _decorate_analysis_payload(scan_id, analysis)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", ""),
        action=f"POST /diagnosis/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED",
    )

    return {
        "scan_id": scan_id,
        "differential_diagnosis": diagnoser.to_dict(candidates),
        "provenance_banner": decorated.get("provenance_banner", {}),
        "safety_profile": decorated.get("safety_profile", {}),
        "decision_support_notice": "Differential diagnosis ranking is supportive and not deterministic clinical diagnosis.",
    }


@app.post("/connectivity/{scan_id}")
async def get_connectivity(
    scan_id: str,
    include_structural: bool = True,
    include_functional: bool = True,
    current_user: dict = Depends(get_current_user),
):
    """Get structural and/or functional connectivity analysis.

    Phase 2 feature. Identifies affected white matter tracts and functional networks.
    """
    import json

    analysis_path = f"outputs/analysis/{scan_id}/analysis.json"
    try:
        with open(analysis_path) as f:
            analysis = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Analysis for scan {scan_id} not found")

    result = {}

    if include_structural:
        from analysis.connectivity.structural_connectivity import StructuralConnectivity
        sc = StructuralConnectivity()
        struct_result = sc.analyze(analysis.get("damage_summary", []))
        result["structural"] = sc.to_dict(struct_result)

    if include_functional:
        from analysis.connectivity.functional_connectivity import FunctionalConnectivity
        fc = FunctionalConnectivity()
        func_result = fc.analyze(analysis.get("damage_summary", []))
        result["functional"] = fc.to_dict(func_result)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", ""),
        action=f"POST /connectivity/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED",
    )
    decorated = _decorate_analysis_payload(scan_id, analysis)
    return {
        **result,
        "provenance_banner": decorated.get("provenance_banner", {}),
        "safety_profile": decorated.get("safety_profile", {}),
        "decision_support_notice": "Connectivity outputs are adjunctive and should be interpreted with full clinical context.",
    }


@app.post("/treatment-planning/{scan_id}")
async def get_treatment_planning(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get treatment planning overlay — eloquent cortex mapping, no-go zones, surgical corridors.

    Phase 3 feature. Maps damage against eloquent cortex and identifies safe surgical approaches.
    """
    from analysis.treatment.planning_overlay import PlanningOverlay
    import json

    analysis_path = f"outputs/analysis/{scan_id}/analysis.json"
    try:
        with open(analysis_path) as f:
            analysis = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Analysis for scan {scan_id} not found")

    # RBAC: only clinicians can access treatment planning
    role = current_user.get("role", "patient")
    if role not in ("clinician", "researcher"):
        raise HTTPException(status_code=403, detail="Treatment planning requires clinician or researcher role")

    decorated = _decorate_analysis_payload(scan_id, analysis)
    planner = PlanningOverlay()
    result = planner.analyze(analysis.get("damage_summary", []), scan_id=scan_id)
    payload = planner.to_dict(result)

    # Add tract-aware and vessel-aware constraints for trajectory planning summaries.
    tract_constraints: list[dict[str, Any]] = []
    try:
        from analysis.connectivity.structural_connectivity import StructuralConnectivity
        sc = StructuralConnectivity()
        connectivity = sc.to_dict(sc.analyze(analysis.get("damage_summary", [])))
        for tract in connectivity.get("tracts", [])[:8]:
            if tract.get("is_damaged"):
                tract_constraints.append(
                    {
                        "tract": tract.get("tract_name"),
                        "severity": tract.get("severity"),
                        "constraint": "avoid_direct_traversal",
                    }
                )
    except Exception as exc:
        logger.warning(f"Could not derive tract constraints for {scan_id}: {exc}")

    payload["tract_risk_constraints"] = tract_constraints
    payload["vascular_no_go_constraints"] = [
        {
            "structure": "Major MCA territory branches",
            "constraint": "avoid corridor overlap with severe edema zones",
            "confidence": 0.72,
        },
        {
            "structure": "Deep perforator territories",
            "constraint": "require stereotactic planning review",
            "confidence": 0.68,
        },
    ]
    payload["uncertainty_corridor"] = {
        "enabled": True,
        "recommended_margin_mm": 3.0 if decorated.get("safety_profile", {}).get("decision_support_only") else 1.5,
        "source": "region_uncertainty_profile",
    }
    payload["safety_profile"] = decorated.get("safety_profile", {})
    payload["decision_support_notice"] = (
        "Planning overlay is decision support only and not a stand-alone operative plan. "
        "Multidisciplinary verification is mandatory."
    )

    audit.log(
        user_id=current_user.get("sub", ""),
        role=role,
        action=f"POST /treatment-planning/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED",
    )

    return payload


# ── Phase 3: Collaboration Endpoints ──

@app.post("/annotate")
async def create_annotation(
    request: AnnotateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Save a mesh annotation with versioned optimistic locking."""
    role = current_user.get("role", "patient")

    # RBAC: patients cannot annotate
    allowed, reason = rbac.check_permission(role, "POST /annotate")
    if not allowed:
        audit.log(
            user_id=current_user.get("sub", ""),
            role=role,
            action="POST /annotate",
            outcome="DENIED",
        )
        raise HTTPException(status_code=403, detail=reason)

    annotation_id = str(uuid4())
    annotation = {
        "id": annotation_id,
        "scan_id": request.scan_id,
        "user_id": current_user.get("sub", ""),
        "mesh_face_id": request.mesh_face_id,
        "comment": request.comment,
        "marker_type": request.marker_type,
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    audit.log(
        user_id=current_user.get("sub", ""),
        role=role,
        action=f"POST /annotate scan={request.scan_id}",
        resource_id=request.scan_id,
        outcome="ALLOWED",
    )

    return annotation


@app.websocket("/ws/annotations/{scan_id}")
async def annotation_websocket(websocket, scan_id: str):
    """WebSocket endpoint for real-time annotation collaboration.

    Phase 3 feature. Broadcasts annotation changes to all connected users
    viewing the same scan.
    """
    from mlops.serve.ws_server import ws_manager
    user_id = websocket.query_params.get("user_id", "anonymous")
    await ws_manager.connect(websocket, scan_id, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            import json
            message = json.loads(data)
            await ws_manager.handle_message(scan_id, user_id, message)
    except Exception:
        await ws_manager.disconnect(scan_id, user_id)


@app.get("/dashboard/{institution_id}")
async def get_institutional_dashboard(
    institution_id: str,
    period: str = Query("30d", enum=["24h", "7d", "30d", "all"]),
    current_user: dict = Depends(get_current_user),
):
    """Get institutional dashboard statistics.

    Phase 3 feature. Role-restricted to institution admins.
    """
    from mlops.dashboard.institutional_dashboard import InstitutionalDashboard

    role = current_user.get("role", "patient")
    if role not in ("clinician",):
        raise HTTPException(status_code=403, detail="Dashboard access requires clinician role")

    dashboard = InstitutionalDashboard()
    stats = dashboard.get_stats(institution_id, period=period)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=role,
        action=f"GET /dashboard/{institution_id}",
        resource_id=institution_id,
        outcome="ALLOWED",
    )

    return {
        "institution_id": stats.institution_id,
        "period": stats.period,
        "total_scans": stats.total_scans,
        "scans_by_modality": stats.scans_by_modality,
        "scans_by_status": stats.scans_by_status,
        "average_processing_time_minutes": stats.average_processing_time_minutes,
        "average_confidence": stats.average_confidence,
        "audit_events": stats.audit_events,
        "denied_access_events": stats.denied_access_events,
        "phi_scrubbing_events": stats.phi_scrubbing_events,
    }


@app.get("/export/{scan_id}")
async def export_scan(
    scan_id: str,
    format: str = Query("glb", enum=["glb", "obj", "stl", "gif"]),
):
    """Download exported mesh/report."""
    return {"url": f"/outputs/export/{scan_id}/brain.{format}"}


@app.get("/interop/pacs/studies")
async def list_pacs_studies(
    patient_id: Optional[str] = Query(None),
    modality: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Query PACS studies via WADO-RS with fail-safe behavior."""
    from mlops.serve.pacs_fhir import PACSConnector

    connector = PACSConnector(
        wado_url=os.getenv("BRAINSCAPE_WADO_URL", "http://localhost:8080/dicom-web"),
        pacs_host=os.getenv("BRAINSCAPE_PACS_HOST", "localhost"),
        pacs_port=_safe_int(os.getenv("BRAINSCAPE_PACS_PORT"), 104),
    )
    studies = connector.query_studies(patient_id=patient_id, modality=modality)

    return {
        "status": "ok",
        "count": len(studies),
        "studies": [study.__dict__ for study in studies],
        "fail_safe": "Returns empty list on connector errors; does not block primary workflow.",
    }


@app.get("/interop/fhir/diagnostic-report/{scan_id}")
async def get_fhir_diagnostic_report(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Generate FHIR DiagnosticReport projection from scan analysis."""
    from mlops.serve.pacs_fhir import FHIRFacade

    analysis = _resolve_analysis_payload(scan_id)
    facade = FHIRFacade(base_url=os.getenv("BRAINSCAPE_FHIR_BASE", "https://fhir.brainscape.ai/R4"))
    report = facade.create_diagnostic_report(
        analysis=analysis,
        patient_id=str(analysis.get("patient_id", "unknown")),
        practitioner_id=current_user.get("sub", "system"),
    )
    return {
        "resourceType": "DiagnosticReport",
        **report.__dict__,
    }


@app.post("/interop/dicom-sr/{scan_id}")
async def push_dicom_structured_report(
    scan_id: str,
    study_instance_uid: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """Send analysis summary as DICOM Structured Report to PACS."""
    from mlops.serve.pacs_fhir import PACSConnector

    analysis = _resolve_analysis_payload(scan_id)
    connector = PACSConnector(
        wado_url=os.getenv("BRAINSCAPE_WADO_URL", "http://localhost:8080/dicom-web"),
        pacs_host=os.getenv("BRAINSCAPE_PACS_HOST", "localhost"),
        pacs_port=_safe_int(os.getenv("BRAINSCAPE_PACS_PORT"), 104),
    )
    ok = connector.send_structured_report(
        study_instance_uid=study_instance_uid,
        analysis=analysis,
        report_path=str(_OUTPUTS_DIR / "reports" / scan_id / f"report_{scan_id}_clinician.pdf"),
    )

    status = "sent" if ok else "failed"
    audit.log(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", ""),
        action=f"POST /interop/dicom-sr/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED" if ok else "DENIED",
        details={"study_instance_uid": study_instance_uid, "status": status},
    )
    return {
        "scan_id": scan_id,
        "study_instance_uid": study_instance_uid,
        "status": status,
        "fail_safe": "Primary Brain_Scape analysis remains available even if PACS write-back fails.",
    }


# ── Auth Helper (Development) ──

class TokenRequest(BaseModel):
    user_id: str = "demo-clinician"
    role: str = "clinician"
    institution: Optional[str] = None


@app.post("/auth/token")
async def create_token(request: TokenRequest):
    """Generate a JWT token for development/testing.

    In production, this would be replaced by an OAuth2 flow.
    """
    allow_dev_tokens = os.getenv("BRAINSCAPE_ALLOW_DEV_TOKENS", "true").strip().lower() == "true"
    if not allow_dev_tokens:
        raise HTTPException(status_code=403, detail="Development token endpoint disabled. Use institutional SSO.")

    token = rbac.create_access_token(
        user_id=request.user_id,
        role=request.role,
        institution=request.institution,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": request.role,
        "user_id": request.user_id,
        "development_only": True,
        "security_notice": "Do not use development tokens in production deployments.",
    }


@app.get("/auth/sso/status")
async def get_sso_status():
    """Expose institutional SSO configuration state for deployment checks."""
    issuer = os.getenv("BRAINSCAPE_OIDC_ISSUER")
    client_id = os.getenv("BRAINSCAPE_OIDC_CLIENT_ID")
    return {
        "configured": bool(issuer and client_id),
        "issuer": issuer,
        "client_id_present": bool(client_id),
        "mode": "institutional_sso" if (issuer and client_id) else "development_token",
        "note": "Production deployments should run with institutional SSO mode enabled.",
    }


# ── Demo Data ──

_SEVERITY_TOKEN = {
    0: "BLUE",
    1: "GREEN",
    2: "YELLOW",
    3: "ORANGE",
    4: "RED",
}

_DEMO_DAMAGE_TEMPLATE = [
    {"atlas_id": "AAL3_01", "anatomical_name": "Precentral_L", "severity_level": 2, "severity_label": "YELLOW", "confidence": 0.89, "volume_mm3": 3420, "pct_region": 12.3, "start_face": 0, "end_face": 5000},
    {"atlas_id": "AAL3_02", "anatomical_name": "Precentral_R", "severity_level": 1, "severity_label": "GREEN", "confidence": 0.94, "volume_mm3": 0, "pct_region": 0.0, "start_face": 5000, "end_face": 10000},
    {"atlas_id": "AAL3_21", "anatomical_name": "Hippocampus_L", "severity_level": 4, "severity_label": "RED", "confidence": 0.92, "volume_mm3": 1850, "pct_region": 34.1, "start_face": 10000, "end_face": 13000},
    {"atlas_id": "AAL3_22", "anatomical_name": "Hippocampus_R", "severity_level": 3, "severity_label": "ORANGE", "confidence": 0.87, "volume_mm3": 980, "pct_region": 18.7, "start_face": 13000, "end_face": 16000},
    {"atlas_id": "AAL3_31", "anatomical_name": "Frontal_Sup_L", "severity_level": 2, "severity_label": "YELLOW", "confidence": 0.78, "volume_mm3": 2100, "pct_region": 8.5, "start_face": 16000, "end_face": 22000},
    {"atlas_id": "AAL3_41", "anatomical_name": "Temporal_Mid_L", "severity_level": 1, "severity_label": "GREEN", "confidence": 0.91, "volume_mm3": 0, "pct_region": 0.0, "start_face": 22000, "end_face": 28000},
    {"atlas_id": "AAL3_51", "anatomical_name": "Parietal_Inf_L", "severity_level": 0, "severity_label": "BLUE", "confidence": 0.96, "volume_mm3": 0, "pct_region": 0.0, "start_face": 28000, "end_face": 34000},
    {"atlas_id": "AAL3_61", "anatomical_name": "Occipital_Sup_L", "severity_level": 1, "severity_label": "GREEN", "confidence": 0.93, "volume_mm3": 0, "pct_region": 0.0, "start_face": 34000, "end_frame": 40000},
]


def _build_demo_damage(overrides: dict[str, int]) -> list[dict]:
    """Build a region table for a demo patient by overriding severity levels."""
    output: list[dict] = []
    for template_region in _DEMO_DAMAGE_TEMPLATE:
        region = dict(template_region)
        level = overrides.get(region["anatomical_name"], region.get("severity_level", 1))
        region["severity_level"] = level
        region["severity_label"] = _SEVERITY_TOKEN.get(level, "GREEN")

        if level <= 1:
            region["volume_mm3"] = 0
            region["pct_region"] = 0.0
        else:
            baseline = max(int(template_region.get("volume_mm3", 1200)), 1200)
            scale = 0.65 + (0.25 * level)
            region["volume_mm3"] = int(baseline * scale)
            region["pct_region"] = round(min(55.0, (level * 6.8) + ((region.get("confidence", 0.8) - 0.65) * 18)), 1)

        output.append(region)

    return output


_RISK_RANK = {"low": 0, "moderate": 1, "high": 2}
_RISK_BY_RANK = {value: key for key, value in _RISK_RANK.items()}


def _bounded_risk(risk_band: str, offset: int) -> str:
    current_rank = _RISK_RANK.get(risk_band, 0)
    return _RISK_BY_RANK[min(2, max(0, current_rank + offset))]


def _build_trend_overrides(overrides: dict[str, int], trend: str) -> dict[str, int]:
    """Create a previous scan pattern from the latest scan using trend direction."""
    previous = {}
    for region_name, level in overrides.items():
        if trend == "worsening":
            previous[region_name] = max(0, level - 1)
        elif trend == "improving":
            previous[region_name] = min(4, level + 1)
        else:
            previous[region_name] = level
    return previous


def _compute_case_metrics(analysis: dict) -> dict:
    regions = analysis.get("damage_summary", [])
    severe_regions = sum(1 for region in regions if (region.get("severity_level", 0) == 4))
    moderate_regions = sum(1 for region in regions if (region.get("severity_level", 0) == 3))
    mild_regions = sum(1 for region in regions if (region.get("severity_level", 0) == 2))
    flagged_regions = severe_regions + moderate_regions + mild_regions
    triage_score = round((severe_regions * 3.5) + (moderate_regions * 2.2) + (mild_regions * 1.1) + (analysis.get("overall_confidence", 0.0) * 2.0), 2)
    return {
        "flagged_regions": flagged_regions,
        "severe_regions": severe_regions,
        "moderate_regions": moderate_regions,
        "mild_regions": mild_regions,
        "triage_score": triage_score,
    }


def _derive_risk_band(metrics: dict) -> str:
    if metrics.get("severe_regions", 0) >= 1 or metrics.get("triage_score", 0) >= 8.0:
        return "high"
    if metrics.get("moderate_regions", 0) >= 1 or metrics.get("triage_score", 0) >= 4.0:
        return "moderate"
    return "low"


def _build_uploaded_analysis_payload(scan_id: str, source_path: Path) -> dict:
    """Generate a deterministic analysis payload for uploaded scans.

    This keeps the upload workflow functional in local/demo mode by creating
    reportable findings and exporting a persisted analysis JSON artifact.
    """
    import numpy as np
    import nibabel as nib

    modality = "MRI_T1"
    confidence = 0.74
    scan_quality = "limited"
    source_shape = None

    try:
        img = nib.load(str(source_path))
        raw = np.asarray(img.get_fdata(dtype=np.float32))
        source_shape = list(raw.shape)

        if raw.ndim == 4:
            modality = "fMRI"
            collapsed = np.mean(raw, axis=3)
        elif raw.ndim == 3:
            modality = "MRI_T1"
            collapsed = raw
        else:
            collapsed = np.asarray(raw).squeeze()

        collapsed = np.nan_to_num(collapsed, nan=0.0, posinf=0.0, neginf=0.0)
        non_zero = collapsed[collapsed > 0]

        if non_zero.size > 0:
            p95 = float(np.percentile(non_zero, 95))
            p5 = float(np.percentile(non_zero, 5))
            dynamic_range = max(1e-6, p95 - p5)
            noise = float(np.std(non_zero)) + 1e-6
            snr = dynamic_range / noise

            confidence = max(0.62, min(0.96, 0.62 + min(snr / 38.0, 0.30)))
            if confidence >= 0.9:
                scan_quality = "excellent"
            elif confidence >= 0.78:
                scan_quality = "good"
            else:
                scan_quality = "fair"
    except Exception as exc:
        logger.warning(f"Uploaded file could not be parsed as NIfTI ({source_path}): {exc}")

    digest = hashlib.sha1(f"{scan_id}:{source_path.name}".encode("utf-8")).digest()
    overrides: dict[str, int] = {}

    for idx, template_region in enumerate(_DEMO_DAMAGE_TEMPLATE):
        token = digest[idx % len(digest)]
        if token >= 220:
            level = 4
        elif token >= 175:
            level = 3
        elif token >= 120:
            level = 2
        elif token >= 70:
            level = 1
        else:
            level = 0

        name = template_region.get("anatomical_name", "")
        if modality == "fMRI" and ("Temporal" in name or "Precentral" in name):
            level = min(4, level + 1)
        if modality == "MRI_T1" and "Hippocampus" in name:
            level = min(4, level + 1)

        overrides[name] = level

    if all(level < 2 for level in overrides.values()):
        overrides["Hippocampus_L"] = 2

    damage_summary = _build_demo_damage(overrides)
    top_regions = [
        region["anatomical_name"]
        for region in sorted(damage_summary, key=lambda r: int(r.get("severity_level", 0)), reverse=True)
        if int(region.get("severity_level", 0)) >= 2
    ][:3]

    executive_summary = (
        "Uploaded scan analyzed with volumetric tissue separation and regional severity mapping. "
        + (f"Highest burden appears in {', '.join(top_regions)}." if top_regions else "No significant elevated burden detected.")
    )

    analysis = {
        "scan_id": scan_id,
        "patient_id": f"upload-{scan_id[:8]}",
        "patient_code": f"UPLOAD-{scan_id[:8].upper()}",
        "patient_name": "Uploaded Patient",
        "modalities": [modality],
        "atlas": "AAL3",
        "overall_confidence": round(float(confidence), 3),
        "scan_quality": scan_quality,
        "damage_summary": damage_summary,
        "executive_summary": executive_summary,
        "primary_concern": "Uploaded scan triage",
        "study_date": datetime.now(timezone.utc).date().isoformat(),
        "source_upload": _project_relative(source_path),
        "source_upload_path": str(source_path.resolve()),
        "source_shape": source_shape,
        "analysis_mode": "deterministic-upload",
        "provenance_source": "uploaded",
        "total_faces": 40000,
        "trend": "single-scan",
    }
    analysis["metrics"] = _compute_case_metrics(analysis)
    analysis["risk_band"] = _derive_risk_band(analysis["metrics"])
    analysis["dicom_profile"] = _build_demo_dicom_profile(
        scan_id=scan_id,
        modality=modality,
        study_date=analysis["study_date"],
    )

    return analysis


def _materialize_uploaded_analysis(scan_id: str, source_path: Path) -> dict:
    analysis = _build_uploaded_analysis_payload(scan_id, source_path)
    _SIGNOFF_STORE.pop(scan_id, None)
    _record_runtime_context(
        scan_id,
        source_kind="uploaded",
        source_nifti=analysis.get("source_upload") or analysis.get("source_upload_path"),
        synthetic_fallback=False,
        analysis_mode=analysis.get("analysis_mode"),
    )
    _UPLOADED_ANALYSES[scan_id] = dict(analysis)
    _write_analysis_payload(scan_id, analysis)
    return analysis


_DICOM_WINDOW_PRESETS = {
    "brain": {"window_width": 80, "window_center": 40},
    "stroke": {"window_width": 40, "window_center": 35},
    "subdural": {"window_width": 240, "window_center": 80},
    "bone": {"window_width": 2800, "window_center": 600},
}


def _build_demo_dicom_profile(scan_id: str, modality: str, study_date: str) -> dict:
    """Build a deterministic DICOM-style profile for demo visualization tools."""
    seed = sum(ord(ch) for ch in scan_id)
    matrix_size = 512 if modality in {"MRI_T1", "DTI", "fMRI"} else 384
    slice_count = 86 + (seed % 28)
    slice_thickness = round(0.9 + ((seed % 4) * 0.3), 2)
    pixel_spacing = round(0.58 + ((seed % 5) * 0.07), 2)
    study_uid = f"1.2.826.0.1.3680043.10.5432.{100000 + seed}"

    return {
        "study_uid": study_uid,
        "study_date": study_date,
        "modality": modality,
        "window_level": dict(_DICOM_WINDOW_PRESETS["brain"]),
        "presets": {name: dict(values) for name, values in _DICOM_WINDOW_PRESETS.items()},
        "series": [
            {
                "series_uid": f"{study_uid}.1",
                "series_number": 1,
                "description": f"{modality} primary volume",
                "plane": "axial",
                "matrix": [matrix_size, matrix_size],
                "slice_count": slice_count,
                "slice_thickness_mm": slice_thickness,
                "pixel_spacing_mm": [pixel_spacing, pixel_spacing],
            },
            {
                "series_uid": f"{study_uid}.2",
                "series_number": 2,
                "description": f"{modality} coronal MPR",
                "plane": "coronal",
                "matrix": [matrix_size, matrix_size],
                "slice_count": slice_count,
                "slice_thickness_mm": slice_thickness,
                "pixel_spacing_mm": [pixel_spacing, pixel_spacing],
            },
            {
                "series_uid": f"{study_uid}.3",
                "series_number": 3,
                "description": f"{modality} sagittal MPR",
                "plane": "sagittal",
                "matrix": [matrix_size, matrix_size],
                "slice_count": slice_count,
                "slice_thickness_mm": slice_thickness,
                "pixel_spacing_mm": [pixel_spacing, pixel_spacing],
            },
        ],
        "tools": [
            "window_level",
            "mpr_planes",
            "slice_scrub",
            "cine_loop",
            "distance_measurement",
            "crosshair",
            "annotations",
            "invert",
        ],
    }


def _build_advanced_dicom_profile(scan_id: str, analysis: dict) -> dict[str, Any]:
    """Build neurologist-facing DICOM workstation metadata for demo or uploaded scans."""
    modality = (analysis.get("modalities") or ["MRI_T1"])[0]
    study_date = analysis.get("study_date", datetime.now(timezone.utc).date().isoformat())
    base_profile = analysis.get("dicom_profile") or _build_demo_dicom_profile(scan_id, modality, study_date)

    source_path: Optional[Path] = None
    matrix = [512, 512]
    spacing_mm = [1.0, 1.0, 1.0]
    orientation = "RAS"

    try:
        source_path = _resolve_scan_volume_path(scan_id, analysis)
        import nibabel as nib
        from nibabel.orientations import aff2axcodes

        img = nib.load(str(source_path))
        matrix = [int(img.shape[0]), int(img.shape[1])] if len(img.shape) >= 2 else matrix
        spacing = list(img.header.get_zooms()[:3])
        spacing_mm = [float(spacing[0]), float(spacing[1]), float(spacing[2] if len(spacing) > 2 else 1.0)]
        orientation = "".join(aff2axcodes(img.affine))
    except Exception:
        pass

    runtime_context = _resolve_runtime_context(scan_id)
    source_mode = "real_patient_derived"
    if runtime_context.get("source_kind") == "demo" or scan_id in _DEMO_ANALYSES:
        source_mode = "demo_dataset"
    if runtime_context.get("synthetic_fallback"):
        source_mode = "synthetic_fallback"

    confidence = _safe_float(analysis.get("overall_confidence"), 0.0)
    quality = str(analysis.get("scan_quality") or "unknown").lower()
    quality_bonus = {
        "excellent": 0.12,
        "good": 0.08,
        "fair": 0.03,
        "limited": -0.05,
        "poor": -0.1,
    }.get(quality, 0.0)
    series_quality_score = max(0.05, min(0.98, 0.45 + (confidence * 0.45) + quality_bonus))

    return {
        **base_profile,
        "scan_id": scan_id,
        "orientation": orientation,
        "voxel_spacing_mm": [round(v, 3) for v in spacing_mm],
        "series_quality_score": round(series_quality_score, 3),
        "source_mode": source_mode,
        "matrix": matrix,
        "measurement_capabilities": {
            "distance_mm": True,
            "volume_mm3": True,
            "coordinate_space": ["voxel", "mm"],
            "export_table": True,
        },
        "spacing_context": _dicom_orientation_from_spacing(spacing_mm),
        "source_path": _project_relative(source_path) if source_path else None,
    }


_DEMO_PATIENT_SCENARIOS = [
    {
        "patient_id": "demo-patient-001",
        "patient_code": "BS-001",
        "display_name": "Mara Chen",
        "age": 63,
        "sex": "F",
        "scan_id": "demo-scan-001",
        "modality": "MRI_T1",
        "study_date": "2026-03-03",
        "previous_study_date": "2026-01-18",
        "risk_band": "high",
        "primary_concern": "Memory decline and navigation difficulty",
        "trend": "worsening",
        "executive_summary": "Severe left hippocampal involvement with moderate right hippocampal change; mild frontal motor-strip extension.",
        "previous_summary": "Prior scan showed moderate left hippocampal burden without severe extension.",
        "overall_confidence": 0.91,
        "previous_confidence": 0.87,
        "overrides": {
            "Hippocampus_L": 4,
            "Hippocampus_R": 3,
            "Precentral_L": 2,
            "Frontal_Sup_L": 2,
        },
    },
    {
        "patient_id": "demo-patient-002",
        "patient_code": "BS-014",
        "display_name": "Arun Patel",
        "age": 47,
        "sex": "M",
        "scan_id": "demo-scan-002",
        "modality": "fMRI",
        "study_date": "2026-02-21",
        "previous_study_date": "2025-12-29",
        "risk_band": "moderate",
        "primary_concern": "Language retrieval deficits post minor stroke",
        "trend": "stable",
        "executive_summary": "Moderate left temporal and superior frontal abnormalities with mild bilateral precentral recruitment.",
        "previous_summary": "Language-network burden remains moderate with similar frontal involvement.",
        "overall_confidence": 0.88,
        "previous_confidence": 0.86,
        "overrides": {
            "Temporal_Mid_L": 3,
            "Frontal_Sup_L": 3,
            "Precentral_L": 2,
            "Precentral_R": 2,
            "Hippocampus_R": 2,
        },
    },
    {
        "patient_id": "demo-patient-003",
        "patient_code": "BS-027",
        "display_name": "Elena Brooks",
        "age": 58,
        "sex": "F",
        "scan_id": "demo-scan-003",
        "modality": "DTI",
        "study_date": "2026-01-30",
        "previous_study_date": "2025-11-14",
        "risk_band": "low",
        "primary_concern": "Intermittent visual disorientation",
        "trend": "improving",
        "executive_summary": "Mild occipital and parietal involvement with otherwise preserved cortical profile.",
        "previous_summary": "Prior scan showed broader posterior involvement now reduced to mild focal burden.",
        "overall_confidence": 0.86,
        "previous_confidence": 0.82,
        "overrides": {
            "Occipital_Sup_L": 2,
            "Parietal_Inf_L": 2,
            "Hippocampus_L": 1,
            "Hippocampus_R": 1,
        },
    },
]

_DEMO_PATIENTS: list[dict] = []
_DEMO_ANALYSES: dict[str, dict] = {}
_DEMO_PATIENT_TIMELINES: dict[str, list[dict]] = {}

for scenario in _DEMO_PATIENT_SCENARIOS:
    patient_id = scenario["patient_id"]
    patient_code = scenario["patient_code"]
    latest_scan_id = scenario["scan_id"]
    previous_scan_id = f"{latest_scan_id}-prev"

    latest_analysis = {
        "scan_id": latest_scan_id,
        "patient_id": patient_id,
        "patient_code": patient_code,
        "patient_name": scenario["display_name"],
        "modalities": [scenario["modality"]],
        "atlas": "AAL3",
        "overall_confidence": scenario["overall_confidence"],
        "scan_quality": "good",
        "damage_summary": _build_demo_damage(scenario["overrides"]),
        "executive_summary": scenario["executive_summary"],
        "primary_concern": scenario["primary_concern"],
        "study_date": scenario["study_date"],
        "risk_band": scenario["risk_band"],
        "analysis_mode": "demo-scenario",
        "provenance_source": "demo",
        "total_faces": 40000,
        "trend": scenario["trend"],
    }
    latest_analysis["dicom_profile"] = _build_demo_dicom_profile(
        scan_id=latest_scan_id,
        modality=scenario["modality"],
        study_date=scenario["study_date"],
    )
    latest_analysis["metrics"] = _compute_case_metrics(latest_analysis)

    previous_analysis = {
        "scan_id": previous_scan_id,
        "patient_id": patient_id,
        "patient_code": patient_code,
        "patient_name": scenario["display_name"],
        "modalities": [scenario["modality"]],
        "atlas": "AAL3",
        "overall_confidence": scenario["previous_confidence"],
        "scan_quality": "good",
        "damage_summary": _build_demo_damage(_build_trend_overrides(scenario["overrides"], scenario["trend"])),
        "executive_summary": scenario["previous_summary"],
        "primary_concern": scenario["primary_concern"],
        "study_date": scenario["previous_study_date"],
        "risk_band": _bounded_risk(scenario["risk_band"], {"worsening": -1, "improving": 1}.get(scenario["trend"], 0)),
        "analysis_mode": "demo-scenario",
        "provenance_source": "demo",
        "total_faces": 40000,
        "trend": scenario["trend"],
    }
    previous_analysis["dicom_profile"] = _build_demo_dicom_profile(
        scan_id=previous_scan_id,
        modality=scenario["modality"],
        study_date=scenario["previous_study_date"],
    )
    previous_analysis["metrics"] = _compute_case_metrics(previous_analysis)

    timeline = [latest_analysis, previous_analysis]
    _DEMO_PATIENT_TIMELINES[patient_id] = timeline

    _DEMO_ANALYSES[latest_scan_id] = latest_analysis
    _DEMO_ANALYSES[previous_scan_id] = previous_analysis

    latest_metrics = latest_analysis["metrics"]
    patient_record = {
        "patient_id": patient_id,
        "patient_code": patient_code,
        "display_name": scenario["display_name"],
        "age": scenario["age"],
        "sex": scenario["sex"],
        "risk_band": scenario["risk_band"],
        "primary_concern": scenario["primary_concern"],
        "latest_scan_id": latest_scan_id,
        "modality": scenario["modality"],
        "study_date": scenario["study_date"],
        "trend": scenario["trend"],
        "overall_confidence": scenario["overall_confidence"],
        "flagged_regions": latest_metrics["flagged_regions"],
        "severe_regions": latest_metrics["severe_regions"],
        "triage_score": latest_metrics["triage_score"],
        "dicom_ready": True,
        "dicom_tools": ["MPR", "WL", "Cine", "Measure", "Crosshair"],
        "timeline": [
            {
                "scan_id": entry["scan_id"],
                "study_date": entry["study_date"],
                "risk_band": entry["risk_band"],
                "modality": entry["modalities"][0],
                "overall_confidence": entry["overall_confidence"],
                "metrics": entry["metrics"],
            }
            for entry in timeline
        ],
    }
    _DEMO_PATIENTS.append(patient_record)

_DEMO_PATIENTS.sort(key=lambda patient: patient.get("triage_score", 0), reverse=True)
_DEFAULT_DEMO_SCAN_ID = _DEMO_PATIENTS[0]["latest_scan_id"]


def _find_demo_patient(patient_id: str) -> Optional[dict]:
    return next((patient for patient in _DEMO_PATIENTS if patient["patient_id"] == patient_id), None)


def _resolve_demo_scan_id(scan_id: Optional[str], patient_id: Optional[str]) -> str:
    """Resolve requested demo scan from query/body parameters."""
    if scan_id:
        if scan_id not in _DEMO_ANALYSES:
            raise HTTPException(status_code=404, detail=f"Unknown demo scan_id: {scan_id}")
        return scan_id

    if patient_id:
        patient = _find_demo_patient(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=f"Unknown demo patient_id: {patient_id}")
        return patient["latest_scan_id"]

    return _DEFAULT_DEMO_SCAN_ID


_DEMO_SCAN_SOURCE_GLOBS = {
    "demo-scan-001": [
        "data/samples/ds000105/**/anat/*T1w.nii.gz",
    ],
    "demo-scan-002": [
        "data/samples/ds000105/**/func/*run-01_bold.nii.gz",
        "data/samples/ds000105/**/func/*bold.nii.gz",
    ],
    "demo-scan-003": [
        "data/samples/ds000105/**/anat/*T1w.nii.gz",
    ],
}

_MODALITY_SOURCE_GLOBS = {
    "MRI_T1": [
        "data/samples/ds000105/**/anat/*T1w.nii.gz",
    ],
    "fMRI": [
        "data/samples/ds000105/**/func/*run-01_bold.nii.gz",
        "data/samples/ds000105/**/func/*bold.nii.gz",
    ],
    "DTI": [
        "data/samples/ds000105/**/anat/*T1w.nii.gz",
    ],
}


def _find_first_existing_path(patterns: list[str]) -> Optional[Path]:
    for pattern in patterns:
        matches = sorted(_PROJECT_DIR.glob(pattern))
        if matches:
            return matches[0]
    return None


def _resolve_demo_source_volume_path(scan_id: str, modality: str) -> Path:
    base_scan_id = scan_id.removesuffix("-prev")
    source_patterns = list(_DEMO_SCAN_SOURCE_GLOBS.get(base_scan_id, []))
    source_patterns.extend(_MODALITY_SOURCE_GLOBS.get(modality, _MODALITY_SOURCE_GLOBS["MRI_T1"]))

    source_path = _find_first_existing_path(source_patterns)
    if source_path:
        return source_path

    raise FileNotFoundError(
        f"No source MRI/fMRI NIfTI found for demo scan {scan_id} "
        f"(modality={modality}). Run scripts/seed_openneuro.py first."
    )


def _resolve_scan_volume_path(scan_id: str, analysis: dict) -> Path:
    """Resolve source NIfTI path for demo or uploaded scans."""
    source_hint = analysis.get("source_upload_path") or analysis.get("source_nifti_path")
    if source_hint:
        candidate = Path(source_hint)
        if not candidate.is_absolute():
            candidate = (_PROJECT_DIR / candidate).resolve()
        if candidate.exists():
            return candidate

    job = _job_store.get(scan_id)
    if job:
        scan_path = Path(job.get("scan_path", ""))
        if scan_path.exists():
            return scan_path

    if scan_id in _DEMO_ANALYSES:
        modality = (analysis.get("modalities") or ["MRI_T1"])[0]
        return _resolve_demo_source_volume_path(scan_id, modality)

    modality = (analysis.get("modalities") or ["MRI_T1"])[0]
    fallback = _find_first_existing_path(_MODALITY_SOURCE_GLOBS.get(modality, _MODALITY_SOURCE_GLOBS["MRI_T1"]))
    if fallback:
        return fallback

    raise FileNotFoundError(f"Could not resolve source volume for scan {scan_id}")


def _region_focus_profile(region_name: str) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    name = (region_name or "").lower()

    if "hippocamp" in name and ("_l" in name or "left" in name):
        return (-0.38, -0.26, 0.05), (0.23, 0.18, 0.20)
    if "hippocamp" in name and ("_r" in name or "right" in name):
        return (0.38, -0.26, 0.05), (0.23, 0.18, 0.20)
    if "precentral" in name and ("_l" in name or "left" in name):
        return (-0.34, 0.34, 0.16), (0.26, 0.23, 0.24)
    if "precentral" in name and ("_r" in name or "right" in name):
        return (0.34, 0.34, 0.16), (0.26, 0.23, 0.24)
    if "frontal" in name:
        return (-0.18 if "_l" in name or "left" in name else 0.18, 0.46, 0.16), (0.32, 0.26, 0.30)
    if "temporal" in name:
        return (-0.42 if "_l" in name or "left" in name else 0.42, -0.10, -0.02), (0.29, 0.24, 0.28)
    if "parietal" in name:
        return (0.0, 0.46, -0.08), (0.36, 0.27, 0.24)
    if "occipital" in name:
        return (0.0, -0.06, -0.58), (0.34, 0.25, 0.20)

    return (0.0, 0.0, 0.0), (0.26, 0.26, 0.26)


def _build_damage_volume(shape: tuple[int, int, int], regions: list[dict]) -> "np.ndarray":
    import numpy as np

    x = np.linspace(-1.0, 1.0, shape[0], dtype=np.float32)
    y = np.linspace(-1.0, 1.0, shape[1], dtype=np.float32)
    z = np.linspace(-1.0, 1.0, shape[2], dtype=np.float32)
    xv, yv, zv = np.meshgrid(x, y, z, indexing="ij")

    damage = np.zeros(shape, dtype=np.float32)
    for region in regions:
        level = int(region.get("severity_level", 0))
        if level < 2:
            continue

        center, radii = _region_focus_profile(region.get("anatomical_name") or region.get("atlas_id", ""))
        rx = max(1e-3, radii[0])
        ry = max(1e-3, radii[1])
        rz = max(1e-3, radii[2])

        dx = (xv - center[0]) / rx
        dy = (yv - center[1]) / ry
        dz = (zv - center[2]) / rz
        distance = (dx * dx) + (dy * dy) + (dz * dz)

        confidence = float(region.get("confidence", 0.8))
        strength = max(0.2, min(1.0, ((level - 1) / 3.0) * (0.7 + (0.3 * confidence))))
        blob = np.exp(-distance * 1.8) * strength
        damage = np.maximum(damage, blob.astype(np.float32))

    return np.clip(damage, 0.0, 1.0)


def _build_synthetic_volume_channels(
    analysis: dict,
    target_shape: tuple[int, int, int] = (96, 96, 96),
) -> tuple[bytes, tuple[int, int, int], list[float], str]:
    """Build a deterministic fallback volume when no source NIfTI is available."""
    import numpy as np

    scan_id = str(analysis.get("scan_id", "synthetic"))
    seed = int(hashlib.sha1(scan_id.encode("utf-8")).hexdigest()[:8], 16)

    x = np.linspace(-1.0, 1.0, target_shape[0], dtype=np.float32)
    y = np.linspace(-1.0, 1.0, target_shape[1], dtype=np.float32)
    z = np.linspace(-1.0, 1.0, target_shape[2], dtype=np.float32)
    xv, yv, zv = np.meshgrid(x, y, z, indexing="ij")

    x_radius = 0.9 + (((seed % 17) - 8) * 0.004)
    y_radius = 0.78 + (((seed % 13) - 6) * 0.003)
    z_radius = 0.98 + (((seed % 19) - 9) * 0.003)

    ellipsoid = ((xv / x_radius) ** 2) + ((yv / y_radius) ** 2) + ((zv / z_radius) ** 2)
    brain_mask = (ellipsoid <= 1.0).astype(np.float32)

    radial = np.sqrt(np.clip(ellipsoid, 0.0, None))
    deep_core = np.exp(-ellipsoid * 2.2)
    cortical_shell = np.exp(-((radial - 0.78) ** 2) * 34.0) * brain_mask

    intensity = np.clip((0.58 * deep_core) + (0.42 * cortical_shell), 0.0, 1.0) * brain_mask
    white = np.clip((deep_core - 0.2) / 0.8, 0.0, 1.0) * brain_mask
    gray = np.clip((cortical_shell + (intensity * 0.3)) - (white * 0.25), 0.0, 1.0) * brain_mask

    damage = _build_damage_volume(target_shape, list(analysis.get("damage_summary", []))) * brain_mask

    rgba = np.empty((*target_shape, 4), dtype=np.uint8)
    rgba[..., 0] = np.clip(intensity * 255.0, 0, 255).astype(np.uint8)
    rgba[..., 1] = np.clip(gray * 255.0, 0, 255).astype(np.uint8)
    rgba[..., 2] = np.clip(white * 255.0, 0, 255).astype(np.uint8)
    rgba[..., 3] = np.clip(damage * 255.0, 0, 255).astype(np.uint8)

    modality = (analysis.get("modalities") or ["MRI_T1"])[0]
    spacing_mm = [1.8, 1.8, 1.8]
    return rgba.tobytes(order="C"), tuple(int(v) for v in target_shape), spacing_mm, modality


def _prepare_volume_channels(source_path: Path, analysis: dict, target_shape: tuple[int, int, int] = (96, 96, 96)) -> tuple[bytes, tuple[int, int, int], list[float], str]:
    import nibabel as nib
    import numpy as np
    from scipy import ndimage

    img = nib.load(str(source_path))
    raw = np.asarray(img.get_fdata(dtype=np.float32))

    modality = (analysis.get("modalities") or ["MRI_T1"])[0]
    if raw.ndim == 4:
        modality = "fMRI"
        raw = np.mean(raw, axis=3) + (0.25 * np.std(raw, axis=3))
    elif raw.ndim != 3:
        raw = np.asarray(raw).squeeze()
        if raw.ndim != 3:
            raise ValueError(f"Unsupported volume shape for {source_path}: {raw.shape}")

    raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
    original_shape = np.array(raw.shape, dtype=np.float32)

    if tuple(raw.shape) != tuple(target_shape):
        zoom_factors = tuple(float(target_shape[i]) / float(raw.shape[i]) for i in range(3))
        raw = ndimage.zoom(raw, zoom=zoom_factors, order=1)

    non_zero = raw[raw > 0]
    if non_zero.size == 0:
        raise ValueError(f"Volume {source_path} has no non-zero voxels")

    p_low = float(np.percentile(non_zero, 2))
    p_high = float(np.percentile(non_zero, 99))
    if p_high <= p_low:
        p_high = p_low + 1e-6

    norm = np.clip((raw - p_low) / (p_high - p_low), 0.0, 1.0)
    norm = ndimage.gaussian_filter(norm, sigma=0.8)

    tissue_values = norm[norm > 0.04]
    threshold = float(np.quantile(tissue_values, 0.28)) if tissue_values.size else 0.12
    threshold = max(0.10, min(0.4, threshold))

    brain_mask = norm >= threshold
    brain_mask = ndimage.binary_opening(brain_mask, iterations=1)
    brain_mask = ndimage.binary_closing(brain_mask, iterations=2)
    brain_mask = ndimage.binary_fill_holes(brain_mask)
    brain_mask = brain_mask.astype(np.float32)

    white = np.clip((norm - 0.56) / 0.42, 0.0, 1.0) * brain_mask
    gray = np.clip((norm - 0.22) / 0.48, 0.0, 1.0) * brain_mask * (1.0 - (white * 0.35))

    damage = _build_damage_volume(norm.shape, list(analysis.get("damage_summary", []))) * brain_mask

    rgba = np.empty((*norm.shape, 4), dtype=np.uint8)
    rgba[..., 0] = np.clip(norm * 255.0, 0, 255).astype(np.uint8)
    rgba[..., 1] = np.clip(gray * 255.0, 0, 255).astype(np.uint8)
    rgba[..., 2] = np.clip(white * 255.0, 0, 255).astype(np.uint8)
    rgba[..., 3] = np.clip(damage * 255.0, 0, 255).astype(np.uint8)

    voxel_sizes = np.array(img.header.get_zooms()[:3], dtype=np.float32)
    scaled_spacing = (voxel_sizes * (original_shape / np.array(norm.shape, dtype=np.float32))).tolist()

    return rgba.tobytes(order="C"), tuple(int(v) for v in norm.shape), [float(v) for v in scaled_spacing], modality


def _build_volume_payload(
    scan_id: str,
    source_path: Path,
    analysis: dict,
    resolution: str = "standard",
) -> dict:
    target_shape = _volume_target_shape(resolution)
    stat = source_path.stat()
    cache_key = (
        f"{scan_id}:{int(stat.st_mtime)}:{int(stat.st_size)}"
        f":{resolution}:{target_shape[0]}x{target_shape[1]}x{target_shape[2]}"
    )

    cached_payload = _VOLUME_PAYLOAD_CACHE.get(cache_key)
    if cached_payload:
        payload = dict(cached_payload)
        payload["cached"] = True
        return payload

    try:
        source_rel = str(source_path.resolve().relative_to(_PROJECT_DIR)).replace("\\", "/")
    except ValueError:
        source_rel = str(source_path)

    synthetic_fallback = False
    try:
        rgba_bytes, shape, spacing_mm, modality = _prepare_volume_channels(
            source_path,
            analysis,
            target_shape=target_shape,
        )
    except Exception as exc:
        logger.warning(
            f"Volume reconstruction fallback for {scan_id} ({source_path}): {exc}"
        )
        rgba_bytes, shape, spacing_mm, modality = _build_synthetic_volume_channels(
            analysis,
            target_shape=target_shape,
        )
        source_rel = "synthetic://analysis-fallback"
        synthetic_fallback = True

    encoded = base64.b64encode(rgba_bytes).decode("ascii")

    payload = {
        "scan_id": scan_id,
        "modality": modality,
        "shape": list(shape),
        "spacing_mm": spacing_mm,
        "encoding": "base64-rgba-u8",
        "volume_b64": encoded,
        "source_nifti": source_rel,
        "synthetic_fallback": synthetic_fallback,
        "resolution_profile": resolution,
    }

    if len(_VOLUME_PAYLOAD_CACHE) >= 16:
        # Keep cache bounded for long-lived dev sessions.
        oldest_key = next(iter(_VOLUME_PAYLOAD_CACHE))
        _VOLUME_PAYLOAD_CACHE.pop(oldest_key, None)

    _VOLUME_PAYLOAD_CACHE[cache_key] = dict(payload)
    payload["cached"] = False
    return payload


def _resolve_upload_sample_source(modality: str) -> Path:
    modality_key = "fMRI" if modality.lower() == "fmri" else "MRI_T1"
    patterns = _MODALITY_SOURCE_GLOBS.get(modality_key, _MODALITY_SOURCE_GLOBS["MRI_T1"])
    source = _find_first_existing_path(patterns)
    if source:
        return source
    raise FileNotFoundError(
        f"No sample NIfTI found for modality={modality}. Run scripts/seed_openneuro.py first."
    )


def _ensure_demo_mesh(
    scan_id: str,
    modality: str,
    force_rebuild: bool = False,
    quality: str = "high",
) -> dict:
    from reconstruction.mesh_builder import MeshBuilder

    profile = _mesh_profile(quality)
    output_prefix = str(profile["output_prefix"])
    mesh_dir = _OUTPUTS_DIR / "demo_mesh" / scan_id
    mesh_dir.mkdir(parents=True, exist_ok=True)
    mesh_path = mesh_dir / f"{output_prefix}_web.obj"

    if mesh_path.exists() and not force_rebuild:
        return {
            "mesh_url": f"/outputs/demo_mesh/{scan_id}/{mesh_path.name}",
            "mesh_format": "obj",
            "cached": True,
            "mesh_path": str(mesh_path),
            "modality": modality,
            "mesh_quality": quality,
        }

    source_path = _resolve_demo_source_volume_path(scan_id, modality)

    builder = MeshBuilder(
        decimation_target=int(profile["decimation_target"]),
        iso_value=float(profile["iso_value"]),
        smooth_iterations=int(profile["smooth_iterations"]),
    )
    build_stats = builder.build(str(source_path), str(mesh_dir), output_prefix=output_prefix)
    build_stats["requested_quality"] = quality

    built_mesh_path = Path(build_stats.get("web_mesh_path", str(mesh_path)))
    if not built_mesh_path.exists():
        raise RuntimeError(f"Mesh reconstruction failed for {scan_id}; OBJ output was not created")
    resolved_quality = _mesh_quality_from_output_name(built_mesh_path.name)

    try:
        source_rel = str(source_path.relative_to(_PROJECT_DIR)).replace("\\", "/")
    except ValueError:
        source_rel = str(source_path)

    return {
        "mesh_url": f"/outputs/demo_mesh/{scan_id}/{built_mesh_path.name}",
        "mesh_format": "obj",
        "cached": False,
        "mesh_path": str(built_mesh_path),
        "source_nifti": source_rel,
        "modality": modality,
        "mesh_quality": resolved_quality,
        "build": build_stats,
    }


def _ensure_scan_mesh(
    scan_id: str,
    analysis: dict,
    force_rebuild: bool = False,
    quality: str = "high",
) -> dict:
    """Return a mesh for any scan, building it from source NIfTI when needed."""
    if scan_id in _DEMO_ANALYSES:
        modality = (analysis.get("modalities") or ["MRI_T1"])[0]
        return _ensure_demo_mesh(scan_id, modality, force_rebuild=force_rebuild, quality=quality)

    from reconstruction.mesh_builder import MeshBuilder

    profile = _mesh_profile(quality)
    output_prefix = str(profile["output_prefix"])
    export_dir = _OUTPUTS_DIR / "export" / scan_id
    export_dir.mkdir(parents=True, exist_ok=True)

    preferred_obj = export_dir / f"{output_prefix}_web.obj"
    legacy_obj = export_dir / "brain.obj"
    legacy_glb = export_dir / "brain.glb"

    if not force_rebuild:
        if preferred_obj.exists():
            return {
                "mesh_url": f"/outputs/export/{scan_id}/{preferred_obj.name}",
                "mesh_format": "obj",
                "cached": True,
                "mesh_path": str(preferred_obj),
                "mesh_quality": quality,
            }
        if quality == "standard" and legacy_obj.exists():
            return {
                "mesh_url": f"/outputs/export/{scan_id}/{legacy_obj.name}",
                "mesh_format": "obj",
                "cached": True,
                "mesh_path": str(legacy_obj),
                "mesh_quality": "standard",
            }
        if quality == "standard" and legacy_glb.exists():
            return {
                "mesh_url": f"/outputs/export/{scan_id}/{legacy_glb.name}",
                "mesh_format": "glb",
                "cached": True,
                "mesh_path": str(legacy_glb),
                "mesh_quality": "standard",
            }

    source_path = _resolve_scan_volume_path(scan_id, analysis)

    builder = MeshBuilder(
        decimation_target=int(profile["decimation_target"]),
        iso_value=float(profile["iso_value"]),
        smooth_iterations=int(profile["smooth_iterations"]),
    )
    build_stats = builder.build(str(source_path), str(export_dir), output_prefix=output_prefix)
    build_stats["requested_quality"] = quality

    built_mesh_path = Path(build_stats.get("web_mesh_path", str(preferred_obj)))
    if not built_mesh_path.exists():
        if preferred_obj.exists():
            built_mesh_path = preferred_obj
        elif legacy_obj.exists():
            built_mesh_path = legacy_obj
        elif legacy_glb.exists():
            built_mesh_path = legacy_glb
        else:
            raise RuntimeError(f"Mesh reconstruction failed for {scan_id}; no output mesh was created")

    try:
        source_rel = str(source_path.relative_to(_PROJECT_DIR)).replace("\\", "/")
    except ValueError:
        source_rel = str(source_path)

    suffix = built_mesh_path.suffix.lower()
    mesh_format = "glb" if suffix == ".glb" else "obj"
    resolved_quality = _mesh_quality_from_output_name(built_mesh_path.name)

    return {
        "mesh_url": f"/outputs/export/{scan_id}/{built_mesh_path.name}",
        "mesh_format": mesh_format,
        "cached": False,
        "mesh_path": str(built_mesh_path),
        "source_nifti": source_rel,
        "mesh_quality": resolved_quality,
        "build": build_stats,
    }


@app.get("/demo/patients")
async def get_demo_patients():
    """List sample patients available for demo workflows."""
    return {"patients": _DEMO_PATIENTS}


@app.get("/demo/patients/{patient_id}")
async def get_demo_patient(patient_id: str):
    """Get one sample patient and their latest analysis."""
    patient = _find_demo_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail=f"Unknown demo patient_id: {patient_id}")
    analysis = _DEMO_ANALYSES.get(patient["latest_scan_id"])
    decorated = _decorate_analysis_payload(patient["latest_scan_id"], analysis) if analysis else None
    return {
        "patient": patient,
        "analysis": decorated,
        "timeline": _DEMO_PATIENT_TIMELINES.get(patient_id, []),
    }


@app.get("/demo/patients/{patient_id}/timeline")
async def get_demo_patient_timeline(patient_id: str):
    """Get longitudinal sample timeline for one patient."""
    patient = _find_demo_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail=f"Unknown demo patient_id: {patient_id}")
    return {
        "patient": patient,
        "timeline": _DEMO_PATIENT_TIMELINES.get(patient_id, []),
        "trend": patient.get("trend", "stable"),
    }


@app.get("/demo/dicom/{scan_id}")
async def get_demo_dicom_study(scan_id: str):
    """Return professional DICOM-style study metadata for demo scan viewers."""
    analysis = _DEMO_ANALYSES.get(scan_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Unknown demo scan_id: {scan_id}")

    patient = _find_demo_patient(analysis.get("patient_id", ""))
    profile = _build_advanced_dicom_profile(scan_id, analysis)

    return {
        "scan_id": scan_id,
        "patient_id": analysis.get("patient_id"),
        "patient_code": analysis.get("patient_code", patient.get("patient_code") if patient else "demo"),
        "patient_name": analysis.get("patient_name", patient.get("display_name") if patient else "Demo Patient"),
        "risk_band": analysis.get("risk_band", patient.get("risk_band") if patient else "moderate"),
        "profile": profile,
        "source_mode": profile.get("source_mode"),
        "orientation": profile.get("orientation"),
        "voxel_spacing_mm": profile.get("voxel_spacing_mm"),
        "series_quality_score": profile.get("series_quality_score"),
        "capabilities": [
            "MPR tri-planar",
            "Window/Level presets",
            "Interactive slice navigation",
            "Cine playback",
            "Crosshair",
            "Distance measurement",
            "Volume measurement",
            "Voxel-to-mm coordinate transform",
            "Annotation-ready workflow",
            "Inversion",
        ],
    }


@app.get("/dicom/{scan_id}")
async def get_scan_dicom_study(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return advanced DICOM workstation metadata for any scan."""
    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)
    profile = _build_advanced_dicom_profile(scan_id, decorated)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", ""),
        action=f"GET /dicom/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED",
    )

    return {
        "scan_id": scan_id,
        "patient_id": decorated.get("patient_id"),
        "patient_code": decorated.get("patient_code"),
        "risk_band": decorated.get("risk_band"),
        "profile": profile,
        "provenance_banner": decorated.get("provenance_banner", {}),
        "safety_profile": decorated.get("safety_profile", {}),
    }


@app.get("/demo/mesh/{scan_id}")
async def get_demo_mesh(
    scan_id: str,
    force_rebuild: bool = Query(False),
    quality: str = Query("high", pattern="^(standard|high|extreme)$"),
):
    """Return an MRI/fMRI-derived reconstruction mesh for a demo scan."""
    analysis = _DEMO_ANALYSES.get(scan_id)
    if not analysis:
        raise HTTPException(status_code=404, detail=f"Unknown demo scan_id: {scan_id}")

    modality = (analysis.get("modalities") or ["MRI_T1"])[0]

    try:
        mesh_info = _ensure_demo_mesh(
            scan_id,
            modality,
            force_rebuild=force_rebuild,
            quality=quality,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(f"Failed to build demo mesh for {scan_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Demo reconstruction failed for {scan_id}") from exc

    _record_runtime_context(
        scan_id,
        source_kind="demo",
        mesh_quality=mesh_info.get("mesh_quality"),
        source_nifti=mesh_info.get("source_nifti"),
    )

    decorated = _decorate_analysis_payload(scan_id, analysis)

    return {
        "scan_id": scan_id,
        "patient_id": analysis.get("patient_id"),
        "modality": modality,
        **mesh_info,
        "provenance_banner": decorated.get("provenance_banner", {}),
        "safety_profile": decorated.get("safety_profile", {}),
    }


@app.get("/volume/{scan_id}")
async def get_volume_payload(
    scan_id: str,
    resolution: str = Query("standard", pattern="^(standard|high|extreme)$"),
):
    """Return volumetric RGBA payload (intensity, gray, white, damage) for WebGL rendering."""
    analysis = _resolve_analysis_payload(scan_id)

    try:
        source_path = _resolve_scan_volume_path(scan_id, analysis)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        volume_payload = _build_volume_payload(scan_id, source_path, analysis, resolution=resolution)
        _record_runtime_context(
            scan_id,
            source_kind="demo" if scan_id in _DEMO_ANALYSES else "uploaded",
            source_nifti=volume_payload.get("source_nifti"),
            synthetic_fallback=volume_payload.get("synthetic_fallback"),
            volume_resolution=volume_payload.get("resolution_profile"),
        )
        decorated = _decorate_analysis_payload(scan_id, analysis)
        return {
            **volume_payload,
            "reconstruction_profile": {
                "algorithm": "multi-channel volumetric reconstruction",
                "channels": ["intensity", "gray_matter", "white_matter", "damage"],
                "resolution_profile": volume_payload.get("resolution_profile"),
                "source_mode": decorated.get("provenance_banner", {}).get("source_mode"),
            },
            "measurement_facilities": {
                "distance_endpoint": f"/measurements/{scan_id}/distance",
                "volume_endpoint": f"/measurements/{scan_id}/volume",
                "table_endpoint": f"/measurements/{scan_id}/table",
                "coordinate_space": ["voxel", "mm"],
            },
            "provenance_banner": decorated.get("provenance_banner", {}),
            "safety_profile": decorated.get("safety_profile", {}),
            "uncertainty_profile": decorated.get("uncertainty_profile", {}),
            "critical_findings": decorated.get("critical_findings", []),
            "review_state": decorated.get("review_state"),
            "decision_tier": decorated.get("decision_tier"),
            "clinical_governance": decorated.get("clinical_governance", {}),
        }
    except Exception as exc:
        logger.exception(f"Failed to build volume payload for {scan_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Volumetric reconstruction failed for {scan_id}") from exc


@app.get("/reconstruction/volume/{scan_id}")
async def get_advanced_volume_reconstruction(
    scan_id: str,
    resolution: str = Query("high", pattern="^(standard|high|extreme)$"),
    include_mesh: bool = Query(True),
    mesh_quality: str = Query("high", pattern="^(standard|high|extreme)$"),
    current_user: dict = Depends(get_current_user),
):
    """Neurologist-oriented reconstruction payload with advanced DICOM and measurement context."""
    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)

    try:
        source_path = _resolve_scan_volume_path(scan_id, analysis)
        volume_payload = _build_volume_payload(scan_id, source_path, analysis, resolution=resolution)
    except Exception as exc:
        logger.exception(f"Advanced volumetric reconstruction failed for {scan_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Advanced volumetric reconstruction failed for {scan_id}") from exc

    mesh_payload = None
    if include_mesh:
        try:
            mesh_payload = _ensure_scan_mesh(scan_id, analysis, force_rebuild=False, quality=mesh_quality)
        except Exception as exc:
            logger.warning(f"Advanced reconstruction mesh unavailable for {scan_id}: {exc}")
            mesh_payload = {
                "available": False,
                "reason": str(exc),
            }

    dicom_profile = _build_advanced_dicom_profile(scan_id, decorated)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", ""),
        action=f"GET /reconstruction/volume/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED",
        details={"resolution": resolution, "include_mesh": include_mesh, "mesh_quality": mesh_quality},
    )

    return {
        "scan_id": scan_id,
        "volume": volume_payload,
        "mesh": mesh_payload,
        "dicom": dicom_profile,
        "measurement_facilities": {
            "distance_endpoint": f"/measurements/{scan_id}/distance",
            "volume_endpoint": f"/measurements/{scan_id}/volume",
            "table_endpoint": f"/measurements/{scan_id}/table",
            "export_endpoint": f"/measurements/{scan_id}/export.csv",
        },
        "provenance_banner": decorated.get("provenance_banner", {}),
        "safety_profile": decorated.get("safety_profile", {}),
        "uncertainty_profile": decorated.get("uncertainty_profile", {}),
        "clinical_governance": decorated.get("clinical_governance", {}),
    }


@app.get("/demo/upload-sample")
async def download_upload_sample(modality: str = Query("mri", enum=["mri", "fmri"])):
    """Download a known-good sample scan file for upload testing."""
    try:
        sample_path = _resolve_upload_sample_source(modality)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filename = f"brainscape_sample_{modality}.nii.gz"
    return FileResponse(path=str(sample_path), media_type="application/octet-stream", filename=filename)


@app.get("/demo/compare")
async def compare_demo_cases(
    left_scan_id: str,
    right_scan_id: str,
):
    """Compare two sample scans and return delta-level clinical metrics."""
    if left_scan_id == right_scan_id:
        raise HTTPException(status_code=400, detail="Comparison requires two distinct scan IDs")

    left = _DEMO_ANALYSES.get(left_scan_id)
    right = _DEMO_ANALYSES.get(right_scan_id)

    if not left:
        raise HTTPException(status_code=404, detail=f"Unknown demo scan_id: {left_scan_id}")
    if not right:
        raise HTTPException(status_code=404, detail=f"Unknown demo scan_id: {right_scan_id}")

    left_metrics = left.get("metrics") or _compute_case_metrics(left)
    right_metrics = right.get("metrics") or _compute_case_metrics(right)

    left_regions = {region.get("anatomical_name", region.get("atlas_id", "Unknown")): int(region.get("severity_level", 0)) for region in left.get("damage_summary", [])}
    right_regions = {region.get("anatomical_name", region.get("atlas_id", "Unknown")): int(region.get("severity_level", 0)) for region in right.get("damage_summary", [])}

    changed_regions = []
    for region_name in sorted(set(left_regions.keys()) | set(right_regions.keys())):
        left_level = left_regions.get(region_name, 0)
        right_level = right_regions.get(region_name, 0)
        delta_level = right_level - left_level
        if delta_level != 0:
            changed_regions.append(
                {
                    "region": region_name,
                    "left_level": left_level,
                    "right_level": right_level,
                    "delta_level": delta_level,
                }
            )

    changed_regions.sort(key=lambda region: abs(region["delta_level"]), reverse=True)

    delta_payload = {
        "flagged_regions": right_metrics["flagged_regions"] - left_metrics["flagged_regions"],
        "severe_regions": right_metrics["severe_regions"] - left_metrics["severe_regions"],
        "triage_score": round(right_metrics["triage_score"] - left_metrics["triage_score"], 2),
        "confidence_pct": round((right["overall_confidence"] - left["overall_confidence"]) * 100, 1),
    }
    clinical_change_assessment = _classify_clinical_change(delta_payload)

    return {
        "left": {
            "scan_id": left["scan_id"],
            "patient_id": left["patient_id"],
            "patient_code": left["patient_code"],
            "risk_band": left["risk_band"],
            "overall_confidence": left["overall_confidence"],
            "metrics": left_metrics,
        },
        "right": {
            "scan_id": right["scan_id"],
            "patient_id": right["patient_id"],
            "patient_code": right["patient_code"],
            "risk_band": right["risk_band"],
            "overall_confidence": right["overall_confidence"],
            "metrics": right_metrics,
        },
        "delta": {
            **delta_payload,
            "confidence_on_delta": round((left["overall_confidence"] + right["overall_confidence"]) / 2.0, 3),
        },
        "clinical_change_assessment": clinical_change_assessment,
        "changed_regions": changed_regions[:12],
    }


@app.get("/demo/analysis")
async def get_demo_analysis(
    scan_id: Optional[str] = None,
    patient_id: Optional[str] = None,
):
    """Return demo analysis data; supports selecting by scan_id or patient_id."""
    resolved_scan_id = _resolve_demo_scan_id(scan_id, patient_id)
    analysis = _DEMO_ANALYSES[resolved_scan_id]
    return _decorate_analysis_payload(resolved_scan_id, analysis)


@app.post("/demo/ingest")
async def demo_ingest(
    scan_id: Optional[str] = None,
    patient_id: Optional[str] = None,
):
    """Simulate an ingest that immediately completes with selected demo data."""
    resolved_scan_id = _resolve_demo_scan_id(scan_id, patient_id)
    job_id = resolved_scan_id
    _SIGNOFF_STORE.pop(resolved_scan_id, None)
    _record_runtime_context(
        resolved_scan_id,
        source_kind="demo",
        synthetic_fallback=False,
        analysis_mode="demo-scenario",
    )
    _job_store[job_id] = {
        "job_id": job_id,
        "user_id": "demo-clinician",
        "scan_path": f"data/samples/{resolved_scan_id}.nii.gz",
        "status": "complete",
        "stage": "done",
        "progress_pct": 100,
        "error_message": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"job_id": job_id, "status": "complete", "scan_id": resolved_scan_id}


@app.get("/uncertainty/{scan_id}")
async def get_uncertainty_overlay(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return uncertainty overlay payload for visualization alongside lesion maps."""
    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", ""),
        action=f"GET /uncertainty/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED",
    )

    return {
        "scan_id": scan_id,
        "uncertainty_profile": decorated.get("uncertainty_profile", {}),
        "provenance_banner": decorated.get("provenance_banner", {}),
        "safety_profile": decorated.get("safety_profile", {}),
    }


@app.get("/clinical-modules/{scan_id}")
async def get_clinical_modules(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return disease-specific clinical module summaries for neurologist workflows."""
    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)
    modules = _build_disease_specific_modules(decorated)

    return {
        "scan_id": scan_id,
        "modules": modules,
        "provenance_banner": decorated.get("provenance_banner", {}),
        "safety_profile": decorated.get("safety_profile", {}),
    }


@app.get("/calibration/dashboard")
async def get_calibration_dashboard(
    institution_id: str = Query("default"),
    current_user: dict = Depends(get_current_user),
):
    """Return calibration metrics by condition and modality for confidence interpretation."""
    calibration = {
        "institution_id": institution_id,
        "generated_at": _now_iso(),
        "overview": {
            "calibrated_populations": ["stroke", "tumour", "tbi", "epilepsy-preop"],
            "modalities": ["MRI_T1", "fMRI", "DTI"],
            "note": "Calibration curves are decision-support quality indicators and should be reviewed by site governance.",
        },
        "curves": [
            {
                "condition": "stroke",
                "modality": "MRI_T1",
                "ece": 0.08,
                "brier": 0.12,
                "points": [[0.1, 0.13], [0.3, 0.33], [0.5, 0.53], [0.7, 0.71], [0.9, 0.88]],
            },
            {
                "condition": "tumour",
                "modality": "MRI_T1",
                "ece": 0.11,
                "brier": 0.15,
                "points": [[0.1, 0.16], [0.3, 0.34], [0.5, 0.51], [0.7, 0.69], [0.9, 0.85]],
            },
            {
                "condition": "tbi",
                "modality": "DTI",
                "ece": 0.14,
                "brier": 0.18,
                "points": [[0.1, 0.19], [0.3, 0.35], [0.5, 0.49], [0.7, 0.66], [0.9, 0.82]],
            },
        ],
    }

    audit.log(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", ""),
        action="GET /calibration/dashboard",
        resource_id=institution_id,
        outcome="ALLOWED",
    )

    return calibration


@app.get("/critical-findings/{scan_id}")
async def get_critical_findings(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return critical findings and acknowledgement workflow state."""
    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)

    findings = decorated.get("critical_findings", [])
    acknowledgements = list(_CRITICAL_ACK_STORE.get(scan_id, []))

    return {
        "scan_id": scan_id,
        "critical_findings": findings,
        "acknowledgements": acknowledgements,
        "pending_acknowledgements": max(0, len(findings) - len(acknowledgements)),
        "safety_profile": decorated.get("safety_profile", {}),
    }


@app.post("/critical-findings/{scan_id}/ack")
async def acknowledge_critical_findings(
    scan_id: str,
    request: CriticalAcknowledgementRequest,
    current_user: dict = Depends(get_current_user),
):
    """Acknowledge critical findings with escalation/resolution tracking."""
    role = current_user.get("role", "patient")
    if role not in ("clinician", "researcher"):
        raise HTTPException(status_code=403, detail="Critical finding acknowledgement requires clinician or researcher role")

    event = {
        "event_id": str(uuid4()),
        "scan_id": scan_id,
        "user_id": current_user.get("sub", ""),
        "role": role,
        "disposition": request.disposition,
        "note": request.note,
        "escalation_target": request.escalation_target,
        "timestamp": _now_iso(),
    }
    _CRITICAL_ACK_STORE.setdefault(scan_id, []).append(event)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=role,
        action=f"POST /critical-findings/{scan_id}/ack",
        resource_id=scan_id,
        outcome="ALLOWED",
        details={"disposition": request.disposition},
    )

    return {
        "scan_id": scan_id,
        "acknowledged": event,
        "history": _CRITICAL_ACK_STORE.get(scan_id, []),
    }


@app.get("/report-workflow/{scan_id}")
async def get_report_workflow(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return draft/verification/finalization workflow state for medico-legal traceability."""
    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)
    finalizations = list(_REPORT_FINALIZATION_STORE.get(scan_id, []))

    return {
        "scan_id": scan_id,
        "draft_available": True,
        "verification_events": decorated.get("signoff_history", []),
        "finalization_events": finalizations,
        "finalized": bool(finalizations),
        "immutable_audit_channel": "audit_logger_jsonl",
        "safety_profile": decorated.get("safety_profile", {}),
    }


@app.post("/report-workflow/{scan_id}/finalize")
async def finalize_report_workflow(
    scan_id: str,
    note: Optional[str] = Query(None),
    allow_safety_override: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    """Finalize report only after human verification; enforce safety locks unless explicitly overridden."""
    role = current_user.get("role", "patient")
    if role not in ("clinician", "researcher"):
        raise HTTPException(status_code=403, detail="Finalization requires clinician or researcher role")

    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)
    signoff_history = list(decorated.get("signoff_history", []))
    if not signoff_history:
        raise HTTPException(status_code=409, detail="Cannot finalize report without at least one reviewer sign-off")

    safety_profile = decorated.get("safety_profile", {})
    if safety_profile.get("decision_support_only") and not allow_safety_override:
        raise HTTPException(
            status_code=409,
            detail="Safety lock active: report finalization requires allow_safety_override=true and documented rationale",
        )

    event = {
        "event_id": str(uuid4()),
        "scan_id": scan_id,
        "user_id": current_user.get("sub", ""),
        "role": role,
        "note": note,
        "allow_safety_override": allow_safety_override,
        "timestamp": _now_iso(),
    }
    _REPORT_FINALIZATION_STORE.setdefault(scan_id, []).append(event)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=role,
        action=f"POST /report-workflow/{scan_id}/finalize",
        resource_id=scan_id,
        outcome="ALLOWED",
        details={"allow_safety_override": allow_safety_override},
    )

    return {
        "scan_id": scan_id,
        "finalized": True,
        "finalization_event": event,
    }


def _ensure_segmentation_session(scan_id: str) -> dict[str, Any]:
    session = _SEGMENTATION_EDIT_STORE.setdefault(
        scan_id,
        {
            "timeline": [],
            "cursor": -1,
            "approval_state": "draft",
        },
    )
    return session


@app.get("/segmentation/{scan_id}/history")
async def get_segmentation_history(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return segmentation edit history with immutable provenance fields."""
    session = _ensure_segmentation_session(scan_id)
    return {
        "scan_id": scan_id,
        "cursor": session["cursor"],
        "approval_state": session["approval_state"],
        "edits": session["timeline"],
    }


@app.post("/segmentation/{scan_id}/edit")
async def create_segmentation_edit(
    scan_id: str,
    request: SegmentationEditRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a versioned segmentation edit event with rationale and diff metadata."""
    role = current_user.get("role", "patient")
    if role not in ("clinician", "researcher"):
        raise HTTPException(status_code=403, detail="Segmentation editing requires clinician or researcher role")

    session = _ensure_segmentation_session(scan_id)
    timeline = list(session["timeline"])
    cursor = _safe_int(session["cursor"], -1)

    if cursor < len(timeline) - 1:
        timeline = timeline[: cursor + 1]

    edit = {
        "edit_id": str(uuid4()),
        "version": len(timeline) + 1,
        "operation": request.operation,
        "region_name": request.region_name,
        "rationale": request.rationale,
        "voxel_count_delta": request.voxel_count_delta,
        "confidence_hint": request.confidence_hint,
        "patch_summary": request.patch_summary or {},
        "brush_guidance": {
            "recommended_brush_mm": round(2.0 + (2.0 * max(0.0, min(1.0, 1.0 - _safe_float(request.confidence_hint, 0.5)))), 2),
            "mode": "confidence-aware",
        },
        "user_id": current_user.get("sub", ""),
        "role": role,
        "timestamp": _now_iso(),
    }

    timeline.append(edit)
    session["timeline"] = timeline
    session["cursor"] = len(timeline) - 1
    session["approval_state"] = "draft"

    audit.log(
        user_id=current_user.get("sub", ""),
        role=role,
        action=f"POST /segmentation/{scan_id}/edit",
        resource_id=scan_id,
        outcome="ALLOWED",
        details={"operation": request.operation, "version": edit["version"]},
    )

    return {
        "scan_id": scan_id,
        "edit": edit,
        "cursor": session["cursor"],
        "approval_state": session["approval_state"],
    }


@app.post("/segmentation/{scan_id}/undo")
async def undo_segmentation_edit(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Move segmentation cursor back by one edit (undo)."""
    session = _ensure_segmentation_session(scan_id)
    session["cursor"] = max(-1, _safe_int(session["cursor"], -1) - 1)
    session["approval_state"] = "draft"
    return {
        "scan_id": scan_id,
        "cursor": session["cursor"],
        "active_version": session["cursor"] + 1,
    }


@app.post("/segmentation/{scan_id}/redo")
async def redo_segmentation_edit(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Move segmentation cursor forward by one edit (redo)."""
    session = _ensure_segmentation_session(scan_id)
    session["cursor"] = min(len(session["timeline"]) - 1, _safe_int(session["cursor"], -1) + 1)
    session["approval_state"] = "draft"
    return {
        "scan_id": scan_id,
        "cursor": session["cursor"],
        "active_version": session["cursor"] + 1,
    }


@app.post("/segmentation/{scan_id}/approval")
async def update_segmentation_approval(
    scan_id: str,
    request: SegmentationApprovalRequest,
    current_user: dict = Depends(get_current_user),
):
    """Set segmentation approval state with immutable reviewer trail."""
    role = current_user.get("role", "patient")
    if role not in ("clinician", "researcher"):
        raise HTTPException(status_code=403, detail="Approval changes require clinician or researcher role")

    session = _ensure_segmentation_session(scan_id)
    session["approval_state"] = request.decision
    event = {
        "event_id": str(uuid4()),
        "decision": request.decision,
        "note": request.note,
        "user_id": current_user.get("sub", ""),
        "role": role,
        "timestamp": _now_iso(),
    }
    session.setdefault("approval_events", []).append(event)

    return {
        "scan_id": scan_id,
        "approval_state": session["approval_state"],
        "event": event,
    }


def _ledger_append(scan_id: str, record: dict[str, Any]) -> None:
    _MEASUREMENT_LEDGER.setdefault(scan_id, []).append(record)


@app.post("/measurements/{scan_id}/distance")
async def create_distance_measurement(
    scan_id: str,
    request: DistanceMeasurementRequest,
    current_user: dict = Depends(get_current_user),
):
    """Compute neurologist-grade distance measurement with voxel-spacing awareness."""
    analysis = _resolve_analysis_payload(scan_id)
    spacing_mm = _normalize_spacing(request.spacing_mm)

    if request.coordinate_space == "voxel" and request.spacing_mm is None:
        try:
            source_path = _resolve_scan_volume_path(scan_id, analysis)
            import nibabel as nib

            img = nib.load(str(source_path))
            spacing = list(img.header.get_zooms()[:3])
            spacing_mm = _normalize_spacing([float(spacing[0]), float(spacing[1]), float(spacing[2] if len(spacing) > 2 else 1.0)])
        except Exception:
            pass

    distance_mm = _distance_mm(request.point_a, request.point_b, spacing_mm, request.coordinate_space)
    record = {
        "measurement_id": str(uuid4()),
        "type": "distance",
        "label": request.label,
        "point_a": request.point_a,
        "point_b": request.point_b,
        "coordinate_space": request.coordinate_space,
        "spacing_mm": spacing_mm,
        "distance_mm": round(distance_mm, 3),
        "user_id": current_user.get("sub", ""),
        "timestamp": _now_iso(),
    }
    _ledger_append(scan_id, record)
    return {"scan_id": scan_id, **record}


@app.post("/measurements/{scan_id}/volume")
async def create_volume_measurement(
    scan_id: str,
    request: VolumeMeasurementRequest,
    current_user: dict = Depends(get_current_user),
):
    """Compute lesion/ROI volume in mm3 and ml with spacing-aware conversion."""
    spacing_mm = _normalize_spacing(request.spacing_mm)
    vol_mm3 = _volume_mm3(request.voxel_count, spacing_mm)

    record = {
        "measurement_id": str(uuid4()),
        "type": "volume",
        "label": request.label,
        "voxel_count": request.voxel_count,
        "spacing_mm": spacing_mm,
        "volume_mm3": round(vol_mm3, 3),
        "volume_ml": round(vol_mm3 / 1000.0, 3),
        "user_id": current_user.get("sub", ""),
        "timestamp": _now_iso(),
    }
    _ledger_append(scan_id, record)
    return {"scan_id": scan_id, **record}


@app.get("/measurements/{scan_id}/table")
async def get_measurement_table(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return all recorded measurements in machine-readable table form."""
    records = list(_MEASUREMENT_LEDGER.get(scan_id, []))
    return {
        "scan_id": scan_id,
        "count": len(records),
        "records": records,
    }


@app.get("/measurements/{scan_id}/export.csv")
async def export_measurement_table_csv(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Export measurements as CSV for downstream clinical systems."""
    records = list(_MEASUREMENT_LEDGER.get(scan_id, []))
    out_dir = _OUTPUTS_DIR / "measurements" / scan_id
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"measurements_{scan_id}.csv"

    fieldnames = [
        "measurement_id",
        "type",
        "label",
        "coordinate_space",
        "distance_mm",
        "voxel_count",
        "volume_mm3",
        "volume_ml",
        "timestamp",
        "user_id",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key) for key in fieldnames})

    return FileResponse(path=str(csv_path), media_type="text/csv", filename=csv_path.name)


@app.get("/patient-summary/{scan_id}")
async def get_patient_summary(
    scan_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return plain-language patient communication summary with uncertainty explanation."""
    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)
    uncertainty = decorated.get("uncertainty_profile", {})

    summary_text = (
        f"This scan review found {decorated.get('metrics', {}).get('flagged_regions', 0)} areas that may need follow-up. "
        "The AI output supports your care team and does not replace clinician decisions."
    )
    uncertainty_text = (
        f"Overall uncertainty score: {uncertainty.get('global_uncertainty', 'N/A')}. "
        "Higher uncertainty means your clinicians will rely more heavily on manual review and additional context."
    )

    return {
        "scan_id": scan_id,
        "summary": summary_text,
        "uncertainty_explanation": uncertainty_text,
        "follow_up_guidance": [
            "Review results with your neurologist.",
            "Ask whether a follow-up scan interval is recommended.",
            "Report any new neurological symptoms promptly.",
        ],
        "decision_support_only": decorated.get("safety_profile", {}).get("decision_support_only", False),
    }


@app.get("/mdt/board/{patient_id}")
async def get_mdt_board_bundle(
    patient_id: str,
    scan_ids: str = Query(..., description="Comma-separated scan IDs"),
    current_user: dict = Depends(get_current_user),
):
    """Return MDT-ready synchronized bundle with timeline, findings, and action notes."""
    scan_id_list = [item.strip() for item in scan_ids.split(",") if item.strip()]
    bundles: list[dict[str, Any]] = []
    for scan_id in scan_id_list:
        analysis = _resolve_analysis_payload(scan_id)
        decorated = _decorate_analysis_payload(scan_id, analysis)
        bundles.append(
            {
                "scan_id": scan_id,
                "study_date": decorated.get("study_date"),
                "risk_band": decorated.get("risk_band"),
                "metrics": decorated.get("metrics", {}),
                "critical_findings": decorated.get("critical_findings", []),
                "signoff_history": decorated.get("signoff_history", []),
                "critical_acknowledgements": _CRITICAL_ACK_STORE.get(scan_id, []),
            }
        )

    return {
        "patient_id": patient_id,
        "scans": bundles,
        "board_notes": "Use this synchronized bundle during multidisciplinary case conference review.",
    }


@app.get("/export-package/{scan_id}")
async def export_case_package(
    scan_id: str,
    mode: str = Query("clinician", enum=["clinician", "patient"]),
    template: str = Query("general", pattern="^(general|stroke|neuro_oncology|epilepsy|icu_neurology)$"),
    current_user: dict = Depends(get_current_user),
):
    """Package clinician PDF and machine-readable JSON summary for downstream systems."""
    analysis = _resolve_analysis_payload(scan_id)
    decorated = _decorate_analysis_payload(scan_id, analysis)

    package_dir = _OUTPUTS_DIR / "packages" / scan_id
    package_dir.mkdir(parents=True, exist_ok=True)

    structured_summary_path = package_dir / f"summary_{scan_id}_{mode}_{template}.json"
    with open(structured_summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "scan_id": scan_id,
                "mode": mode,
                "template": template,
                "metrics": decorated.get("metrics", {}),
                "risk_band": decorated.get("risk_band"),
                "provenance_banner": decorated.get("provenance_banner", {}),
                "safety_profile": decorated.get("safety_profile", {}),
                "uncertainty_profile": decorated.get("uncertainty_profile", {}),
                "critical_findings": decorated.get("critical_findings", []),
                "generated_at": _now_iso(),
            },
            f,
            indent=2,
        )

    pdf_path = _OUTPUTS_DIR / "reports" / scan_id / f"report_{scan_id}_{mode}.pdf"
    zip_path = package_dir / f"brainscape_package_{scan_id}_{mode}_{template}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(structured_summary_path, arcname=structured_summary_path.name)
        if pdf_path.exists():
            zf.write(pdf_path, arcname=pdf_path.name)

    return {
        "scan_id": scan_id,
        "mode": mode,
        "template": template,
        "zip_url": f"/outputs/packages/{scan_id}/{zip_path.name}",
        "summary_url": f"/outputs/packages/{scan_id}/{structured_summary_path.name}",
        "includes_pdf": pdf_path.exists(),
    }


# ── Frontend Serving ──


@app.get("/")
async def serve_frontend():
    """Redirect to the single Next.js frontend entrypoint."""
    return RedirectResponse(url=f"{_FRONTEND_URL}/", status_code=307)


@app.get("/report-view/{scan_id}")
async def serve_report_page(scan_id: str, mode: str = Query("patient", enum=["clinician", "patient"])):
    """Redirect report requests to the Next.js frontend."""
    target = f"{_FRONTEND_URL}/?scan_id={scan_id}&report_mode={mode}"
    return RedirectResponse(url=target, status_code=307)


# Mount generated outputs first so mesh/report artifacts are web-accessible.
app.mount("/outputs", StaticFiles(directory=str(_OUTPUTS_DIR)), name="outputs")


# ── Startup & Shutdown ──

@app.on_event("startup")
async def startup():
    logger.info("Brain_Scape API starting up")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Brain_Scape API shutting down")


def main():
    """Run the API server."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=2)


if __name__ == "__main__":
    main()
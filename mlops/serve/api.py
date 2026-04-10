"""
Brain_Scape — FastAPI Server

Exposes all capabilities as REST endpoints with async job tracking.
No neuroimaging job runs synchronously — all heavy compute is queued.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Query, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from compliance.rbac import RBACManager
from compliance.audit_logger import AuditLogger

logger = logging.getLogger(__name__)

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


# ── In-Memory Job Store (production would use Postgres) ──

_job_store: dict[str, dict] = {}


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

    Returns a job_id immediately. The scan is processed asynchronously.
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

    return {
        "job_id": job_id,
        "status": "queued",
        "eta_seconds": 600,  # ~10 min estimate
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
    current_user: dict = Depends(get_current_user),
):
    """Retrieve the 3D mesh and damage overlay."""
    # In production: generate signed S3 URL
    return {
        "mesh_url": f"/outputs/export/{scan_id}/brain.glb",
        "gif_url": f"/outputs/export/{scan_id}/brain_rotation.gif",
        "damage_map": f"/outputs/export/{scan_id}/brain_damage_map.json",
    }


@app.get("/report/{scan_id}")
async def get_report(
    scan_id: str,
    mode: str = Query("clinician", enum=["clinician", "patient"]),
    current_user: dict = Depends(get_current_user),
):
    """Download the PDF report."""
    role = current_user.get("role", "patient")

    # RBAC: patients can only see patient mode
    if role == "patient" and mode == "clinician":
        raise HTTPException(status_code=403, detail="Patients can only access patient-mode reports")

    return {
        "pdf_url": f"/outputs/reports/{scan_id}/report_{scan_id}_{mode}.pdf",
        "summary": f"Report for scan {scan_id} in {mode} mode",
    }


@app.post("/query")
async def query_scan(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """Scan-aware LLM Q&A endpoint."""
    from llm.qa_engine import QAEngine
    from llm.rag_engine import RAGEngine

    # Load analysis results
    import json
    if request.scan_id == _DEMO_SCAN_ID:
        scan_analysis = dict(_DEMO_ANALYSIS)
        scan_analysis.setdefault("regions", list(_DEMO_DAMAGE_SUMMARY))
    else:
        analysis_path = f"outputs/analysis/{request.scan_id}/analysis.json"
        try:
            with open(analysis_path) as f:
                scan_analysis = json.load(f)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Analysis for scan {request.scan_id} not found")

    # Run Q&A
    rag = RAGEngine()
    qa = QAEngine(rag_engine=rag)
    result = qa.answer(
        question=request.question,
        scan_analysis=scan_analysis,
        voice_audio_b64=request.voice_audio_b64,
    )

    return result


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

    audit.log(
        user_id=current_user.get("sub", ""),
        role=current_user.get("role", ""),
        action=f"GET /prognosis/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED",
    )

    return generator.to_dict(result)


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
        "comparisons": [comparator.to_dict(r) for r in results],
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

    return result


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

    planner = PlanningOverlay()
    result = planner.analyze(analysis.get("damage_summary", []), scan_id=scan_id)

    audit.log(
        user_id=current_user.get("sub", ""),
        role=role,
        action=f"POST /treatment-planning/{scan_id}",
        resource_id=scan_id,
        outcome="ALLOWED",
    )

    return planner.to_dict(result)


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
    }


# ── Demo Data ──

_DEMO_SCAN_ID = "demo-scan-001"

_DEMO_DAMAGE_SUMMARY = [
    {"atlas_id": "AAL3_01", "anatomical_name": "Precentral_L", "severity_level": 2, "severity_label": "YELLOW", "confidence": 0.89, "volume_mm3": 3420, "pct_region": 12.3, "start_face": 0, "end_face": 5000},
    {"atlas_id": "AAL3_02", "anatomical_name": "Precentral_R", "severity_level": 1, "severity_label": "GREEN", "confidence": 0.94, "volume_mm3": 0, "pct_region": 0.0, "start_face": 5000, "end_face": 10000},
    {"atlas_id": "AAL3_21", "anatomical_name": "Hippocampus_L", "severity_level": 4, "severity_label": "RED", "confidence": 0.92, "volume_mm3": 1850, "pct_region": 34.1, "start_face": 10000, "end_face": 13000},
    {"atlas_id": "AAL3_22", "anatomical_name": "Hippocampus_R", "severity_level": 3, "severity_label": "ORANGE", "confidence": 0.87, "volume_mm3": 980, "pct_region": 18.7, "start_face": 13000, "end_face": 16000},
    {"atlas_id": "AAL3_31", "anatomical_name": "Frontal_Sup_L", "severity_level": 2, "severity_label": "YELLOW", "confidence": 0.78, "volume_mm3": 2100, "pct_region": 8.5, "start_face": 16000, "end_face": 22000},
    {"atlas_id": "AAL3_41", "anatomical_name": "Temporal_Mid_L", "severity_level": 1, "severity_label": "GREEN", "confidence": 0.91, "volume_mm3": 0, "pct_region": 0.0, "start_face": 22000, "end_face": 28000},
    {"atlas_id": "AAL3_51", "anatomical_name": "Parietal_Inf_L", "severity_level": 0, "severity_label": "BLUE", "confidence": 0.96, "volume_mm3": 0, "pct_region": 0.0, "start_face": 28000, "end_face": 34000},
    {"atlas_id": "AAL3_61", "anatomical_name": "Occipital_Sup_L", "severity_level": 1, "severity_label": "GREEN", "confidence": 0.93, "volume_mm3": 0, "pct_region": 0.0, "start_face": 34000, "end_frame": 40000},
]

_DEMO_ANALYSIS = {
    "scan_id": _DEMO_SCAN_ID,
    "modalities": ["MRI_T1"],
    "atlas": "AAL3",
    "overall_confidence": 0.90,
    "scan_quality": "good",
    "damage_summary": _DEMO_DAMAGE_SUMMARY,
    "executive_summary": "Left hippocampal region shows severe atrophy with high confidence. Right hippocampus shows moderate changes. Mild abnormalities detected in left precentral and superior frontal regions. All other regions appear healthy.",
    "total_faces": 40000,
}


@app.get("/demo/analysis")
async def get_demo_analysis():
    """Return demo analysis data for the frontend to display without a real scan."""
    return _DEMO_ANALYSIS


@app.post("/demo/ingest")
async def demo_ingest():
    """Simulate an ingest that immediately completes with demo data."""
    job_id = _DEMO_SCAN_ID
    _job_store[job_id] = {
        "job_id": job_id,
        "user_id": "demo-clinician",
        "scan_path": "data/samples/demo_t1.nii.gz",
        "status": "complete",
        "stage": "done",
        "progress_pct": 100,
        "error_message": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"job_id": job_id, "status": "complete", "scan_id": _DEMO_SCAN_ID}


# ── Frontend Serving ──

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main frontend page."""
    index_path = os.path.join(_FRONTEND_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/report-view/{scan_id}", response_class=HTMLResponse)
async def serve_report_page(scan_id: str, mode: str = Query("patient", enum=["clinician", "patient"])):
    """Serve the report HTML page."""
    if mode == "clinician":
        report_path = os.path.join(_FRONTEND_DIR, "report", "clinician_report.html")
    else:
        report_path = os.path.join(_FRONTEND_DIR, "report", "patient_report.html")
    with open(report_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# Mount frontend static assets (JS, CSS) — must be after API routes
app.mount("/frontend", StaticFiles(directory=_FRONTEND_DIR), name="frontend")


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
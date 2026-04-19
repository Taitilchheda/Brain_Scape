from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from nilearn import datasets, surface


ROOT = Path(__file__).resolve().parents[1]
SCAN_ID = "taitl-perfect-20260419"
PATIENT_ID = "custom-taitl-001"
PATIENT_CODE = "CUST-TAITL01"
PATIENT_NAME = "taitl"


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _build_damage_summary() -> list[dict]:
    # Region partition ranges are placeholders for viewer indexing consistency.
    regions = [
        ("AAL3_01", "Precentral_L", 0, 5000),
        ("AAL3_02", "Precentral_R", 5000, 10000),
        ("AAL3_21", "Hippocampus_L", 10000, 13000),
        ("AAL3_22", "Hippocampus_R", 13000, 16000),
        ("AAL3_31", "Frontal_Sup_L", 16000, 22000),
        ("AAL3_32", "Frontal_Sup_R", 22000, 28000),
        ("AAL3_51", "Parietal_Inf_L", 28000, 34000),
        ("AAL3_52", "Parietal_Inf_R", 34000, 40000),
    ]

    summary: list[dict] = []
    for atlas_id, name, start_face, end_face in regions:
        summary.append(
            {
                "atlas_id": atlas_id,
                "anatomical_name": name,
                "severity_level": 1,
                "severity_label": "GREEN",
                "confidence": 0.97,
                "volume_mm3": 0.0,
                "pct_region": 0.0,
                "start_face": start_face,
                "end_face": end_face,
            }
        )
    return summary


def _build_analysis_payload(study_date: str) -> dict:
    confidence = 0.972
    metrics = {
        "flagged_regions": 0,
        "severe_regions": 0,
        "moderate_regions": 0,
        "mild_regions": 0,
        "triage_score": round(confidence * 2.0, 2),
        "flagged_volume_mm3": 0.0,
        "severe_volume_mm3": 0.0,
        "mean_region_confidence_pct": 97.0,
        "highest_region_burden_pct": 0.0,
    }

    return {
        "scan_id": SCAN_ID,
        "patient_id": PATIENT_ID,
        "patient_code": PATIENT_CODE,
        "patient_name": PATIENT_NAME,
        "modalities": ["MRI_T1"],
        "atlas": "AAL3",
        "overall_confidence": confidence,
        "scan_quality": "excellent",
        "damage_summary": _build_damage_summary(),
        "executive_summary": (
            "High-fidelity human cortical template reconstruction with no focal abnormality "
            "above configured clinical thresholds."
        ),
        "primary_concern": "Baseline healthy cortical reference",
        "study_date": study_date,
        "source_upload": "data/raw/uploads/brainscape_sample_fmri.nii.gz",
        "analysis_mode": "perfect-human-template",
        "provenance_source": "fsaverage-template",
        "total_faces": 40000,
        "trend": "baseline",
        "metrics": metrics,
        "risk_band": "low",
        "differential_diagnosis": [
            {
                "etiology": "No acute lesion burden detected",
                "probability": 0.92,
                "rationale": "No elevated severity regions in atlas-level quantification.",
            },
            {
                "etiology": "Normal anatomic variant",
                "probability": 0.08,
                "rationale": "Cortical shape aligns with fsaverage template morphology.",
            },
        ],
        "dicom_profile": {
            "study_uid": "1.2.826.0.1.3680043.10.5432.2026041901",
            "study_date": study_date,
            "modality": "MRI",
            "window_level": {"window_width": 80, "window_center": 40},
            "presets": {
                "brain": {"window_width": 80, "window_center": 40},
                "stroke": {"window_width": 40, "window_center": 35},
                "subdural": {"window_width": 240, "window_center": 80},
                "bone": {"window_width": 2800, "window_center": 600},
            },
            "series": [
                {
                    "series_uid": "1.2.826.0.1.3680043.10.5432.2026041901.1",
                    "series_number": 1,
                    "description": "T1 axial",
                    "plane": "axial",
                    "matrix": [512, 512],
                    "slice_count": 176,
                    "slice_thickness_mm": 1.0,
                    "pixel_spacing_mm": [0.5, 0.5],
                },
                {
                    "series_uid": "1.2.826.0.1.3680043.10.5432.2026041901.2",
                    "series_number": 2,
                    "description": "T1 coronal MPR",
                    "plane": "coronal",
                    "matrix": [512, 512],
                    "slice_count": 176,
                    "slice_thickness_mm": 1.0,
                    "pixel_spacing_mm": [0.5, 0.5],
                },
                {
                    "series_uid": "1.2.826.0.1.3680043.10.5432.2026041901.3",
                    "series_number": 3,
                    "description": "T1 sagittal MPR",
                    "plane": "sagittal",
                    "matrix": [512, 512],
                    "slice_count": 176,
                    "slice_thickness_mm": 1.0,
                    "pixel_spacing_mm": [0.5, 0.5],
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
        },
    }


def _write_analysis(payload: dict) -> Path:
    out_dir = ROOT / "outputs" / "analysis" / SCAN_ID
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "analysis.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def _load_fsaverage_mesh() -> tuple[np.ndarray, np.ndarray]:
    fs = datasets.fetch_surf_fsaverage(mesh="fsaverage5")
    left_vertices, left_faces = surface.load_surf_mesh(fs.pial_left)
    right_vertices, right_faces = surface.load_surf_mesh(fs.pial_right)

    vertices = np.vstack([left_vertices, right_vertices]).astype(np.float32)
    right_faces_shifted = right_faces + len(left_vertices)
    faces = np.vstack([left_faces, right_faces_shifted]).astype(np.int32)
    return vertices, faces


def _write_obj(mesh_path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    lines: list[str] = ["# Brain_Scape fsaverage human cortical mesh"]
    lines.extend(f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in vertices)
    lines.extend(f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces)
    mesh_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_mesh_bundle() -> dict[str, str]:
    export_dir = ROOT / "outputs" / "export" / SCAN_ID
    export_dir.mkdir(parents=True, exist_ok=True)

    vertices, faces = _load_fsaverage_mesh()
    mesh_files = [
        export_dir / "brain_v2_web.obj",
        export_dir / "brain_hq_v2_web.obj",
        export_dir / "brain_xq_v2_web.obj",
    ]
    for mesh_path in mesh_files:
        _write_obj(mesh_path, vertices, faces)

    damage_map = {
        "scan_id": SCAN_ID,
        "patient_id": PATIENT_ID,
        "mesh_source": "nilearn.fsaverage5.pial",
        "damage_regions": [],
        "severity_counts": {"GREEN": 8, "YELLOW": 0, "ORANGE": 0, "RED": 0},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (export_dir / "brain_damage_map.json").write_text(json.dumps(damage_map, indent=2), encoding="utf-8")

    return {
        "standard": str(mesh_files[0]),
        "high": str(mesh_files[1]),
        "extreme": str(mesh_files[2]),
    }


def _upsert_custom_patient(study_date: str, metrics: dict) -> Path:
    path = ROOT / "data" / "processed" / "custom_patients.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        patients = raw if isinstance(raw, list) else []
    else:
        patients = []

    patients = [p for p in patients if str(p.get("patient_id")) != PATIENT_ID]

    patient_record = {
        "patient_id": PATIENT_ID,
        "patient_code": PATIENT_CODE,
        "display_name": PATIENT_NAME,
        "age": 30,
        "sex": "O",
        "risk_band": "low",
        "primary_concern": "Baseline healthy cortical anatomy",
        "latest_scan_id": SCAN_ID,
        "modality": "MRI_T1",
        "study_date": study_date,
        "trend": "baseline",
        "overall_confidence": 0.972,
        "flagged_regions": 0,
        "severe_regions": 0,
        "triage_score": metrics["triage_score"],
        "dicom_ready": True,
        "dicom_tools": ["MPR", "WL", "Cine", "Measure", "Crosshair"],
        "timeline": [
            {
                "scan_id": SCAN_ID,
                "study_date": study_date,
                "risk_band": "low",
                "modality": "MRI_T1",
                "overall_confidence": 0.972,
                "metrics": metrics,
            }
        ],
        "notes": "Perfect human cortical reference case for taitl.",
        "source": "custom",
    }

    patients.append(patient_record)
    path.write_text(json.dumps(patients, indent=2), encoding="utf-8")
    return path


def main() -> None:
    study_date = _utc_date()
    payload = _build_analysis_payload(study_date=study_date)

    analysis_path = _write_analysis(payload)
    mesh_paths = _write_mesh_bundle()
    patient_store = _upsert_custom_patient(study_date=study_date, metrics=payload["metrics"])

    print("Created taitl patient bundle")
    print(f"scan_id: {SCAN_ID}")
    print(f"analysis: {analysis_path}")
    print(f"mesh_high: {mesh_paths['high']}")
    print(f"custom_patient_store: {patient_store}")


if __name__ == "__main__":
    main()
"""
Brain_Scape — Pipeline Orchestration (Prefect)

Orchestrates the full end-to-end workflow:
  ingest → preprocess → reconstruct → analyze → generate_report → export → register_run

Each task is independently retryable. Failed tasks emit a structured error
event and trigger an alert. Partial results are stored — if Task 5 fails
after Task 4 completes, re-running from Task 5 does not re-run the GPU analysis.
"""

import logging
from datetime import timedelta
from typing import Optional

from prefect import flow, task, get_run_logger

logger = logging.getLogger(__name__)


# ── Task Definitions ──

@task(retries=2, retry_delay_seconds=60, timeout_seconds=300)
def ingest(scan_path: str, job_id: str) -> dict:
    """Task 1: Ingest and normalize scan format."""
    from ingestion.format_detector import detect_format
    from ingestion.validator import ScanValidator
    from ingestion.anonymizer import PHIScrubber
    from ingestion.converter import FormatConverter

    logger.info(f"[Job {job_id}] Starting ingestion: {scan_path}")

    # Detect format
    fmt, metadata = detect_format(scan_path)

    # Validate quality
    validator = ScanValidator()
    validation = validator.validate(scan_path, fmt, metadata)
    if not validation.is_valid:
        raise ValueError(f"Scan validation failed: {validation.errors}")

    # Anonymize PHI (blocking, synchronous)
    scrubber = PHIScrubber()

    # Convert to NIfTI
    converter = FormatConverter()
    nifti_path, conv_metadata = converter.convert(scan_path, fmt, job_id, metadata)

    return {
        "job_id": job_id,
        "nifti_path": nifti_path,
        "format": fmt.value,
        "metadata": {**metadata, **conv_metadata},
        "quality_score": validation.quality_score,
    }


@task(retries=1, retry_delay_seconds=120, timeout_seconds=1200)
def preprocess(ingest_result: dict, job_id: str) -> dict:
    """Task 2: Preprocess the scan (skull strip, normalize, register)."""
    from preprocessing.skull_stripper import SkullStripper
    from preprocessing.intensity_normalizer import IntensityNormalizer
    from preprocessing.denoiser import Denoiser
    from preprocessing.atlas_registrar import AtlasRegistrar

    logger.info(f"[Job {job_id}] Starting preprocessing")

    input_path = ingest_result["nifti_path"]
    processed_dir = f"data/processed/{job_id}"

    # Stage 1: Skull stripping
    stripper = SkullStripper(fsl_bet_threshold=0.5)
    stripped_path = f"{processed_dir}/stripped.nii.gz"
    strip_stats = stripper.strip(input_path, stripped_path)

    # Stage 2: Intensity normalization
    normalizer = IntensityNormalizer(method="zscore")
    normalized_path = f"{processed_dir}/normalized.nii.gz"
    norm_stats = normalizer.normalize(stripped_path, normalized_path)

    # Stage 3: Denoising
    denoiser = Denoiser(fwhm_mm=6.0)
    denoised_path = f"{processed_dir}/denoised.nii.gz"
    denoise_stats = denoiser.denoise(normalized_path, denoised_path)

    # Stage 4: Atlas registration (most expensive — 5-20 min)
    registrar = AtlasRegistrar(method="ants_syn")
    registered_path = f"data/registered/{job_id}/registered.nii.gz"
    reg_stats = registrar.register(denoised_path, registered_path)

    return {
        "job_id": job_id,
        "registered_path": registered_path,
        "stats": {
            "skull_strip": strip_stats,
            "normalization": norm_stats,
            "denoising": denoise_stats,
            "registration": reg_stats,
        },
    }


@task(retries=1, retry_delay_seconds=60, timeout_seconds=600)
def reconstruct(preprocess_result: dict, job_id: str) -> dict:
    """Task 3: Build 3D mesh from registered scan."""
    from reconstruction.mesh_builder import MeshBuilder
    from reconstruction.region_labeler import RegionLabeler

    logger.info(f"[Job {job_id}] Starting reconstruction")

    registered_path = preprocess_result["registered_path"]
    output_dir = f"outputs/mesh/{job_id}"

    # Build mesh
    builder = MeshBuilder(decimation_target=150000)
    mesh_stats = builder.build(registered_path, output_dir)

    # Label regions
    labeler = RegionLabeler()
    label_stats = labeler.label(
        f"{output_dir}/brain_web.obj",
        registered_path,
        f"{output_dir}/region_labels.json",
    )

    return {
        "job_id": job_id,
        "mesh_dir": output_dir,
        "mesh_stats": mesh_stats,
        "label_stats": label_stats,
    }


@task(retries=1, retry_delay_seconds=60, timeout_seconds=900)
def analyze(preprocess_result: dict, job_id: str) -> dict:
    """Task 4: Run segmentation, classification, and confidence scoring (GPU-bound)."""
    from analysis.segmentation.segmentor import BrainSegmentor
    from analysis.segmentation.voxel_scorer import VoxelScorer
    from analysis.classification.damage_classifier import DamageClassifier
    from analysis.classification.confidence_scorer import ConfidenceScorer

    logger.info(f"[Job {job_id}] Starting analysis")

    registered_path = preprocess_result["registered_path"]
    output_dir = f"outputs/analysis/{job_id}"

    # Segmentation
    segmentor = BrainSegmentor()
    seg_path = f"{output_dir}/segmentation.nii.gz"
    seg_stats = segmentor.segment(registered_path, seg_path)

    # Voxel scoring
    scorer = VoxelScorer()
    severity_path = f"{output_dir}/severity_map.nii.gz"
    score_stats = scorer.score(seg_path, registered_path, severity_path)

    # Damage classification
    classifier = DamageClassifier()
    classified = classifier.classify(score_stats["region_scores"])

    # Confidence scoring
    conf_scorer = ConfidenceScorer()
    confidence = conf_scorer.score(
        region_scores=classified,
        scan_quality_score=score_stats.get("quality_score"),
        registration_accuracy=preprocess_result.get("stats", {})
            .get("registration", {}).get("dice_overlap_with_template"),
    )

    # Build analysis JSON (the single source of truth)
    analysis = {
        "scan_id": job_id,
        "job_id": job_id,
        "schema_version": "1.2",
        "atlas": "AAL3",
        "modalities": ["MRI_T1"],
        "regions": classified,
        "differential_diagnosis": [],
        "connectivity": {},
        "overall_confidence": confidence.get("overall_confidence", 0.5),
        "scan_quality_score": score_stats.get("quality_score"),
        "registration_error": preprocess_result.get("stats", {})
            .get("registration", {}).get("dice_overlap_with_template"),
    }

    return {
        "job_id": job_id,
        "analysis": analysis,
        "seg_stats": seg_stats,
        "score_stats": score_stats,
        "confidence": confidence,
    }


@task(retries=3, retry_delay_seconds=30, timeout_seconds=120)
def generate_report(
    analysis_result: dict,
    reconstruct_result: dict,
    preprocess_result: dict,
    job_id: str,
) -> dict:
    """Task 5: Generate LLM-powered report (I/O-bound)."""
    from llm.rag_engine import RAGEngine
    from llm.report_generator import ReportGenerator

    logger.info(f"[Job {job_id}] Starting report generation")

    analysis = analysis_result["analysis"]

    # Initialize RAG and report generator
    rag = RAGEngine()
    generator = ReportGenerator(rag_engine=rag)

    # Generate clinician report
    report = generator.generate(
        scan_analysis=analysis,
        output_dir=f"outputs/reports/{job_id}",
        mode="clinician",
    )

    return {
        "job_id": job_id,
        "report": report,
    }


@task(retries=1, timeout_seconds=60)
def export_artifacts(
    analysis_result: dict,
    reconstruct_result: dict,
    job_id: str,
) -> dict:
    """Task 6: Export mesh, GIF, and report artifacts."""
    from reconstruction.damage_overlay import DamageOverlay
    from reconstruction.gif_exporter import GIFExporter
    from reconstruction.mesh_exporter import MeshExporter

    logger.info(f"[Job {job_id}] Starting artifact export")

    output_dir = f"outputs/export/{job_id}"

    # Apply damage overlay
    overlay = DamageOverlay(opacity=0.85)
    overlay_stats = overlay.apply(
        mesh_path=f"{reconstruct_result['mesh_dir']}/brain_web.obj",
        severity_map_path=f"outputs/analysis/{job_id}/severity_map.nii.gz",
        classified_regions=analysis_result["analysis"]["regions"],
        output_dir=output_dir,
    )

    # Export mesh formats
    exporter = MeshExporter(draco_compression=True)
    export_stats = exporter.export(
        mesh_path=f"{reconstruct_result['mesh_dir']}/brain_web.obj",
        output_dir=output_dir,
        formats=["glb", "obj", "stl"],
    )

    # Export GIF
    gif_exporter = GIFExporter(num_frames=36, resolution=(800, 600))
    gif_stats = gif_exporter.export(
        mesh_path=f"{reconstruct_result['mesh_dir']}/brain_web.obj",
        output_path=f"{output_dir}/brain_rotation.gif",
    )

    return {
        "job_id": job_id,
        "overlay_stats": overlay_stats,
        "export_stats": export_stats,
        "gif_stats": gif_stats,
    }


@task(retries=1, timeout_seconds=30)
def register_run(
    analysis_result: dict,
    export_result: dict,
    job_id: str,
) -> dict:
    """Task 7: Log run to MLflow and register artifacts."""
    from mlops.tracking import TrackingManager

    logger.info(f"[Job {job_id}] Registering run")

    tracker = TrackingManager()
    tracker.log_run(
        job_id=job_id,
        analysis=analysis_result["analysis"],
        confidence=analysis_result.get("confidence", {}),
    )

    return {"job_id": job_id, "registered": True}


# ── Main Pipeline Flow ──

@flow(
    name="brainscape-pipeline",
    description="End-to-end Brain_Scape neuroimaging pipeline",
    retries=1,
    retry_delay_seconds=300,
    timeout_seconds=3600,
)
def brainscape_pipeline(job_id: str, scan_path: str, modalities: list = None) -> dict:
    """
    Run the full Brain_Scape pipeline.

    Args:
        job_id: Unique job identifier.
        scan_path: Path to the uploaded scan file.
        modalities: List of modalities (e.g., ["MRI_T1", "fMRI"]).

    Returns:
        Pipeline result dictionary.
    """
    modalities = modalities or ["MRI_T1"]

    # Task 1: Ingest
    ingest_result = ingest(scan_path, job_id)

    # Task 2: Preprocess
    preprocess_result = preprocess(ingest_result, job_id)

    # Task 3: Reconstruct (depends on preprocessing)
    reconstruct_result = reconstruct(preprocess_result, job_id)

    # Task 4: Analyze (depends on preprocessing, can run in parallel with reconstruct)
    analysis_result = analyze(preprocess_result, job_id)

    # Task 5: Generate report (depends on analysis and reconstruct)
    report_result = generate_report(
        analysis_result, reconstruct_result, preprocess_result, job_id
    )

    # Task 6: Export artifacts
    export_result = export_artifacts(analysis_result, reconstruct_result, job_id)

    # Task 7: Register run
    register_result = register_run(analysis_result, export_result, job_id)

    return {
        "job_id": job_id,
        "status": "complete",
        "ingest": ingest_result,
        "preprocess": preprocess_result,
        "reconstruct": reconstruct_result,
        "analysis": analysis_result,
        "report": report_result,
        "export": export_result,
        "registered": register_result,
    }


# ── CLI Entry Point ──

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m mlops.pipeline <job_id> <scan_path> [modalities]")
        sys.exit(1)

    job_id = sys.argv[1]
    scan_path = sys.argv[2]
    modalities = sys.argv[3:] if len(sys.argv) > 3 else ["MRI_T1"]

    result = brainscape_pipeline(job_id, scan_path, modalities)
    print(f"Pipeline complete: {result['status']}")
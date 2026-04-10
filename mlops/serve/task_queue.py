"""
Brain_Scape — Celery Task Queue

Neuroimaging pipelines take minutes to hours. No request blocks the API thread.
Jobs are queued, tracked, and results retrieved by job ID.
"""

import logging
from celery import Celery
from typing import Optional

logger = logging.getLogger(__name__)

# Celery app configuration
app = Celery(
    "brainscape",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_soft_time_limit=1800,  # 30 min
    task_time_limit=3600,  # 60 min hard limit
    worker_prefetch_multiplier=1,
    task_routes={
        "mlops.serve.task_queue.process_scan": {"queue": "gpu"},
    },
)


@app.task(bind=True, max_retries=2, default_retry_delay=60)
def process_scan(self, job_id: str, scan_path: str, modalities: list = None):
    """
    Process a scan through the full Brain_Scape pipeline.

    This is the main Celery task that runs the pipeline end-to-end.
    GPU-bound tasks (nnU-Net segmentation) are routed to the GPU queue.
    """
    from mlops.pipeline import brainscape_pipeline

    modalities = modalities or ["MRI_T1"]

    try:
        result = brainscape_pipeline(job_id, scan_path, modalities)
        return result
    except Exception as exc:
        logger.error(f"Pipeline failed for job {job_id}: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=3, default_retry_delay=30)
def run_segmentation(self, scan_path: str, job_id: str):
    """Run nnU-Net segmentation only (GPU-bound)."""
    from analysis.segmentation.segmentor import BrainSegmentor

    try:
        segmentor = BrainSegmentor()
        result = segmentor.segment(scan_path, f"outputs/analysis/{job_id}/segmentation.nii.gz")
        return result
    except Exception as exc:
        logger.error(f"Segmentation failed for job {job_id}: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=3, default_retry_delay=10)
def run_llm_query(self, scan_id: str, question: str, scan_analysis: dict):
    """Run an LLM Q&A query (I/O-bound)."""
    from llm.qa_engine import QAEngine
    from llm.rag_engine import RAGEngine

    try:
        rag = RAGEngine()
        qa = QAEngine(rag_engine=rag)
        result = qa.answer(question=question, scan_analysis=scan_analysis)
        return result
    except Exception as exc:
        logger.error(f"LLM query failed for scan {scan_id}: {exc}")
        raise self.retry(exc=exc)


@app.task
def update_job_status(job_id: str, status: str, stage: str, progress_pct: int):
    """Update job status in the database."""
    # In production: update Postgres jobs table
    logger.info(f"Job {job_id}: status={status}, stage={stage}, progress={progress_pct}%")
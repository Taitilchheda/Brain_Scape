"""
Brain_Scape — MLflow Tracking Manager

Logs every training and inference run to MLflow:
model architecture, hyperparameters, segmentation Dice scores,
classification accuracy, confidence calibration metrics.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TrackingManager:
    """MLflow experiment and run tracking for Brain_Scape."""

    def __init__(self, tracking_uri: Optional[str] = None):
        self.tracking_uri = tracking_uri or "http://localhost:5000"
        self._client = None

    def _get_client(self):
        """Lazy-initialize MLflow client."""
        if self._client is not None:
            return self._client

        try:
            import mlflow
            mlflow.set_tracking_uri(self.tracking_uri)
            self._client = mlflow
            return self._client
        except ImportError:
            logger.warning("MLflow not available. Logging to file instead.")
            self._client = None
            return None

    def log_run(
        self,
        job_id: str,
        analysis: dict,
        confidence: dict,
        experiment_name: str = "brainscape",
    ) -> str:
        """
        Log a pipeline run to MLflow.

        Args:
            job_id: Unique job identifier.
            analysis: Analysis results dictionary.
            confidence: Confidence scoring results.
            experiment_name: MLflow experiment name.

        Returns:
            MLflow run ID.
        """
        mlflow = self._get_client()

        if mlflow is not None:
            return self._log_to_mlflow(job_id, analysis, confidence, experiment_name)
        else:
            return self._log_to_file(job_id, analysis, confidence)

    def _log_to_mlflow(
        self, job_id: str, analysis: dict, confidence: dict, experiment_name: str
    ) -> str:
        """Log to MLflow server."""
        import mlflow

        mlflow.set_experiment(experiment_name)

        with mlflow.start_run(run_name=f"brainscape-{job_id}") as run:
            # Log parameters
            mlflow.log_params({
                "job_id": job_id,
                "atlas": analysis.get("atlas", "unknown"),
                "modalities": ",".join(analysis.get("modalities", [])),
                "schema_version": analysis.get("schema_version", "1.0"),
            })

            # Log metrics
            mlflow.log_metrics({
                "overall_confidence": confidence.get("overall_confidence", 0),
                "scan_quality_score": analysis.get("scan_quality_score", 0),
                "num_affected_regions": len([
                    r for r in analysis.get("regions", [])
                    if r.get("severity_level", 0) >= 2
                ]),
            })

            # Log region-level metrics
            for i, region in enumerate(analysis.get("regions", [])[:10]):
                prefix = f"region_{i}_"
                mlflow.log_metrics({
                    f"{prefix}severity": region.get("severity_level", 0),
                    f"{prefix}confidence": region.get("confidence", 0),
                })

            # Log tags
            mlflow.set_tags({
                "pipeline_version": "1.0.0",
                "job_type": "inference",
            })

            return run.info.run_id

    @staticmethod
    def _log_to_file(job_id: str, analysis: dict, confidence: dict) -> str:
        """Fallback: log to local file."""
        import json
        from datetime import datetime

        log_dir = Path("logs/mlflow")
        log_dir.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "job_id": job_id,
            "timestamp": datetime.utcnow().isoformat(),
            "analysis": analysis,
            "confidence": confidence,
        }

        log_file = log_dir / f"run_{job_id}.json"
        with open(log_file, "w") as f:
            json.dump(log_entry, f, indent=2)

        return str(log_file)
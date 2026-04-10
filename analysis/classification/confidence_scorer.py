"""
Brain_Scape — Confidence Scorer

Every prediction in the system carries a confidence score. Derived from:
  1. Deep ensemble agreement — fraction of N=5 models agreeing on severity
  2. Scan quality score — SNR + registration accuracy
  3. Atlas registration accuracy — deformation field smoothness

Final confidence = w1 * ensemble_agreement + w2 * scan_quality + w3 * registration_accuracy

This prevents clinicians from over-trusting uncertain predictions and
enables threshold filtering for clinical decisions.
"""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """
    Computes confidence scores for damage classifications.

    Three components feed the confidence score:
    1. Ensemble agreement (fraction of models agreeing on severity)
    2. Scan quality (SNR measurement + registration error)
    3. Atlas registration accuracy (deformation field smoothness)

    Weights are tunable via configs/models.yaml.
    """

    def __init__(
        self,
        ensemble_size: int = 5,
        weights: Optional[dict] = None,
        clinical_filter_threshold: float = 0.7,
        display_filter_threshold: float = 0.5,
    ):
        """
        Args:
            ensemble_size: Number of model variants in the ensemble.
            weights: Confidence component weights.
                    Default: ensemble_agreement=0.5, scan_quality=0.3, registration_accuracy=0.2
            clinical_filter_threshold: Below this, findings are flagged for review.
            display_filter_threshold: Below this, findings are hidden from patient view.
        """
        self.ensemble_size = ensemble_size
        self.weights = weights or {
            "ensemble_agreement": 0.5,
            "scan_quality": 0.3,
            "registration_accuracy": 0.2,
        }
        self.clinical_filter_threshold = clinical_filter_threshold
        self.display_filter_threshold = display_filter_threshold

        # Validate weights sum to 1.0
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Weights sum to {total}, not 1.0. Normalizing.")
            for key in self.weights:
                self.weights[key] /= total

    def score(
        self,
        ensemble_predictions: Optional[list[int]] = None,
        scan_quality_score: Optional[float] = None,
        registration_accuracy: Optional[float] = None,
        region_scores: Optional[list[dict]] = None,
    ) -> dict:
        """
        Compute confidence scores for all classified regions.

        Args:
            ensemble_predictions: List of severity levels predicted by each
                ensemble member for a given region.
            scan_quality_score: Overall scan quality (0.0 to 1.0).
                Derived from SNR measurement.
            registration_accuracy: Atlas registration quality (0.0 to 1.0).
                Derived from deformation field smoothness.
            region_scores: List of region score dicts from VoxelScorer.

        Returns:
            Dictionary with overall and per-region confidence scores.
        """
        # Compute individual confidence components
        ensemble_agreement = self._compute_ensemble_agreement(ensemble_predictions)
        quality = scan_quality_score if scan_quality_score is not None else 0.5
        registration = registration_accuracy if registration_accuracy is not None else 0.5

        # Weighted combination
        overall_confidence = (
            self.weights["ensemble_agreement"] * ensemble_agreement
            + self.weights["scan_quality"] * quality
            + self.weights["registration_accuracy"] * registration
        )

        # Clamp to [0, 1]
        overall_confidence = max(0.0, min(1.0, overall_confidence))

        result = {
            "overall_confidence": round(overall_confidence, 4),
            "components": {
                "ensemble_agreement": round(ensemble_agreement, 4),
                "scan_quality": round(quality, 4),
                "registration_accuracy": round(registration, 4),
            },
            "weights": self.weights,
            "clinical_filter_threshold": self.clinical_filter_threshold,
            "display_filter_threshold": self.display_filter_threshold,
            "regions": [],
        }

        # Per-region confidence
        if region_scores:
            for region in region_scores:
                region_confidence = self._compute_region_confidence(
                    region, overall_confidence, quality, registration
                )
                result["regions"].append(region_confidence)

        # Flagging
        result["requires_clinical_review"] = overall_confidence < self.clinical_filter_threshold
        result["hidden_from_patient_view"] = overall_confidence < self.display_filter_threshold

        logger.info(
            f"Confidence scoring complete. "
            f"Overall: {overall_confidence:.2%}, "
            f"Review required: {result['requires_clinical_review']}"
        )

        return result

    def _compute_ensemble_agreement(
        self, predictions: Optional[list[int]]
    ) -> float:
        """
        Compute ensemble agreement score.

        Agreement = fraction of models that agree on the majority severity level.
        """
        if predictions is None:
            return 0.5  # Default if no ensemble available

        if len(predictions) == 0:
            return 0.0

        # Find the majority vote
        from collections import Counter
        counts = Counter(predictions)
        majority_level, majority_count = counts.most_common(1)[0]

        # Agreement = fraction of models agreeing with the majority
        agreement = majority_count / len(predictions)
        return float(agreement)

    def _compute_region_confidence(
        self,
        region: dict,
        overall_confidence: float,
        scan_quality: float,
        registration_accuracy: float,
    ) -> dict:
        """
        Compute confidence for a specific region.

        Region confidence may differ from overall confidence based on
        local factors (e.g., regions near ventricles are harder to classify).
        """
        mean_severity = region.get("mean_severity", 0.0)
        volume_pct = region.get("volume_pct_of_region", 0.0)

        # Very small affected volumes are less certain
        size_penalty = min(0.1, volume_pct * 0.01)  # Small penalty for tiny findings

        # Very high severity is more certain than borderline cases
        severity_boost = 0.05 if mean_severity > 0.8 else 0.0

        region_confidence = overall_confidence - size_penalty + severity_boost
        region_confidence = max(0.0, min(1.0, region_confidence))

        return {
            "atlas_id": region.get("atlas_id", "unknown"),
            "anatomical_name": region.get("anatomical_name", "unknown"),
            "confidence": round(region_confidence, 4),
            "severity_level": region.get("severity_level", 0),
            "severity_label": region.get("severity_label", "BLUE"),
            "requires_clinical_review": region_confidence < self.clinical_filter_threshold,
            "hidden_from_patient_view": region_confidence < self.display_filter_threshold,
        }

    @staticmethod
    def compute_scan_quality_score(
        snr_estimate: float,
        registration_dice: Optional[float] = None,
    ) -> float:
        """
        Compute a scan quality score from SNR and registration accuracy.

        Args:
            snr_estimate: Signal-to-noise ratio from the validator.
            registration_dice: Dice overlap with MNI template after registration.

        Returns:
            Quality score between 0.0 and 1.0.
        """
        # Normalize SNR: good scans have SNR > 20
        snr_score = min(1.0, snr_estimate / 50.0)

        if registration_dice is not None:
            # Dice overlap > 0.9 is good, > 0.95 is excellent
            dice_score = min(1.0, registration_dice / 0.95)
            quality = 0.5 * snr_score + 0.5 * dice_score
        else:
            quality = snr_score

        return max(0.0, min(1.0, quality))
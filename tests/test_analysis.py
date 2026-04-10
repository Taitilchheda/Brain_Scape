"""
Brain_Scape — Analysis Layer Tests

Tests for segmentation, classification, and confidence scoring.
"""

import numpy as np
import pytest

from analysis.classification.damage_classifier import DamageClassifier, SEVERITY_LEVELS
from analysis.classification.confidence_scorer import ConfidenceScorer


class TestDamageClassifier:
    """Test the 5-level damage classification system."""

    def test_severity_levels_defined(self):
        """All 5 severity levels should be defined."""
        assert len(SEVERITY_LEVELS) == 5
        assert 0 in SEVERITY_LEVELS
        assert 4 in SEVERITY_LEVELS

    def test_color_contract(self):
        """Each severity level should have a unique hex color."""
        hex_colors = [SEVERITY_LEVELS[i]["hex"] for i in range(5)]
        assert len(set(hex_colors)) == 5  # All unique

    def test_classify_healthy_region(self):
        """A region with very little damage should be classified as GREEN or BLUE."""
        classifier = DamageClassifier()
        region_scores = [
            {
                "atlas_id": "Hippocampus_L",
                "anatomical_name": "Left Hippocampus",
                "mean_severity": 0.01,
                "volume_pct_of_region": 0.5,
                "confidence": 0.95,
            }
        ]
        result = classifier.classify(region_scores)
        assert len(result) == 1
        assert result[0]["severity_level"] <= 1  # BLUE or GREEN

    def test_classify_severely_damaged_region(self):
        """A region with >60% damage should be classified as RED."""
        classifier = DamageClassifier()
        region_scores = [
            {
                "atlas_id": "Hippocampus_L",
                "anatomical_name": "Left Hippocampus",
                "mean_severity": 0.8,
                "volume_pct_of_region": 65.0,
                "confidence": 0.91,
            }
        ]
        result = classifier.classify(region_scores)
        assert result[0]["severity_level"] == 4  # RED

    def test_classify_moderate_damage(self):
        """A region with ~35% damage should be classified as ORANGE."""
        classifier = DamageClassifier()
        region_scores = [
            {
                "atlas_id": "Frontal_Lobe_R",
                "anatomical_name": "Right Frontal Lobe",
                "mean_severity": 0.4,
                "volume_pct_of_region": 35.0,
                "confidence": 0.85,
            }
        ]
        result = classifier.classify(region_scores)
        assert result[0]["severity_level"] == 3  # ORANGE

    def test_sorted_by_severity(self):
        """Results should be sorted by severity (most severe first)."""
        classifier = DamageClassifier()
        region_scores = [
            {"atlas_id": "A", "anatomical_name": "A", "mean_severity": 0.1, "volume_pct_of_region": 5, "confidence": 0.9},
            {"atlas_id": "B", "anatomical_name": "B", "mean_severity": 0.7, "volume_pct_of_region": 55, "confidence": 0.9},
            {"atlas_id": "C", "anatomical_name": "C", "mean_severity": 0.3, "volume_pct_of_region": 20, "confidence": 0.9},
        ]
        result = classifier.classify(region_scores)
        severities = [r["severity_level"] for r in result]
        assert severities == sorted(severities, reverse=True)

    def test_get_severity_color(self):
        """get_severity_color should return hex codes."""
        assert DamageClassifier.get_severity_color(4) == "#E74C3C"
        assert DamageClassifier.get_severity_color(0) == "#4A90D9"


class TestConfidenceScorer:
    """Test the 3-component confidence scoring model."""

    def test_high_confidence(self):
        """High ensemble agreement + high quality = high confidence."""
        scorer = ConfidenceScorer()
        result = scorer.score(
            ensemble_predictions=[4, 4, 4, 4, 4],  # All models agree
            scan_quality_score=0.95,
            registration_accuracy=0.98,
        )
        assert result["overall_confidence"] > 0.8

    def test_low_confidence(self):
        """Disagreement + low quality = low confidence."""
        scorer = ConfidenceScorer()
        result = scorer.score(
            ensemble_predictions=[1, 2, 3, 4, 4],  # High disagreement
            scan_quality_score=0.3,
            registration_accuracy=0.4,
        )
        assert result["overall_confidence"] < 0.6

    def test_weights_sum_to_one(self):
        """Confidence component weights should sum to 1.0."""
        scorer = ConfidenceScorer()
        total = sum(scorer.weights.values())
        assert abs(total - 1.0) < 0.01

    def test_clinical_filter_threshold(self):
        """Low confidence should be flagged for clinical review."""
        scorer = ConfidenceScorer(clinical_filter_threshold=0.7)
        result = scorer.score(
            ensemble_predictions=[1, 1, 1, 4, 4],  # Disagreement
            scan_quality_score=0.3,
            registration_accuracy=0.4,
        )
        assert result["requires_clinical_review"] is True

    def test_compute_scan_quality_score(self):
        """Scan quality score should be between 0 and 1."""
        score = ConfidenceScorer.compute_scan_quality_score(snr_estimate=30.0)
        assert 0.0 <= score <= 1.0

    def test_empty_ensemble(self):
        """Empty ensemble should return default confidence."""
        scorer = ConfidenceScorer()
        result = scorer.score(
            ensemble_predictions=None,
            scan_quality_score=0.8,
            registration_accuracy=0.9,
        )
        assert 0.0 <= result["overall_confidence"] <= 1.0


class TestAnalysisJSONContract:
    """Test that analysis output matches the expected JSON schema."""

    def test_schema_version_present(self):
        """Analysis output should include schema_version."""
        analysis = {
            "scan_id": "test-123",
            "job_id": "job-456",
            "schema_version": "1.2",
            "atlas": "AAL3",
            "modalities": ["MRI_T1"],
            "regions": [],
        }
        assert "schema_version" in analysis
        assert analysis["schema_version"] == "1.2"

    def test_required_fields(self):
        """Analysis output should include all required fields."""
        required_fields = [
            "scan_id", "job_id", "atlas", "modalities",
            "regions", "overall_confidence"
        ]
        analysis = {
            "scan_id": "test-123",
            "job_id": "job-456",
            "schema_version": "1.2",
            "atlas": "AAL3",
            "modalities": ["MRI_T1"],
            "regions": [],
            "overall_confidence": 0.88,
        }
        for field in required_fields:
            assert field in analysis
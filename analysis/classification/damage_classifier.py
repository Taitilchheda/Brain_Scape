"""
Brain_Scape — Damage Classifier

Maps per-region severity scores to the 5-level color scale:
  0: BLUE    (#4A90D9) — Not implicated
  1: GREEN   (#27AE60) — No damage detected
  2: YELLOW  (#F1C40F) — Mild abnormality
  3: ORANGE  (#E67E22) — Moderate-to-severe
  4: RED     (#E74C3C) — Severe damage

The color contract is defined once in configs/models.yaml and
referenced by reconstruction, frontend, and report generation.
"""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Color Contract ──
# Defined once, referenced everywhere. Do NOT duplicate.
SEVERITY_LEVELS = {
    0: {"label": "BLUE",    "hex": "#4A90D9", "semantic": "Not implicated"},
    1: {"label": "GREEN",   "hex": "#27AE60", "semantic": "No damage detected"},
    2: {"label": "YELLOW",  "hex": "#F1C40F", "semantic": "Mild abnormality"},
    3: {"label": "ORANGE",  "hex": "#E67E22", "semantic": "Moderate-to-severe"},
    4: {"label": "RED",     "hex": "#E74C3C", "semantic": "Severe damage"},
}


class DamageClassifier:
    """
    Classifies damage severity per atlas region using the 5-level color scale.

    Takes per-region severity scores from VoxelScorer and produces
    a structured classification output with the standard color mapping.
    """

    def __init__(
        self,
        thresholds: Optional[dict] = None,
        atlas_labels: Optional[dict] = None,
    ):
        """
        Args:
            thresholds: Severity thresholds mapping percentage to levels.
                       Defaults from configs/models.yaml.
            atlas_labels: Mapping of atlas region IDs to anatomical names.
        """
        self.thresholds = thresholds or {
            "blue": 0.00,   # Not implicated
            "green": 0.01,  # No damage detected
            "yellow": 0.10, # Mild abnormality
            "orange": 0.30, # Moderate-to-severe
            "red": 0.60,    # Severe damage
        }
        self.atlas_labels = atlas_labels or {}

    def classify(
        self,
        region_scores: list[dict],
    ) -> list[dict]:
        """
        Classify damage severity for each atlas region.

        Args:
            region_scores: Output from VoxelScorer.score() -> region_scores list.

        Returns:
            List of classified regions with severity levels, labels, and colors.
        """
        classified = []

        for region in region_scores:
            atlas_id = region["atlas_id"]
            mean_severity = region.get("mean_severity", 0.0)
            volume_pct = region.get("volume_pct_of_region", 0.0)
            confidence = region.get("confidence", 0.5)

            # Determine severity level based on percentage of damaged tissue
            level = self._classify_level(volume_pct)

            # Determine severity level based on mean severity score
            severity_level = self._classify_severity(mean_severity)

            # Use the higher of the two (more conservative approach)
            final_level = max(level, severity_level)

            classified_region = {
                "atlas_id": atlas_id,
                "anatomical_name": region.get(
                    "anatomical_name",
                    self.atlas_labels.get(atlas_id, atlas_id),
                ),
                "severity_level": final_level,
                "severity_label": SEVERITY_LEVELS[final_level]["label"],
                "severity_hex": SEVERITY_LEVELS[final_level]["hex"],
                "severity_semantic": SEVERITY_LEVELS[final_level]["semantic"],
                "volume_mm3": region.get("volume_mm3", 0.0),
                "volume_pct_of_region": volume_pct,
                "mean_severity": mean_severity,
                "confidence": confidence,
            }
            classified.append(classified_region)

        # Sort by severity (most severe first)
        classified.sort(key=lambda x: x["severity_level"], reverse=True)

        logger.info(
            f"Damage classification: "
            f"{sum(1 for r in classified if r['severity_level'] >= 3)} severe/critical regions, "
            f"{sum(1 for r in classified if r['severity_level'] >= 2)} total affected regions"
        )

        return classified

    def _classify_level(self, volume_pct: float) -> int:
        """
        Classify severity based on percentage of region damaged.

        Uses the threshold mapping from configs/models.yaml:
            0%  -> BLUE (not implicated)
            1%  -> GREEN (no damage detected)
            10% -> YELLOW (mild abnormality)
            30% -> ORANGE (moderate-to-severe)
            60% -> RED (severe damage)
        """
        if volume_pct < self.thresholds["green"]:
            return 0  # BLUE
        elif volume_pct < self.thresholds["yellow"]:
            return 1  # GREEN
        elif volume_pct < self.thresholds["orange"]:
            return 2  # YELLOW
        elif volume_pct < self.thresholds["red"]:
            return 3  # ORANGE
        else:
            return 4  # RED

    def _classify_severity(self, mean_severity: float) -> int:
        """
        Classify severity based on mean severity score (0.0 to 1.0).
        """
        if mean_severity < 0.05:
            return 0  # BLUE
        elif mean_severity < 0.15:
            return 1  # GREEN
        elif mean_severity < 0.35:
            return 2  # YELLOW
        elif mean_severity < 0.65:
            return 3  # ORANGE
        else:
            return 4  # RED

    @staticmethod
    def get_severity_color(level: int) -> str:
        """Get the hex color for a severity level."""
        return SEVERITY_LEVELS.get(level, SEVERITY_LEVELS[0])["hex"]

    @staticmethod
    def get_severity_label(level: int) -> str:
        """Get the label for a severity level."""
        return SEVERITY_LEVELS.get(level, SEVERITY_LEVELS[0])["label"]

    @staticmethod
    def get_severity_semantic(level: int) -> str:
        """Get the semantic description for a severity level."""
        return SEVERITY_LEVELS.get(level, SEVERITY_LEVELS[0])["semantic"]
"""
Brain_Scape — Voxel Scorer

Converts binary segmentation masks into continuous severity scores
per voxel and per atlas region. Outputs volume of affected tissue
in mm^3 and as a percentage of total region volume.
"""

import logging
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


class VoxelScorer:
    """
    Scores damage severity per voxel and per atlas region.

    Takes a segmentation mask and registered brain volume,
    intersects with atlas parcellation, and produces a
    structured scoring output.
    """

    def __init__(
        self,
        atlas_path: str = "data/atlases/AAL3.nii.gz",
        severity_thresholds: Optional[dict] = None,
    ):
        """
        Args:
            atlas_path: Path to the atlas parcellation file.
            severity_thresholds: Custom severity thresholds by label.
        """
        self.atlas_path = atlas_path
        self.severity_thresholds = severity_thresholds or {
            "healthy": 0.0,
            "mild": 0.10,
            "moderate": 0.30,
            "severe": 0.60,
        }

    def score(
        self,
        segmentation_path: str,
        registered_path: str,
        output_path: str,
    ) -> dict:
        """
        Score damage severity per voxel and per atlas region.

        Args:
            segmentation_path: Path to the segmentation mask from segmentor.
            registered_path: Path to the MNI152-registered brain scan.
            output_path: Path to write the severity map.

        Returns:
            Dictionary with per-region severity scores and volumes.
        """
        # Load inputs
        seg_img = nib.load(segmentation_path)
        seg_data = seg_img.get_fdata()

        reg_img = nib.load(registered_path)
        reg_data = reg_img.get_fdata()

        voxel_sizes = reg_img.header.get_zooms()[:3]
        voxel_volume_mm3 = voxel_sizes[0] * voxel_sizes[1] * voxel_sizes[2]

        # Load atlas parcellation
        atlas_data = None
        atlas_labels = {}
        if Path(self.atlas_path).exists():
            atlas_img = nib.load(self.atlas_path)
            atlas_data = atlas_img.get_fdata()

            # Extract unique region labels
            unique_labels = np.unique(atlas_data).astype(int)
            for label in unique_labels:
                if label == 0:
                    continue  # Background
                atlas_labels[label] = f"Region_{label}"

        # Compute continuous severity score per voxel
        brain_mask = reg_data > 0
        severity_map = np.zeros_like(reg_data, dtype=np.float32)

        if seg_data.ndim == reg_data.ndim:
            # Continuous segmentation (probabilities or severity)
            severity_map[brain_mask] = seg_data[brain_mask]
        else:
            # Binary or multi-label segmentation — convert to severity
            severity_map = self._labels_to_severity(seg_data, brain_mask)

        # Save severity map
        severity_img = nib.Nifti1Image(severity_map, reg_img.affine, reg_img.header)
        nib.save(severity_img, output_path)

        # Compute per-region scores
        region_scores = self._compute_region_scores(
            severity_map, atlas_data, atlas_labels, brain_mask, voxel_volume_mm3
        )

        # Compute overall statistics
        damage_voxels = np.sum(severity_map[brain_mask] > self.severity_thresholds["mild"])
        total_brain_voxels = np.sum(brain_mask)

        stats = {
            "total_brain_volume_mm3": float(total_brain_voxels * voxel_volume_mm3),
            "total_damage_volume_mm3": float(damage_voxels * voxel_volume_mm3),
            "damage_pct_of_brain": round(
                damage_voxels / total_brain_voxels * 100, 2
            ) if total_brain_voxels > 0 else 0.0,
            "mean_severity": float(np.mean(severity_map[brain_mask])),
            "max_severity": float(np.max(severity_map[brain_mask])),
            "severity_std": float(np.std(severity_map[brain_mask])),
            "voxel_volume_mm3": float(voxel_volume_mm3),
            "region_scores": region_scores,
            "atlas_used": Path(self.atlas_path).stem if Path(self.atlas_path).exists() else "none",
        }

        logger.info(
            f"Voxel scoring complete. "
            f"Damage: {stats['damage_pct_of_brain']:.1f}% of brain, "
            f"{len(region_scores)} regions scored."
        )
        return stats

    def _labels_to_severity(
        self, seg_data: np.ndarray, brain_mask: np.ndarray
    ) -> np.ndarray:
        """
        Convert integer segmentation labels to continuous severity scores.

        Label mapping:
            0 = background (0.0)
            1 = healthy tissue (0.0)
            2 = mild damage (0.3)
            3 = moderate damage (0.6)
            4+ = severe damage (0.8+)
        """
        severity = np.zeros_like(seg_data, dtype=np.float32)

        label_to_severity = {
            0: 0.0,   # Background
            1: 0.0,   # Healthy
            2: 0.3,   # Mild damage
            3: 0.6,   # Moderate damage
            4: 0.8,   # Severe damage
            5: 0.95,  # Very severe
        }

        for label, sev in label_to_severity.items():
            severity[seg_data == label] = sev

        # Labels above 5 get even higher severity
        severity[seg_data > 5] = 1.0

        # Apply brain mask
        severity[~brain_mask] = 0.0

        return severity

    def _compute_region_scores(
        self,
        severity_map: np.ndarray,
        atlas_data: Optional[np.ndarray],
        atlas_labels: dict,
        brain_mask: np.ndarray,
        voxel_volume_mm3: float,
    ) -> list[dict]:
        """
        Compute severity scores for each atlas region.

        Returns a list of region dictionaries with:
        - atlas_id, anatomical_name (if available)
        - severity_level, severity_label
        - volume_mm3, volume_pct_of_region
        - mean_severity, max_severity
        """
        region_scores = []

        if atlas_data is None:
            # No atlas available — score the whole brain
            damage_mask = severity_map > self.severity_thresholds["mild"]
            damage_volume = np.sum(damage_mask) * voxel_volume_mm3
            total_volume = np.sum(brain_mask) * voxel_volume_mm3

            region_scores.append({
                "atlas_id": "whole_brain",
                "anatomical_name": "Whole Brain",
                "severity_level": self._severity_level(np.mean(severity_map[brain_mask])),
                "severity_label": self._severity_label(np.mean(severity_map[brain_mask])),
                "volume_mm3": float(damage_volume),
                "volume_pct_of_region": round(
                    damage_volume / total_volume * 100, 2
                ) if total_volume > 0 else 0.0,
                "mean_severity": float(np.mean(severity_map[brain_mask])),
                "max_severity": float(np.max(severity_map[brain_mask])),
                "confidence": 0.5,  # Lower confidence without atlas
            })
            return region_scores

        # Score each atlas region
        unique_labels = np.unique(atlas_data).astype(int)

        for label in unique_labels:
            if label == 0:
                continue  # Skip background

            region_mask = atlas_data == label
            region_brain = region_mask & brain_mask
            region_volume = np.sum(region_brain)

            if region_volume == 0:
                continue

            # Severity within this region
            region_severity = severity_map[region_brain]
            mean_sev = float(np.mean(region_severity))
            max_sev = float(np.max(region_severity))

            # Volume of damaged tissue in this region
            damage_in_region = region_severity > self.severity_thresholds["mild"]
            damage_volume = np.sum(damage_in_region) * voxel_volume_mm3
            total_region_volume = region_volume * voxel_volume_mm3

            region_scores.append({
                "atlas_id": f"Region_{label}",
                "anatomical_name": atlas_labels.get(label, f"Region_{label}"),
                "severity_level": self._severity_level(mean_sev),
                "severity_label": self._severity_label(mean_sev),
                "volume_mm3": float(damage_volume),
                "volume_pct_of_region": round(
                    damage_volume / total_region_volume * 100, 2
                ) if total_region_volume > 0 else 0.0,
                "mean_severity": round(mean_sev, 4),
                "max_severity": round(max_sev, 4),
                "confidence": 0.8,  # Higher confidence with atlas
            })

        # Sort by severity (most damaged first)
        region_scores.sort(key=lambda x: x["mean_severity"], reverse=True)

        return region_scores

    def _severity_level(self, mean_severity: float) -> int:
        """Map mean severity score to integer level 0-4."""
        if mean_severity < self.severity_thresholds["mild"]:
            return 1  # GREEN
        elif mean_severity < self.severity_thresholds["moderate"]:
            return 2  # YELLOW
        elif mean_severity < self.severity_thresholds["severe"]:
            return 3  # ORANGE
        else:
            return 4  # RED

    def _severity_label(self, mean_severity: float) -> str:
        """Map mean severity score to color label."""
        level = self._severity_level(mean_severity)
        labels = {0: "BLUE", 1: "GREEN", 2: "YELLOW", 3: "ORANGE", 4: "RED"}
        return labels.get(level, "BLUE")
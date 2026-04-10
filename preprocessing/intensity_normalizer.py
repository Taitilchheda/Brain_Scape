"""
Brain_Scape — Intensity Normalizer

Standardizes voxel intensity ranges across different MRI scanners.
Different scanners produce different intensity ranges for the same
tissue type. Normalization makes scans from different hospitals
comparable.

Must run after skull stripping (skull has extreme intensities).
"""

import logging
from typing import Optional

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


class IntensityNormalizer:
    """
    Normalizes voxel intensity values for cross-scanner comparability.

    Supports three normalization methods:
    - zscore: Mean=0, Std=1 (most common for ML pipelines)
    - minmax: Scale to [0, 1]
    - histogram_matching: Match to a reference intensity distribution
    """

    def __init__(
        self,
        method: str = "zscore",
        percentile_clip: tuple[float, float] = (1.0, 99.0),
    ):
        """
        Args:
            method: Normalization method ("zscore", "minmax", "histogram_matching").
            percentile_clip: Clip intensities below/above these percentiles
                           before normalizing to remove outlier voxels.
        """
        self.method = method
        self.percentile_clip = percentile_clip

    def normalize(
        self,
        input_path: str,
        output_path: str,
        reference_path: Optional[str] = None,
    ) -> dict:
        """
        Normalize voxel intensities in a brain scan.

        Args:
            input_path: Path to skull-stripped NIfTI file.
            output_path: Path to write normalized NIfTI file.
            reference_path: Optional reference image for histogram matching.

        Returns:
            Dictionary with normalization statistics.
        """
        img = nib.load(input_path)
        data = img.get_fdata()

        # Get brain mask (non-zero voxels)
        brain_mask = data > 0
        brain_data = data[brain_mask]

        if len(brain_data) == 0:
            logger.warning("No brain voxels found — skipping normalization.")
            nib.save(img, output_path)
            return {"skipped": True, "reason": "no_brain_voxels"}

        # Clip extreme intensities
        low_clip = np.percentile(brain_data, self.percentile_clip[0])
        high_clip = np.percentile(brain_data, self.percentile_clip[1])
        clipped = np.clip(data, low_clip, high_clip)

        # Apply normalization method
        if self.method == "zscore":
            normalized = self._zscore_normalize(clipped, brain_mask)
        elif self.method == "minmax":
            normalized = self._minmax_normalize(clipped, brain_mask)
        elif self.method == "histogram_matching":
            if reference_path is None:
                logger.warning(
                    "No reference image for histogram matching. "
                    "Falling back to zscore normalization."
                )
                normalized = self._zscore_normalize(clipped, brain_mask)
            else:
                normalized = self._histogram_matching(clipped, brain_mask, reference_path)
        else:
            raise ValueError(f"Unknown normalization method: {self.method}")

        # Save normalized image
        normalized_img = nib.Nifti1Image(normalized, img.affine, img.header)
        nib.save(normalized_img, output_path)

        stats = {
            "method": self.method,
            "original_range": [float(brain_data.min()), float(brain_data.max())],
            "original_mean": float(brain_data.mean()),
            "original_std": float(brain_data.std()),
            "clip_percentiles": list(self.percentile_clip),
            "clip_values": [float(low_clip), float(high_clip)],
        }

        # Add normalized range stats
        norm_brain = normalized[brain_mask]
        stats["normalized_range"] = [float(norm_brain.min()), float(norm_brain.max())]
        stats["normalized_mean"] = float(norm_brain.mean())
        stats["normalized_std"] = float(norm_brain.std())

        logger.info(
            f"Intensity normalization ({self.method}): "
            f"range [{brain_data.min():.1f}, {brain_data.max():.1f}] -> "
            f"[{norm_brain.min():.2f}, {norm_brain.max():.2f}]"
        )
        return stats

    @staticmethod
    def _zscore_normalize(data: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Z-score normalization: (x - mean) / std for brain voxels only."""
        brain = data[mask]
        mean = brain.mean()
        std = brain.std()

        if std == 0:
            return data

        normalized = data.copy()
        normalized[mask] = (brain - mean) / std
        # Keep background as 0
        normalized[~mask] = 0
        return normalized

    @staticmethod
    def _minmax_normalize(data: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Min-max normalization: scale to [0, 1] for brain voxels only."""
        brain = data[mask]
        min_val = brain.min()
        max_val = brain.max()

        if max_val == min_val:
            return data

        normalized = data.copy()
        normalized[mask] = (brain - min_val) / (max_val - min_val)
        normalized[~mask] = 0
        return normalized

    @staticmethod
    def _histogram_matching(
        data: np.ndarray, mask: np.ndarray, reference_path: str
    ) -> np.ndarray:
        """
        Match intensity distribution to a reference scan.

        Uses histogram specification to transform the input intensities
        so that they follow the same distribution as the reference.
        """
        ref_img = nib.load(reference_path)
        ref_data = ref_img.get_fdata()
        ref_mask = ref_data > 0
        ref_brain = ref_data[ref_mask]

        source_brain = data[mask]

        # Compute CDFs
        src_hist, src_bins = np.histogram(source_brain, bins=256)
        ref_hist, _ = np.histogram(ref_brain, bins=256)

        src_cdf = np.cumsum(src_hist).astype(float)
        src_cdf /= src_cdf[-1]
        ref_cdf = np.cumsum(ref_hist).astype(float)
        ref_cdf /= ref_cdf[-1]

        # Create mapping: source CDF -> reference CDF
        mapping = np.interp(src_cdf, ref_cdf, (src_bins[:-1] + src_bins[1:]) / 2)

        # Apply mapping
        normalized = data.copy()
        flat_brain = source_brain.flatten()
        indices = np.digitize(flat_brain, src_bins[:-1]) - 1
        indices = np.clip(indices, 0, len(mapping) - 1)
        matched_brain = mapping[indices]

        normalized[mask] = matched_brain.reshape(source_brain.shape)
        normalized[~mask] = 0

        return normalized
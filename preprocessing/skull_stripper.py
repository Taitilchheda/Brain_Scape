"""
Brain_Scape — Skull Stripper

Removes non-brain tissue (skull, scalp, meninges) from structural MRI scans
using FSL BET (Brain Extraction Tool). Must run before intensity normalization
because skull voxels have extreme intensities that distort normalization.
"""

import logging
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


class SkullStripper:
    """
    Removes non-brain tissue from structural MRI scans.

    Uses FSL BET as the primary method with configurable threshold.
    Falls back to a simple intensity-based method if FSL is not available.
    """

    def __init__(self, fsl_bet_threshold: float = 0.5, method: str = "fsl_bet"):
        """
        Args:
            fsl_bet_threshold: BET fractional intensity threshold.
                0.0 = keep more tissue, 1.0 = aggressive stripping.
            method: "fsl_bet" or "intensity_fallback".
        """
        self.threshold = fsl_bet_threshold
        self.method = method

    def strip(
        self,
        input_path: str,
        output_path: str,
    ) -> dict:
        """
        Remove non-brain tissue from a structural MRI scan.

        Args:
            input_path: Path to the input NIfTI file (skull-on).
            output_path: Path to write the skull-stripped NIfTI file.

        Returns:
            Dictionary with stripping statistics.
        """
        if self.method == "fsl_bet":
            return self._strip_fsl_bet(input_path, output_path)
        else:
            return self._strip_intensity(input_path, output_path)

    def _strip_fsl_bet(self, input_path: str, output_path: str) -> dict:
        """Run FSL BET for skull stripping."""
        try:
            import subprocess

            cmd = [
                "bet",
                input_path,
                output_path,
                "-f", str(self.threshold),
                "-m",  # Generate binary brain mask
            ]

            logger.info(f"Running FSL BET: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                logger.warning(
                    f"FSL BET failed (exit {result.returncode}): {result.stderr}. "
                    f"Falling back to intensity-based method."
                )
                return self._strip_intensity(input_path, output_path)

            # Load and validate output
            img = nib.load(output_path)
            stats = self._compute_stats(img)

            logger.info(
                f"Skull stripping complete: {stats['brain_voxel_pct']:.1f}% brain voxels"
            )
            return stats

        except FileNotFoundError:
            logger.warning("FSL BET not found. Falling back to intensity-based method.")
            return self._strip_intensity(input_path, output_path)
        except subprocess.TimeoutExpired:
            logger.warning("FSL BET timed out. Falling back to intensity-based method.")
            return self._strip_intensity(input_path, output_path)

    def _strip_intensity(self, input_path: str, output_path: str) -> dict:
        """
        Fallback skull stripping using intensity-based thresholding.

        Uses Otsu's method to find an initial threshold, then applies
        morphological operations to clean up the brain mask.
        """
        img = nib.load(input_path)
        data = img.get_fdata()

        # Otsu's method for threshold
        threshold = self._otsu_threshold(data)
        brain_mask = data > threshold

        # Morphological cleanup
        brain_mask = self._morphological_cleanup(brain_mask)

        # Apply mask
        stripped_data = data * brain_mask

        # Save
        stripped_img = nib.Nifti1Image(stripped_data, img.affine, img.header)
        nib.save(stripped_img, output_path)

        # Also save the mask
        mask_path = output_path.replace(".nii.gz", "_mask.nii.gz")
        mask_img = nib.Nifti1Image(brain_mask.astype(np.int8), img.affine, img.header)
        nib.save(mask_img, mask_path)

        stats = self._compute_stats_from_mask(data, brain_mask)
        logger.info(
            f"Intensity-based skull stripping complete: "
            f"{stats['brain_voxel_pct']:.1f}% brain voxels"
        )
        return stats

    @staticmethod
    def _otsu_threshold(data: np.ndarray) -> float:
        """Compute Otsu's threshold for brain/non-brain separation."""
        non_zero = data[data > 0].flatten()
        if len(non_zero) == 0:
            return 0.0

        # Compute histogram
        hist, bin_edges = np.histogram(non_zero, bins=256)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

        # Otsu's method
        total = hist.sum()
        sum_total = (bin_centers * hist).sum()
        sum_bg = 0.0
        weight_bg = 0
        max_variance = 0.0
        best_threshold = float(bin_centers[0])

        for i in range(len(hist)):
            weight_bg += hist[i]
            if weight_bg == 0:
                continue
            weight_fg = total - weight_bg
            if weight_fg == 0:
                break

            sum_bg += bin_centers[i] * hist[i]
            mean_bg = sum_bg / weight_bg
            mean_fg = (sum_total - sum_bg) / weight_fg

            variance = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
            if variance > max_variance:
                max_variance = variance
                best_threshold = float(bin_centers[i])

        return best_threshold

    @staticmethod
    def _morphological_cleanup(mask: np.ndarray) -> np.ndarray:
        """Apply morphological operations to clean up the brain mask."""
        from scipy import ndimage

        # Fill holes
        filled = ndimage.binary_fill_holes(mask)

        # Remove small connected components (noise)
        labeled, num_features = ndimage.label(filled)
        if num_features > 1:
            component_sizes = ndimage.sum(filled, labeled, range(1, num_features + 1))
            largest = np.argmax(component_sizes) + 1
            filled = labeled == largest

        # Slight erosion then dilation (opening) to remove skull edges
        struct = ndimage.generate_binary_structure(3, 1)
        filled = ndimage.binary_opening(filled, structure=struct, iterations=1)

        return filled.astype(bool)

    @staticmethod
    def _compute_stats(img: nib.Nifti1Image) -> dict:
        """Compute skull stripping statistics from the output image."""
        data = img.get_fdata()
        total_voxels = data.size
        brain_voxels = np.count_nonzero(data)
        return {
            "total_voxels": int(total_voxels),
            "brain_voxels": int(brain_voxels),
            "brain_voxel_pct": round(brain_voxels / total_voxels * 100, 2),
        }

    @staticmethod
    def _compute_stats_from_mask(data: np.ndarray, mask: np.ndarray) -> dict:
        """Compute statistics from data and mask."""
        total_voxels = data.size
        brain_voxels = np.count_nonzero(mask)
        return {
            "total_voxels": int(total_voxels),
            "brain_voxels": int(brain_voxels),
            "brain_voxel_pct": round(brain_voxels / total_voxels * 100, 2),
            "method": "intensity_fallback",
        }
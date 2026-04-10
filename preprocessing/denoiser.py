"""
Brain_Scape — Denoiser

Spatial smoothing and noise removal for neuroimaging data.
Preserves tissue boundaries while removing acquisition noise.

Must run after motion correction (noise is amplified by motion).
"""

import logging
from typing import Optional

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


class Denoiser:
    """
    Removes acquisition noise from neuroimaging data.

    Supports Gaussian smoothing and non-local means denoising.
    """

    def __init__(
        self,
        smoothing_method: str = "gaussian",
        fwhm_mm: float = 6.0,
        nlmeans_patch_radius: int = 1,
        nlmeans_search_radius: int = 3,
    ):
        """
        Args:
            smoothing_method: "gaussian" or "nlmeans".
            fwhm_mm: Full-width half-maximum for Gaussian kernel (mm).
            nlmeans_patch_radius: Patch radius for NLMeans denoising.
            nlmeans_search_radius: Search radius for NLMeans denoising.
        """
        self.smoothing_method = smoothing_method
        self.fwhm_mm = fwhm_mm
        self.nlmeans_patch_radius = nlmeans_patch_radius
        self.nlmeans_search_radius = nlmeans_search_radius

    def denoise(
        self,
        input_path: str,
        output_path: str,
    ) -> dict:
        """
        Denoise a brain scan.

        Args:
            input_path: Path to the input NIfTI file.
            output_path: Path to write the denoised NIfTI file.

        Returns:
            Dictionary with denoising statistics.
        """
        img = nib.load(input_path)
        data = img.get_fdata()
        brain_mask = data > 0

        if self.smoothing_method == "gaussian":
            smoothed = self._gaussian_smooth(data, img, brain_mask)
        elif self.smoothing_method == "nlmeans":
            smoothed = self._nlmeans_denoise(data, brain_mask)
        else:
            raise ValueError(f"Unknown smoothing method: {self.smoothing_method}")

        # Preserve zeros (background)
        smoothed[~brain_mask] = 0

        # Save
        smoothed_img = nib.Nifti1Image(smoothed, img.affine, img.header)
        nib.save(smoothed_img, output_path)

        stats = {
            "method": self.smoothing_method,
            "fwhm_mm": self.fwhm_mm,
            "noise_reduction_pct": self._estimate_noise_reduction(data, smoothed, brain_mask),
        }

        logger.info(
            f"Denoising ({self.smoothing_method}): "
            f"noise reduced by ~{stats['noise_reduction_pct']:.1f}%"
        )
        return stats

    def _gaussian_smooth(
        self,
        data: np.ndarray,
        img: nib.Nifti1Image,
        brain_mask: np.ndarray,
    ) -> np.ndarray:
        """
        Apply Gaussian spatial smoothing.

        Converts FWHM in mm to sigma in voxels, then applies 3D Gaussian filter.
        """
        from scipy.ndimage import gaussian_filter

        # Convert FWHM to sigma
        # FWHM = 2 * sqrt(2 * ln(2)) * sigma ≈ 2.355 * sigma
        voxel_sizes = img.header.get_zooms()[:3]
        sigma_voxels = []
        for fwhm, vox_size in zip([self.fwhm_mm] * 3, voxel_sizes):
            sigma_mm = fwhm / 2.355
            sigma_voxels.append(sigma_mm / vox_size)

        smoothed = gaussian_filter(data.astype(np.float32), sigma=sigma_voxels)
        return smoothed

    def _nlmeans_denoise(
        self,
        data: np.ndarray,
        brain_mask: np.ndarray,
    ) -> np.ndarray:
        """
        Apply Non-Local Means denoising.

        Better at preserving edges than Gaussian smoothing, but slower.
        """
        try:
            from skimage.restoration import denoise_nl_means

            # NLMeans works best on normalized data
            brain_data = data[brain_mask]
            mean_val = brain_data.mean()
            std_val = brain_data.std()

            if std_val == 0:
                return data

            normalized = data.copy()
            normalized[brain_mask] = (brain_data - mean_val) / std_val
            normalized[~brain_mask] = 0

            # Apply NLMeans
            denoised = denoise_nl_means(
                normalized,
                patch_size=2 * self.nlmeans_patch_radius + 1,
                patch_distance=2 * self.nlmeans_search_radius + 1,
                h=0.8,  # Noise standard deviation parameter
                fast_mode=True,
            )

            # Denormalize
            result = denoised * std_val + mean_val
            return result

        except ImportError:
            logger.warning(
                "scikit-image not available for NLMeans. "
                "Falling back to Gaussian smoothing."
            )
            return self._gaussian_smooth(data, nib.load(""), brain_mask)

    @staticmethod
    def _estimate_noise_reduction(
        original: np.ndarray,
        smoothed: np.ndarray,
        brain_mask: np.ndarray,
    ) -> float:
        """Estimate percentage of noise removed."""
        orig_std = original[brain_mask].std()
        smooth_std = smoothed[brain_mask].std()

        if orig_std == 0:
            return 0.0

        return round((1 - smooth_std / orig_std) * 100, 1)
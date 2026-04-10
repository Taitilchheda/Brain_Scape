"""
Brain_Scape — Motion Corrector

Corrects for patient head movement during fMRI acquisition using
FSL MCFLIRT. Aligns every volume to a reference volume.

Only applies to fMRI (4D) data. Must run before slice timing correction.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


class MotionCorrector:
    """
    Corrects head motion in fMRI time-series data.

    Uses FSL MCFLIRT to align all volumes to a reference volume.
    For non-fMRI data (3D structural scans), this step is skipped.
    """

    def __init__(
        self,
        reference_volume: str = "middle",
        cost_function: str = "normcorr",
        degrees_of_freedom: int = 6,
    ):
        """
        Args:
            reference_volume: Which volume to align to.
                "middle" — middle volume of the time series
                "first" — first volume
                Or an explicit integer index.
            cost_function: MCFLIRT cost function.
                "normcorr" — normalized correlation
                "mutualinfo" — mutual information
                "corratio" — correlation ratio
            degrees_of_freedom: DOF for registration (6=rigid, 9=affine).
        """
        self.reference_volume = reference_volume
        self.cost_function = cost_function
        self.degrees_of_freedom = degrees_of_freedom

    def correct(
        self,
        input_path: str,
        output_path: str,
        is_fmri: bool = True,
    ) -> dict:
        """
        Apply motion correction to an fMRI scan.

        Args:
            input_path: Path to the input 4D NIfTI file.
            output_path: Path to write the motion-corrected file.
            is_fmri: Whether the input is fMRI (4D). If False, skip.

        Returns:
            Dictionary with motion correction statistics.
        """
        if not is_fmri:
            logger.info("Not fMRI data — skipping motion correction.")
            return {"skipped": True, "reason": "not_fmri"}

        # Verify input is 4D
        img = nib.load(input_path)
        if len(img.shape) < 4:
            logger.info("Input is 3D — skipping motion correction.")
            return {"skipped": True, "reason": "not_4d"}

        num_volumes = img.shape[3]

        # Determine reference volume index
        ref_idx = self._get_reference_index(num_volumes)

        try:
            return self._correct_mcflirt(input_path, output_path, ref_idx)
        except FileNotFoundError:
            logger.warning("FSL MCFLIRT not found. Falling back to simple method.")
            return self._correct_simple(input_path, output_path, ref_idx)

    def _correct_mcflirt(
        self, input_path: str, output_path: str, ref_idx: int
    ) -> dict:
        """Run FSL MCFLIRT for motion correction."""
        cmd = [
            "mcflirt",
            "-in", input_path,
            "-out", output_path,
            "-refvol", str(ref_idx),
            "-cost", self.cost_function,
            "-dof", str(self.degrees_of_freedom),
            "-plots",  # Generate motion parameter plots
            "-mats",   # Save transformation matrices
        ]

        logger.info(f"Running MCFLIRT: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            raise RuntimeError(f"MCFLIRT failed: {result.stderr}")

        # Parse motion parameters from the .par file
        stats = {
            "method": "fsl_mcflirt",
            "reference_volume": ref_idx,
            "cost_function": self.cost_function,
            "degrees_of_freedom": self.degrees_of_freedom,
            "num_volumes": nib.load(input_path).shape[3],
        }

        # Try to read motion parameters
        par_file = output_path + ".par"
        if Path(par_file).exists():
            motion_params = np.loadtxt(par_file)
            stats["max_translation_mm"] = float(np.max(np.abs(motion_params[:, 3:])))
            stats["max_rotation_deg"] = float(np.max(np.abs(motion_params[:, :3])))
            stats["mean_translation_mm"] = float(np.mean(np.abs(motion_params[:, 3:])))
            stats["motion_exceeded_threshold"] = stats["max_translation_mm"] > 2.0

        logger.info(
            f"Motion correction complete. "
            f"Max translation: {stats.get('max_translation_mm', 'N/A')}mm"
        )
        return stats

    def _correct_simple(
        self, input_path: str, output_path: str, ref_idx: int
    ) -> dict:
        """
        Simple motion correction fallback using rigid registration.

        Uses nibabel + scipy for a basic volume-to-volume alignment.
        """
        img = nib.load(input_path)
        data = img.get_fdata()
        ref_volume = data[..., ref_idx]

        corrected = np.zeros_like(data)
        corrected[..., ref_idx] = ref_volume

        from scipy.ndimage import shift

        for i in range(data.shape[3]):
            if i == ref_idx:
                corrected[..., i] = data[..., i]
                continue

            # Simple cross-correlation to estimate shift
            vol = data[..., i]
            shift_estimate = self._estimate_shift(ref_volume, vol)

            # Apply shift
            corrected[..., i] = shift(vol, shift_estimate, order=1)

        # Save corrected image
        corrected_img = nib.Nifti1Image(corrected, img.affine, img.header)
        nib.save(corrected_img, output_path)

        return {
            "method": "simple_crosscorr",
            "reference_volume": ref_idx,
            "num_volumes": data.shape[3],
        }

    def _get_reference_index(self, num_volumes: int) -> int:
        """Get the reference volume index."""
        if self.reference_volume == "middle":
            return num_volumes // 2
        elif self.reference_volume == "first":
            return 0
        else:
            try:
                return int(self.reference_volume)
            except ValueError:
                return num_volumes // 2

    @staticmethod
    def _estimate_shift(ref: np.ndarray, moving: np.ndarray) -> tuple:
        """
        Estimate translational shift between two volumes using
        phase correlation (FFT-based).
        """
        from scipy.signal import fftconvolve

        # Compute cross-correlation in Fourier domain
        product = np.fft.ffn(ref) * np.conj(np.fft.ffn(moving))
        cc = np.fft.iffn(product)
        cc_shift = np.unravel_index(np.argmax(np.abs(cc)), cc.shape)

        # Convert to shift relative to center
        center = np.array(ref.shape) // 2
        shift = np.array(cc_shift) - center

        # Handle wrap-around
        for i in range(len(shift)):
            if shift[i] > center[i]:
                shift[i] -= ref.shape[i]

        return tuple(shift.astype(float))
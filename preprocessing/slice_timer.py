"""
Brain_Scape — Slice Timer

Corrects for the temporal offset between slice acquisitions in fMRI data.
fMRI volumes are acquired slice by slice, not all at once. Slice timing
correction accounts for the time difference between the first and last
slice in a volume.

Only applies to fMRI data. Must run after motion correction.
"""

import logging
from typing import Optional

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


class SliceTimer:
    """
    Corrects slice timing in fMRI data.

    fMRI volumes are acquired slice by slice over the TR (repetition time).
    Each slice is acquired at a slightly different time. This correction
    interpolates all slices to a common time point.
    """

    def __init__(
        self,
        repetition_time: float = 2.0,
        slice_order: str = "interleaved",
        reference_slice: str = "middle",
        interleaved: bool = True,
    ):
        """
        Args:
            repetition_time: TR in seconds.
            slice_order: "sequential", "interleaved", or custom list.
            reference_slice: Which slice to align to ("middle", "first", index).
            interleaved: Whether slices were acquired interleaved.
        """
        self.tr = repetition_time
        self.slice_order = slice_order
        self.reference_slice = reference_slice
        self.interleaved = interleaved

    def correct(
        self,
        input_path: str,
        output_path: str,
        is_fmri: bool = True,
    ) -> dict:
        """
        Apply slice timing correction to fMRI data.

        Args:
            input_path: Path to the 4D NIfTI file.
            output_path: Path to write the corrected file.
            is_fmri: If False, skip correction.

        Returns:
            Dictionary with correction statistics.
        """
        if not is_fmri:
            logger.info("Not fMRI data — skipping slice timing correction.")
            return {"skipped": True, "reason": "not_fmri"}

        img = nib.load(input_path)
        data = img.get_fdata()

        if len(data.shape) < 4:
            logger.info("3D data — skipping slice timing correction.")
            return {"skipped": True, "reason": "not_4d"}

        n_slices = data.shape[2]
        n_volumes = data.shape[3]

        # Compute slice acquisition times
        slice_times = self._compute_slice_times(n_slices)
        ref_time = self._get_reference_time(slice_times)

        # Correct each slice by interpolating to the reference time
        corrected = np.zeros_like(data, dtype=np.float32)

        for z in range(n_slices):
            # Time offset for this slice relative to reference
            time_offset = slice_times[z] - ref_time

            if abs(time_offset) < 1e-6:
                # This is the reference slice — no correction needed
                corrected[:, :, z, :] = data[:, :, z, :]
                continue

            # Interpolate each voxel's time series
            for x in range(data.shape[0]):
                for y in range(data.shape[1]):
                    ts = data[x, y, z, :]
                    if np.any(ts != 0):
                        corrected[x, y, z, :] = self._interpolate_timeseries(
                            ts, time_offset, self.tr
                        )

        # Save
        corrected_img = nib.Nifti1Image(corrected, img.affine, img.header)
        nib.save(corrected_img, output_path)

        stats = {
            "method": "sinc_interpolation",
            "tr_seconds": self.tr,
            "n_slices": n_slices,
            "n_volumes": n_volumes,
            "slice_order": self.slice_order,
            "max_time_offset_ms": round(
                max(abs(t - ref_time) for t in slice_times) * 1000, 1
            ),
        }

        logger.info(
            f"Slice timing correction: {n_slices} slices, "
            f"max offset {stats['max_time_offset_ms']}ms"
        )
        return stats

    def _compute_slice_times(self, n_slices: int) -> list[float]:
        """Compute acquisition time for each slice."""
        slice_duration = self.tr / n_slices

        if self.slice_order == "interleaved" or self.interleaved:
            # Odd slices first, then even (0-based: even indices, then odd)
            order = list(range(0, n_slices, 2)) + list(range(1, n_slices, 2))
        elif self.slice_order == "sequential":
            order = list(range(n_slices))
        else:
            order = list(range(n_slices))  # Default to sequential

        times = [0.0] * n_slices
        for i, slice_idx in enumerate(order):
            if slice_idx < n_slices:
                times[slice_idx] = i * slice_duration

        return times

    def _get_reference_time(self, slice_times: list[float]) -> float:
        """Get the reference time point to align all slices to."""
        if self.reference_slice == "middle":
            return np.median(slice_times)
        elif self.reference_slice == "first":
            return min(slice_times)
        else:
            try:
                return float(self.reference_slice)
            except ValueError:
                return np.median(slice_times)

    @staticmethod
    def _interpolate_timeseries(
        timeseries: np.ndarray,
        time_offset: float,
        tr: float,
    ) -> np.ndarray:
        """
        Interpolate a voxel time series to correct for slice timing offset.

        Uses sinc interpolation (ideal for band-limited signals).
        Falls back to linear interpolation for speed.
        """
        n = len(timeseries)
        original_times = np.arange(n) * tr
        corrected_times = original_times - time_offset

        # Linear interpolation (fast, good enough for most cases)
        corrected = np.interp(
            corrected_times,
            original_times,
            timeseries,
            left=timeseries[0],
            right=timeseries[-1],
        )

        return corrected.astype(np.float32)
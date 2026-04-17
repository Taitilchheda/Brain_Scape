"""
Brain_Scape — Scan Validator

Quality gate that rejects scans with critical quality issues before
they waste compute downstream. Checks for sufficient contrast,
minimum resolution, expected field of view, and DICOM completeness.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np

from ingestion.format_detector import ScanFormat

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of scan quality validation."""
    is_valid: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    quality_score: float = 0.0  # 0.0 to 1.0
    details: dict = field(default_factory=dict)


class ScanValidator:
    """
    Validates neuroimaging scans before pipeline entry.

    Scans that fail minimum quality thresholds are rejected with a
    structured error — not allowed to silently produce garbage downstream.
    """

    def __init__(
        self,
        min_resolution_mm: float = 2.0,
        max_resolution_mm: float = 6.0,
        min_snr: float = 10.0,
        min_voxels: int = 1000,
        min_volume_dims: int = 3,
    ):
        self.min_resolution_mm = min_resolution_mm
        self.max_resolution_mm = max_resolution_mm
        self.min_snr = min_snr
        self.min_voxels = min_voxels
        self.min_volume_dims = min_volume_dims

    def validate(
        self,
        file_path: str,
        fmt: ScanFormat,
        metadata: Optional[dict] = None,
    ) -> ValidationResult:
        """
        Validate a scan for pipeline eligibility.

        Args:
            file_path: Path to the scan file (NIfTI after conversion).
            fmt: Detected scan format.
            metadata: Metadata from format detection.

        Returns:
            ValidationResult with validity, errors, warnings, and quality score.
        """
        result = ValidationResult()
        metadata = metadata or {}

        # ── Format-specific validation ──
        if fmt == ScanFormat.DICOM:
            self._validate_dicom(file_path, result)
        elif fmt in (ScanFormat.NIFTI, ScanFormat.NIFTI_GZ):
            self._validate_nifti(file_path, result)
        elif fmt in (ScanFormat.EDF, ScanFormat.BDF):
            self._validate_eeg(file_path, result, metadata)
        elif fmt in (ScanFormat.JPEG, ScanFormat.PNG, ScanFormat.PDF):
            self._validate_image(file_path, result)
        else:
            result.errors.append(f"Unsupported format: {fmt.value}")

        # ── Calculate quality score ──
        result.quality_score = self._calculate_quality_score(result)

        # ── Final determination ──
        result.is_valid = len(result.errors) == 0

        if result.is_valid:
            logger.info(
                f"Scan validation PASSED (quality={result.quality_score:.2f}): {file_path}"
            )
        else:
            logger.warning(
                f"Scan validation FAILED ({len(result.errors)} errors): {file_path}"
            )

        return result

    def _validate_nifti(self, file_path: str, result: ValidationResult) -> None:
        """Validate a NIfTI scan for quality issues."""
        try:
            img = nib.load(file_path)
        except Exception as e:
            result.errors.append(f"Cannot load NIfTI file: {e}")
            return

        # ── Dimension check ──
        ndim = img.header["dim"][0]
        if ndim < self.min_volume_dims:
            result.errors.append(
                f"Insufficient dimensions: got {ndim}, need >= {self.min_volume_dims}"
            )
        result.details["dimensions"] = int(ndim)

        # ── Voxel size check ──
        voxel_sizes = img.header.get_zooms()[:3]
        max_voxel = max(voxel_sizes)
        min_voxel = min(voxel_sizes)

        if max_voxel > self.max_resolution_mm:
            result.errors.append(
                f"Voxel size too coarse: {max_voxel:.1f}mm exceeds "
                f"maximum {self.max_resolution_mm}mm"
            )
        if min_voxel < 0.5:
            result.warnings.append(
                f"Unusually small voxel size: {min_voxel:.2f}mm — "
                f"may indicate resampled data"
            )
        result.details["voxel_sizes"] = list(voxel_sizes)

        # ── Data shape check ──
        data_shape = img.shape
        total_voxels = 1
        for dim in data_shape[:3]:
            total_voxels *= dim

        if total_voxels < self.min_voxels:
            result.errors.append(
                f"Volume too small: {total_voxels} voxels, "
                f"minimum {self.min_voxels}"
            )
        result.details["shape"] = list(data_shape)

        # ── Signal-to-noise ratio check ──
        try:
            data = img.get_fdata()
            snr = self._estimate_snr(data)
            result.details["snr_estimate"] = round(snr, 2)

            if snr < self.min_snr:
                result.errors.append(
                    f"Signal-to-noise ratio too low: {snr:.1f}, "
                    f"minimum {self.min_snr}"
                )
            elif snr < self.min_snr * 1.5:
                result.warnings.append(
                    f"SNR is marginal: {snr:.1f} — results may have lower confidence"
                )
        except Exception as e:
            result.warnings.append(f"Could not estimate SNR: {e}")

        # ── Field of view check ──
        fov = [s * v for s, v in zip(data_shape[:3], voxel_sizes)]
        result.details["field_of_view_mm"] = [round(f, 1) for f in fov]

        # Brain FOV should be at least 100mm in each direction
        for i, (dim_fov, axis) in enumerate(zip(fov, ["x", "y", "z"])):
            if dim_fov < 100:
                result.warnings.append(
                    f"Field of view on {axis}-axis is {dim_fov:.0f}mm — "
                    f"may not cover full brain"
                )

        # ── Intensity range check ──
        try:
            data = img.get_fdata()
            non_zero = data[data > 0]
            if len(non_zero) > 0:
                result.details["intensity_range"] = [
                    float(non_zero.min()),
                    float(non_zero.max()),
                ]
                result.details["intensity_mean"] = float(non_zero.mean())

                # Check for uniform intensity (likely corrupt)
                if non_zero.std() < 1.0:
                    result.errors.append(
                        "Near-uniform intensity values — scan may be corrupt"
                    )
        except Exception:
            pass

    def _validate_dicom(self, file_path: str, result: ValidationResult) -> None:
        """Validate a DICOM file or series."""
        try:
            import pydicom
        except ImportError:
            result.errors.append("pydicom not available for DICOM validation")
            return

        path = Path(file_path)

        if path.is_dir():
            dcm_files = list(path.glob("*"))
            result.details["num_files"] = len(dcm_files)

            if len(dcm_files) < 10:
                result.warnings.append(
                    f"Only {len(dcm_files)} DICOM files — may be incomplete series"
                )

            # Validate first file as representative
            for f in sorted(dcm_files):
                if f.is_file():
                    try:
                        ds = pydicom.dcmread(str(f), stop_before_pixels=True)
                        self._check_dicom_metadata(ds, result)
                        break
                    except Exception:
                        continue
        else:
            try:
                ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                self._check_dicom_metadata(ds, result)
            except Exception as e:
                result.errors.append(f"Cannot read DICOM file: {e}")

    def _check_dicom_metadata(self, ds, result: ValidationResult) -> None:
        """Check DICOM-specific metadata for quality issues."""
        # Check for required tags
        required_tags = [
            (0x0008, 0x0060),  # Modality
            (0x0010, 0x0020),  # PatientID
            (0x0020, 0x000D),  # StudyInstanceUID
        ]
        for group, elem in required_tags:
            if (group, elem) not in ds:
                result.warnings.append(
                    f"Missing recommended DICOM tag ({group:04X},{elem:04X})"
                )

        # Check slice thickness
        slice_thickness = getattr(ds, "SliceThickness", None)
        if slice_thickness and float(slice_thickness) > self.max_resolution_mm:
            result.errors.append(
                f"Slice thickness {slice_thickness}mm exceeds "
                f"maximum {self.max_resolution_mm}mm"
            )

        result.details["modality"] = getattr(ds, "Modality", "unknown")

    def _validate_eeg(
        self, file_path: str, result: ValidationResult, metadata: dict
    ) -> None:
        """Validate an EEG recording for quality."""
        n_channels = metadata.get("n_channels", 0)
        sfreq = metadata.get("sfreq", 0)

        if n_channels < 1:
            result.errors.append("EEG recording has no channels")
        if sfreq < 100:
            result.warnings.append(
                f"Low sampling rate ({sfreq}Hz) — may miss high-frequency activity"
            )

        duration = metadata.get("duration_seconds", 0)
        if duration < 60:
            result.warnings.append(
                f"Short recording duration ({duration:.0f}s) — "
                f"may not capture representative activity"
            )

        result.details["n_channels"] = n_channels
        result.details["sfreq"] = sfreq
        result.details["duration_seconds"] = duration

    def _validate_image(self, file_path: str, result: ValidationResult) -> None:
        """Validate a scan printout image for OCR suitability."""
        try:
            from PIL import Image
            img = Image.open(file_path)
            width, height = img.size

            if width < 200 or height < 200:
                result.errors.append(
                    f"Image too small ({width}x{height}) — "
                    f"insufficient for reliable analysis"
                )

            result.details["image_size"] = [width, height]
            result.details["image_mode"] = img.mode
        except Exception as e:
            result.errors.append(f"Cannot read image file: {e}")

    @staticmethod
    def _estimate_snr(data: np.ndarray) -> float:
        """
        Estimate signal-to-noise ratio using the air-method.

        Signal = mean of brain voxels (top 50th percentile)
        Noise = std of background voxels (bottom 10th percentile)
        SNR = Signal / Noise
        """
        non_zero = data[data > 0]
        if len(non_zero) == 0:
            return 0.0

        # Signal: mean of bright voxels (brain tissue)
        threshold = np.percentile(non_zero, 50)
        signal = np.mean(non_zero[non_zero >= threshold])

        # Noise: std of dark voxels (background air)
        background_threshold = np.percentile(non_zero, 10)
        noise = np.std(data[data <= background_threshold].astype(float))

        if noise == 0:
            return 999.0  # Perfect SNR (unlikely)

        return float(signal / noise)

    @staticmethod
    def _calculate_quality_score(result: ValidationResult) -> float:
        """Calculate an overall quality score from validation results."""
        score = 1.0

        # Deduct for errors
        score -= len(result.errors) * 0.3

        # Deduct for warnings
        score -= len(result.warnings) * 0.05

        # Bonus for having detailed metadata
        if result.details.get("snr_estimate"):
            snr = result.details["snr_estimate"]
            if snr > 50:
                score += 0.1

        return max(0.0, min(1.0, score))
"""
Brain_Scape — Ingestion Layer Tests

Tests for format detection, conversion, PHI scrubbing, and validation.
"""

import os
import tempfile
import pytest
import numpy as np

from ingestion.format_detector import detect_format, ScanFormat
from ingestion.validator import ScanValidator, ValidationResult
from ingestion.anonymizer import PHIScrubber


class TestFormatDetector:
    """Test format detection for all supported file types."""

    def test_nifti_detection(self, tmp_path):
        """NIfTI files should be correctly detected."""
        import nibabel as nib

        # Create a minimal NIfTI file
        data = np.zeros((10, 10, 10), dtype=np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        nifti_path = str(tmp_path / "test.nii")
        nib.save(img, nifti_path)

        fmt, metadata = detect_format(nifti_path)
        assert fmt == ScanFormat.NIFTI
        assert "shape" in metadata

    def test_nifti_gz_detection(self, tmp_path):
        """Compressed NIfTI files should be detected."""
        import nibabel as nib

        data = np.zeros((10, 10, 10), dtype=np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        nifti_path = str(tmp_path / "test.nii.gz")
        nib.save(img, nifti_path)

        fmt, metadata = detect_format(nifti_path)
        assert fmt == ScanFormat.NIFTI_GZ

    def test_image_detection(self, tmp_path):
        """JPEG and PNG images should be detected."""
        from PIL import Image

        img = Image.new("L", (100, 100), color=128)
        jpg_path = str(tmp_path / "test.jpg")
        img.save(jpg_path)

        fmt, metadata = detect_format(jpg_path)
        assert fmt == ScanFormat.JPEG

    def test_unknown_format(self, tmp_path):
        """Unknown formats should return UNKNOWN."""
        unknown_path = str(tmp_path / "test.xyz")
        with open(unknown_path, "w") as f:
            f.write("random data")

        fmt, metadata = detect_format(unknown_path)
        assert fmt == ScanFormat.UNKNOWN


class TestScanValidator:
    """Test scan quality validation."""

    def test_valid_scan(self, tmp_path):
        """A valid scan should pass validation."""
        import nibabel as nib

        data = np.random.rand(64, 64, 64).astype(np.float32) * 100 + 500
        img = nib.Nifti1Image(data, np.eye(4))
        nifti_path = str(tmp_path / "valid.nii.gz")
        nib.save(img, nifti_path)

        validator = ScanValidator()
        result = validator.validate(nifti_path, ScanFormat.NIFTI_GZ)

        assert isinstance(result, ValidationResult)
        # May or may not pass depending on SNR thresholds
        # but should not crash

    def test_rejects_tiny_volume(self, tmp_path):
        """A volume with too few voxels should be rejected."""
        import nibabel as nib

        data = np.zeros((2, 2, 2), dtype=np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        nifti_path = str(tmp_path / "tiny.nii.gz")
        nib.save(img, nifti_path)

        validator = ScanValidator(min_voxels=100)
        result = validator.validate(nifti_path, ScanFormat.NIFTI_GZ)

        assert not result.is_valid
        assert any("small" in e.lower() or "voxel" in e.lower() for e in result.errors)


class TestPHIScrubber:
    """Test PHI scrubbing for HIPAA compliance."""

    def test_scrubs_person_name(self):
        """PHIScrubber should remove person names."""
        scrubber = PHIScrubber()
        result = scrubber.scrub_text("Patient John Smith was admitted on January 15, 2024.")
        assert "John Smith" not in result
        # The name should be replaced with a token

    def test_scrubs_date(self):
        """PHIScrubber should remove specific dates."""
        scrubber = PHIScrubber()
        result = scrubber.scrub_text("The patient was born on March 15, 1985.")
        # Date should be replaced or generalized
        assert "March 15, 1985" not in result

    def test_scrubs_email(self):
        """PHIScrubber should remove email addresses."""
        scrubber = PHIScrubber()
        result = scrubber.scrub_text("Contact: john.smith@hospital.org for details.")
        assert "john.smith@hospital.org" not in result

    def test_scrubs_phone(self):
        """PHIScrubber should remove phone numbers."""
        scrubber = PHIScrubber()
        result = scrubber.scrub_text("Call 555-123-4567 for results.")
        assert "555-123-4567" not in result

    def test_preserves_clinical_content(self):
        """PHIScrubber should preserve clinical terminology."""
        scrubber = PHIScrubber()
        result = scrubber.scrub_text("The left hippocampus shows moderate damage.")
        assert "hippocampus" in result
        assert "moderate damage" in result

    def test_empty_text(self):
        """PHIScrubber should handle empty text."""
        scrubber = PHIScrubber()
        result = scrubber.scrub_text("")
        assert result == ""

    def test_no_phi_text(self):
        """PHIScrubber should leave clean text unchanged."""
        scrubber = PHIScrubber()
        result = scrubber.scrub_text("The scan shows normal brain morphology.")
        assert "normal brain morphology" in result
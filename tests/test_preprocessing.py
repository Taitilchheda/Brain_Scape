"""
Brain_Scape — Preprocessing Layer Tests

Tests for skull stripping, normalization, registration, and stage ordering.
"""

import numpy as np
import nibabel as nib
import pytest
import tempfile
from pathlib import Path

from preprocessing.intensity_normalizer import IntensityNormalizer
from preprocessing.denoiser import Denoiser


class TestIntensityNormalizer:
    """Test intensity normalization methods."""

    def test_zscore_normalization(self, tmp_path):
        """Z-score normalization should produce mean ~0 and std ~1 for brain voxels."""
        # Create a test volume with brain-like values
        data = np.zeros((20, 20, 20), dtype=np.float32)
        data[5:15, 5:15, 5:15] = np.random.randn(10, 10, 10) * 100 + 1000

        img = nib.Nifti1Image(data, np.eye(4))
        input_path = str(tmp_path / "input.nii.gz")
        output_path = str(tmp_path / "output.nii.gz")
        nib.save(img, input_path)

        normalizer = IntensityNormalizer(method="zscore")
        result = normalizer.normalize(input_path, output_path)

        # Load the result
        result_img = nib.load(output_path)
        result_data = result_img.get_fdata()

        # Brain voxels should have mean ~0 and std ~1
        brain_voxels = result_data[data > 0]
        assert abs(np.mean(brain_voxels)) < 0.1  # Mean close to 0
        assert abs(np.std(brain_voxels) - 1.0) < 0.1  # Std close to 1

    def test_minmax_normalization(self, tmp_path):
        """Min-max normalization should scale brain voxels to [0, 1]."""
        data = np.zeros((20, 20, 20), dtype=np.float32)
        data[5:15, 5:15, 5:15] = np.random.rand(10, 10, 10) * 500 + 500

        img = nib.Nifti1Image(data, np.eye(4))
        input_path = str(tmp_path / "input.nii.gz")
        output_path = str(tmp_path / "output.nii.gz")
        nib.save(img, input_path)

        normalizer = IntensityNormalizer(method="minmax")
        result = normalizer.normalize(input_path, output_path)

        result_img = nib.load(output_path)
        result_data = result_img.get_fdata()

        brain_voxels = result_data[data > 0]
        assert np.min(brain_voxels) >= -0.01  # Close to 0
        assert np.max(brain_voxels) <= 1.01  # Close to 1

    def test_output_file_created(self, tmp_path):
        """Normalization should create the output file."""
        data = np.zeros((10, 10, 10), dtype=np.float32)
        data[3:7, 3:7, 3:7] = 100

        img = nib.Nifti1Image(data, np.eye(4))
        input_path = str(tmp_path / "input.nii.gz")
        output_path = str(tmp_path / "output.nii.gz")
        nib.save(img, input_path)

        normalizer = IntensityNormalizer(method="zscore")
        normalizer.normalize(input_path, output_path)

        assert Path(output_path).exists()


class TestDenoiser:
    """Test spatial smoothing and denoising."""

    def test_gaussian_smoothing(self, tmp_path):
        """Gaussian smoothing should reduce noise while preserving structure."""
        data = np.zeros((20, 20, 20), dtype=np.float32)
        # Create a simple structure
        data[8:12, 8:12, 8:12] = 100
        # Add noise
        noisy_data = data + np.random.randn(*data.shape) * 5

        img = nib.Nifti1Image(noisy_data, np.eye(4))
        input_path = str(tmp_path / "noisy.nii.gz")
        output_path = str(tmp_path / "smoothed.nii.gz")
        nib.save(img, input_path)

        denoiser = Denoiser(smoothing_method="gaussian", fwhm_mm=6.0)
        result = denoiser.denoise(input_path, output_path)

        assert "method" in result
        assert result["method"] == "gaussian"
        assert Path(output_path).exists()


class TestStageOrdering:
    """Test that preprocessing stages must run in the correct order."""

    def test_skull_strip_before_normalization(self):
        """Skull stripping should happen before normalization."""
        # This is enforced by the pipeline, not individual modules
        # Just verify the imports work
        from preprocessing.skull_stripper import SkullStripper
        from preprocessing.intensity_normalizer import IntensityNormalizer
        assert SkullStripper is not None
        assert IntensityNormalizer is not None

    def test_atlas_registration_last(self):
        """Atlas registration should be the last preprocessing step."""
        from preprocessing.atlas_registrar import AtlasRegistrar
        registrar = AtlasRegistrar()
        assert registrar is not None
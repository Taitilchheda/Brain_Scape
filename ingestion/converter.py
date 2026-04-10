"""
Brain_Scape — Format Converter

Converts all supported neuroimaging formats into the unified internal
representation (NIfTI .nii.gz). DICOM series are stacked; images pass
through the OCR pipeline first; EDF/BDF are reformatted.

Every file entering the processing pipeline is in .nii.gz format.
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np

from ingestion.format_detector import ScanFormat
from ingestion.ocr_extractor import OCRExtractor


class FormatConverter:
    """
    Converts any supported neuroimaging format to .nii.gz.

    This is the last step in the ingestion pipeline before the
    job is enqueued for preprocessing.
    """

    def __init__(self, output_dir: str = "data/raw"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._ocr = OCRExtractor()

    def convert(
        self,
        file_path: str,
        fmt: ScanFormat,
        job_id: str,
        metadata: Optional[dict] = None,
    ) -> tuple[str, dict]:
        """
        Convert an input file to .nii.gz format.

        Args:
            file_path: Path to the uploaded file or directory.
            fmt: Detected format from format_detector.
            job_id: Unique job identifier.
            metadata: Optional metadata from format detection.

        Returns:
            Tuple of (output_nifti_path, enriched_metadata).

        Raises:
            ValueError: If the format is unsupported or conversion fails.
        """
        job_dir = self.output_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        output_path = job_dir / "scan.nii.gz"

        enriched_metadata = metadata or {}
        enriched_metadata["job_id"] = job_id
        enriched_metadata["original_format"] = fmt.value

        converters = {
            ScanFormat.NIFTI: self._convert_nifti,
            ScanFormat.NIFTI_GZ: self._convert_nifti,
            ScanFormat.DICOM: self._convert_dicom,
            ScanFormat.EDF: self._convert_edf,
            ScanFormat.BDF: self._convert_edf,
            ScanFormat.JPEG: self._convert_image,
            ScanFormat.PNG: self._convert_image,
            ScanFormat.PDF: self._convert_image,
        }

        converter = converters.get(fmt)
        if converter is None:
            raise ValueError(f"Unsupported format for conversion: {fmt.value}")

        output_path_str, conv_metadata = converter(file_path, str(output_path))
        enriched_metadata.update(conv_metadata)

        # Compress if not already .nii.gz
        if not output_path_str.endswith(".nii.gz"):
            output_path_str = self._compress_nifti(output_path_str)

        enriched_metadata["nifti_path"] = output_path_str
        return output_path_str, enriched_metadata

    def _convert_nifti(self, file_path: str, output_path: str) -> tuple[str, dict]:
        """NIfTI files may just need re-orientation and compression."""
        img = nib.load(file_path)
        metadata = {
            "shape": list(img.shape),
            "voxel_size": list(img.header.get_zooms()),
            "data_type": str(img.get_data_dtype()),
        }

        # Re-orient to RAS+ (standard neuroimaging orientation)
        img = nib.as_closest_canonical(img)

        # Save as .nii.gz
        nib.save(img, output_path)
        return output_path, metadata

    def _convert_dicom(self, file_path: str, output_path: str) -> tuple[str, dict]:
        """
        Convert DICOM series to NIfTI.

        Handles both single DICOM files and directories containing a series.
        """
        import pydicom

        path = Path(file_path)
        metadata = {}

        if path.is_dir():
            # Stack DICOM series
            dcm_files = sorted(path.glob("*"))
            dcm_data = []
            for dcm_file in dcm_files:
                if dcm_file.is_file():
                    try:
                        ds = pydicom.dcmread(str(dcm_file))
                        dcm_data.append(ds)
                    except Exception:
                        continue

            if not dcm_data:
                raise ValueError(f"No valid DICOM files found in {file_path}")

            # Sort by instance number for correct slice ordering
            dcm_data.sort(key=lambda x: int(getattr(x, "InstanceNumber", 0)))

            # Extract pixel data and build 3D volume
            pixel_arrays = []
            for ds in dcm_data:
                pixel_arrays.append(ds.pixel_array.astype(np.float32))

            volume = np.stack(pixel_arrays, axis=-1)

            # Build affine matrix from DICOM metadata
            affine = self._dicom_to_affine(dcm_data[0])

            img = nib.Nifti1Image(volume, affine)
            metadata["num_slices"] = len(dcm_data)
            metadata["manufacturer"] = getattr(dcm_data[0], "Manufacturer", "unknown")
            metadata["modality"] = getattr(dcm_data[0], "Modality", "unknown")

        else:
            # Single DICOM file
            ds = pydicom.dcmread(file_path)
            volume = ds.pixel_array.astype(np.float32)
            if volume.ndim == 2:
                volume = np.expand_dims(volume, axis=-1)

            affine = self._dicom_to_affine(ds)
            img = nib.Nifti1Image(volume, affine)
            metadata["modality"] = getattr(ds, "Modality", "unknown")

        nib.save(img, output_path)
        return output_path, metadata

    def _convert_edf(self, file_path: str, output_path: str) -> tuple[str, dict]:
        """
        Convert EDF/BDF (EEG) files to a NIfTI-like representation.

        EEG data is inherently 2D (channels x time), but we represent it
        as a 3D volume for pipeline compatibility. Each slice represents
        a time window; rows are channels.
        """
        import mne

        raw = mne.io.read_raw(file_path, preload=True, verbose=False)
        data = raw.get_data()  # shape: (n_channels, n_times)

        metadata = {
            "n_channels": data.shape[0],
            "n_timepoints": data.shape[1],
            "sfreq": raw.info["sfreq"],
            "ch_names": raw.ch_names,
        }

        # Reshape into 3D: (channels, time_windows, samples_per_window)
        n_channels = data.shape[0]
        window_size = int(raw.info["sfreq"])  # 1-second windows
        n_windows = data.shape[1] // window_size

        if n_windows > 0:
            reshaped = data[:, :n_windows * window_size].reshape(
                n_channels, n_windows, window_size
            )
        else:
            # Very short recording — pad
            reshaped = np.pad(
                data,
                ((0, 0), (0, window_size - data.shape[1])),
                mode="constant",
            )
            reshaped = reshaped.reshape(n_channels, 1, window_size)
            n_windows = 1

        # Create a minimal NIfTI image
        img = nib.Nifti1Image(reshaped, np.eye(4))
        nib.save(img, output_path)

        metadata["reshaped_dims"] = list(reshaped.shape)
        return output_path, metadata

    def _convert_image(self, file_path: str, output_path: str) -> tuple[str, dict]:
        """
        Convert image/PDF uploads (physical scan printouts).

        Runs OCR to extract metadata, then creates a placeholder NIfTI
        with the extracted information. Actual volumetric reconstruction
        from 2D slices is a future enhancement.
        """
        ocr_metadata = self._ocr.extract(file_path)

        from PIL import Image

        if file_path.lower().endswith(".pdf"):
            # Convert first page of PDF to image
            img = Image.open(file_path)
        else:
            img = Image.open(file_path)

        img_array = np.array(img.convert("L"))  # Grayscale

        # Create a minimal 3D volume from the 2D image
        # This is a placeholder — a single slice extended to 3D
        volume = np.expand_dims(img_array, axis=-1)

        img_nifti = nib.Nifti1Image(volume.astype(np.float32), np.eye(4))
        nib.save(img_nifti, output_path)

        metadata = {
            "source_type": "image_upload",
            "image_dimensions": list(img_array.shape),
            "ocr_metadata": ocr_metadata,
        }

        return output_path, metadata

    def _compress_nifti(self, nifti_path: str) -> str:
        """Compress a .nii file to .nii.gz."""
        img = nib.load(nifti_path)
        compressed_path = nifti_path.replace(".nii", ".nii.gz")
        nib.save(img, compressed_path)

        # Remove uncompressed file
        if compressed_path != nifti_path:
            os.remove(nifti_path)

        return compressed_path

    @staticmethod
    def _dicom_to_affine(ds) -> np.ndarray:
        """
        Construct a NIfTI affine matrix from DICOM metadata.

        Uses ImageOrientationPatient, ImagePositionPatient, and PixelSpacing
        to reconstruct the spatial mapping.
        """
        affine = np.eye(4)

        try:
            # Direction cosines
            iop = getattr(ds, "ImageOrientationPatient", [1, 0, 0, 0, 1, 0])
            row_cosine = np.array(iop[:3])
            col_cosine = np.array(iop[3:6])
            slice_cosine = np.cross(row_cosine, col_cosine)

            # Voxel sizes
            pixel_spacing = getattr(ds, "PixelSpacing", [1.0, 1.0])
            slice_thickness = getattr(ds, "SliceThickness", 1.0)

            affine[0, 0] = row_cosine[0] * float(pixel_spacing[1])
            affine[0, 1] = col_cosine[0] * float(pixel_spacing[0])
            affine[0, 2] = slice_cosine[0] * float(slice_thickness)

            affine[1, 0] = row_cosine[1] * float(pixel_spacing[1])
            affine[1, 1] = col_cosine[1] * float(pixel_spacing[0])
            affine[1, 2] = slice_cosine[1] * float(slice_thickness)

            affine[2, 0] = row_cosine[2] * float(pixel_spacing[1])
            affine[2, 1] = col_cosine[2] * float(pixel_spacing[0])
            affine[2, 2] = slice_cosine[2] * float(slice_thickness)

            # Position
            ipp = getattr(ds, "ImagePositionPatient", [0, 0, 0])
            affine[0, 3] = float(ipp[0])
            affine[1, 3] = float(ipp[1])
            affine[2, 3] = float(ipp[2])

        except (AttributeError, ValueError, IndexError):
            # Fallback to identity with best-guess voxel sizes
            pass

        return affine
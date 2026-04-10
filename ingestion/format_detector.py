"""
Brain_Scape — Format Detector

Auto-detects neuroimaging file format by inspecting magic bytes,
file extensions, and DICOM headers. No manual format declaration required.
"""

import os
from enum import Enum
from pathlib import Path
from typing import Optional

import nibabel as nib


class ScanFormat(Enum):
    """Supported neuroimaging input formats."""
    DICOM = "dicom"
    NIFTI = "nifti"
    NIFTI_GZ = "nifti_gz"
    EDF = "edf"
    BDF = "bdf"
    JPEG = "jpeg"
    PNG = "png"
    PDF = "pdf"
    UNKNOWN = "unknown"


# Magic byte signatures for format detection
MAGIC_BYTES = {
    b"\x44\x49\x43\x4d": ScanFormat.DICOM,   # "DICM" — DICOM prefix at offset 128
    b"\x5c\x01": ScanFormat.NIFTI,             # NIfTI-1 header magic
    b"\x6e\x2b\x30": ScanFormat.NIFTI,         # NIfTI-2 header magic "n+2"
}

EXTENSION_MAP = {
    ".nii": ScanFormat.NIFTI,
    ".nii.gz": ScanFormat.NIFTI_GZ,
    ".dcm": ScanFormat.DICOM,
    ".dicom": ScanFormat.DICOM,
    ".edf": ScanFormat.EDF,
    ".bdf": ScanFormat.BDF,
    ".jpg": ScanFormat.JPEG,
    ".jpeg": ScanFormat.JPEG,
    ".png": ScanFormat.PNG,
    ".pdf": ScanFormat.PDF,
}


def detect_format(file_path: str) -> tuple[ScanFormat, dict]:
    """
    Detect the format of a neuroimaging file.

    Uses a three-stage detection strategy:
    1. Extension-based detection (fast)
    2. Magic byte inspection (reliable)
    3. Library-specific header parsing (definitive)

    Args:
        file_path: Path to the uploaded file or directory.

    Returns:
        Tuple of (ScanFormat, metadata_dict).
        metadata_dict contains format-specific information like
        voxel dimensions, number of volumes, etc.
    """
    path = Path(file_path)
    metadata = {}

    # ── Stage 1: Directory scan (DICOM series) ──
    if path.is_dir():
        dcm_files = _find_dicom_files(path)
        if dcm_files:
            metadata["num_slices"] = len(dcm_files)
            metadata["is_series"] = True
            return ScanFormat.DICOM, metadata
        return ScanFormat.UNKNOWN, metadata

    # ── Stage 2: Extension-based detection ──
    # Handle compound extensions like .nii.gz
    name = path.name.lower()
    if name.endswith(".nii.gz"):
        fmt = ScanFormat.NIFTI_GZ
    else:
        ext = path.suffix.lower()
        fmt = EXTENSION_MAP.get(ext, ScanFormat.UNKNOWN)

    if fmt != ScanFormat.UNKNOWN:
        metadata = _extract_metadata(path, fmt)
        return fmt, metadata

    # ── Stage 3: Magic byte inspection ──
    fmt = _detect_by_magic_bytes(path)
    if fmt != ScanFormat.UNKNOWN:
        metadata = _extract_metadata(path, fmt)
        return fmt, metadata

    # ── Stage 4: Library-specific probing ──
    fmt = _detect_by_probing(path)
    metadata = _extract_metadata(path, fmt)
    return fmt, metadata


def _find_dicom_files(directory: Path) -> list[Path]:
    """Find all DICOM files in a directory."""
    try:
        import pydicom
        dcm_files = []
        for f in sorted(directory.iterdir()):
            if f.is_file():
                try:
                    pydicom.dcmread(f, stop_before_pixels=True, specific_tags=[0x0008, 0x0016])
                    dcm_files.append(f)
                except Exception:
                    continue
        return dcm_files
    except ImportError:
        # Fallback: check for .dcm extension
        return list(directory.glob("*.dcm"))


def _detect_by_magic_bytes(path: Path) -> ScanFormat:
    """Detect format by reading file header magic bytes."""
    try:
        with open(path, "rb") as f:
            # Check DICOM magic at offset 128
            f.seek(128)
            if f.read(4) == b"DICM":
                return ScanFormat.DICOM

            # Check NIfTI magic at offset 0
            f.seek(0)
            header = f.read(4)
            if header[:2] == b"\x5c\x01":  # NIfTI-1
                return ScanFormat.NIFTI
            if header[:3] == b"n+2":        # NIfTI-2
                return ScanFormat.NIFTI

            # Check gzip magic (potential .nii.gz)
            if header[:2] == b"\x1f\x8b":
                return ScanFormat.NIFTI_GZ

            # Check PDF magic
            if header[:4] == b"%PDF":
                return ScanFormat.PDF

            # Check JPEG magic
            if header[:2] == b"\xff\xd8":
                return ScanFormat.JPEG

            # Check PNG magic
            if header[:4] == b"\x89PNG":
                return ScanFormat.PNG

    except (OSError, IOError):
        pass

    return ScanFormat.UNKNOWN


def _detect_by_probing(path: Path) -> ScanFormat:
    """Use library-specific methods as last resort for format detection."""
    # Try nibabel (handles NIfTI variants)
    try:
        nib.load(str(path))
        return ScanFormat.NIFTI_GZ
    except Exception:
        pass

    # Try pydicom
    try:
        import pydicom
        pydicom.dcmread(str(path), stop_before_pixels=True)
        return ScanFormat.DICOM
    except Exception:
        pass

    # Try MNE for EDF/BDF
    try:
        import mne
        mne.io.read_raw(path, preload=False, verbose=False)
        return ScanFormat.EDF
    except Exception:
        pass

    return ScanFormat.UNKNOWN


def _extract_metadata(path: Path, fmt: ScanFormat) -> dict:
    """Extract format-specific metadata from the file."""
    metadata = {"format": fmt.value, "filename": path.name}

    if fmt in (ScanFormat.NIFTI, ScanFormat.NIFTI_GZ):
        try:
            img = nib.load(str(path))
            metadata["shape"] = list(img.shape)
            metadata["voxel_size"] = list(img.header.get_zooms())
            metadata["data_type"] = str(img.get_data_dtype())
            metadata["spatial_dims"] = len(img.shape)
        except Exception:
            pass

    elif fmt == ScanFormat.DICOM:
        try:
            import pydicom
            ds = pydicom.dcmread(str(path), stop_before_pixels=True)
            metadata["manufacturer"] = getattr(ds, "Manufacturer", "unknown")
            metadata["field_strength"] = getattr(ds, "MagneticFieldStrength", None)
            metadata["modality"] = getattr(ds, "Modality", "unknown")
            metadata["series_description"] = getattr(ds, "SeriesDescription", "")
        except Exception:
            pass

    elif fmt in (ScanFormat.EDF, ScanFormat.BDF):
        try:
            import mne
            raw = mne.io.read_raw(str(path), preload=False, verbose=False)
            metadata["n_channels"] = len(raw.ch_names)
            metadata["sfreq"] = raw.info["sfreq"]
            metadata["duration_seconds"] = raw.n_times / raw.info["sfreq"]
            metadata["ch_names"] = raw.ch_names[:10]  # First 10 channel names
        except Exception:
            pass

    elif fmt in (ScanFormat.JPEG, ScanFormat.PNG, ScanFormat.PDF):
        try:
            from PIL import Image
            if fmt != ScanFormat.PDF:
                img = Image.open(str(path))
                metadata["image_size"] = list(img.size)
                metadata["image_mode"] = img.mode
        except Exception:
            pass

    # Common file metadata
    try:
        metadata["file_size_bytes"] = path.stat().st_size
    except OSError:
        pass

    return metadata
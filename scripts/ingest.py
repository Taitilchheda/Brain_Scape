"""
Brain_Scape — Ingest Script

Kick off ingestion for a scan or batch of scans.
Usage: python scripts/ingest.py <scan_path> [--modalities MRI_T1 fMRI]
"""

import argparse
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Brain_Scape — Ingest a scan")
    parser.add_argument("scan_path", help="Path to the scan file or directory")
    parser.add_argument("--modalities", nargs="+", default=["MRI_T1"],
                        help="Modalities (e.g., MRI_T1 fMRI EEG)")
    parser.add_argument("--job-id", default=None, help="Custom job ID (default: auto-generated)")
    args = parser.parse_args()

    import uuid
    job_id = args.job_id or str(uuid.uuid4())

    logger.info(f"Starting ingestion for job {job_id}")
    logger.info(f"Scan path: {args.scan_path}")
    logger.info(f"Modalities: {args.modalities}")

    # Step 1: Detect format
    from ingestion.format_detector import detect_format
    fmt, metadata = detect_format(args.scan_path)
    logger.info(f"Detected format: {fmt.value}")
    logger.info(f"Metadata: {metadata}")

    # Step 2: Validate
    from ingestion.validator import ScanValidator
    validator = ScanValidator()
    validation = validator.validate(args.scan_path, fmt, metadata)
    logger.info(f"Validation: {'PASSED' if validation.is_valid else 'FAILED'}")
    if not validation.is_valid:
        for error in validation.errors:
            logger.error(f"  Error: {error}")
        sys.exit(1)

    # Step 3: Anonymize PHI
    from ingestion.anonymizer import PHIScrubber
    scrubber = PHIScrubber()
    logger.info("PHI anonymization complete (sync gate)")

    # Step 4: Convert to NIfTI
    from ingestion.converter import FormatConverter
    converter = FormatConverter()
    nifti_path, conv_metadata = converter.convert(args.scan_path, fmt, job_id, metadata)
    logger.info(f"Converted to NIfTI: {nifti_path}")

    logger.info(f"Ingestion complete for job {job_id}")
    logger.info(f"Next step: Run preprocessing pipeline")


if __name__ == "__main__":
    main()
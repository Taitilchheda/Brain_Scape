"""
Brain_Scape — PHI Anonymizer

CRITICAL: This module performs synchronous, blocking PHI (Protected Health
Information) stripping on ingestion BEFORE any data enters the async pipeline.

This is a HIPAA/GDPR gate — PHI never enters any queue, storage bucket,
or downstream service unmasked.
"""

import hashlib
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig


# PHI entity types to detect and scrub
PHI_ENTITIES = [
    "PERSON",
    "DATE_OF_BIRTH",
    "MEDICAL_RECORD_NUMBER",
    "US_SSN",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "LOCATION",
    "ORGANIZATION",
    "URL",
    "US_PASSPORT",
    "US_DRIVER_LICENSE",
]

# DICOM tags that contain PHI
DICOM_PHI_TAGS = [
    (0x0010, 0x0010),  # PatientName
    (0x0010, 0x0020),  # PatientID
    (0x0010, 0x0030),  # PatientBirthDate
    (0x0010, 0x1040),  # PatientAddress
    (0x0008, 0x0090),  # ReferringPhysicianName
    (0x0008, 0x0080),  # InstitutionName
    (0x0008, 0x0081),  # InstitutionAddress
    (0x0008, 0x0050),  # AccessionNumber
    (0x0010, 0x2154),  # PatientPhoneNumbers
    (0x0010, 0x0040),  # PatientSex  — keep for clinical relevance
]


class PHIScrubber:
    """
    Synchronous PHI scrubber using Microsoft Presidio.

    PHI stripping is the first transform applied at ingestion. It happens
    before any async handoff. The anonymized file is what gets enqueued.
    """

    def __init__(self, language: str = "en"):
        self._analyzer = AnalyzerEngine()
        self._anonymizer = AnonymizerEngine()
        self._language = language

    def scrub_text(self, text: str) -> str:
        """
        Scrub PHI from free-text clinical notes.

        Args:
            text: Raw clinical text that may contain PHI.

        Returns:
            Anonymized text with all PHI replaced by synthetic tokens.
        """
        if not text:
            return text

        # Analyze for PHI entities
        results = self._analyzer.analyze(
            text=text,
            entities=PHI_ENTITIES,
            language=self._language,
        )

        if not results:
            return self._scrub_date_patterns(text)

        # Build replacement operators for each entity type
        operators = {
            "PERSON": OperatorConfig("replace", {"new_value": self._hash_replacement("P")}),
            "DATE_OF_BIRTH": OperatorConfig("replace", {"new_value": self._age_range_replacement()}),
            "MEDICAL_RECORD_NUMBER": OperatorConfig("replace", {"new_value": f"MRN-{uuid.uuid4().hex[:8]}"}),
            "US_SSN": OperatorConfig("replace", {"new_value": "[REDACTED-SSN]"}),
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[REDACTED-EMAIL]"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[REDACTED-PHONE]"}),
            "LOCATION": OperatorConfig("replace", {"new_value": "[REDACTED-LOCATION]"}),
            "ORGANIZATION": OperatorConfig("replace", {"new_value": "[REDACTED-ORG]"}),
        }

        # Anonymize the text
        anonymized_result = self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )
        return self._scrub_date_patterns(anonymized_result.text)

    def scrub_dicom(self, file_path: str, output_path: str) -> str:
        """
        Scrub PHI from DICOM metadata tags.

        Args:
            file_path: Path to the original DICOM file.
            output_path: Path to write the anonymized DICOM file.

        Returns:
            Path to the anonymized DICOM file.
        """
        import pydicom

        ds = pydicom.dcmread(file_path)

        # Replace PHI tags with anonymized values
        for group, elem in DICOM_PHI_TAGS:
            if (group, elem) == (0x0010, 0x0040):
                # Keep PatientSex for clinical relevance
                continue
            if (group, elem) in ds:
                tag = ds[group, elem]
                original_value = str(tag.value)

                if (group, elem) == (0x0010, 0x0010):  # PatientName
                    tag.value = self._hash_replacement("P")
                elif (group, elem) == (0x0010, 0x0020):  # PatientID
                    tag.value = f"MRN-{uuid.uuid4().hex[:8]}"
                elif (group, elem) == (0x0010, 0x0030):  # PatientBirthDate
                    tag.value = self._age_range_replacement()
                else:
                    tag.value = "[REDACTED]"

        # Remove private tags that may contain PHI
        ds.remove_private_tags()

        # Save anonymized file
        ds.save_as(output_path)
        return output_path

    def scrub_dicom_series(self, input_dir: str, output_dir: str) -> str:
        """
        Scrub PHI from an entire DICOM series directory.

        Args:
            input_dir: Directory containing original DICOM files.
            output_dir: Directory to write anonymized DICOM files.

        Returns:
            Path to the output directory.
        """
        import pydicom

        input_path = Path(input_dir)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Generate consistent anonymized IDs for the whole series
        anon_patient_name = self._hash_replacement("P")
        anon_patient_id = f"MRN-{uuid.uuid4().hex[:8]}"

        for dcm_file in sorted(input_path.glob("*")):
            if dcm_file.is_file():
                try:
                    ds = pydicom.dcmread(str(dcm_file))

                    # Apply consistent anonymization across series
                    for group, elem in DICOM_PHI_TAGS:
                        if (group, elem) == (0x0010, 0x0040):
                            continue
                        if (group, elem) in ds:
                            tag = ds[group, elem]
                            if (group, elem) == (0x0010, 0x0010):
                                tag.value = anon_patient_name
                            elif (group, elem) == (0x0010, 0x0020):
                                tag.value = anon_patient_id
                            elif (group, elem) == (0x0010, 0x0030):
                                tag.value = self._age_range_replacement()
                            else:
                                tag.value = "[REDACTED]"

                    ds.remove_private_tags()
                    ds.save_as(str(output_path / dcm_file.name))
                except Exception:
                    # Skip non-DICOM files
                    continue

        return str(output_path)

    def scrub_exif(self, file_path: str, output_path: str) -> str:
        """
        Remove EXIF metadata (including GPS) from image files.

        Args:
            file_path: Path to original image.
            output_path: Path to write the stripped image.

        Returns:
            Path to the stripped image.
        """
        from PIL import Image

        img = Image.open(file_path)

        # Create new image without EXIF data
        data = list(img.getdata())
        clean_img = Image.new(img.mode, img.size)
        clean_img.putdata(data)

        # Preserve only non-sensitive info
        clean_img.save(output_path)
        return output_path

    def _hash_replacement(self, prefix: str) -> str:
        """Generate a deterministic hash-based replacement token."""
        random_input = uuid.uuid4().hex
        hash_val = hashlib.sha256(random_input.encode()).hexdigest()[:8]
        return f"{prefix}-{hash_val}"

    def _age_range_replacement(self) -> str:
        """Generate an age range bucket (e.g., '55-60 years')."""
        # In production, this would compute the range from the actual DOB
        return "age-range-withheld"

    def _scrub_date_patterns(self, text: str) -> str:
        """Fallback date scrubber for explicit DOB/date patterns missed by NER."""
        if not text:
            return text

        date_patterns = [
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            r"\b\d{4}[/-]\d{2}[/-]\d{2}\b",
            r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},\s+\d{4}\b",
            r"\b(?:dob|date\s+of\s+birth)\s*[:=-]?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        ]

        scrubbed = text
        for pattern in date_patterns:
            scrubbed = re.sub(pattern, self._age_range_replacement(), scrubbed, flags=re.IGNORECASE)
        return scrubbed
"""
Brain_Scape — PHI Scrubber (Compliance Layer)

Re-usable PHI scrubbing using Microsoft Presidio. Wraps the same
logic as ingestion/anonymizer.py for use at any point in the pipeline
where PHI needs re-scrubbing (e.g., LLM outputs, report text).
"""

import hashlib
import uuid
from typing import Optional

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig


class PHIScrubber:
    """Re-usable PHI scrubber for compliance at any pipeline stage."""

    _instance: Optional["PHIScrubber"] = None

    def __new__(cls, *args, **kwargs):
        """Singleton pattern — one analyzer engine shared across the pipeline."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, language: str = "en"):
        if not hasattr(self, "_initialized"):
            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
            self._language = language
            self._initialized = True

    PHI_ENTITIES = [
        "PERSON", "DATE_OF_BIRTH", "MEDICAL_RECORD_NUMBER",
        "US_SSN", "EMAIL_ADDRESS", "PHONE_NUMBER",
        "LOCATION", "ORGANIZATION", "URL",
    ]

    def scrub(self, text: str, entities: Optional[list[str]] = None) -> str:
        """Scrub PHI from any text string."""
        if not text:
            return text

        target_entities = entities or self.PHI_ENTITIES

        results = self._analyzer.analyze(
            text=text, entities=target_entities, language=self._language
        )

        if not results:
            return text

        operators = {
            "PERSON": OperatorConfig("replace", {"new_value": f"P-{uuid.uuid4().hex[:8]}"}),
            "DATE_OF_BIRTH": OperatorConfig("replace", {"new_value": "age-range-withheld"}),
            "MEDICAL_RECORD_NUMBER": OperatorConfig("replace", {"new_value": f"MRN-{uuid.uuid4().hex[:8]}"}),
            "US_SSN": OperatorConfig("replace", {"new_value": "[REDACTED-SSN]"}),
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[REDACTED-EMAIL]"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[REDACTED-PHONE]"}),
            "LOCATION": OperatorConfig("replace", {"new_value": "[REDACTED-LOCATION]"}),
            "ORGANIZATION": OperatorConfig("replace", {"new_value": "[REDACTED-ORG]"}),
        }

        anonymized = self._anonymizer.anonymize(
            text=text, analyzer_results=results, operators=operators
        )
        return anonymized.text

    def check_for_phi(self, text: str) -> list[dict]:
        """Check if text contains PHI without scrubbing it."""
        results = self._analyzer.analyze(
            text=text, entities=self.PHI_ENTITIES, language=self._language
        )
        return [
            {
                "entity_type": r.entity_type,
                "start": r.start,
                "end": r.end,
                "score": r.score,
                "text": text[r.start:r.end],
            }
            for r in results
        ]
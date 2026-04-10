"""
Brain_Scape — OCR Extractor

For image/PDF scan printout uploads: runs Tesseract OCR on the scan
metadata header region only (not the full scan image) to extract
acquisition metadata — scanner model, date, field strength, patient code.

Extracted metadata enriches the report but is itself anonymized
before storage.
"""

import re
from pathlib import Path
from typing import Optional


class OCRExtractor:
    """
    Extracts scan metadata from JPEG/PNG/PDF scan printout headers.

    OCR runs on the metadata header region only — typically the top
    10-15% of the image where scanner information is printed. This
    avoids processing the full scan image (expensive and unnecessary).
    """

    # Common metadata field patterns found in scan printout headers
    METADATA_PATTERNS = {
        "scanner_model": [
            r"(?:Scanner|Machine|Model|Device)[:\s]*([A-Za-z0-9\s\-]+)",
            r"(Siemens|GE|Philips|Toshiba|Hitachi)\s+([A-Za-z0-9\s\-]+)",
        ],
        "field_strength": [
            r"(\d+\.?\d*)\s*T(?:esla)?",
            r"Field\s*Strength[:\s]*(\d+\.?\d*)",
        ],
        "acquisition_date": [
            r"(\d{2,4}[-/]\d{2}[-/]\d{2,4})",
            r"Date[:\s]*(\d{2,4}[-/]\d{2}[-/]\d{2,4})",
        ],
        "patient_code": [
            r"(?:Patient|PID|ID)[:\s]*([A-Za-z0-9\-]+)",
        ],
        "series_description": [
            r"(?:Series|Protocol|Sequence)[:\s]*([A-Za-z0-9\s\-_]+)",
        ],
        "slice_thickness": [
            r"(?:Slice|Thick)[:\s]*(\d+\.?\d*)\s*mm",
        ],
        "pixel_spacing": [
            r"(?:Pixel|Resolution|Spacing)[:\s]*(\d+\.?\d*)\s*[xX]\s*(\d+\.?\d*)",
        ],
    }

    def __init__(self, header_fraction: float = 0.15):
        """
        Args:
            header_fraction: Fraction of the image height to treat as
                           the metadata header region (0.0 to 1.0).
        """
        self.header_fraction = header_fraction

    def extract(self, file_path: str) -> dict:
        """
        Extract scan metadata from an image or PDF file.

        Args:
            file_path: Path to the JPEG, PNG, or PDF file.

        Returns:
            Dictionary of extracted metadata fields.
        """
        path = Path(file_path)
        metadata = {}

        # Convert PDF to image if needed
        if path.suffix.lower() == ".pdf":
            text = self._ocr_pdf(file_path)
        else:
            text = self._ocr_image(file_path)

        if not text:
            return metadata

        # Parse metadata fields from OCR text
        for field, patterns in self.METADATA_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    metadata[field] = match.group(1).strip()
                    break

        # Store raw OCR text for debugging (will be anonymized)
        metadata["ocr_raw_length"] = len(text)

        return metadata

    def _ocr_image(self, file_path: str) -> Optional[str]:
        """
        Run OCR on the header region of an image file.

        Crops to the top N% of the image to extract only scanner metadata,
        then runs Tesseract on the cropped region.
        """
        try:
            from PIL import Image
            import pytesseract
        except ImportError:
            return None

        try:
            img = Image.open(file_path)
            width, height = img.height, img.width

            # Crop to header region
            header_height = int(img.height * self.header_fraction)
            if header_height < 50:
                header_height = min(50, img.height)

            header_crop = img.crop((0, 0, img.width, header_height))

            # Run Tesseract on the cropped header
            text = pytesseract.image_to_string(header_crop)
            return text.strip() if text else None

        except Exception:
            # Fallback: OCR the full image (slower but more reliable)
            try:
                text = pytesseract.image_to_string(file_path)
                return text.strip() if text else None
            except Exception:
                return None

    def _ocr_pdf(self, file_path: str) -> Optional[str]:
        """
        Run OCR on a PDF scan printout.

        Converts the first page to an image, then runs the image OCR pipeline.
        """
        try:
            from pdf2image import convert_from_path
            import pytesseract
        except ImportError:
            return None

        try:
            # Convert first page of PDF to image
            pages = convert_from_path(file_path, first_page=1, last_page=1)
            if not pages:
                return None

            img = pages[0]
            header_height = int(img.height * self.header_fraction)
            header_crop = img.crop((0, 0, img.width, header_height))

            text = pytesseract.image_to_string(header_crop)
            return text.strip() if text else None

        except Exception:
            return None
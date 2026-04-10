"""
Brain_Scape — PACS / HL7 FHIR Integration

DICOM WADO-RS for PACS connectivity and HL7 FHIR facade layer.
Supports query/retrieve from PACS systems and FHIR resource mapping.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class PACSStudy:
    """Represents a DICOM study from PACS."""
    study_instance_uid: str
    patient_id: str
    patient_name: str
    study_date: str
    study_description: str
    modality: str
    accession_number: str
    number_of_series: int = 0
    number_of_instances: int = 0
    study_status: str = ""


@dataclass
class FHIRDiagnosticReport:
    """FHIR DiagnosticReport resource mapping."""
    id: str
    status: str  # registered | partial | preliminary | final | amended | corrected | appended | cancelled | entered-in-error | unknown
    category: str  # radiology
    code: str  # LOINC code for brain MRI
    subject: str  # Reference to Patient
    effective_datetime: str
    issued: str
    performer: str  # Reference to Practitioner
    conclusion: str = ""
    conclusion_code: List[str] = field(default_factory=list)
    imaging_study: str = ""  # Reference to ImagingStudy
    presented_form: List[Dict] = field(default_factory=list)


@dataclass
class FHIRPatient:
    """FHIR Patient resource mapping."""
    id: str
    identifier: List[Dict] = field(default_factory=list)
    name: List[Dict] = field(default_factory=list)
    birth_date: str = ""
    gender: str = ""
    managing_organization: str = ""


class PACSConnector:
    """Connect to PACS systems via DICOM WADO-RS.

    Supports:
    - Query studies by patient ID, date range, modality
    - Retrieve DICOM series and instances
    - Send Brain_Scape results back as DICOM Structured Reports
    """

    def __init__(
        self,
        pacs_aet: str = "BRAINSCAPE",
        pacs_host: str = "localhost",
        pacs_port: int = 104,
        pacs_aec: str = "PACS",
        wado_url: str = "http://localhost:8080/dicom-web",
    ):
        self.aet = pacs_aet
        self.host = pacs_host
        self.port = pacs_port
        self.aec = pacs_aec
        self.wado_url = wado_url.rstrip("/")

    def query_studies(
        self,
        patient_id: Optional[str] = None,
        study_date_from: Optional[str] = None,
        study_date_to: Optional[str] = None,
        modality: Optional[str] = None,
        accession_number: Optional[str] = None,
    ) -> List[PACSStudy]:
        """Query PACS for studies matching criteria.

        Args:
            patient_id: Patient identifier (MRN)
            study_date_from: Start date (YYYYMMDD)
            study_date_to: End date (YYYYMMDD)
            modality: DICOM modality (MR, CT, etc.)
            accession_number: Accession number

        Returns:
            List of PACSStudy objects
        """
        try:
            import requests

            params = {}
            if patient_id:
                params["PatientID"] = patient_id
            if study_date_from and study_date_to:
                params["StudyDate"] = f"{study_date_from}-{study_date_to}"
            elif study_date_from:
                params["StudyDate"] = f"{study_date_from}-"
            if modality:
                params["ModalitiesInStudy"] = modality
            if accession_number:
                params["AccessionNumber"] = accession_number

            response = requests.get(
                f"{self.wado_url}/studies",
                params=params,
                headers={"Accept": "application/dicom+json"},
                timeout=30,
            )
            response.raise_for_status()

            studies = []
            for result in response.json():
                # Parse DICOM JSON response
                study = PACSStudy(
                    study_instance_uid=self._get_dicom_tag(result, "0020000D"),
                    patient_id=self._get_dicom_tag(result, "00100020"),
                    patient_name=self._get_dicom_tag(result, "00100010"),
                    study_date=self._get_dicom_tag(result, "00080020"),
                    study_description=self._get_dicom_tag(result, "00081030"),
                    modality=self._get_dicom_tag(result, "00080061"),
                    accession_number=self._get_dicom_tag(result, "00080050"),
                )
                studies.append(study)

            logger.info(f"Found {len(studies)} studies from PACS")
            return studies

        except ImportError:
            logger.warning("requests library not available")
            return []
        except Exception as e:
            logger.error(f"PACS query failed: {e}")
            return []

    def retrieve_series(
        self,
        study_instance_uid: str,
        series_instance_uid: str,
        output_dir: str,
    ) -> List[str]:
        """Retrieve DICOM series from PACS.

        Args:
            study_instance_uid: Study Instance UID
            series_instance_uid: Series Instance UID
            output_dir: Directory to save DICOM files

        Returns:
            List of saved file paths
        """
        try:
            import requests
            import os

            os.makedirs(output_dir, exist_ok=True)

            url = (
                f"{self.wado_url}/studies/{study_instance_uid}"
                f"/series/{series_instance_uid}/instances"
            )

            response = requests.get(
                url,
                headers={"Accept": "application/dicom+zip"},
                timeout=120,
            )
            response.raise_for_status()

            # Save as zip and extract
            zip_path = os.path.join(output_dir, f"{series_instance_uid}.zip")
            with open(zip_path, "wb") as f:
                f.write(response.content)

            # Extract
            import zipfile
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(output_dir)

            # Find extracted DICOM files
            dcm_files = []
            for root, dirs, files in os.walk(output_dir):
                for fn in files:
                    if fn.endswith(".dcm") or not fn.contains("."):
                        dcm_files.append(os.path.join(root, fn))

            logger.info(f"Retrieved {len(dcm_files)} DICOM instances")
            return dcm_files

        except Exception as e:
            logger.error(f"PACS retrieve failed: {e}")
            return []

    def send_structured_report(
        self,
        study_instance_uid: str,
        analysis: Dict,
        report_path: str,
    ) -> bool:
        """Send Brain_Scape analysis as DICOM Structured Report to PACS.

        Args:
            study_instance_uid: Study to attach report to
            analysis: Analysis JSON
            report_path: Path to generated PDF report

        Returns:
            True if successful
        """
        try:
            import requests

            # Create DICOM Structured Report (SR)
            sr = self._create_structured_report(study_instance_uid, analysis)

            url = f"{self.wado_url}/studies/{study_instance_uid}/series"
            response = requests.post(
                url,
                json=sr,
                headers={"Content-Type": "application/dicom+json"},
                timeout=30,
            )
            response.raise_for_status()

            logger.info(f"Sent Structured Report for study {study_instance_uid}")
            return True

        except Exception as e:
            logger.error(f"Failed to send Structured Report: {e}")
            return False

    def _create_structured_report(self, study_uid: str, analysis: Dict) -> Dict:
        """Create a DICOM Structured Report from analysis data."""
        import uuid
        return {
            "00080005": {"vr": "CS", "Value": ["ISO_IR 192"]},
            "00080016": {"vr": "UI", "Value": ["1.2.840.10008.5.1.4.1.1.88.33"]},
            "00080018": {"vr": "UI", "Value": [str(uuid.uuid4())]},
            "00080060": {"vr": "CS", "Value": ["SR"]},
            "0020000D": {"vr": "UI", "Value": [study_uid]},
            "0040A010": {"vr": "CS", "Value": ["CONTAINS"]},
            "0040A730": {"vr": "SQ", "Value": self._build_sr_content(analysis)},
        }

    def _build_sr_content(self, analysis: Dict) -> List[Dict]:
        """Build SR content sequence from analysis data."""
        content = []
        for region in analysis.get("damage_summary", []):
            content.append({
                "0040A040": {"vr": "CS", "Value": ["FINDING"]},
                "0040A043": {"vr": "SQ", "Value": [{
                    "00080100": {"vr": "SH", "Value": ["BRNSCAPE"]},
                    "00080102": {"vr": "SH", "Value": ["99BRAINSCAPE"]},
                    "00080104": {"vr": "LO", "Value": [region.get("anatomical_name", "")]},
                }]},
                "0040A080": {"vr": "SQ", "Value": [{
                    "0040A040": {"vr": "CS", "Value": ["CODE"]},
                    "00080100": {"vr": "SH", "Value": [region.get("severity_label", "")]},
                }]},
            })
        return content

    @staticmethod
    def _get_dicom_tag(dicom_json: Dict, tag: str) -> str:
        """Extract a value from DICOM JSON by tag."""
        element = dicom_json.get(tag, {})
        value = element.get("Value", [""])[0] if "Value" in element else ""
        return str(value)


class FHIRFacade:
    """HL7 FHIR facade layer for interoperability.

    Maps Brain_Scape resources to FHIR R4 resources:
    - Patient
    - DiagnosticReport
    - ImagingStudy
    - Observation
    """

    def __init__(self, base_url: str = "https://fhir.brainscape.ai/R4"):
        self.base_url = base_url.rstrip("/")

    def create_patient(self, patient_data: Dict) -> FHIRPatient:
        """Create a FHIR Patient resource from Brain_Scape data."""
        return FHIRPatient(
            id=patient_data.get("id", ""),
            identifier=[{
                "system": "http://brainscape.ai/patient-mrn",
                "value": patient_data.get("mrn", ""),
            }],
            name=[{
                "family": patient_data.get("last_name", "ANONYMOUS"),
                "given": [patient_data.get("first_name", "")],
            }],
            birth_date=patient_data.get("birth_date", ""),
            gender=patient_data.get("gender", "unknown"),
            managing_organization=patient_data.get("institution", ""),
        )

    def create_diagnostic_report(
        self,
        analysis: Dict,
        patient_id: str,
        practitioner_id: str = "system",
    ) -> FHIRDiagnosticReport:
        """Create a FHIR DiagnosticReport from Brain_Scape analysis."""
        damage_summary = analysis.get("damage_summary", [])
        conclusion_parts = []
        conclusion_codes = []

        for region in damage_summary:
            name = region.get("anatomical_name", "Unknown")
            severity = region.get("severity_label", "UNKNOWN")
            confidence = region.get("confidence", 0)
            conclusion_parts.append(
                f"{name}: {severity} severity (confidence: {confidence:.0%})"
            )

        return FHIRDiagnosticReport(
            id=analysis.get("scan_id", ""),
            status="final" if analysis.get("overall_confidence", 0) > 0.5 else "preliminary",
            category="RAD",
            code="37771-2",  # LOINC for Brain MRI report
            subject=f"Patient/{patient_id}",
            effective_datetime=analysis.get("scan_metadata", {}).get(
                "acquisition_date", datetime.utcnow().isoformat()
            ),
            issued=datetime.utcnow().isoformat(),
            performer=f"Practitioner/{practitioner_id}",
            conclusion="; ".join(conclusion_parts),
            conclusion_code=conclusion_codes,
            imaging_study=f"ImagingStudy/{analysis.get('scan_id', '')}",
        )

    def fhir_patient_to_dict(self, patient: FHIRPatient) -> Dict:
        """Convert FHIRPatient to FHIR R4 JSON."""
        return {
            "resourceType": "Patient",
            "id": patient.id,
            "identifier": patient.identifier,
            "name": patient.name,
            "birthDate": patient.birth_date,
            "gender": patient.gender,
            "managingOrganization": patient.managing_organization,
        }

    def fhir_report_to_dict(self, report: FHIRDiagnosticReport) -> Dict:
        """Convert FHIRDiagnosticReport to FHIR R4 JSON."""
        return {
            "resourceType": "DiagnosticReport",
            "id": report.id,
            "status": report.status,
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                    "code": report.category,
                    "display": "Radiology",
                }]
            }],
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": report.code,
                    "display": "MRI Brain",
                }]
            },
            "subject": {"reference": report.subject},
            "effectiveDateTime": report.effective_datetime,
            "issued": report.issued,
            "performer": [{"reference": report.performer}],
            "conclusion": report.conclusion,
            "conclusionCode": report.conclusion_code,
            "imagingStudy": [{"reference": report.imaging_study}],
        }

    def submit_to_fhir_server(self, resource: Dict, resource_type: str) -> Optional[str]:
        """Submit a FHIR resource to a FHIR server."""
        try:
            import requests
            response = requests.post(
                f"{self.base_url}/{resource_type}",
                json=resource,
                headers={"Content-Type": "application/fhir+json"},
                timeout=30,
            )
            response.raise_for_status()
            created = response.json()
            return created.get("id")
        except ImportError:
            logger.warning("requests library not available")
            return None
        except Exception as e:
            logger.error(f"FHIR submission failed: {e}")
            return None
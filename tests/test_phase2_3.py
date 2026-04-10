"""
Brain_Scape — Phase 2 & 3 Tests

Tests for differential diagnosis, longitudinal analysis, multimodal fusion,
connectivity, prognosis, voice interface, treatment planning, PACS/FHIR,
and WebSocket annotation collaboration.
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch


# ── Differential Diagnosis ──

class TestDifferentialDiagnosis:
    """Test the differential diagnosis engine."""

    def setup_method(self):
        from analysis.classification.differential_diagnosis import DifferentialDiagnoser
        self.diagnoser = DifferentialDiagnoser()

    def test_returns_ranked_candidates(self):
        """Should return ranked list of diagnosis candidates."""
        damage = [
            {"anatomical_name": "Left Middle Cerebral Artery Territory",
             "severity_level": 4, "severity_label": "RED", "confidence": 0.9,
             "volume_mm3": 800, "volume_pct_of_region": 45},
        ]
        candidates = self.diagnoser.diagnose(damage)
        assert len(candidates) > 0
        assert candidates[0].rank == 1
        assert candidates[0].probability > 0

    def test_ranks_by_probability(self):
        """Candidates should be sorted by probability descending."""
        damage = [
            {"anatomical_name": "Left Hippocampus", "severity_level": 3,
             "severity_label": "ORANGE", "confidence": 0.8,
             "volume_mm3": 500, "volume_pct_of_region": 30},
            {"anatomical_name": "Right Frontal Lobe", "severity_level": 2,
             "severity_label": "YELLOW", "confidence": 0.7,
             "volume_mm3": 300, "volume_pct_of_region": 15},
        ]
        candidates = self.diagnoser.diagnose(damage)
        probs = [c.probability for c in candidates]
        assert probs == sorted(probs, reverse=True)

    def test_probabilities_sum_to_one(self):
        """Rule-based probabilities should sum to approximately 1.0."""
        damage = [
            {"anatomical_name": "Basal Ganglia", "severity_level": 4,
             "severity_label": "RED", "confidence": 0.9,
             "volume_mm3": 800, "volume_pct_of_region": 45},
        ]
        candidates = self.diagnoser.diagnose(damage)
        total = sum(c.probability for c in candidates)
        assert 0.95 <= total <= 1.05

    def test_empty_damage_returns_empty(self):
        """Should return empty list for no damage."""
        candidates = self.diagnoser.diagnose([])
        assert len(candidates) == 0

    def test_to_dict_serializable(self):
        """to_dict should return serializable dicts."""
        damage = [
            {"anatomical_name": "Left Hippocampus", "severity_level": 4,
             "severity_label": "RED", "confidence": 0.9,
             "volume_mm3": 800, "volume_pct_of_region": 45},
        ]
        candidates = self.diagnoser.diagnose(damage)
        result = self.diagnoser.to_dict(candidates)
        assert isinstance(result, list)
        assert all(isinstance(c, dict) for c in result)

    def test_eight_etiologies_supported(self):
        """Should support all 8 etiologies."""
        from analysis.classification.differential_diagnosis import ETIOLOGIES
        assert len(ETIOLOGIES) == 8
        assert "stroke" in ETIOLOGIES
        assert "dementia" in ETIOLOGIES


# ── Longitudinal Analysis ──

class TestLongitudinalAnalysis:
    """Test the temporal comparator."""

    def setup_method(self):
        from analysis.longitudinal.temporal_comparator import TemporalComparator
        self.comparator = TemporalComparator()

    def test_detects_worsening(self):
        """Should detect worsening between two timepoints."""
        before = {
            "damage_summary": [
                {"anatomical_name": "Left Hippocampus", "severity_level": 2,
                 "severity_label": "YELLOW", "confidence": 0.8,
                 "volume_mm3": 200, "volume_pct_of_region": 10},
            ],
        }
        after = {
            "damage_summary": [
                {"anatomical_name": "Left Hippocampus", "severity_level": 4,
                 "severity_label": "RED", "confidence": 0.9,
                 "volume_mm3": 800, "volume_pct_of_region": 45},
            ],
        }
        result = self.comparator.compare(before, after, "patient-1")
        assert result.overall_trend in ["worsening", "mixed"]

    def test_detects_improvement(self):
        """Should detect improvement between two timepoints."""
        before = {
            "damage_summary": [
                {"anatomical_name": "Left Hippocampus", "severity_level": 4,
                 "severity_label": "RED", "confidence": 0.9,
                 "volume_mm3": 800, "volume_pct_of_region": 45},
            ],
        }
        after = {
            "damage_summary": [
                {"anatomical_name": "Left Hippocampus", "severity_level": 1,
                 "severity_label": "GREEN", "confidence": 0.9,
                 "volume_mm3": 50, "volume_pct_of_region": 2},
            ],
        }
        result = self.comparator.compare(before, after, "patient-1")
        assert result.overall_trend in ["improving", "mixed"]

    def test_atrophy_rate_calculation(self):
        """Should calculate atrophy rate when months_between is provided."""
        before = {
            "damage_summary": [
                {"anatomical_name": "Left Hippocampus", "severity_level": 2,
                 "severity_label": "YELLOW", "confidence": 0.8,
                 "volume_mm3": 200, "volume_pct_of_region": 10},
            ],
        }
        after = {
            "damage_summary": [
                {"anatomical_name": "Left Hippocampus", "severity_level": 3,
                 "severity_label": "ORANGE", "confidence": 0.85,
                 "volume_mm3": 500, "volume_pct_of_region": 25},
            ],
        }
        result = self.comparator.compare(before, after, "patient-1", months_between=6)
        assert result.atrophy_rate_global is not None

    def test_delta_map_generation(self):
        """Should generate a delta map for visualization."""
        before = {"damage_summary": [
            {"anatomical_name": "Left Hippocampus", "severity_level": 2,
             "severity_label": "YELLOW", "confidence": 0.8,
             "volume_mm3": 200, "volume_pct_of_region": 10},
        ]}
        after = {"damage_summary": [
            {"anatomical_name": "Left Hippocampus", "severity_level": 4,
             "severity_label": "RED", "confidence": 0.9,
             "volume_mm3": 800, "volume_pct_of_region": 45},
        ]}
        result = self.comparator.compare(before, after, "patient-1")
        delta_map = self.comparator.generate_delta_map(result)
        assert "regions" in delta_map
        assert delta_map["trend"] in ["worsening", "improving", "stable", "mixed"]


# ── Multimodal Fusion ──

class TestMultimodalFusion:
    """Test the multimodal fusion engine."""

    def setup_method(self):
        from analysis.fusion.multimodal_fuser import MultimodalFuser, ModalityResult
        self.fuser = MultimodalFuser()

    def test_fuse_multiple_modalities(self):
        """Should fuse damage from multiple modalities."""
        from analysis.fusion.multimodal_fuser import ModalityResult
        results = [
            ModalityResult(modality="MRI_T1", region_scores=[
                {"anatomical_name": "Left Hippocampus", "severity_level": 4,
                 "severity_label": "RED", "confidence": 0.9, "volume_pct_of_region": 45},
            ], confidence=0.9),
            ModalityResult(modality="fMRI", region_scores=[
                {"anatomical_name": "Left Hippocampus", "severity_level": 3,
                 "severity_label": "ORANGE", "confidence": 0.7, "volume_pct_of_region": 30},
            ], confidence=0.7),
        ]
        result = self.fuser.fuse(results)
        assert len(result.region_scores) > 0
        assert result.overall_confidence > 0

    def test_weight_normalization(self):
        """Weights for available modalities should sum to 1."""
        from analysis.fusion.multimodal_fuser import ModalityResult
        results = [
            ModalityResult(modality="MRI_T1", region_scores=[], confidence=0.9),
            ModalityResult(modality="EEG", region_scores=[], confidence=0.5),
        ]
        result = self.fuser.fuse(results)
        total_weight = sum(result.modality_weights_used.values())
        assert abs(total_weight - 1.0) < 0.01

    def test_single_modality(self):
        """Should work with a single modality."""
        from analysis.fusion.multimodal_fuser import ModalityResult
        results = [
            ModalityResult(modality="MRI_T1", region_scores=[
                {"anatomical_name": "Left Hippocampus", "severity_level": 4,
                 "severity_label": "RED", "confidence": 0.9, "volume_pct_of_region": 45},
            ], confidence=0.9),
        ]
        result = self.fuser.fuse(results)
        assert len(result.region_scores) > 0


# ── Connectivity Analysis ──

class TestConnectivityAnalysis:
    """Test structural and functional connectivity."""

    def test_structural_connectivity(self):
        """Should identify affected white matter tracts."""
        from analysis.connectivity.structural_connectivity import StructuralConnectivity
        sc = StructuralConnectivity()
        damage = [
            {"anatomical_name": "Left Hippocampus", "severity_level": 4,
             "severity_label": "RED", "confidence": 0.9},
        ]
        result = sc.analyze(damage)
        assert len(result.tracts) > 0
        assert "fornix" in result.damaged_tracts or "cingulum" in result.damaged_tracts

    def test_functional_connectivity(self):
        """Should identify disrupted functional networks."""
        from analysis.connectivity.functional_connectivity import FunctionalConnectivity
        fc = FunctionalConnectivity()
        damage = [
            {"anatomical_name": "Left Hippocampus", "severity_level": 4,
             "severity_label": "RED", "confidence": 0.9},
        ]
        result = fc.analyze(damage)
        assert len(result.networks) > 0
        assert isinstance(result.disrupted_networks, list)

    def test_structural_to_dict(self):
        """Should serialize to dict."""
        from analysis.connectivity.structural_connectivity import StructuralConnectivity
        sc = StructuralConnectivity()
        result = sc.analyze([
            {"anatomical_name": "Left Frontal Lobe", "severity_level": 3,
             "severity_label": "ORANGE", "confidence": 0.8},
        ])
        d = sc.to_dict(result)
        assert isinstance(d, dict)
        assert "tracts" in d


# ── Prognosis Generator ──

class TestPrognosisGenerator:
    """Test the prognosis timeline generator."""

    def setup_method(self):
        from llm.prognosis_generator import PrognosisGenerator
        self.generator = PrognosisGenerator()

    def test_generates_milestones(self):
        """Should generate recovery milestones with probability ranges."""
        analysis = {
            "scan_id": "test-1",
            "damage_summary": [
                {"anatomical_name": "Left Hippocampus", "severity_level": 4,
                 "severity_label": "RED", "confidence": 0.9,
                 "volume_mm3": 800, "volume_pct_of_region": 45},
            ],
            "overall_confidence": 0.85,
        }
        result = self.generator.generate(analysis)
        assert len(result.milestones) > 0
        assert result.overall_prognosis in ["favorable", "guarded", "poor"]

    def test_milestones_have_probability_ranges(self):
        """Each milestone should have a probability range."""
        analysis = {
            "scan_id": "test-1",
            "damage_summary": [
                {"anatomical_name": "Left Frontal Lobe", "severity_level": 3,
                 "severity_label": "ORANGE", "confidence": 0.8,
                 "volume_mm3": 500, "volume_pct_of_region": 25},
            ],
            "overall_confidence": 0.8,
        }
        result = self.generator.generate(analysis)
        for m in result.milestones:
            assert len(m.probability_range) == 2
            assert 0 <= m.probability_range[0] <= m.probability_range[1] <= 1

    def test_disclaimer_included(self):
        """Prognosis should always include a disclaimer."""
        analysis = {"scan_id": "test", "damage_summary": [], "overall_confidence": 0.5}
        result = self.generator.generate(analysis)
        assert len(result.disclaimer) > 0
        assert "AI-generated" in result.disclaimer or "not a substitute" in result.disclaimer

    def test_age_adjustment(self):
        """Younger patients should have better prognosis."""
        analysis = {
            "scan_id": "test",
            "damage_summary": [
                {"anatomical_name": "Left Hippocampus", "severity_level": 3,
                 "severity_label": "ORANGE", "confidence": 0.8,
                 "volume_mm3": 500, "volume_pct_of_region": 25},
            ],
            "overall_confidence": 0.8,
        }
        young_result = self.generator.generate(analysis, patient_metadata={"age": 30})
        old_result = self.generator.generate(analysis, patient_metadata={"age": 80})
        # Young patient should have higher milestone probabilities
        if young_result.milestones and old_result.milestones:
            young_avg = np.mean([m.probability_range[1] for m in young_result.milestones])
            old_avg = np.mean([m.probability_range[1] for m in old_result.milestones])
            assert young_avg >= old_avg


# ── Voice Interface ──

class TestVoiceInterface:
    """Test the voice query interface."""

    def test_transcribe_without_whisper(self):
        """Should return error gracefully when Whisper is not installed."""
        from llm.voice_interface import VoiceInterface
        vi = VoiceInterface()
        result = vi.transcribe("nonexistent.wav")
        assert "error" in result

    def test_tts_instructions(self):
        """Should return browser TTS instructions."""
        from llm.voice_interface import VoiceInterface
        vi = VoiceInterface()
        instructions = vi.get_tts_instructions()
        assert instructions["method"] == "browser_speech_synthesis"


# ── Treatment Planning ──

class TestTreatmentPlanning:
    """Test the treatment planning overlay."""

    def setup_method(self):
        from analysis.treatment.planning_overlay import PlanningOverlay
        self.planner = PlanningOverlay()

    def test_identifies_no_go_zones(self):
        """Should identify critical no-go zones when eloquent areas are damaged."""
        damage = [
            {"anatomical_name": "Left Inferior Frontal Gyrus", "severity_level": 4,
             "severity_label": "RED", "confidence": 0.9,
             "volume_mm3": 800, "volume_pct_of_region": 45},
        ]
        result = self.planner.analyze(damage, scan_id="test-1")
        assert len(result.no_go_zones) > 0

    def test_contraindicated_when_critical_hit(self):
        """Should be contraindicated when critical eloquent area is directly hit."""
        damage = [
            {"anatomical_name": "Brainstem", "severity_level": 4,
             "severity_label": "RED", "confidence": 0.9,
             "volume_mm3": 800, "volume_pct_of_region": 45},
        ]
        result = self.planner.analyze(damage, scan_id="test-1")
        assert result.intervention_viability["overall_viability"] == "contraindicated"

    def test_feasible_when_no_eloquent_damage(self):
        """Should be feasible when damage is in non-eloquent areas."""
        damage = [
            {"anatomical_name": "Right Anterior Temporal Pole", "severity_level": 2,
             "severity_label": "YELLOW", "confidence": 0.7,
             "volume_mm3": 200, "volume_pct_of_region": 10},
        ]
        result = self.planner.analyze(damage, scan_id="test-1")
        assert result.intervention_viability["overall_viability"] in ["feasible", "caution"]

    def test_warnings_for_critical_areas(self):
        """Should generate warnings when critical areas are affected."""
        damage = [
            {"anatomical_name": "Precentral Gyrus", "severity_level": 4,
             "severity_label": "RED", "confidence": 0.9,
             "volume_mm3": 800, "volume_pct_of_region": 45},
        ]
        result = self.planner.analyze(damage, scan_id="test-1")
        assert len(result.warnings) > 0


# ── PACS/FHIR ──

class TestPACSFHIR:
    """Test PACS connector and FHIR facade."""

    def test_fhir_patient_creation(self):
        """Should create a FHIR Patient resource."""
        from mlops.serve.pacs_fhir import FHIRFacade
        facade = FHIRFacade()
        patient = facade.create_patient({
            "id": "patient-1",
            "mrn": "MRN-12345",
            "last_name": "Doe",
            "first_name": "Jane",
            "birth_date": "1980-01-01",
            "gender": "female",
        })
        assert patient.id == "patient-1"
        d = facade.fhir_patient_to_dict(patient)
        assert d["resourceType"] == "Patient"

    def test_fhir_diagnostic_report_creation(self):
        """Should create a FHIR DiagnosticReport resource."""
        from mlops.serve.pacs_fhir import FHIRFacade
        facade = FHIRFacade()
        analysis = {
            "scan_id": "scan-1",
            "damage_summary": [
                {"anatomical_name": "Left Hippocampus", "severity_label": "RED",
                 "confidence": 0.9, "severity_level": 4},
            ],
            "overall_confidence": 0.85,
        }
        report = facade.create_diagnostic_report(analysis, "patient-1")
        d = facade.fhir_report_to_dict(report)
        assert d["resourceType"] == "DiagnosticReport"
        assert "Left Hippocampus" in d["conclusion"]

    def test_pacs_study_dataclass(self):
        """PACSStudy should be constructable."""
        from mlops.serve.pacs_fhir import PACSStudy
        study = PACSStudy(
            study_instance_uid="1.2.3.4.5",
            patient_id="P-001",
            patient_name="ANONYMOUS",
            study_date="20250101",
            study_description="Brain MRI",
            modality="MR",
            accession_number="ACC-001",
        )
        assert study.study_instance_uid == "1.2.3.4.5"


# ── Annotation WebSocket ──

class TestAnnotationWebSocket:
    """Test the annotation WebSocket manager."""

    def test_session_creation(self):
        """Should create annotation sessions on demand."""
        from mlops.serve.ws_server import AnnotationWebSocketManager
        manager = AnnotationWebSocketManager()
        session = manager.get_or_create_session("scan-1")
        assert session.scan_id == "scan-1"
        assert len(session.connections) == 0

    def test_session_reuse(self):
        """Should reuse existing sessions for the same scan."""
        from mlops.serve.ws_server import AnnotationWebSocketManager
        manager = AnnotationWebSocketManager()
        s1 = manager.get_or_create_session("scan-1")
        s2 = manager.get_or_create_session("scan-1")
        assert s1 is s2

    def test_session_info(self):
        """Should return session information."""
        from mlops.serve.ws_server import AnnotationWebSocketManager
        manager = AnnotationWebSocketManager()
        manager.get_or_create_session("scan-1")
        info = manager.get_session_info("scan-1")
        assert info is not None
        assert info["scan_id"] == "scan-1"
        assert info["active_users"] == 0


# ── Institutional Dashboard ──

class TestInstitutionalDashboard:
    """Test institutional dashboard and data residency."""

    def test_data_residency_check(self):
        """Should enforce data residency rules for GDPR."""
        from mlops.dashboard.institutional_dashboard import InstitutionalDashboard, InstitutionConfig
        dashboard = InstitutionalDashboard()

        # EU institution with GDPR
        eu_config = InstitutionConfig(
            institution_id="eu-hospital-1",
            name="EU Hospital",
            data_residency_region="eu-west-1",
            gdpr_enabled=True,
        )
        dashboard.register_institution(eu_config)

        # EU data should stay in EU
        assert dashboard.check_data_residency("eu-hospital-1", "eu-west-1") is True
        assert dashboard.check_data_residency("eu-hospital-1", "us-east-1") is False

    def test_grafana_dashboard_config(self):
        """Should generate Grafana dashboard configuration."""
        from mlops.dashboard.institutional_dashboard import InstitutionalDashboard, InstitutionConfig
        dashboard = InstitutionalDashboard()

        dashboard.register_institution(InstitutionConfig(
            institution_id="test-hospital",
            name="Test Hospital",
        ))

        config = dashboard.get_grafana_dashboard_config("test-hospital")
        assert "dashboard" in config
        assert "panels" in config["dashboard"]
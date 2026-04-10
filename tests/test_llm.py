"""
Brain_Scape — LLM & RAG Tests

Tests for RAG engine, Q&A engine, report generator, and prompt templates.
Uses mocked LLM calls to avoid API dependency.
"""

import pytest
from unittest.mock import MagicMock, patch

from llm.prompt_templates import (
    qa_prompt,
    clinician_report_prompt,
    patient_report_prompt,
    prognosis_prompt,
    VERSION,
    TEMPLATES,
)


class TestPromptTemplates:
    """Test that all prompt templates render correctly."""

    def test_version_defined(self):
        """Prompt templates should have a version number."""
        assert VERSION is not None
        assert isinstance(VERSION, str)

    def test_all_templates_registered(self):
        """All template names should be registered."""
        expected = ["qa", "clinician_report", "patient_report", "prognosis", "rag_retrieval"]
        for name in expected:
            assert name in TEMPLATES

    def test_qa_prompt_renders(self):
        """Q&A prompt should include the question and context."""
        result = qa_prompt(
            question="Is this region related to speech?",
            context="SCAN CONTEXT:\nLeft inferior frontal gyrus: ORANGE severity"
        )
        assert "speech" in result.lower()
        assert "SCAN CONTEXT" in result
        assert "INSTRUCTIONS" in result

    def test_clinician_report_prompt_renders(self):
        """Clinician report prompt should include structured findings."""
        structured = {
            "scan_metadata": {"scan_id": "test-123"},
            "damage_summary": [{"anatomical_name": "Left Hippocampus", "severity_label": "RED"}],
        }
        result = clinician_report_prompt(structured, [])
        assert "Left Hippocampus" in result
        assert "STRUCTURED FINDINGS" in result

    def test_patient_report_prompt_renders(self):
        """Patient report prompt should request plain English."""
        structured = {"damage_summary": [{"anatomical_name": "Hippocampus"}]}
        result = patient_report_prompt(structured)
        assert "plain English" in result.lower() or "patient" in result.lower()

    def test_prognosis_prompt_renders(self):
        """Prognosis prompt should include findings and metadata."""
        structured = {"damage_summary": [{"anatomical_name": "Left Hippocampus"}]}
        result = prognosis_prompt(structured, patient_metadata={"age": 55})
        assert "prognosis" in result.lower() or "recovery" in result.lower()
        assert "55" in result

    def test_get_template(self):
        """get_template should return the correct function."""
        from llm.prompt_templates import get_template
        qa_fn = get_template("qa")
        assert qa_fn is not None

    def test_get_template_unknown(self):
        """get_template should raise ValueError for unknown templates."""
        from llm.prompt_templates import get_template
        with pytest.raises(ValueError):
            get_template("nonexistent")


class TestRAGEngine:
    """Test RAG engine with mocked vector store."""

    def test_embed_text_returns_vector(self):
        """embed_text should return a list of floats."""
        from llm.rag_engine import RAGEngine
        rag = RAGEngine(vector_store="weaviate")
        embedding = rag.embed_text("test query about hippocampal damage")
        assert isinstance(embedding, list)
        assert len(embedding) > 0

    def test_chunk_text(self):
        """_chunk_text should split text into overlapping chunks."""
        from llm.rag_engine import RAGEngine
        rag = RAGEngine(vector_store="weaviate")
        text = " ".join(["word"] * 1000)
        chunks = rag._chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) > 1
        # Each chunk should be approximately chunk_size words
        for chunk in chunks:
            assert len(chunk.split()) <= 120  # Some tolerance for overlap


class TestQAEngine:
    """Test Q&A engine with mocked LLM."""

    def test_fallback_answer_damaged_regions(self):
        """Without LLM, QA should produce a basic answer about damaged regions."""
        from llm.qa_engine import QAEngine
        from llm.rag_engine import RAGEngine

        rag = RAGEngine(vector_store="weaviate")
        qa = QAEngine(rag_engine=rag, llm_client=None)

        analysis = {
            "regions": [
                {"anatomical_name": "Left Hippocampus", "severity_level": 4, "severity_label": "RED", "confidence": 0.91},
                {"anatomical_name": "Right Frontal Lobe", "severity_level": 2, "severity_label": "YELLOW", "confidence": 0.78},
            ],
            "overall_confidence": 0.85,
        }

        result = qa.answer("What regions are damaged?", analysis)
        assert "Left Hippocampus" in result["answer"]
        assert result["question"] == "What regions are damaged?"

    def test_extract_citations(self):
        """_extract_citations should pull citation info from RAG results."""
        from llm.qa_engine import QAEngine
        rag_results = [
            {"title": "Hippocampal Damage and Memory", "source": "Neurology", "year": "2023", "doi": "10.1234/test"},
        ]
        citations = QAEngine._extract_citations(rag_results)
        assert len(citations) == 1
        assert citations[0]["title"] == "Hippocampal Damage and Memory"


class TestReportGenerator:
    """Test report generation with mocked LLM."""

    def test_executive_summary_with_damage(self):
        """Executive summary should mention damaged regions."""
        from llm.report_generator import ReportGenerator
        from llm.rag_engine import RAGEngine

        rag = RAGEngine(vector_store="weaviate")
        generator = ReportGenerator(rag_engine=rag, llm_client=None)

        structured = {
            "damage_summary": [
                {"anatomical_name": "Left Hippocampus", "severity_level": 4, "confidence": 0.91, "volume_mm3": 823.4, "volume_pct_of_region": 61.2},
                {"anatomical_name": "Right Frontal Lobe", "severity_level": 2, "confidence": 0.78, "volume_mm3": 450.0, "volume_pct_of_region": 15.0},
            ],
            "differential_diagnosis": [],
            "connectivity": {},
            "overall_confidence": 0.85,
        }

        summary = generator._generate_executive_summary(structured)
        assert "2" in summary  # 2 affected regions
        assert "Left Hippocampus" in summary

    def test_executive_summary_no_damage(self):
        """Executive summary should handle no damage case."""
        from llm.report_generator import ReportGenerator
        from llm.rag_engine import RAGEngine

        rag = RAGEngine(vector_store="weaviate")
        generator = ReportGenerator(rag_engine=rag, llm_client=None)

        structured = {
            "damage_summary": [],
            "overall_confidence": 0.92,
        }

        summary = generator._generate_executive_summary(structured)
        assert "No significant damage" in summary
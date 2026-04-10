"""
Brain_Scape — Report Generator

Generates clinical PDF reports using a two-pass LLM prompt chain:
  Pass 1: Structured extraction from analysis JSON
  Pass 2a: Clinician mode — full technical depth with citations
  Pass 2b: Patient mode — plain English, visual-first (Phase 2)

The two-pass chain ensures both reports are consistent in their
underlying facts while being appropriately different in presentation.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from llm.prompt_templates import PromptTemplates
from llm.rag_engine import RAGEngine

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generates clinical reports in clinician and patient modes.

    Uses a two-pass LLM chain:
    - Pass 1: Structured extraction (cheap, consistent)
    - Pass 2a/b: Role-specific rendering (clinician or patient)
    """

    def __init__(
        self,
        rag_engine: RAGEngine,
        llm_client=None,
        model: str = "gpt-4",
        pdf_engine: str = "reportlab",
    ):
        self.rag = rag_engine
        self.llm_client = llm_client
        self.model = model
        self.pdf_engine = pdf_engine

    def generate(
        self,
        scan_analysis: dict,
        output_dir: str,
        mode: str = "clinician",
        include_gif: bool = True,
    ) -> dict:
        """
        Generate a clinical report.

        Args:
            scan_analysis: Full analysis JSON from the pipeline.
            output_dir: Directory to write report files.
            mode: "clinician" or "patient" (Phase 2).
            include_gif: Whether to include the rotational GIF.

        Returns:
            Dictionary with report metadata and file paths.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        scan_id = scan_analysis.get("scan_id", "unknown")

        # ── Pass 1: Structured Extraction ──
        logger.info("Pass 1: Structured extraction from analysis JSON...")
        structured = self._extract_structured_findings(scan_analysis)

        # ── Retrieve RAG context ──
        rag_context = self._retrieve_rag_context(scan_analysis)

        # ── Pass 2: Role-Specific Rendering ──
        if mode == "clinician":
            logger.info("Pass 2a: Generating clinician report...")
            report_content = self._render_clinician_report(
                structured, rag_context, scan_analysis
            )
        elif mode == "patient":
            logger.info("Pass 2b: Generating patient report...")
            report_content = self._render_patient_report(
                structured, rag_context, scan_analysis
            )
        else:
            raise ValueError(f"Unknown report mode: {mode}")

        # ── Generate PDF ──
        pdf_path = str(out / f"report_{scan_id}_{mode}.pdf")
        self._generate_pdf(report_content, pdf_path, mode)

        # ── Save JSON version ──
        json_path = str(out / f"report_{scan_id}_{mode}.json")
        with open(json_path, "w") as f:
            json.dump(report_content, f, indent=2)

        result = {
            "scan_id": scan_id,
            "mode": mode,
            "pdf_path": pdf_path,
            "json_path": json_path,
            "generated_at": datetime.utcnow().isoformat(),
            "structured_findings": structured,
        }

        logger.info(f"Report generated: {mode} mode, saved to {pdf_path}")
        return result

    def _extract_structured_findings(self, analysis: dict) -> dict:
        """
        Pass 1: Extract structured findings from analysis JSON.

        This produces a consistent intermediate representation that
        both clinician and patient renderers draw from.
        """
        structured = {
            "scan_metadata": {
                "scan_id": analysis.get("scan_id", "unknown"),
                "modalities": analysis.get("modalities", []),
                "atlas": analysis.get("atlas", "AAL3"),
                "scan_quality_score": analysis.get("scan_quality_score", None),
            },
            "damage_summary": [],
            "differential_diagnosis": analysis.get("differential_diagnosis", []),
            "connectivity": analysis.get("connectivity", {}),
            "overall_confidence": analysis.get("overall_confidence", None),
        }

        # Extract damage regions
        for region in analysis.get("regions", []):
            structured["damage_summary"].append({
                "anatomical_name": region.get("anatomical_name", "Unknown"),
                "severity_level": region.get("severity_level", 0),
                "severity_label": region.get("severity_label", "BLUE"),
                "confidence": region.get("confidence", None),
                "volume_mm3": region.get("volume_mm3", None),
                "volume_pct": region.get("volume_pct_of_region", None),
            })

        return structured

    def _render_clinician_report(
        self,
        structured: dict,
        rag_context: list[dict],
        analysis: dict,
    ) -> dict:
        """
        Pass 2a: Render clinician-mode report.

        Full technical depth: Brodmann area labels, voxel volumes,
        confidence intervals, differential rankings, connectivity stats,
        chain-of-thought reasoning, citations.
        """
        if self.llm_client:
            prompt = PromptTemplates.clinician_report_prompt(structured, rag_context)
            llm_text = self._call_llm(prompt)
        else:
            llm_text = self._generate_fallback_clinician_report(structured)

        return {
            "mode": "clinician",
            "executive_summary": self._generate_executive_summary(structured),
            "damage_map": structured["damage_summary"],
            "differential_diagnosis": structured["differential_diagnosis"],
            "connectivity": structured["connectivity"],
            "detailed_findings": llm_text,
            "confidence_assessment": {
                "overall": structured.get("overall_confidence"),
                "regions": [
                    {"region": r["anatomical_name"], "confidence": r["confidence"]}
                    for r in structured["damage_summary"]
                    if r.get("confidence") is not None
                ],
            },
            "citations": self._extract_citations(rag_context),
            "methodology": {
                "segmentation": "nnU-Net v2 (3d_fullres)",
                "classification": "5-level severity scale",
                "confidence": "3-component weighted model",
                "atlas": structured["scan_metadata"].get("atlas", "AAL3"),
            },
        }

    def _render_patient_report(
        self,
        structured: dict,
        rag_context: list[dict],
        analysis: dict,
    ) -> dict:
        """
        Pass 2b: Render patient-mode report (Phase 2 — placeholder).

        Plain English, visual-first, minimal jargon, emotional framing.
        """
        # Phase 2 implementation — placeholder for now
        return {
            "mode": "patient",
            "note": "Patient report mode is a Phase 2 feature.",
            "structured_findings": structured,
        }

    def _retrieve_rag_context(self, analysis: dict) -> list[dict]:
        """Retrieve RAG context based on analysis findings."""
        # Build query from damaged regions
        damaged = [r for r in analysis.get("regions", []) if r.get("severity_level", 0) >= 2]
        if not damaged:
            return []

        query_parts = [r.get("anatomical_name", "") for r in damaged[:3]]
        query = " ".join(query_parts) + " brain damage clinical implications"

        return self.rag.retrieve(query, top_k=5)

    def _generate_pdf(
        self, report_content: dict, output_path: str, mode: str
    ) -> None:
        """Generate PDF from report content."""
        if self.pdf_engine == "reportlab":
            self._generate_reportlab_pdf(report_content, output_path, mode)
        elif self.pdf_engine == "weasyprint":
            self._generate_weasyprint_pdf(report_content, output_path, mode)
        else:
            self._generate_reportlab_pdf(report_content, output_path, mode)

    def _generate_reportlab_pdf(
        self, report_content: dict, output_path: str, mode: str
    ) -> None:
        """Generate PDF using ReportLab."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table

            doc = SimpleDocTemplate(output_path, pagesize=A4)
            styles = getSampleStyleSheet()
            elements = []

            # Title
            elements.append(Paragraph("Brain_Scape — Clinical Report", styles["Title"]))
            elements.append(Spacer(1, 20))

            # Executive Summary
            summary = report_content.get("executive_summary", "No summary available.")
            elements.append(Paragraph("Executive Summary", styles["Heading2"]))
            elements.append(Paragraph(summary, styles["Normal"]))
            elements.append(Spacer(1, 12))

            # Damage Map Table
            damage_map = report_content.get("damage_map", [])
            if damage_map:
                elements.append(Paragraph("Damage Assessment", styles["Heading2"]))
                table_data = [["Region", "Severity", "Confidence", "Volume (mm³)"]]
                for region in damage_map:
                    table_data.append([
                        region.get("anatomical_name", "Unknown"),
                        region.get("severity_label", "N/A"),
                        f"{region.get('confidence', 'N/A')}",
                        f"{region.get('volume_mm3', 'N/A')}",
                    ])
                table = Table(table_data)
                elements.append(table)
                elements.append(Spacer(1, 12))

            # Differential Diagnosis
            diff_diag = report_content.get("differential_diagnosis", [])
            if diff_diag:
                elements.append(Paragraph("Differential Diagnosis", styles["Heading2"]))
                for diag in diff_diag:
                    elements.append(Paragraph(
                        f"• {diag.get('etiology', 'Unknown')}: "
                        f"{diag.get('probability', 'N/A')} probability",
                        styles["Normal"]
                    ))

            doc.build(elements)
            logger.info(f"PDF generated: {output_path}")

        except ImportError:
            logger.warning("ReportLab not available. PDF generation skipped.")
            # Write JSON fallback
            with open(output_path.replace(".pdf", ".json"), "w") as f:
                json.dump(report_content, f, indent=2)

    @staticmethod
    def _generate_weasyprint_pdf(
        report_content: dict, output_path: str, mode: str
    ) -> None:
        """Generate PDF using WeasyPrint (HTML -> PDF)."""
        try:
            from weasyprint import HTML

            html_content = "<html><body><h1>Brain_Scape Report</h1>"
            html_content += f"<p>Mode: {mode}</p>"
            html_content += f"<pre>{json.dumps(report_content, indent=2)}</pre>"
            html_content += "</body></html>"

            HTML(string=html_content).write_pdf(output_path)

        except ImportError:
            logger.warning("WeasyPrint not available.")

    @staticmethod
    def _generate_executive_summary(structured: dict) -> str:
        """Generate a brief executive summary of the findings."""
        damaged = [r for r in structured["damage_summary"] if r.get("severity_level", 0) >= 2]
        total = len(structured["damage_summary"])

        if not damaged:
            return "No significant damage detected in the analyzed brain scan."

        severe = [r for r in damaged if r.get("severity_level", 0) >= 4]
        summary = (
            f"Analysis identified {len(damaged)} affected regions out of {total} assessed. "
        )
        if severe:
            names = [r["anatomical_name"] for r in severe[:3]]
            summary += f"Severely damaged regions include: {', '.join(names)}. "

        overall_conf = structured.get("overall_confidence")
        if overall_conf:
            summary += f"Overall confidence: {overall_conf:.0%}."

        return summary

    @staticmethod
    def _generate_fallback_clinician_report(structured: dict) -> str:
        """Generate a basic clinician report without LLM."""
        lines = ["CLINICAL FINDINGS:", ""]

        for region in structured.get("damage_summary", []):
            lines.append(
                f"• {region.get('anatomical_name', 'Unknown')}: "
                f"{region.get('severity_label', 'N/A')} severity "
                f"(confidence: {region.get('confidence', 'N/A')}, "
                f"volume: {region.get('volume_mm3', 'N/A')} mm³)"
            )

        if structured.get("differential_diagnosis"):
            lines.append("")
            lines.append("DIFFERENTIAL DIAGNOSIS:")
            for diag in structured["differential_diagnosis"]:
                lines.append(
                    f"• {diag.get('etiology', 'Unknown')}: "
                    f"probability {diag.get('probability', 'N/A')}"
                )

        return "\n".join(lines)

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM API."""
        try:
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=4096,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            return f"Error: {str(e)}"

    @staticmethod
    def _extract_citations(rag_results: list[dict]) -> list[dict]:
        """Extract citations from RAG results."""
        return [
            {
                "title": r.get("title", ""),
                "source": r.get("source", ""),
                "year": r.get("year", ""),
                "doi": r.get("doi", ""),
            }
            for r in rag_results
            if r.get("title")
        ]
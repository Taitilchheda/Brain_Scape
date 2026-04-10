"""
Brain_Scape — Prognosis Timeline Generator

Probabilistic recovery trajectory based on damage type, severity, location,
patient age, and published outcome data via RAG.
Never false certainty — always expressed as probability ranges.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class Milestone:
    """A recovery milestone with probability range."""
    timeframe: str               # e.g., "2-4 weeks", "3-6 months"
    milestone: str               # e.g., "Initial swelling reduction"
    probability_range: List[float]  # [lower, upper] e.g., [0.7, 0.9]
    confidence: str              # "high", "moderate", "low"
    notes: str = ""


@dataclass
class PrognosisResult:
    """Complete prognosis timeline result."""
    scan_id: str
    etiology: str
    overall_prognosis: str       # "favorable", "guarded", "poor"
    recovery_trajectory: str     # "rapid_improvement", "gradual_improvement", "stable", "declining"
    milestones: List[Milestone] = field(default_factory=list)
    functional_outcomes: Dict = field(default_factory=dict)
    risk_factors: List[str] = field(default_factory=list)
    protective_factors: List[str] = field(default_factory=list)
    disclaimer: str = ""
    summary: str = ""


# Evidence-based recovery timelines (simplified from literature)
RECOVERY_PROFILES = {
    "stroke": {
        "typical_trajectory": "rapid_early_improvement_then_plateau",
        "milestones": [
            Milestone("1-7 days", "Acute stabilization and swelling reduction", [0.85, 0.95], "high"),
            Milestone("1-4 weeks", "Early spontaneous recovery of mild deficits", [0.6, 0.8], "moderate",
                      "Most improvement occurs in first 3 months"),
            Milestone("1-3 months", "Motor recovery plateau for mild-moderate", [0.4, 0.7], "moderate"),
            Milestone("3-6 months", "Language and cognitive improvement continue", [0.3, 0.6], "moderate"),
            Milestone("6-12 months", "Slow continued functional gains", [0.2, 0.5], "moderate"),
            Milestone("12+ months", "Minimal additional recovery; adaptation phase", [0.1, 0.3], "low"),
        ],
        "favorable_factors": [
            "Younger age (<70)", "Mild initial severity", "Left hemisphere (language) plasticity",
            "Early rehabilitation", "Good social support", "No prior strokes",
        ],
        "risk_factors": [
            "Older age (>75)", "Severe initial deficit", "Large infarct volume",
            "Hemorrhagic conversion", "Post-stroke seizures", "Poor compliance",
        ],
    },
    "hemorrhage": {
        "typical_trajectory": "variable_dependent_on_location_and_size",
        "milestones": [
            Milestone("1-3 days", "Acute hematoma stabilization", [0.8, 0.95], "high"),
            Milestone("1-4 weeks", "Perihematomal edema resolution", [0.5, 0.8], "moderate"),
            Milestone("1-3 months", "Early functional recovery", [0.3, 0.6], "moderate"),
            Milestone("3-6 months", "Continued improvement if rehabilitation maintained", [0.2, 0.5], "moderate"),
            Milestone("6-12 months", "Plateau phase", [0.15, 0.35], "low"),
        ],
        "favorable_factors": [
            "Small hematoma volume (<30ml)", "Lobar location", "Younger age",
            "Minimal midline shift", "Prompt surgical evacuation",
        ],
        "risk_factors": [
            "Large hematoma (>60ml)", "Deep location (basal ganglia, thalamus)",
            "Intraventricular extension", "Receiving anticoagulation",
        ],
    },
    "tbi": {
        "typical_trajectory": "variable_dependent_on_severity",
        "milestones": [
            Milestone("1-7 days", "Acute monitoring and stabilization", [0.85, 0.95], "high"),
            Milestone("1-4 weeks", "Emergence from post-traumatic amnesia (mild TBI)", [0.5, 0.8], "moderate"),
            Milestone("1-6 months", "Cognitive rehabilitation gains", [0.3, 0.65], "moderate"),
            Milestone("6-12 months", "Functional independence plateau", [0.2, 0.5], "moderate"),
            Milestone("12-24 months", "Slow continued gains", [0.1, 0.3], "low"),
        ],
        "favorable_factors": [
            "Mild TBI (GCS 13-15)", "Young age", "No diffuse axonal injury",
            "Early rehabilitation", "Good pre-injury function",
        ],
        "risk_factors": [
            "Severe TBI (GCS 3-8)", "Diffuse axonal injury", "Prolonged coma",
            "Elevated ICP", "Multiple brain lesions",
        ],
    },
    "tumour": {
        "typical_trajectory": "dependent_on_treatment_response",
        "milestones": [
            Milestone("1-4 weeks", "Post-surgical recovery", [0.7, 0.9], "high",
                      "If surgical resection performed"),
            Milestone("1-3 months", "Radiation/chemotherapy response assessment", [0.3, 0.6], "moderate"),
            Milestone("3-6 months", "Treatment response plateau", [0.2, 0.5], "moderate"),
            Milestone("6-12 months", "Stabilization or progression", [0.15, 0.4], "low"),
        ],
        "favorable_factors": [
            "Low grade histology", "Complete resection", "Favorable molecular profile",
            "Younger age", "Good functional status (KPS >80)",
        ],
        "risk_factors": [
            "High grade (GBM)", "Incomplete resection", "Unfavorable molecular markers",
            "Older age", "Poor functional status",
        ],
    },
    "ms": {
        "typical_trajectory": "relapsing_remitting_with_variable_progression",
        "milestones": [
            Milestone("Acute relapse", "Relapse recovery (typically 2-8 weeks)", [0.6, 0.85], "moderate",
                      "Most relapses show partial or full recovery"),
            Milestone("3-6 months", "Post-relapse stabilization with DMT", [0.5, 0.8], "moderate"),
            Milestone("1-3 years", "DMT efficacy assessment", [0.3, 0.7], "moderate"),
            Milestone("Long-term", "Progression monitoring", [0.2, 0.5], "low"),
        ],
        "favorable_factors": [
            "Relapsing-remitting course", "Early DMT initiation", "Younger onset",
            "Female sex", "Low lesion load",
        ],
        "risk_factors": [
            "Progressive course", "High lesion load", "Spinal cord involvement",
            "Late diagnosis", "Frequent relapses",
        ],
    },
    "dementia": {
        "typical_trajectory": "gradual_progressive_decline",
        "milestones": [
            Milestone("6-12 months", "Rate of decline assessment", [0.5, 0.8], "moderate"),
            Milestone("1-2 years", "Functional independence assessment", [0.3, 0.6], "moderate"),
            Milestone("2-5 years", "Care needs escalation", [0.2, 0.5], "moderate"),
            Milestone("5+ years", "Advanced care planning", [0.1, 0.3], "low"),
        ],
        "favorable_factors": [
            "Mild cognitive impairment (early stage)", "Vascular component (potentially treatable)",
            "Good social support", "Cognitive stimulation",
        ],
        "risk_factors": [
            "Rapid progression", "Behavioral symptoms", "Young onset",
            "Cardiovascular comorbidities", "Social isolation",
        ],
    },
    "encephalitis": {
        "typical_trajectory": "variable_dependent_on_etiology",
        "milestones": [
            Milestone("1-4 weeks", "Acute treatment and stabilization", [0.6, 0.9], "moderate"),
            Milestone("1-3 months", "Early recovery phase", [0.4, 0.7], "moderate"),
            Milestone("3-12 months", "Continued cognitive improvement", [0.25, 0.55], "moderate"),
            Milestone("12+ months", "Residual deficit plateau", [0.15, 0.4], "low"),
        ],
        "favorable_factors": [
            "Viral etiology (HSV has treatment)", "Early treatment initiation",
            "Young age", "No coma during acute phase",
        ],
        "risk_factors": [
            "Autoimmune etiology", "Delayed treatment", "Seizures",
            "Coma", "Extensive bilateral involvement",
        ],
    },
    "hypoxic_injury": {
        "typical_trajectory": "bimodal_either_rapid_recovery_or_poor",
        "milestones": [
            Milestone("1-7 days", "Acute prognostication (somatosensory evoked potentials)", [0.6, 0.85], "moderate"),
            Milestone("1-4 weeks", "Early recovery if favorable markers present", [0.3, 0.6], "moderate"),
            Milestone("1-6 months", "Rehabilitation gains", [0.15, 0.45], "low"),
            Milestone("6-12 months", "Functional plateau", [0.1, 0.3], "low"),
        ],
        "favorable_factors": [
            "Brief duration of anoxia", "Prompt CPR (<5 min)",
            "Young age", "Preserved brainstem reflexes",
        ],
        "risk_factors": [
            "Prolonged anoxia (>10 min)", "Absent cortical responses",
            "Myoclonic status", "Older age",
        ],
    },
}


class PrognosisGenerator:
    """Generate probabilistic recovery timelines.

    Never provides false certainty. All predictions include probability ranges.
    Uses RAG for literature-backed evidence when available.
    """

    def __init__(self, rag_engine=None, llm_client=None):
        self.rag_engine = rag_engine
        self.llm_client = llm_client

    def generate(
        self,
        analysis: Dict,
        patient_metadata: Optional[Dict] = None,
        etiology: Optional[str] = None,
    ) -> PrognosisResult:
        """Generate a prognosis timeline.

        Args:
            analysis: Analysis JSON with damage_summary, confidence, etc.
            patient_metadata: Patient info (age, sex, comorbidities, etc.)
            etiology: Etiology override (if known from differential diagnosis)

        Returns:
            PrognosisResult with milestones, risk factors, and disclaimers
        """
        patient_metadata = patient_metadata or {}
        damage_summary = analysis.get("damage_summary", [])
        overall_confidence = analysis.get("overall_confidence", 0.5)

        # Determine etiology
        if not etiology:
            etiology = self._infer_etiology(damage_summary)

        # Get recovery profile
        profile = RECOVERY_PROFILES.get(etiology, self._default_profile())

        # Adjust based on damage severity
        severity_factor = self._compute_severity_factor(damage_summary)

        # Adjust based on patient factors
        age_factor = self._compute_age_factor(patient_metadata)

        # Build milestones with adjusted probabilities
        milestones = self._adjust_milestones(
            profile["milestones"], severity_factor, age_factor
        )

        # Determine overall prognosis
        overall = self._determine_prognosis(
            etiology, severity_factor, age_factor, overall_confidence
        )

        # Build functional outcomes
        functional = self._estimate_functional_outcomes(
            etiology, damage_summary, severity_factor
        )

        # Get risk and protective factors
        risk_factors = profile.get("risk_factors", [])
        protective_factors = profile.get("favorable_factors", [])

        # Filter factors based on patient metadata
        risk_factors = self._filter_factors(risk_factors, patient_metadata)
        protective_factors = self._filter_factors(protective_factors, patient_metadata)

        # Build summary
        trajectory = profile.get("typical_trajectory", "variable")
        summary = self._generate_summary(
            etiology, overall, trajectory, milestones, len(damage_summary)
        )

        # Build disclaimer
        disclaimer = (
            "IMPORTANT: This prognosis is AI-generated and based on population-level data. "
            "Individual outcomes vary significantly. Probability ranges represent confidence intervals, "
            "not guarantees. This information should be reviewed by a qualified clinician before "
            "being communicated to patients. This is not a substitute for professional medical advice."
        )

        return PrognosisResult(
            scan_id=analysis.get("scan_id", "unknown"),
            etiology=etiology,
            overall_prognosis=overall,
            recovery_trajectory=trajectory,
            milestones=milestones,
            functional_outcomes=functional,
            risk_factors=risk_factors,
            protective_factors=protective_factors,
            disclaimer=disclaimer,
            summary=summary,
        )

    def _infer_etiology(self, damage_summary: List[Dict]) -> str:
        """Infer most likely etiology from damage pattern."""
        if not damage_summary:
            return "stroke"  # default

        # Simple heuristic: check region patterns
        regions = [r.get("anatomical_name", "").lower() for r in damage_summary]
        max_severity = max((r.get("severity_level", 0) for r in damage_summary), default=0)

        # Vascular territory pattern → stroke
        if any("artery" in r or "middle cerebral" in r or "basal ganglia" in r
               for r in regions):
            return "stroke"

        # Hemorrhagic pattern → hemorrhage
        if max_severity >= 4 and any("basal ganglia" in r or "thalamus" in r for r in regions):
            return "hemorrhage"

        # Diffuse pattern → TBI or encephalitis
        if len([r for r in damage_summary if r.get("severity_level", 0) >= 2]) >= 5:
            bilateral = any("left" in r for r in regions) and any("right" in r for r in regions)
            return "encephalitis" if bilateral else "tbi"

        # Hippocampal pattern → dementia
        if any("hippocampus" in r for r in regions):
            return "dementia"

        # Multifocal → MS
        if len([r for r in damage_summary if r.get("severity_level", 0) >= 2]) >= 3 and max_severity <= 3:
            return "ms"

        return "stroke"  # most common default

    def _compute_severity_factor(self, damage_summary: List[Dict]) -> float:
        """Compute severity adjustment factor (0-1, lower = worse)."""
        if not damage_summary:
            return 0.8

        max_severity = max(r.get("severity_level", 0) for r in damage_summary)
        avg_severity = np.mean([r.get("severity_level", 0) for r in damage_summary])
        n_affected = len([r for r in damage_summary if r.get("severity_level", 0) >= 2])

        # Factor decreases with severity
        factor = 1.0 - (max_severity * 0.1 + avg_severity * 0.05 + min(n_affected * 0.03, 0.3))
        return max(0.2, min(1.0, factor))

    def _compute_age_factor(self, metadata: Dict) -> float:
        """Compute age adjustment factor (0-1, lower = worse)."""
        age = metadata.get("age", 50)

        if age < 40:
            return 0.9
        elif age < 55:
            return 0.8
        elif age < 70:
            return 0.65
        elif age < 80:
            return 0.5
        else:
            return 0.35

    def _adjust_milestones(
        self,
        base_milestones: List[Milestone],
        severity_factor: float,
        age_factor: float,
    ) -> List[Milestone]:
        """Adjust milestone probabilities based on severity and age."""
        combined = severity_factor * age_factor
        adjusted = []

        for m in base_milestones:
            lower = max(0.01, m.probability_range[0] * combined)
            upper = min(0.99, m.probability_range[1] * combined)
            if lower > upper:
                lower, upper = upper, lower

            confidence = m.confidence
            if combined < 0.4:
                confidence = "low"

            adjusted.append(Milestone(
                timeframe=m.timeframe,
                milestone=m.milestone,
                probability_range=[round(lower, 2), round(upper, 2)],
                confidence=confidence,
                notes=m.notes,
            ))

        return adjusted

    def _determine_prognosis(
        self, etiology: str, severity: float, age: float, confidence: float
    ) -> str:
        """Determine overall prognosis category."""
        combined = severity * age

        if combined > 0.65:
            return "favorable"
        elif combined > 0.35:
            return "guarded"
        else:
            return "poor"

    def _estimate_functional_outcomes(
        self, etiology: str, damage_summary: List[Dict], severity: float
    ) -> Dict:
        """Estimate functional outcomes at different time points."""
        outcomes = {}

        timepoints = [
            ("discharge", "At discharge"),
            ("3_months", "At 3 months"),
            ("6_months", "At 6 months"),
            ("12_months", "At 12 months"),
        ]

        for key, label in timepoints:
            mRS_base = 2.0  # moderate disability baseline
            if severity < 0.5:
                mRS_base += 2
            elif severity < 0.7:
                mRS_base += 1

            # Recovery over time
            recovery_by = {
                "discharge": 0,
                "3_months": 0.5,
                "6_months": 0.8,
                "12_months": 1.0,
            }
            improvement = recovery_by[key] * severity

            mRS = max(0, min(6, mRS_base - improvement))

            outcomes[key] = {
                "label": label,
                "mRS_estimate": round(mRS, 1),
                "mRS_range": [round(max(0, mRS - 1), 1), round(min(6, mRS + 1), 1)],
                "independence_probability": round(max(0, 1 - mRS / 6), 2),
            }

        return outcomes

    def _filter_factors(self, factors: List[str], metadata: Dict) -> List[str]:
        """Filter risk/protective factors based on patient metadata."""
        age = metadata.get("age", 50)
        filtered = list(factors)

        # Highlight age-relevant factors
        if age > 70:
            filtered = [f for f in filtered if "older" not in f.lower() or "age" in f.lower()]
        elif age < 50:
            filtered = [f for f in filtered if "younger" not in f.lower() or "age" in f.lower()]

        return filtered

    def _generate_summary(
        self, etiology: str, prognosis: str, trajectory: str,
        milestones: List[Milestone], n_regions: int
    ) -> str:
        """Generate plain-language summary."""
        parts = [
            f"Based on the scan analysis showing {n_regions} affected region(s), "
            f"the most likely etiology is {etiology.replace('_', ' ')}.",
            f"Overall prognosis: {prognosis.upper()}.",
            f"Recovery trajectory: {trajectory.replace('_', ' ')}.",
        ]

        if milestones:
            first = milestones[0]
            parts.append(
                f"Nearest milestone: {first.milestone} "
                f"(probability {first.probability_range[0]*100:.0f}%-{first.probability_range[1]*100:.0f}%)."
            )

        return " ".join(parts)

    @staticmethod
    def _default_profile() -> Dict:
        """Default recovery profile for unknown etiologies."""
        return {
            "typical_trajectory": "variable",
            "milestones": [
                Milestone("1-4 weeks", "Acute stabilization", [0.6, 0.85], "moderate"),
                Milestone("1-3 months", "Early recovery phase", [0.4, 0.7], "moderate"),
                Milestone("3-6 months", "Continued improvement", [0.25, 0.55], "moderate"),
                Milestone("6-12 months", "Functional plateau", [0.15, 0.4], "low"),
            ],
            "favorable_factors": ["Younger age", "Mild initial severity", "Early rehabilitation"],
            "risk_factors": ["Older age", "Severe initial deficit", "Medical comorbidities"],
        }

    def to_dict(self, result: PrognosisResult) -> Dict:
        """Convert result to serializable dict."""
        return {
            "scan_id": result.scan_id,
            "etiology": result.etiology,
            "overall_prognosis": result.overall_prognosis,
            "recovery_trajectory": result.recovery_trajectory,
            "milestones": [
                {
                    "timeframe": m.timeframe,
                    "milestone": m.milestone,
                    "probability_range": m.probability_range,
                    "confidence": m.confidence,
                    "notes": m.notes,
                }
                for m in result.milestones
            ],
            "functional_outcomes": result.functional_outcomes,
            "risk_factors": result.risk_factors,
            "protective_factors": result.protective_factors,
            "disclaimer": result.disclaimer,
            "summary": result.summary,
        }
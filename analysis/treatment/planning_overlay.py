"""
Brain_Scape — Treatment Planning Overlay

Maps damage regions against eloquent cortex (speech, motor, vision)
and white matter tracts to highlight surgical no-go zones and
suggest intervention viability.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import logging
import re

logger = logging.getLogger(__name__)


# Eloquent cortex regions — damage here has disproportionate functional impact
ELOQUENT_CORTEX = {
    "broca_area": {
        "anatomical_name": "Left Inferior Frontal Gyrus (Broca's Area, BA44/45)",
        "function": "Speech production",
        "deficit_if_damaged": "Broca's aphasia (expressive aphasia) — can understand but cannot produce fluent speech",
        "surgical_risk": "CRITICAL — avoid at all costs",
        "laterality": "left_dominant",
        "ba_labels": ["BA44", "BA45"],
    },
    "wernicke_area": {
        "anatomical_name": "Left Superior Temporal Gyrus (Wernicke's Area, BA22)",
        "function": "Language comprehension",
        "deficit_if_damaged": "Wernicke's aphasia (receptive aphasia) — fluent but nonsensical speech",
        "surgical_risk": "CRITICAL — avoid at all costs",
        "laterality": "left_dominant",
        "ba_labels": ["BA22"],
    },
    "primary_motor_cortex": {
        "anatomical_name": "Precentral Gyrus (Motor Homunculus, BA4)",
        "function": "Voluntary motor control",
        "deficit_if_damaged": "Contralateral hemiparesis/hemiplegia",
        "surgical_risk": "CRITICAL — avoid",
        "laterality": "bilateral",
        "ba_labels": ["BA4"],
    },
    "primary_somatosensory": {
        "anatomical_name": "Postcentral Gyrus (Somatosensory, BA1-3)",
        "function": "Touch, proprioception, pain sensation",
        "deficit_if_damaged": "Contralateral sensory loss",
        "surgical_risk": "HIGH — avoid if possible",
        "laterality": "bilateral",
        "ba_labels": ["BA1", "BA2", "BA3"],
    },
    "primary_visual_cortex": {
        "anatomical_name": "Occipital Cortex (V1, BA17)",
        "function": "Visual processing",
        "deficit_if_damaged": "Contralateral homonymous hemianopia",
        "surgical_risk": "HIGH — avoid if possible",
        "laterality": "bilateral",
        "ba_labels": ["BA17"],
    },
    "hippocampus": {
        "anatomical_name": "Hippocampus (Bilateral)",
        "function": "Memory formation (episodic, spatial)",
        "deficit_if_damaged": "Anterograde amnesia (bilateral); partial memory loss (unilateral)",
        "surgical_risk": "HIGH — bilateral damage must be avoided",
        "laterality": "bilateral",
        "ba_labels": ["BA28", "BA34", "BA35", "BA36"],
    },
    "brainstem": {
        "anatomical_name": "Brainstem (Midbrain, Pons, Medulla)",
        "function": "Consciousness, breathing, cranial nerves, motor/sensory pathways",
        "deficit_if_damaged": "Locked-in syndrome, respiratory failure, cranial nerve palsies",
        "surgical_risk": "CRITICAL — extreme caution",
        "laterality": "bilateral",
        "ba_labels": [],
    },
    "optic_radiation": {
        "anatomical_name": "Optic Radiation (Meyer's Loop)",
        "function": "Visual field transmission from LGN to visual cortex",
        "deficit_if_damaged": "Contralateral homonymous quadrantanopia",
        "surgical_risk": "MODERATE — map preoperatively",
        "laterality": "bilateral",
        "ba_labels": [],
    },
    "arcuate_fasciculus": {
        "anatomical_name": "Arcuate Fasciculus",
        "function": "Language repetition (connecting Broca's and Wernicke's areas)",
        "deficit_if_damaged": "Conduction aphasia — can speak and understand but cannot repeat",
        "surgical_risk": "HIGH — especially in dominant hemisphere",
        "laterality": "left_dominant",
        "ba_labels": [],
    },
}

# Surgical no-go zone classification
SURGICAL_RISK_LEVELS = {
    "CRITICAL": {"color": "#FF0000", "description": "No surgical intervention — functional area with catastrophic deficit risk"},
    "HIGH": {"color": "#FF6600", "description": "Extreme caution — significant functional deficit likely if damaged"},
    "MODERATE": {"color": "#FFCC00", "description": "Map preoperatively — functional deficit possible but recoverable"},
    "LOW": {"color": "#00CC00", "description": "Relatively safe — minimal functional deficit risk"},
    "SAFE": {"color": "#0066FF", "description": "Non-eloquent area — surgical corridor acceptable"},
}


@dataclass
class EloquentRegionAssessment:
    """Assessment of damage proximity to an eloquent region."""
    eloquent_area: str
    anatomical_name: str
    function: str
    deficit_if_damaged: str
    surgical_risk: str
    damage_proximity: str  # "direct_hit", "adjacent", "nearby", "distant"
    distance_mm: Optional[float] = None
    affected: bool = False
    recommendation: str = ""


@dataclass
class TreatmentPlanningResult:
    """Complete treatment planning overlay result."""
    scan_id: str
    eloquent_assessments: List[EloquentRegionAssessment] = field(default_factory=list)
    no_go_zones: List[Dict] = field(default_factory=list)
    surgical_corridors: List[Dict] = field(default_factory=list)
    intervention_viability: Dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    summary: str = ""


class PlanningOverlay:
    """Map damage regions against eloquent cortex and white matter tracts.

    Identifies:
    - Surgical no-go zones (critical eloquent areas)
    - Safe surgical corridors (non-eloquent areas)
    - Intervention viability based on damage proximity to critical structures
    """

    def __init__(self):
        self.eloquent_cortex = ELOQUENT_CORTEX

    def analyze(
        self,
        damage_summary: List[Dict],
        scan_id: str = "unknown",
    ) -> TreatmentPlanningResult:
        """Analyze damage proximity to eloquent cortex and generate treatment planning overlay.

        Args:
            damage_summary: Region-level damage from damage_classifier
            scan_id: Scan identifier

        Returns:
            TreatmentPlanningResult with eloquent assessments, no-go zones, and corridors
        """
        damaged_names = {
            r["anatomical_name"].lower(): r for r in damage_summary
            if r.get("severity_level", 0) >= 2
        }

        assessments = []
        no_go_zones = []
        warnings = []
        affected_areas = []

        for area_id, area_info in self.eloquent_cortex.items():
            assessment = self._assess_eloquent_area(area_id, area_info, damaged_names)
            assessments.append(assessment)

            if assessment.affected:
                affected_areas.append(area_id)
                risk_tier = self._risk_tier(assessment.surgical_risk)
                if risk_tier in ["CRITICAL", "HIGH"]:
                    no_go_zones.append({
                        "area_id": area_id,
                        "name": area_info["anatomical_name"],
                        "risk_level": risk_tier,
                        "risk_color": SURGICAL_RISK_LEVELS.get(
                            risk_tier, {}
                        ).get("color", "#FF0000"),
                        "proximity": assessment.damage_proximity,
                        "deficit": area_info["deficit_if_damaged"],
                    })

                if risk_tier == "CRITICAL":
                    warnings.append(
                        f"CRITICAL: {area_info['anatomical_name']} is directly affected — "
                        f"surgical intervention carries catastrophic risk of {area_info['deficit_if_damaged'].lower()}"
                    )

        # Find safe surgical corridors (areas with no damage and not eloquent)
        corridors = self._find_surgical_corridors(damaged_names)

        # Determine intervention viability
        viability = self._assess_intervention_viability(
            assessments, no_go_zones, len(damaged_names)
        )

        # Build summary
        summary = self._generate_summary(assessments, no_go_zones, corridors, viability)

        return TreatmentPlanningResult(
            scan_id=scan_id,
            eloquent_assessments=assessments,
            no_go_zones=no_go_zones,
            surgical_corridors=corridors,
            intervention_viability=viability,
            warnings=warnings,
            summary=summary,
        )

    def _assess_eloquent_area(
        self,
        area_id: str,
        area_info: Dict,
        damaged_names: Dict,
    ) -> EloquentRegionAssessment:
        """Assess how close damage is to an eloquent area."""
        anatomical = area_info["anatomical_name"].lower()
        ba_labels = area_info.get("ba_labels", [])
        area_terms = {t for t in re.split(r"[^a-z]+", anatomical) if len(t) > 3}
        id_terms = {t for t in area_id.lower().split("_") if len(t) > 3}

        # Check direct hit
        direct_hit = False
        for damaged_name in damaged_names:
            damaged_terms = {t for t in re.split(r"[^a-z]+", damaged_name.lower()) if len(t) > 3}
            # Check if any damaged region name overlaps with this eloquent area
            if (anatomical in damaged_name or
                damaged_name in anatomical or
                self._partial_match(damaged_name, anatomical) or
                len(damaged_terms & area_terms) >= 2 or
                len(damaged_terms & id_terms) >= 2):
                direct_hit = True
                break

            # Check Brodmann area overlap
            for ba in ba_labels:
                if ba.lower() in damaged_name:
                    direct_hit = True
                    break
            if direct_hit:
                break

        # Determine proximity
        if direct_hit:
            proximity = "direct_hit"
            recommendation = f"Avoid surgical approach through {area_info['anatomical_name']}. {area_info['deficit_if_damaged']}."
        elif self._is_adjacent(area_id, damaged_names, area_info):
            proximity = "adjacent"
            recommendation = f"Caution: damage near {area_info['anatomical_name']}. Risk of {area_info['deficit_if_damaged'].lower()}."
        else:
            proximity = "distant"
            recommendation = f"{area_info['anatomical_name']} appears safe from current damage."

        return EloquentRegionAssessment(
            eloquent_area=area_id,
            anatomical_name=area_info["anatomical_name"],
            function=area_info["function"],
            deficit_if_damaged=area_info["deficit_if_damaged"],
            surgical_risk=area_info["surgical_risk"],
            damage_proximity=proximity,
            affected=direct_hit,
            recommendation=recommendation,
        )

    def _is_adjacent(self, area_id: str, damaged_names: Dict, area_info: Dict) -> bool:
        """Check if any damaged region is adjacent to an eloquent area."""
        anatomical = area_info["anatomical_name"].lower()

        # Adjacent region mapping (simplified)
        adjacent_regions = {
            "broca_area": ["left frontal", "left inferior frontal", "precentral"],
            "wernicke_area": ["left temporal", "left superior temporal", "angular"],
            "primary_motor_cortex": ["precentral", "frontal", "supplementary motor"],
            "primary_somatosensory": ["postcentral", "parietal"],
            "primary_visual_cortex": ["occipital", "calcarine"],
            "hippocampus": ["temporal", "medial temporal", "parahippocampal", "entorhinal"],
            "brainstem": ["cerebellum", "pons", "medulla", "midbrain"],
            "optic_radiation": ["temporal", "parietal", "occipital"],
            "arcuate_fasciculus": ["left frontal", "left temporal", "left parietal"],
        }

        area_adjacent = adjacent_regions.get(area_id, [])
        anatomical_terms = {t for t in re.split(r"[^a-z]+", anatomical) if len(t) > 4}

        for damaged_name in damaged_names:
            for adj in area_adjacent:
                if adj in damaged_name or damaged_name in adj:
                    return True
            if any(term in damaged_name for term in anatomical_terms):
                return True

        return False

    def _find_surgical_corridors(self, damaged_names: Dict) -> List[Dict]:
        """Identify safe surgical corridors — non-damaged, non-eloquent areas."""
        # Define potential surgical approach corridors
        corridors = [
            {
                "name": "Anterior Frontal (Non-dominant)",
                "approach": "Transfrontal approach via non-dominant frontal lobe",
                "eloquent_structures_at_risk": ["Prefrontal cortex (personality, executive function)"],
                "risk_level": "LOW",
                "description": "Safe corridor if non-dominant hemisphere and prefrontal cortex is spared",
            },
            {
                "name": "Posterior Temporal (Non-dominant)",
                "approach": "Transtemporal approach via non-dominant temporal lobe",
                "eloquent_structures_at_risk": ["Optic radiation", "Auditory cortex"],
                "risk_level": "MODERATE",
                "description": "Acceptable if optic radiation is mapped preoperatively",
            },
            {
                "name": "Superior Parietal (Non-dominant)",
                "approach": "Transparietal approach via non-dominant parietal lobe",
                "eloquent_structures_at_risk": ["Somatosensory cortex", "Superior longitudinal fasciculus"],
                "risk_level": "LOW to MODERATE",
                "description": "Relatively safe if avoiding somatosensory strip",
            },
            {
                "name": "Anterior Intertemporal",
                "approach": "Subtemporal approach via anterior temporal pole",
                "eloquent_structures_at_risk": ["Hippocampus", "Optic radiation (Meyer's loop)"],
                "risk_level": "MODERATE to HIGH",
                "description": "Requires careful hippocampal mapping; risk to visual fields",
            },
        ]

        # Filter corridors based on current damage
        safe_corridors = []
        for corridor in corridors:
            is_safe = True
            for damaged_name in damaged_names:
                if any(risk.lower() in damaged_name for risk in corridor["eloquent_structures_at_risk"]):
                    is_safe = False
                    break

            corridor["available"] = is_safe
            safe_corridors.append(corridor)

        return safe_corridors

    def _assess_intervention_viability(
        self,
        assessments: List[EloquentRegionAssessment],
        no_go_zones: List[Dict],
        n_damaged: int,
    ) -> Dict:
        """Overall assessment of surgical/treatment intervention viability."""
        critical_hits = sum(1 for a in assessments if a.affected and self._risk_tier(a.surgical_risk) == "CRITICAL")
        high_hits = sum(1 for a in assessments if a.affected and self._risk_tier(a.surgical_risk) == "HIGH")

        if critical_hits > 0:
            overall = "contraindicated"
            description = "Surgical intervention contraindicated — critical eloquent areas directly involved"
        elif high_hits >= 2:
            overall = "high_risk"
            description = "High surgical risk — multiple eloquent areas near damage zone"
        elif high_hits == 1:
            overall = "caution"
            description = "Moderate surgical risk — one eloquent area near damage; careful mapping required"
        elif n_damaged > 0:
            overall = "feasible"
            description = "Surgical intervention feasible — no critical eloquent areas directly involved"
        else:
            overall = "no_damage"
            description = "No significant damage detected — treatment planning not applicable"

        available_corridors = sum(1 for c in self._find_surgical_corridors({}) if c.get("available", True))

        return {
            "overall_viability": overall,
            "description": description,
            "critical_areas_affected": critical_hits,
            "high_risk_areas_affected": high_hits,
            "no_go_zones_count": len(no_go_zones),
            "available_corridors": available_corridors,
            "recommendations": self._generate_recommendations(critical_hits, high_hits, overall),
        }

    def _generate_recommendations(
        self, critical_hits: int, high_hits: int, viability: str
    ) -> List[str]:
        """Generate clinical recommendations based on assessment."""
        recs = []

        if viability == "contraindicated":
            recs.append("Conventional surgical resection is contraindicated")
            recs.append("Consider stereotactic biopsy if tissue diagnosis needed")
            recs.append("Consider radiosurgery (SRS) as alternative to open surgery")
            recs.append("Functional MRI (fMRI) and DTI tractography mapping strongly recommended")
        elif viability == "high_risk":
            recs.append("Preoperative functional mapping (fMRI, DTI) is essential")
            recs.append("Consider awake craniotomy with cortical stimulation mapping")
            recs.append("Neuro-navigation with tractography integration recommended")
            recs.append("Plan surgical approach to minimize eloquent cortex traversal")
        elif viability == "caution":
            recs.append("Preoperative functional mapping recommended")
            recs.append("Intraoperative neuro-monitoring advised")
            recs.append("Plan surgical corridor to avoid adjacent eloquent areas")
        elif viability == "feasible":
            recs.append("Standard surgical approach acceptable")
            recs.append("Routine preoperative imaging sufficient")
            recs.append("Consider DTI tractography for approach optimization")

        recs.append("All treatment decisions should be reviewed by a multidisciplinary team")

        return recs

    def _generate_summary(self, assessments, no_go_zones, corridors, viability) -> str:
        """Generate a plain-text summary of the treatment planning assessment."""
        parts = []
        parts.append(f"Intervention viability: {viability['overall_viability'].upper()}.")
        parts.append(viability['description'])

        if no_go_zones:
            zone_names = [z['name'] for z in no_go_zones[:3]]
            parts.append(f"No-go zones ({len(no_go_zones)}): {', '.join(zone_names)}")

        available = [c for c in corridors if c.get('available', True)]
        if available:
            parts.append(f"Available surgical corridors: {len(available)}")

        return " ".join(parts)

    @staticmethod
    def _partial_match(a: str, b: str) -> bool:
        a_words = set(a.lower().split())
        b_words = set(b.lower().split())
        overlap = a_words & b_words
        content_words = {w for w in overlap if len(w) > 3}
        return len(content_words) >= min(2, len(b_words))

    @staticmethod
    def _risk_tier(risk_text: str) -> str:
        """Normalize free-form risk text to canonical surgical risk tiers."""
        norm = (risk_text or "").upper()
        for tier in ["CRITICAL", "HIGH", "MODERATE", "LOW", "SAFE"]:
            if tier in norm:
                return tier
        return "LOW"

    def to_dict(self, result: TreatmentPlanningResult) -> Dict:
        """Convert result to serializable dict."""
        return {
            "scan_id": result.scan_id,
            "eloquent_assessments": [
                {
                    "eloquent_area": a.eloquent_area,
                    "anatomical_name": a.anatomical_name,
                    "function": a.function,
                    "deficit_if_damaged": a.deficit_if_damaged,
                    "surgical_risk": a.surgical_risk,
                    "damage_proximity": a.damage_proximity,
                    "affected": a.affected,
                    "recommendation": a.recommendation,
                }
                for a in result.eloquent_assessments
            ],
            "no_go_zones": result.no_go_zones,
            "surgical_corridors": result.surgical_corridors,
            "intervention_viability": result.intervention_viability,
            "warnings": result.warnings,
            "summary": result.summary,
        }
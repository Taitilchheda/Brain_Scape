"""
Brain_Scape — Differential Diagnosis Engine

CNN encoder (ResNet-50 backbone) + Transformer attention over atlas region features.
Multi-label classification over 8 etiologies with evidence-based ranking.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


# 8 supported etiologies
ETIOLOGIES = [
    "stroke",
    "hemorrhage",
    "tbi",             # traumatic brain injury
    "tumour",
    "ms",              # multiple sclerosis
    "dementia",
    "encephalitis",
    "hypoxic_injury",
]

ETIOLOGY_DESCRIPTIONS = {
    "stroke": "Ischemic or hemorrhagic cerebrovascular event",
    "hemorrhage": "Intracerebral or subarachnoid hemorrhage",
    "tbi": "Traumatic brain injury (contusion, diffuse axonal injury)",
    "tumour": "Neoplastic mass effect or infiltration",
    "ms": "Multiple sclerosis demyelination plaques",
    "dementia": "Neurodegenerative atrophy pattern (Alzheimer, FTD, etc.)",
    "encephalitis": "Infectious or autoimmune encephalitis",
    "hypoxic_injury": "Hypoxic-ischemic encephalopathy",
}

# Spatial feature patterns per etiology (which regions and severities are characteristic)
ETIOLOGY_SPATIAL_PATTERNS = {
    "stroke": {
        "typical_regions": [
            "Left Middle Cerebral Artery Territory",
            "Right Middle Cerebral Artery Territory",
            "Left Anterior Cerebral Artery Territory",
            "Right Anterior Cerebral Territory",
            "Left Posterior Cerebral Artery Territory",
            "Right Posterior Cerebral Artery Territory",
            "Basal Ganglia",
            "Thalamus",
            "Internal Capsule",
        ],
        "severity_bias": "ORANGE to RED in vascular territory",
        "shape": "wedge-shaped or territorial",
        "laterality": "often unilateral",
    },
    "hemorrhage": {
        "typical_regions": [
            "Basal Ganglia",
            "Thalamus",
            "Cerebellum",
            "Pons",
            "Lobar White Matter",
        ],
        "severity_bias": "RED core with ORANGE rim",
        "shape": "round or oval with surrounding edema",
        "laterality": "often unilateral",
    },
    "tbi": {
        "typical_regions": [
            "Frontal Lobe",
            "Temporal Lobe",
            "Corpus Callosum",
            "Dorsolateral Brainstem",
            "Gray-White Matter Junction",
        ],
        "severity_bias": "diffuse YELLOW to ORANGE with focal RED",
        "shape": "multifocal, coup-contrecoup",
        "laterality": "bilateral common",
    },
    "tumour": {
        "typical_regions": [
            "Frontal Lobe",
            "Temporal Lobe",
            "Parietal Lobe",
            "Cerebellum",
            "Brainstem",
        ],
        "severity_bias": "RED core with mass effect and ORANGE/YELLOW edema",
        "shape": "irregular mass with surrounding edema",
        "laterality": "unilateral mass, bilateral edema",
    },
    "ms": {
        "typical_regions": [
            "Periventricular White Matter",
            "Corpus Callosum",
            "Optic Radiation",
            "Corticospinal Tract",
            "Cerebellar Peduncles",
        ],
        "severity_bias": "YELLOW to ORANGE multifocal lesions",
        "shape": "ovoid, periventricular, Dawson finger pattern",
        "laterality": "bilateral, asymmetric",
    },
    "dementia": {
        "typical_regions": [
            "Hippocampus",
            "Entorhinal Cortex",
            "Posterior Cingulate",
            "Precuneus",
            "Frontal Cortex",
            "Temporal Cortex",
        ],
        "severity_bias": "YELLOW to ORANGE atrophy pattern",
        "shape": "bilateral symmetrical atrophy",
        "laterality": "bilateral, often symmetric",
    },
    "encephalitis": {
        "typical_regions": [
            "Temporal Lobe (Mesial)",
            "Frontal Lobe",
            "Insula",
            "Cingulate Gyrus",
            "Basal Ganglia",
        ],
        "severity_bias": "ORANGE to RED in affected lobes",
        "shape": "lobar or limbic predilection",
        "laterality": "bilateral, often temporal-predominant",
    },
    "hypoxic_injury": {
        "typical_regions": [
            "Hippocampus",
            "Basal Ganglia",
            "Thalamus",
            "Cerebral Cortex (watershed)",
            "Cerebellum (Purkinje layer)",
        ],
        "severity_bias": "RED in deep gray, ORANGE in watershed",
        "shape": "bilateral symmetric deep gray + watershed",
        "laterality": "bilateral symmetric",
    },
}


@dataclass
class DiagnosisCandidate:
    """A single etiology candidate with evidence."""
    etiology: str
    probability: float
    rank: int
    evidence: Dict = field(default_factory=dict)
    matching_regions: List[str] = field(default_factory=list)
    spatial_features: List[str] = field(default_factory=list)
    confidence: float = 0.0


class DifferentialDiagnoser:
    """Differential diagnosis engine.

    Uses CNN encoder (ResNet-50 backbone pretrained on BraTS) + Transformer
    attention over atlas region features to produce a ranked list of etiologies
    with per-etiology evidence summaries.

    In production, this uses trained neural network weights.
    In development, it uses a rule-based spatial pattern matching fallback.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.model = None
        self._load_model()

    def _load_model(self):
        """Load the CNN+Transformer model if available."""
        if self.model_path and Path(self.model_path).exists():
            try:
                import torch
                self.model = torch.load(self.model_path, map_location="cpu")
                self.model.eval()
                logger.info(f"Loaded differential diagnosis model from {self.model_path}")
            except Exception as e:
                logger.warning(f"Could not load model: {e}. Using rule-based fallback.")
                self.model = None
        else:
            logger.info("No trained model found. Using rule-based spatial pattern matching.")

    def diagnose(
        self,
        damage_summary: List[Dict],
        scan_metadata: Optional[Dict] = None,
        top_k: int = 5,
    ) -> List[DiagnosisCandidate]:
        """Generate a ranked differential diagnosis.

        Args:
            damage_summary: List of region damage dicts from damage_classifier.
                Each must have: anatomical_name, severity_level, severity_label,
                confidence, volume_mm3, volume_pct_of_region
            scan_metadata: Optional scan metadata (modality, age, etc.)
            top_k: Number of top diagnoses to return

        Returns:
            Ranked list of DiagnosisCandidate objects
        """
        if self.model is not None:
            return self._diagnose_with_model(damage_summary, scan_metadata, top_k)
        else:
            return self._diagnose_rule_based(damage_summary, scan_metadata, top_k)

    def _diagnose_with_model(
        self,
        damage_summary: List[Dict],
        scan_metadata: Optional[Dict],
        top_k: int,
    ) -> List[DiagnosisCandidate]:
        """Run diagnosis with the CNN+Transformer model."""
        import torch

        # Prepare input features from damage summary
        region_features = self._encode_region_features(damage_summary)

        with torch.no_grad():
            input_tensor = torch.tensor(region_features, dtype=torch.float32).unsqueeze(0)
            output = self.model(input_tensor)
            probabilities = torch.softmax(output, dim=-1).squeeze(0).numpy()

        candidates = []
        for i, etiology in enumerate(ETIOLOGIES):
            prob = float(probabilities[i])
            if prob > 0.01:
                evidence = self._extract_evidence(etiology, damage_summary)
                candidates.append(DiagnosisCandidate(
                    etiology=etiology,
                    probability=prob,
                    rank=0,
                    evidence=evidence,
                    matching_regions=evidence.get("matching_regions", []),
                    spatial_features=evidence.get("spatial_features", []),
                    confidence=min(prob * 2, 1.0),
                ))

        # Sort by probability and assign ranks
        candidates.sort(key=lambda c: c.probability, reverse=True)
        for i, c in enumerate(candidates[:top_k]):
            c.rank = i + 1

        return candidates[:top_k]

    def _diagnose_rule_based(
        self,
        damage_summary: List[Dict],
        scan_metadata: Optional[Dict],
        top_k: int,
    ) -> List[DiagnosisCandidate]:
        """Rule-based fallback using spatial pattern matching.

        Scores each etiology by:
        1. Region overlap: how many damaged regions match typical regions for that etiology
        2. Severity match: whether the severity pattern matches the expected pattern
        3. Laterality match: whether bilateral/unilateral matches expectations
        4. Shape/feature bonuses from scan metadata
        """
        if not damage_summary:
            return []

        damaged_names = [r["anatomical_name"].lower() for r in damage_summary
                         if r.get("severity_level", 0) >= 2]
        high_severity_names = [r["anatomical_name"].lower() for r in damage_summary
                               if r.get("severity_level", 0) >= 3]
        bilateral = self._check_bilaterality(damage_summary)
        has_mass_effect = self._check_mass_effect(damage_summary)
        has_edema_pattern = self._check_edema_pattern(damage_summary)

        candidates = []

        for etiology in ETIOLOGIES:
            pattern = ETIOLOGY_SPATIAL_PATTERNS[etiology]
            score = 0.0
            matching_regions = []
            spatial_features = []

            # Score 1: Region overlap (0-40 points)
            typical_lower = [r.lower() for r in pattern["typical_regions"]]
            for name in damaged_names:
                for typical in typical_lower:
                    if typical in name or name in typical or self._partial_match(name, typical):
                        score += 40.0 / max(len(typical_lower), 1)
                        matching_regions.append(name.title())
                        break

            # Score 2: Severity match (0-25 points)
            severity_bias = pattern["severity_bias"].lower()
            if "red" in severity_bias and high_severity_names:
                score += 15
            if "orange" in severity_bias and damaged_names:
                score += 10
            if "yellow" in severity_bias and damaged_names:
                score += 5
            if "diffuse" in severity_bias and len(damaged_names) >= 3:
                score += 10
            if "atrophy" in severity_bias and len(damaged_names) >= 2:
                score += 8

            # Score 3: Laterality match (0-15 points)
            laterality = pattern["laterality"].lower()
            if "bilateral" in laterality and bilateral:
                score += 15
            elif "bilateral" in laterality and not bilateral:
                score += 5  # Still possible, just less typical
            elif "unilateral" in laterality and not bilateral:
                score += 15
            elif "unilateral" in laterality and bilateral:
                score += 5

            # Score 4: Shape/feature bonuses (0-20 points)
            shape = pattern["shape"].lower()
            if has_mass_effect and ("mass" in shape or "irregular" in shape):
                score += 10
                spatial_features.append("mass effect detected")
            if has_edema_pattern and ("edema" in severity_bias or "edema" in shape):
                score += 10
                spatial_features.append("edema pattern detected")
            if "watershed" in shape and "watershed" in severity_bias:
                spatial_features.append("watershed distribution pattern")

            # Normalize score to probability
            probability = min(score / 100.0, 0.95)

            # Extract evidence
            evidence = {
                "matching_regions": matching_regions,
                "spatial_features": spatial_features,
                "region_overlap_pct": len(matching_regions) / max(len(pattern["typical_regions"]), 1) * 100,
                "typical_regions": pattern["typical_regions"],
                "severity_bias": pattern["severity_bias"],
                "laterality_expected": pattern["laterality"],
                "shape_expected": pattern["shape"],
                "description": ETIOLOGY_DESCRIPTIONS[etiology],
            }

            if probability > 0.05:
                candidates.append(DiagnosisCandidate(
                    etiology=etiology,
                    probability=probability,
                    rank=0,
                    evidence=evidence,
                    matching_regions=matching_regions,
                    spatial_features=spatial_features,
                    confidence=probability * 0.7,  # Rule-based confidence is lower
                ))

        # Sort and assign ranks
        candidates.sort(key=lambda c: c.probability, reverse=True)
        # Renormalize probabilities to sum to ~1.0
        total = sum(c.probability for c in candidates)
        if total > 0:
            for c in candidates:
                c.probability = c.probability / total

        for i, c in enumerate(candidates[:top_k]):
            c.rank = i + 1

        return candidates[:top_k]

    def _encode_region_features(self, damage_summary: List[Dict]) -> np.ndarray:
        """Encode damage summary into feature vector for the neural model."""
        # Feature vector: 8 etiologies x (severity, volume_pct, confidence) per region
        n_features = len(damage_summary) * 3 if damage_summary else 3
        features = np.zeros(max(n_features, 24), dtype=np.float32)

        for i, region in enumerate(damage_summary[:8]):
            offset = i * 3
            features[offset] = region.get("severity_level", 0) / 4.0
            features[offset + 1] = min(region.get("volume_pct_of_region", 0) / 100.0, 1.0)
            features[offset + 2] = region.get("confidence", 0)

        return features

    def _extract_evidence(
        self,
        etiology: str,
        damage_summary: List[Dict],
    ) -> Dict:
        """Extract evidence for a specific etiology from damage summary."""
        pattern = ETIOLOGY_SPATIAL_PATTERNS.get(etiology, {})
        typical_lower = [r.lower() for r in pattern.get("typical_regions", [])]

        matching = []
        for region in damage_summary:
            name = region.get("anatomical_name", "").lower()
            for typical in typical_lower:
                if typical in name or name in typical or self._partial_match(name, typical):
                    matching.append({
                        "region": region.get("anatomical_name"),
                        "severity": region.get("severity_label"),
                        "confidence": region.get("confidence", 0),
                        "volume_pct": region.get("volume_pct_of_region", 0),
                    })
                    break

        return {
            "matching_regions": [m["region"] for m in matching],
            "matching_details": matching,
            "region_overlap_pct": len(matching) / max(len(typical_lower), 1) * 100,
            "description": ETIOLOGY_DESCRIPTIONS.get(etiology, ""),
        }

    @staticmethod
    def _partial_match(a: str, b: str) -> bool:
        """Check if key words from b appear in a."""
        a_words = set(a.lower().split())
        b_words = set(b.lower().split())
        overlap = a_words & b_words
        # Require at least 2 content words to match, or 1 if b is short
        content_words = {w for w in overlap if len(w) > 3}
        return len(content_words) >= min(2, len(b_words))

    @staticmethod
    def _check_bilaterality(damage_summary: List[Dict]) -> bool:
        """Check if damage is bilateral (affects both left and right hemispheres)."""
        left = any("left" in r.get("anatomical_name", "").lower() for r in damage_summary
                   if r.get("severity_level", 0) >= 2)
        right = any("right" in r.get("anatomical_name", "").lower() for r in damage_summary
                    if r.get("severity_level", 0) >= 2)
        return left and right

    @staticmethod
    def _check_mass_effect(damage_summary: List[Dict]) -> bool:
        """Heuristic: mass effect if one region has very high volume_pct and midline structures are affected."""
        has_high_volume = any(r.get("volume_pct_of_region", 0) > 40 for r in damage_summary)
        has_midline = any("corpus callosum" in r.get("anatomical_name", "").lower()
                          or "ventricle" in r.get("anatomical_name", "").lower()
                          for r in damage_summary)
        return has_high_volume and has_midline

    @staticmethod
    def _check_edema_pattern(damage_summary: List[Dict]) -> bool:
        """Heuristic: edema pattern if there's a RED core surrounded by ORANGE/YELLOW."""
        has_red = any(r.get("severity_level", 0) == 4 for r in damage_summary)
        has_surrounding = any(r.get("severity_level", 0) in [2, 3] for r in damage_summary)
        return has_red and has_surrounding

    def to_dict(self, candidates: List[DiagnosisCandidate]) -> List[Dict]:
        """Convert diagnosis candidates to serializable dicts."""
        return [
            {
                "rank": c.rank,
                "etiology": c.etiology,
                "probability": round(c.probability, 4),
                "confidence": round(c.confidence, 4),
                "description": ETIOLOGY_DESCRIPTIONS.get(c.etiology, ""),
                "matching_regions": c.matching_regions,
                "spatial_features": c.spatial_features,
                "evidence": c.evidence,
            }
            for c in candidates
        ]
"""
Brain_Scape — Multimodal Fusion Engine

Weighted late fusion of EEG + fMRI + DTI maps into a single,
more accurate damage map than any individual modality.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class ModalityResult:
    """Damage result from a single modality."""
    modality: str                    # "MRI_T1", "fMRI", "EEG", "DTI"
    damage_map: Optional[np.ndarray] = None
    region_scores: List[Dict] = field(default_factory=list)
    confidence: float = 0.0
    weight: float = 1.0
    metadata: Dict = field(default_factory=dict)


@dataclass
class FusionResult:
    """Combined multimodal damage assessment."""
    fused_damage_map: Optional[np.ndarray] = None
    region_scores: List[Dict] = field(default_factory=list)
    overall_confidence: float = 0.0
    modality_contributions: Dict[str, float] = field(default_factory=dict)
    modality_weights_used: Dict[str, float] = field(default_factory=dict)
    fusion_method: str = "weighted_late"


# Default weights per modality (spatial resolution priority)
DEFAULT_MODALITY_WEIGHTS = {
    "MRI_T1": 0.40,   # Structural: highest spatial resolution
    "fMRI": 0.25,     # Functional: good spatial, temporal context
    "DTI": 0.20,      # Structural connectivity: white matter integrity
    "EEG": 0.15,      # Functional: highest temporal resolution, lowest spatial
}


class MultimodalFuser:
    """Fuse damage assessments from multiple modalities.

    Uses weighted late fusion: each modality produces its own damage map
    and region scores, then these are combined with modality-specific weights.

    Fusion strategies:
    1. Weighted average (default): each voxel/region weighted by modality confidence
    2. Maximum: take the maximum severity across modalities (conservative)
    3. Bayesian: combine using Bayesian updating with modality priors
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        fusion_method: str = "weighted_late",
    ):
        self.weights = weights or DEFAULT_MODALITY_WEIGHTS.copy()
        self.fusion_method = fusion_method

    def fuse(
        self,
        modality_results: List[ModalityResult],
        voxel_spacing: Optional[Tuple[float, ...]] = None,
    ) -> FusionResult:
        """Fuse multiple modality results into a single assessment.

        Args:
            modality_results: List of ModalityResult objects, one per modality
            voxel_spacing: Physical spacing of voxels (for volume calculations)

        Returns:
            FusionResult with combined damage map, region scores, and confidence
        """
        if not modality_results:
            return FusionResult()

        # Normalize weights for available modalities
        available = {r.modality: r for r in modality_results}
        active_weights = {}
        for mod, w in self.weights.items():
            if mod in available:
                active_weights[mod] = w

        # Re-normalize weights to sum to 1
        total_w = sum(active_weights.values())
        if total_w > 0:
            active_weights = {k: v / total_w for k, v in active_weights.items()}
        else:
            # Equal weights fallback
            n = len(modality_results)
            active_weights = {r.modality: 1.0 / n for r in modality_results}

        # Fuse damage maps (voxel-level)
        fused_map = None
        if self.fusion_method == "weighted_late":
            fused_map = self._fuse_weighted_average(
                modality_results, active_weights
            )
        elif self.fusion_method == "maximum":
            fused_map = self._fuse_maximum(modality_results)
        elif self.fusion_method == "bayesian":
            fused_map = self._fuse_bayesian(
                modality_results, active_weights
            )
        else:
            fused_map = self._fuse_weighted_average(
                modality_results, active_weights
            )

        # Fuse region scores (atlas-level)
        fused_regions = self._fuse_region_scores(
            modality_results, active_weights
        )

        # Compute overall confidence
        total_conf = 0.0
        for r in modality_results:
            w = active_weights.get(r.modality, 0)
            total_conf += r.confidence * w

        # Compute per-modality contribution
        contributions = {}
        for r in modality_results:
            mod = r.modality
            w = active_weights.get(mod, 0)
            contributions[mod] = round(w * r.confidence, 4)

        return FusionResult(
            fused_damage_map=fused_map,
            region_scores=fused_regions,
            overall_confidence=round(total_conf, 4),
            modality_contributions=contributions,
            modality_weights_used=active_weights,
            fusion_method=self.fusion_method,
        )

    def _fuse_weighted_average(
        self,
        results: List[ModalityResult],
        weights: Dict[str, float],
    ) -> Optional[np.ndarray]:
        """Weighted average fusion of voxel-level damage maps."""
        maps = []
        ws = []
        for r in results:
            if r.damage_map is not None:
                maps.append(r.damage_map.astype(np.float64))
                ws.append(weights.get(r.modality, 0))

        if not maps:
            return None

        # Align shapes to smallest common shape
        target_shape = self._common_shape(maps)
        if target_shape is None:
            return None

        fused = np.zeros(target_shape, dtype=np.float64)
        total_w = sum(ws)

        for m, w in zip(maps, ws):
            resized = self._resize_to_shape(m, target_shape)
            fused += resized * (w / total_w)

        return fused

    def _fuse_maximum(
        self,
        results: List[ModalityResult],
    ) -> Optional[np.ndarray]:
        """Maximum fusion: take maximum severity at each voxel."""
        maps = [r.damage_map for r in results if r.damage_map is not None]
        if not maps:
            return None

        target_shape = self._common_shape(maps)
        if target_shape is None:
            return None

        aligned = [self._resize_to_shape(m, target_shape) for m in maps]
        return np.maximum.reduce(aligned)

    def _fuse_bayesian(
        self,
        results: List[ModalityResult],
        weights: Dict[str, float],
    ) -> Optional[np.ndarray]:
        """Bayesian fusion: combine probabilities using Bayesian updating."""
        maps = []
        ws = []
        for r in results:
            if r.damage_map is not None:
                maps.append(r.damage_map.astype(np.float64))
                ws.append(weights.get(r.modality, 0))

        if not maps:
            return None

        target_shape = self._common_shape(maps)
        if target_shape is None:
            return None

        # Start with uniform prior (0.5 probability of damage)
        prior = np.full(target_shape, 0.5, dtype=np.float64)
        posterior = prior.copy()

        for m, w in zip(maps, ws):
            resized = self._resize_to_shape(m, target_shape)
            # Clip to avoid log(0)
            likelihood_pos = np.clip(resized, 0.01, 0.99)
            likelihood_neg = np.clip(1 - resized, 0.01, 0.99)

            # Bayesian update: P(damage | modality) ∝ P(modality | damage) * P(damage)
            posterior = (likelihood_pos * posterior) / (
                likelihood_pos * posterior + likelihood_neg * (1 - posterior) + 1e-10
            )

        return posterior

    def _fuse_region_scores(
        self,
        results: List[ModalityResult],
        weights: Dict[str, float],
    ) -> List[Dict]:
        """Fuse per-region scores from multiple modalities."""
        # Index all regions across modalities
        all_regions: Dict[str, List[Dict]] = {}
        for r in results:
            w = weights.get(r.modality, 0)
            for region in r.region_scores:
                name = region.get("anatomical_name", "")
                if name not in all_regions:
                    all_regions[name] = []
                all_regions[name].append({
                    "modality": r.modality,
                    "weight": w,
                    "confidence": r.confidence,
                    **region,
                })

        fused_regions = []
        for name, entries in all_regions.items():
            # Weighted average severity
            total_w = 0
            weighted_severity = 0
            weighted_volume_pct = 0
            weighted_confidence = 0
            modalities_present = []

            for e in entries:
                mod_weight = e["weight"] * e.get("confidence", 0.5)
                weighted_severity += e.get("severity_level", 0) * mod_weight
                weighted_volume_pct += e.get("volume_pct_of_region", 0) * mod_weight
                weighted_confidence += e.get("confidence", 0) * e["weight"]
                total_w += mod_weight
                modalities_present.append(e["modality"])

            if total_w > 0:
                weighted_severity /= total_w
                weighted_volume_pct /= total_w
                weighted_confidence /= sum(weights.get(m, 0) for m in modalities_present
                                            if m in weights) or 1

            # Determine severity label from average
            severity_label = self._severity_from_level(weighted_severity)

            fused_regions.append({
                "anatomical_name": name,
                "severity_level": round(weighted_severity, 2),
                "severity_label": severity_label,
                "volume_pct_of_region": round(weighted_volume_pct, 2),
                "confidence": round(weighted_confidence, 4),
                "modalities": list(set(modalities_present)),
                "fusion_method": self.fusion_method,
            })

        # Sort by severity
        fused_regions.sort(key=lambda r: r["severity_level"], reverse=True)
        return fused_regions

    @staticmethod
    def _severity_from_level(level: float) -> str:
        """Convert numeric severity level to label."""
        if level >= 3.5:
            return "RED"
        elif level >= 2.5:
            return "ORANGE"
        elif level >= 1.5:
            return "YELLOW"
        elif level >= 0.5:
            return "GREEN"
        else:
            return "BLUE"

    @staticmethod
    def _common_shape(arrays: List[np.ndarray]) -> Optional[Tuple]:
        """Find the smallest common shape for alignment."""
        if not arrays:
            return None
        # Use the minimum dimension along each axis
        shapes = [a.shape for a in arrays]
        ndim = len(shapes[0])
        return tuple(min(s[i] for s in shapes) for i in range(ndim))

    @staticmethod
    def _resize_to_shape(arr: np.ndarray, target_shape: Tuple) -> np.ndarray:
        """Crop or pad array to target shape."""
        if arr.shape == target_shape:
            return arr

        result = np.zeros(target_shape, dtype=arr.dtype)
        slices_src = []
        slices_dst = []
        for i in range(len(target_shape)):
            if arr.shape[i] <= target_shape[i]:
                slices_src.append(slice(None))
                offset = (target_shape[i] - arr.shape[i]) // 2
                slices_dst.append(slice(offset, offset + arr.shape[i]))
            else:
                offset = (arr.shape[i] - target_shape[i]) // 2
                slices_src.append(slice(offset, offset + target_shape[i]))
                slices_dst.append(slice(None))

        result[tuple(slices_dst)] = arr[tuple(slices_src)]
        return result

    def to_dict(self, result: FusionResult) -> Dict:
        """Convert fusion result to serializable dict."""
        return {
            "overall_confidence": result.overall_confidence,
            "fusion_method": result.fusion_method,
            "modality_contributions": result.modality_contributions,
            "modality_weights_used": result.modality_weights_used,
            "region_scores": result.region_scores,
            "region_count": len(result.region_scores),
        }
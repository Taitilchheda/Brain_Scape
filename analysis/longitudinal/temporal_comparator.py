"""
Brain_Scape — Longitudinal Temporal Comparator

Compare multiple scans of the same patient over time.
Produces delta maps, atrophy rates, treatment response tracking.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class RegionDelta:
    """Change in a single atlas region between two timepoints."""
    anatomical_name: str
    severity_delta: float            # Change in severity level (-4 to +4)
    severity_label_before: str
    severity_label_after: str
    volume_mm3_before: float
    volume_mm3_after: float
    volume_delta_mm3: float          # Positive = expanded damage
    volume_pct_before: float
    volume_pct_after: float
    volume_delta_pct: float          # Positive = worsening
    change_direction: str            # "worsened", "improved", "stable"
    atrophy_rate_mm3_per_month: Optional[float] = None
    atrophy_rate_pct_per_month: Optional[float] = None


@dataclass
class LongitudinalResult:
    """Complete longitudinal comparison result."""
    patient_id: str
    timepoints: List[Dict]           # [{scan_id, date, analysis_path}, ...]
    region_deltas: List[RegionDelta]
    overall_trend: str               # "worsening", "improving", "stable", "mixed"
    atrophy_rate_global: Optional[float] = None
    total_damage_volume_before: float = 0.0
    total_damage_volume_after: float = 0.0
    new_regions_affected: List[str] = field(default_factory=list)
    resolved_regions: List[str] = field(default_factory=list)
    summary: str = ""


class TemporalComparator:
    """Compare brain scans across timepoints.

    For each atlas region, computes the change in severity and volume
    between consecutive scans. Produces delta maps for visualization.
    """

    SEVERITY_LEVELS = {
        "BLUE": 0, "GREEN": 1, "YELLOW": 2, "ORANGE": 3, "RED": 4,
    }

    def __init__(self):
        self.results_cache: Dict[str, LongitudinalResult] = {}

    def compare(
        self,
        analysis_before: Dict,
        analysis_after: Dict,
        patient_id: str,
        months_between: Optional[float] = None,
    ) -> LongitudinalResult:
        """Compare two analysis results from different timepoints.

        Args:
            analysis_before: Analysis JSON from earlier scan
            analysis_after: Analysis JSON from later scan
            patient_id: Patient identifier
            months_between: Number of months between scans (for rate calculation)

        Returns:
            LongitudinalResult with per-region deltas and overall trend
        """
        regions_before = self._index_by_region(analysis_before.get("damage_summary", []))
        regions_after = self._index_by_region(analysis_after.get("damage_summary", []))

        all_region_names = set(regions_before.keys()) | set(regions_after.keys())

        deltas = []
        worsening_count = 0
        improving_count = 0
        stable_count = 0

        new_regions = []
        resolved_regions = []

        total_vol_before = 0.0
        total_vol_after = 0.0

        for name in all_region_names:
            before = regions_before.get(name)
            after = regions_after.get(name)

            sev_before = self.SEVERITY_LEVELS.get(
                before.get("severity_label", "GREEN") if before else "GREEN", 1
            )
            sev_after = self.SEVERITY_LEVELS.get(
                after.get("severity_label", "GREEN") if after else "GREEN", 1
            )

            label_before = before.get("severity_label", "GREEN") if before else "GREEN"
            label_after = after.get("severity_label", "GREEN") if after else "GREEN"

            vol_before = before.get("volume_mm3", 0) if before else 0
            vol_after = after.get("volume_mm3", 0) if after else 0
            pct_before = before.get("volume_pct_of_region", 0) if before else 0
            pct_after = after.get("volume_pct_of_region", 0) if after else 0

            total_vol_before += vol_before
            total_vol_after += vol_after

            severity_delta = sev_after - sev_before
            volume_delta = vol_after - vol_before
            pct_delta = pct_after - pct_before

            # Determine change direction
            if severity_delta > 0 or volume_delta > 50:
                direction = "worsened"
                worsening_count += 1
            elif severity_delta < 0 or volume_delta < -50:
                direction = "improved"
                improving_count += 1
            else:
                direction = "stable"
                stable_count += 1

            # Track new and resolved regions
            if before is None and after is not None and sev_after >= 2:
                new_regions.append(name)
            elif before is not None and after is None:
                resolved_regions.append(name)

            # Calculate atrophy rate if time interval is known
            atrophy_rate_mm3 = None
            atrophy_rate_pct = None
            if months_between and months_between > 0:
                atrophy_rate_mm3 = volume_delta / months_between
                atrophy_rate_pct = pct_delta / months_between

            deltas.append(RegionDelta(
                anatomical_name=name,
                severity_delta=severity_delta,
                severity_label_before=label_before,
                severity_label_after=label_after,
                volume_mm3_before=vol_before,
                volume_mm3_after=vol_after,
                volume_delta_mm3=volume_delta,
                volume_pct_before=pct_before,
                volume_pct_after=pct_after,
                volume_delta_pct=pct_delta,
                change_direction=direction,
                atrophy_rate_mm3_per_month=atrophy_rate_mm3,
                atrophy_rate_pct_per_month=atrophy_rate_pct,
            ))

        # Determine overall trend
        if worsening_count > improving_count * 2:
            trend = "worsening"
        elif improving_count > worsening_count * 2:
            trend = "improving"
        elif worsening_count == 0 and improving_count == 0:
            trend = "stable"
        else:
            trend = "mixed"

        # Global atrophy rate
        global_atrophy = None
        if months_between and months_between > 0:
            global_atrophy = (total_vol_after - total_vol_before) / months_between

        # Build summary
        summary = self._generate_summary(
            deltas, trend, new_regions, resolved_regions,
            total_vol_before, total_vol_after, months_between,
        )

        result = LongitudinalResult(
            patient_id=patient_id,
            timepoints=[
                analysis_before.get("scan_metadata", {}),
                analysis_after.get("scan_metadata", {}),
            ],
            region_deltas=deltas,
            overall_trend=trend,
            atrophy_rate_global=global_atrophy,
            total_damage_volume_before=total_vol_before,
            total_damage_volume_after=total_vol_after,
            new_regions_affected=new_regions,
            resolved_regions=resolved_regions,
            summary=summary,
        )

        self.results_cache[patient_id] = result
        return result

    def compare_multiple(
        self,
        analyses: List[Dict],
        patient_id: str,
        dates: Optional[List[str]] = None,
    ) -> List[LongitudinalResult]:
        """Compare multiple timepoints sequentially.

        Produces pairwise comparisons between consecutive scans.
        """
        if len(analyses) < 2:
            raise ValueError("Need at least 2 analyses for longitudinal comparison")

        results = []
        for i in range(len(analyses) - 1):
            months = None
            if dates and i + 1 < len(dates):
                from datetime import datetime
                try:
                    d1 = datetime.fromisoformat(dates[i])
                    d2 = datetime.fromisoformat(dates[i + 1])
                    months = (d2 - d1).days / 30.44
                except (ValueError, TypeError):
                    pass

            result = self.compare(
                analyses[i], analyses[i + 1], patient_id, months
            )
            results.append(result)

        return results

    def generate_delta_map(
        self,
        result: LongitudinalResult,
        output_path: Optional[str] = None,
    ) -> Dict:
        """Generate a delta map for visualization.

        Returns per-region color-coded changes for the 3D viewer.
        """
        delta_map = {
            "patient_id": result.patient_id,
            "trend": result.overall_trend,
            "regions": [],
        }

        # Color coding for changes
        change_colors = {
            "worsened": "#E74C3C",     # Red
            "improved": "#27AE60",     # Green
            "stable": "#4A90D9",       # Blue
        }

        for delta in result.region_deltas:
            delta_map["regions"].append({
                "anatomical_name": delta.anatomical_name,
                "change_direction": delta.change_direction,
                "color": change_colors.get(delta.change_direction, "#4A90D9"),
                "severity_delta": delta.severity_delta,
                "volume_delta_mm3": delta.volume_delta_mm3,
                "volume_delta_pct": round(delta.volume_delta_pct, 2),
                "severity_before": delta.severity_label_before,
                "severity_after": delta.severity_label_after,
                "atrophy_rate_pct_per_month": delta.atrophy_rate_pct_per_month,
            })

        if output_path:
            with open(output_path, "w") as f:
                json.dump(delta_map, f, indent=2)

        return delta_map

    def _index_by_region(self, damage_summary: List[Dict]) -> Dict[str, Dict]:
        """Index damage summary by anatomical name."""
        return {r["anatomical_name"]: r for r in damage_summary if "anatomical_name" in r}

    def _generate_summary(
        self,
        deltas: List[RegionDelta],
        trend: str,
        new_regions: List[str],
        resolved: List[str],
        vol_before: float,
        vol_after: float,
        months: Optional[float],
    ) -> str:
        """Generate a plain-text summary of the longitudinal comparison."""
        worsening = [d for d in deltas if d.change_direction == "worsened"]
        improving = [d for d in deltas if d.change_direction == "improved"]

        parts = [f"Overall trend: {trend.upper()}."]

        if worsening:
            parts.append(f"Worsened regions ({len(worsening)}): " +
                         ", ".join(d.anatomical_name for d in worsening[:5]))

        if improving:
            parts.append(f"Improved regions ({len(improving)}): " +
                         ", ".join(d.anatomical_name for d in improving[:5]))

        if new_regions:
            parts.append(f"Newly affected regions: {', '.join(new_regions[:5])}")

        if resolved:
            parts.append(f"Resolved regions: {', '.join(resolved[:5])}")

        vol_change = vol_after - vol_before
        direction = "increase" if vol_change > 0 else "decrease"
        parts.append(f"Total damage volume: {vol_before:.0f} -> {vol_after:.0f} mm3 "
                      f"({abs(vol_change):.0f} mm3 {direction})")

        if months:
            rate = vol_change / months
            parts.append(f"Rate of change: {rate:.1f} mm3/month")

        return " ".join(parts)

    def to_dict(self, result: LongitudinalResult) -> Dict:
        """Convert result to serializable dict."""
        return {
            "patient_id": result.patient_id,
            "overall_trend": result.overall_trend,
            "total_damage_volume_before": result.total_damage_volume_before,
            "total_damage_volume_after": result.total_damage_volume_after,
            "atrophy_rate_global": result.atrophy_rate_global,
            "new_regions_affected": result.new_regions_affected,
            "resolved_regions": result.resolved_regions,
            "summary": result.summary,
            "region_deltas": [
                {
                    "anatomical_name": d.anatomical_name,
                    "severity_delta": d.severity_delta,
                    "severity_before": d.severity_label_before,
                    "severity_after": d.severity_label_after,
                    "volume_delta_mm3": d.volume_delta_mm3,
                    "volume_delta_pct": round(d.volume_delta_pct, 2),
                    "change_direction": d.change_direction,
                    "atrophy_rate_pct_per_month": d.atrophy_rate_pct_per_month,
                }
                for d in result.region_deltas
            ],
        }
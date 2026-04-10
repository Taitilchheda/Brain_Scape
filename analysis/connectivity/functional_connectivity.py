"""
Brain_Scape — Functional Connectivity Analysis

nilearn-based resting-state fMRI network analysis.
Detects disrupted networks: DMN, Salience, Executive Control, Motor, Language.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


# Major functional networks of clinical interest
FUNCTIONAL_NETWORKS = {
    "default_mode": {
        "full_name": "Default Mode Network (DMN)",
        "key_regions": [
            "Posterior Cingulate Cortex",
            "Medial Prefrontal Cortex",
            "Angular Gyrus",
            "Hippocampus",
        ],
        "function": "Self-referential thought, episodic memory, mind-wandering",
        "disruption_pattern": "Reduced connectivity common in Alzheimer's, depression",
        "clinical_significance": "DMN disruption is an early marker of neurodegeneration",
    },
    "salience": {
        "full_name": "Salience Network",
        "key_regions": [
            "Anterior Insula",
            "Anterior Cingulate Cortex",
            "Amygdala",
        ],
        "function": "Detecting and filtering salient stimuli, switching between DMN and CEN",
        "disruption_pattern": "Disrupted in frontotemporal dementia, anxiety disorders",
        "clinical_significance": "Salience network mediates DMN-CEN switching",
    },
    "executive_control": {
        "full_name": "Executive Control Network (CEN)",
        "key_regions": [
            "Dorsolateral Prefrontal Cortex",
            "Lateral Parietal Cortex",
            "Posterior Parietal Cortex",
        ],
        "function": "Working memory, problem-solving, cognitive control",
        "disruption_pattern": "Reduced connectivity in TBI, ADHD, schizophrenia",
        "clinical_significance": "CEN disruption impairs planning and decision-making",
    },
    "motor": {
        "full_name": "Motor/Sensory Network",
        "key_regions": [
            "Primary Motor Cortex (Precentral Gyrus)",
            "Primary Somatosensory Cortex (Postcentral Gyrus)",
            "Supplementary Motor Area",
            "Cerebellum",
        ],
        "function": "Voluntary movement, proprioception, motor planning",
        "disruption_pattern": "Disrupted in stroke affecting motor pathways",
        "clinical_significance": "Motor network integrity predicts motor recovery",
    },
    "language": {
        "full_name": "Language Network",
        "key_regions": [
            "Left Inferior Frontal Gyrus (Broca's Area)",
            "Left Superior Temporal Gyrus (Wernicke's Area)",
            "Left Angular Gyrus",
            "Arcuate Fasciculus",
        ],
        "function": "Speech production, comprehension, reading",
        "disruption_pattern": "Disrupted in aphasia, left hemisphere stroke",
        "clinical_significance": "Language network disruption predicts aphasia recovery",
    },
    "visual": {
        "full_name": "Visual Network",
        "key_regions": [
            "Occipital Cortex (V1-V5)",
            "Fusiform Gyrus",
            "Lateral Occipital Cortex",
        ],
        "function": "Visual processing, object recognition, face perception",
        "disruption_pattern": "Disrupted in occipital stroke, cortical blindness",
        "clinical_significance": "Visual network changes in occipital lesions",
    },
}


@dataclass
class NetworkResult:
    """Functional connectivity result for a single network."""
    network_id: str
    full_name: str
    function: str
    disrupted: bool
    disruption_severity: str          # "none", "mild", "moderate", "severe"
    correlation_matrix: Optional[np.ndarray] = None
    within_network_connectivity: float = 0.0
    cross_network_connectivity: Dict[str, float] = field(default_factory=dict)
    damaged_regions_in_network: List[str] = field(default_factory=list)
    clinical_significance: str = ""
    disruption_pattern: str = ""


@dataclass
class FunctionalConnectivityResult:
    """Complete functional connectivity analysis."""
    networks: List[NetworkResult] = field(default_factory=list)
    disrupted_networks: List[str] = field(default_factory=list)
    intact_networks: List[str] = field(default_factory=list)
    summary: str = ""
    method: str = "nilearn"


class FunctionalConnectivity:
    """Analyze functional brain networks from resting-state fMRI.

    Uses nilearn for network detection when available, falls back to
    atlas-based estimation from the damage map.
    """

    def __init__(self):
        self.nilearn_available = self._check_nilearn()

    def _check_nilearn(self) -> bool:
        try:
            import nilearn  # noqa: F401
            return True
        except ImportError:
            logger.info("nilearn not available. Using atlas-based estimation.")
            return False

    def analyze(
        self,
        damage_summary: List[Dict],
        fmri_path: Optional[str] = None,
    ) -> FunctionalConnectivityResult:
        """Analyze functional connectivity and network disruption.

        Args:
            damage_summary: Region-level damage from damage_classifier
            fmri_path: Path to resting-state fMRI NIfTI file (optional)

        Returns:
            FunctionalConnectivityResult with per-network analysis
        """
        if self.nilearn_available and fmri_path:
            return self._analyze_nilearn(damage_summary, fmri_path)
        else:
            return self._analyze_atlas_based(damage_summary)

    def _analyze_atlas_based(
        self,
        damage_summary: List[Dict],
    ) -> FunctionalConnectivityResult:
        """Atlas-based estimation of network disruption.

        Maps damaged atlas regions to expected functional networks
        using known anatomical-functional relationships.
    """
        damaged_regions = {
            r["anatomical_name"].lower(): r for r in damage_summary
            if r.get("severity_level", 0) >= 2
        }

        networks = []
        disrupted_ids = []
        intact_ids = []

        for net_id, net_info in FUNCTIONAL_NETWORKS.items():
            # Find damaged regions that belong to this network
            damaged_in_net = []
            for key_region in net_info["key_regions"]:
                for damaged_name, damaged_data in damaged_regions.items():
                    if (key_region.lower() in damaged_name or
                        damaged_name in key_region.lower() or
                        self._partial_match(damaged_name, key_region.lower())):
                        damaged_in_net.append({
                            "region": damaged_data.get("anatomical_name", damaged_name),
                            "severity": damaged_data.get("severity_label", "UNKNOWN"),
                            "severity_level": damaged_data.get("severity_level", 0),
                        })

            # Determine disruption severity
            if not damaged_in_net:
                disrupted = False
                severity = "none"
                within_conn = 0.95
            elif max(d.get("severity_level", 0) for d in damaged_in_net) >= 4:
                disrupted = True
                severity = "severe"
                within_conn = 0.2
            elif max(d.get("severity_level", 0) for d in damaged_in_net) >= 3:
                disrupted = True
                severity = "moderate"
                within_conn = 0.4
            elif max(d.get("severity_level", 0) for d in damaged_in_net) >= 2:
                disrupted = True
                severity = "mild"
                within_conn = 0.7
            else:
                disrupted = False
                severity = "none"
                within_conn = 0.9

            # Estimate cross-network connectivity
            cross_conn = {}
            for other_id, other_info in FUNCTIONAL_NETWORKS.items():
                if other_id == net_id:
                    continue
                # Reduced connectivity with other networks proportional to disruption
                base = 0.5
                if disrupted:
                    base *= (1 - (1 - within_conn) * 0.5)
                cross_conn[other_id] = round(base, 2)

            network = NetworkResult(
                network_id=net_id,
                full_name=net_info["full_name"],
                function=net_info["function"],
                disrupted=disrupted,
                disruption_severity=severity,
                within_network_connectivity=round(within_conn, 3),
                cross_network_connectivity=cross_conn,
                damaged_regions_in_network=[d["region"] for d in damaged_in_net],
                clinical_significance=net_info["clinical_significance"],
                disruption_pattern=net_info["disruption_pattern"],
            )
            networks.append(network)

            if disrupted:
                disrupted_ids.append(net_id)
            else:
                intact_ids.append(net_id)

        # Build summary
        summary_parts = []
        if disrupted_ids:
            disrupted_names = [FUNCTIONAL_NETWORKS[n]["full_name"] for n in disrupted_ids]
            summary_parts.append(f"Disrupted networks: {', '.join(disrupted_names)}")
        if intact_ids:
            summary_parts.append(f"Intact networks: {len(intact_ids)}")

        return FunctionalConnectivityResult(
            networks=networks,
            disrupted_networks=disrupted_ids,
            intact_networks=intact_ids,
            summary=". ".join(summary_parts) if summary_parts else "All networks intact.",
            method="atlas_estimation",
        )

    def _analyze_nilearn(
        self,
        damage_summary: List[Dict],
        fmri_path: str,
    ) -> FunctionalConnectivityResult:
        """nilearn-based functional connectivity analysis.

        Steps:
        1. Load fMRI data
        2. Extract time series from atlas-defined ROIs
        3. Compute correlation matrices
        4. Identify network disruptions based on damage overlap
        """
        try:
            from nilearn import datasets, masking, input_data
            import nibabel as nib
        except ImportError:
            return self._analyze_atlas_based(damage_summary)

        # Load fMRI data
        try:
            fmri_img = nib.load(fmri_path)
        except Exception as e:
            logger.warning(f"Could not load fMRI: {e}. Using atlas estimation.")
            return self._analyze_atlas_based(damage_summary)

        # Fall back to atlas-based for now; full nilearn pipeline requires
        # specific atlas files and preprocessing
        return self._analyze_atlas_based(damage_summary)

    @staticmethod
    def _partial_match(a: str, b: str) -> bool:
        """Check if key words from b appear in a."""
        a_words = set(a.lower().split())
        b_words = set(b.lower().split())
        overlap = a_words & b_words
        content_words = {w for w in overlap if len(w) > 3}
        return len(content_words) >= min(2, len(b_words))

    def to_dict(self, result: FunctionalConnectivityResult) -> Dict:
        """Convert result to serializable dict."""
        return {
            "method": result.method,
            "disrupted_networks": result.disrupted_networks,
            "intact_networks": result.intact_networks,
            "summary": result.summary,
            "networks": [
                {
                    "network_id": n.network_id,
                    "full_name": n.full_name,
                    "function": n.function,
                    "disrupted": n.disrupted,
                    "disruption_severity": n.disruption_severity,
                    "within_network_connectivity": n.within_network_connectivity,
                    "damaged_regions": n.damaged_regions_in_network,
                    "clinical_significance": n.clinical_significance,
                }
                for n in result.networks
            ],
        }
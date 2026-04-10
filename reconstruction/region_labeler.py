"""
Brain_Scape — Region Labeler

Intersects mesh faces with atlas voxel labels to assign anatomical
names to each mesh region. The viewer and report can say
"Left inferior frontal gyrus (Broca's area, Brodmann Area 44)"
rather than a coordinate.

Uses AAL, Brodmann, and Desikan-Killiany atlas parcellations.
"""

import logging
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


class RegionLabeler:
    """
    Labels mesh regions with anatomical names from atlas parcellations.

    Intersects each mesh face with the registered atlas volume to
    determine which anatomical region each face belongs to.
    """

    def __init__(
        self,
        aal_path: str = "data/atlases/AAL3.nii.gz",
        brodmann_path: str = "data/atlases/Brodmann.nii.gz",
        dk_path: str = "data/atlases/DKaparc.nii.gz",
    ):
        self.aal_path = aal_path
        self.brodmann_path = brodmann_path
        self.dk_path = dk_path

    def label(
        self,
        mesh_path: str,
        registered_path: str,
        output_path: str,
    ) -> dict:
        """
        Label mesh regions with atlas anatomical names.

        Args:
            mesh_path: Path to the 3D mesh file (.obj or .stl).
            registered_path: Path to the MNI152-registered brain scan.
            output_path: Path to write the labeled mesh data (JSON).

        Returns:
            Dictionary with labeling statistics.
        """
        # Load the registered brain for coordinate mapping
        reg_img = nib.load(registered_path)
        reg_data = reg_img.get_fdata()
        affine = reg_img.affine

        # Load atlas parcellations
        atlases = self._load_atlases()

        if not atlases:
            logger.warning("No atlas files found. Region labeling will be minimal.")
            return {
                "method": "none",
                "regions_labeled": 0,
                "atlases_available": [],
                "warning": "No atlas files — region labels unavailable",
            }

        # Load mesh vertices
        vertices = self._load_mesh_vertices(mesh_path)

        if len(vertices) == 0:
            return {"method": "none", "regions_labeled": 0}

        # Map each vertex to atlas labels
        vertex_labels = self._map_vertices_to_atlases(vertices, affine, atlases)

        # Aggregate into regions
        regions = self._aggregate_regions(vertex_labels)

        # Save output
        import json
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(regions, f, indent=2)

        stats = {
            "method": "atlas_intersection",
            "regions_labeled": len(regions),
            "atlases_available": list(atlases.keys()),
            "total_vertices": len(vertices),
        }

        logger.info(
            f"Region labeling complete: {len(regions)} regions labeled "
            f"using {list(atlases.keys())}"
        )
        return stats

    def _load_atlases(self) -> dict:
        """Load all available atlas parcellations."""
        atlases = {}

        for name, path in [
            ("AAL", self.aal_path),
            ("Brodmann", self.brodmann_path),
            ("Desikan-Killiany", self.dk_path),
        ]:
            if Path(path).exists():
                try:
                    atlases[name] = nib.load(path).get_fdata().astype(int)
                except Exception as e:
                    logger.warning(f"Could not load atlas {name}: {e}")

        return atlases

    def _load_mesh_vertices(self, mesh_path: str) -> np.ndarray:
        """Load mesh vertices from OBJ file."""
        vertices = []

        path = Path(mesh_path)
        if not path.exists():
            return np.array([])

        if path.suffix.lower() == ".obj":
            with open(path) as f:
                for line in f:
                    if line.startswith("v "):
                        parts = line.strip().split()[1:4]
                        vertices.append([float(x) for x in parts])

        return np.array(vertices) if vertices else np.array([])

    def _map_vertices_to_atlases(
        self,
        vertices: np.ndarray,
        affine: np.ndarray,
        atlases: dict,
    ) -> list[dict]:
        """Map each vertex to its atlas region labels."""
        # Convert world coordinates to voxel indices
        inv_affine = np.linalg.inv(affine)

        vertex_labels = []
        for vertex in vertices:
            # World -> Voxel coordinate
            vox = inv_affine @ np.append(vertex, 1.0)
            vox_idx = np.round(vox[:3]).astype(int)

            labels = {}
            for atlas_name, atlas_data in atlases.items():
                # Check bounds
                if all(0 <= v < s for v, s in zip(vox_idx, atlas_data.shape)):
                    label = int(atlas_data[vox_idx[0], vox_idx[1], vox_idx[2]])
                    if label > 0:  # Skip background
                        labels[atlas_name] = label

            vertex_labels.append(labels)

        return vertex_labels

    def _aggregate_regions(self, vertex_labels: list[dict]) -> list[dict]:
        """Aggregate vertex labels into named regions."""
        from collections import Counter

        # Count occurrences of each unique label combination
        region_counts = Counter()
        for labels in vertex_labels:
            # Use AAL as primary, fall back to Brodmann, then DK
            key = (
                labels.get("AAL", 0),
                labels.get("Brodmann", 0),
                labels.get("Desikan-Killiany", 0),
            )
            if any(k > 0 for k in key):
                region_counts[key] += 1

        regions = []
        for (aal_id, brodmann_id, dk_id), count in region_counts.most_common():
            region = {
                "vertex_count": count,
                "aal_id": aal_id,
                "brodmann_id": brodmann_id,
                "dk_id": dk_id,
            }

            # Add anatomical name (would use a lookup table in production)
            if aal_id > 0:
                region["anatomical_name"] = f"AAL_Region_{aal_id}"
            if brodmann_id > 0:
                region["brodmann_area"] = f"BA{brodmann_id}"
            if dk_id > 0:
                region["dk_region"] = f"DK_{dk_id}"

            regions.append(region)

        return regions
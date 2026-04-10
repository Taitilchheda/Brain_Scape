"""
Brain_Scape — Damage Overlay

Projects the analysis engine's damage severity map onto the mesh surface
and internal volume. Each region is colored by severity:

  BLUE    (#4A90D9) — Not implicated
  GREEN   (#27AE60) — No damage detected
  YELLOW  (#F1C40F) — Mild abnormality
  ORANGE  (#E67E22) — Moderate-to-severe
  RED     (#E74C3C) — Severe damage

Uses the color contract from configs/models.yaml (referenced, never duplicated).
"""

import json
import logging
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np

from analysis.classification.damage_classifier import SEVERITY_LEVELS

logger = logging.getLogger(__name__)


class DamageOverlay:
    """
    Projects damage severity scores onto the 3D mesh surface.

    Takes the classified damage map and maps severity levels to
    per-face colors using the standard color contract.
    """

    def __init__(self, opacity: float = 0.85):
        """
        Args:
            opacity: Overlay opacity (0.0 = transparent, 1.0 = opaque).
        """
        self.opacity = opacity

    def apply(
        self,
        mesh_path: str,
        severity_map_path: str,
        classified_regions: list[dict],
        output_dir: str,
        output_prefix: str = "brain",
    ) -> dict:
        """
        Apply damage color overlay to the mesh.

        Args:
            mesh_path: Path to the 3D mesh (.obj).
            severity_map_path: Path to the severity NIfTI volume.
            classified_regions: Classified regions from DamageClassifier.
            output_dir: Directory for output files.
            output_prefix: Filename prefix.

        Returns:
            Dictionary with overlay statistics.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Load severity map
        sev_img = nib.load(severity_map_path)
        sev_data = sev_img.get_fdata()

        # Load mesh
        vertices, faces = self._load_obj(mesh_path)

        if len(vertices) == 0:
            logger.warning("No mesh vertices found. Cannot apply damage overlay.")
            return {"faces_colored": 0}

        # Map each vertex to severity
        inv_affine = np.linalg.inv(sev_img.affine)
        vertex_colors = self._compute_vertex_colors(vertices, inv_affine, sev_data)

        # Compute face colors from vertex colors
        face_colors = self._compute_face_colors(faces, vertex_colors)

        # Write colored mesh as .obj with vertex colors
        colored_obj_path = str(out / f"{output_prefix}_colored.obj")
        self._write_colored_obj(vertices, faces, vertex_colors, colored_obj_path)

        # Write damage map as JSON for the frontend
        damage_json_path = str(out / f"{output_prefix}_damage_map.json")
        damage_map = self._build_damage_json(classified_regions, face_colors)
        with open(damage_json_path, "w") as f:
            json.dump(damage_map, f, indent=2)

        # Statistics
        color_counts = {}
        for level_info in SEVERITY_LEVELS.values():
            color_counts[level_info["label"]] = 0

        for color in face_colors:
            level = color.get("level", 0)
            label = SEVERITY_LEVELS.get(level, SEVERITY_LEVELS[0])["label"]
            color_counts[label] = color_counts.get(label, 0) + 1

        stats = {
            "faces_colored": len(face_colors),
            "color_distribution": color_counts,
            "opacity": self.opacity,
            "colored_mesh_path": colored_obj_path,
            "damage_map_path": damage_json_path,
        }

        logger.info(
            f"Damage overlay applied: {len(face_colors):,} faces colored. "
            f"Distribution: {color_counts}"
        )
        return stats

    def _compute_vertex_colors(
        self,
        vertices: np.ndarray,
        inv_affine: np.ndarray,
        severity_data: np.ndarray,
    ) -> list[dict]:
        """Map each vertex to a severity level and color."""
        colors = []

        for vertex in vertices:
            # World -> Voxel coordinate
            vox = inv_affine @ np.append(vertex, 1.0)
            vox_idx = np.round(vox[:3]).astype(int)

            # Check bounds
            if all(0 <= v < s for v, s in zip(vox_idx, severity_data.shape)):
                severity = severity_data[vox_idx[0], vox_idx[1], vox_idx[2]]
            else:
                severity = 0.0

            # Map severity to level
            level = self._severity_to_level(float(severity))
            level_info = SEVERITY_LEVELS[level]

            colors.append({
                "level": level,
                "hex": level_info["hex"],
                "semantic": level_info["semantic"],
            })

        return colors

    @staticmethod
    def _compute_face_colors(
        faces: list, vertex_colors: list[dict]
    ) -> list[dict]:
        """Compute face color from its vertices (majority vote)."""
        face_colors = []

        for face in faces:
            # Get vertex colors for this face
            face_vertex_colors = [vertex_colors[v] for v in face if v < len(vertex_colors)]

            if not face_vertex_colors:
                face_colors.append({"level": 0, "hex": SEVERITY_LEVELS[0]["hex"]})
                continue

            # Majority vote on severity level
            levels = [c["level"] for c in face_vertex_colors]
            from collections import Counter
            most_common = Counter(levels).most_common(1)[0][0]
            level_info = SEVERITY_LEVELS[most_common]

            face_colors.append({
                "level": most_common,
                "hex": level_info["hex"],
                "semantic": level_info["semantic"],
            })

        return face_colors

    @staticmethod
    def _severity_to_level(severity: float) -> int:
        """Map continuous severity score to 5-level scale."""
        if severity < 0.05:
            return 0  # BLUE
        elif severity < 0.15:
            return 1  # GREEN
        elif severity < 0.35:
            return 2  # YELLOW
        elif severity < 0.65:
            return 3  # ORANGE
        else:
            return 4  # RED

    def _load_obj(self, path: str) -> tuple[np.ndarray, list]:
        """Load vertices and faces from OBJ file."""
        vertices = []
        faces = []

        with open(path) as f:
            for line in f:
                if line.startswith("v "):
                    parts = line.strip().split()[1:4]
                    vertices.append([float(x) for x in parts])
                elif line.startswith("f "):
                    # Handle various face formats (v, v/vt, v/vt/vn, v//vn)
                    parts = line.strip().split()[1:]
                    face_verts = []
                    for p in parts:
                        idx = int(p.split("/")[0]) - 1  # OBJ is 1-indexed
                        face_verts.append(idx)
                    faces.append(face_verts)

        return np.array(vertices), faces

    def _write_colored_obj(
        self,
        vertices: np.ndarray,
        faces: list,
        vertex_colors: list[dict],
        output_path: str,
    ) -> None:
        """Write OBJ file with vertex colors (extension: vertex color as comment)."""
        with open(output_path, "w") as f:
            for i, vertex in enumerate(vertices):
                color = vertex_colors[i] if i < len(vertex_colors) else SEVERITY_LEVELS[0]
                # OBJ with vertex colors: v x y z r g b
                hex_color = color["hex"].lstrip("#")
                r = int(hex_color[0:2], 16) / 255.0
                g = int(hex_color[2:4], 16) / 255.0
                b = int(hex_color[4:6], 16) / 255.0
                f.write(f"v {vertex[0]:.4f} {vertex[1]:.4f} {vertex[2]:.4f} "
                        f"{r:.4f} {g:.4f} {b:.4f}\n")

            for face in faces:
                face_str = " ".join(str(v + 1) for v in face)  # 1-indexed
                f.write(f"f {face_str}\n")

    def _build_damage_json(
        self,
        classified_regions: list[dict],
        face_colors: list[dict],
    ) -> dict:
        """Build the damage map JSON for the frontend."""
        return {
            "schema_version": "1.0",
            "total_faces": len(face_colors),
            "regions": classified_regions,
            "severity_levels": SEVERITY_LEVELS,
            "overlay_settings": {
                "opacity": self.opacity,
            },
        }
"""
Brain_Scape — GIF Exporter

Renders a 360-degree rotational animation of the brain mesh and
exports it as an animated GIF for embedding in reports or sharing
in clinical communications.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class GIFExporter:
    """
    Exports 360-degree rotational GIF of the brain mesh.

    Renders frames from multiple viewing angles, then assembles
    them into an animated GIF using Matplotlib or Pillow.
    """

    def __init__(
        self,
        num_frames: int = 36,
        resolution: tuple[int, int] = (800, 600),
        dpi: int = 100,
        rotation_axis: str = "z",
        elevation: float = 20.0,
        fps: int = 10,
    ):
        """
        Args:
            num_frames: Number of rotation frames (36 = 10 deg per frame).
            resolution: (width, height) in pixels.
            dpi: Dots per inch for rendering.
            rotation_axis: Axis to rotate around ("x", "y", "z").
            elevation: Camera elevation angle in degrees.
            fps: Frames per second in the output GIF.
        """
        self.num_frames = num_frames
        self.resolution = resolution
        self.dpi = dpi
        self.rotation_axis = rotation_axis
        self.elevation = elevation
        self.fps = fps

    def export(
        self,
        mesh_path: str,
        output_path: str,
        damage_map_path: Optional[str] = None,
    ) -> dict:
        """
        Export a 360-degree rotational GIF of the brain mesh.

        Args:
            mesh_path: Path to the colored .obj mesh file.
            output_path: Path to write the output GIF.
            damage_map_path: Optional JSON damage map for overlay controls.

        Returns:
            Dictionary with export statistics.
        """
        try:
            return self._export_matplotlib(mesh_path, output_path)
        except ImportError:
            logger.warning("Matplotlib 3D not available. Trying Pillow fallback.")
            return self._export_pillow(mesh_path, output_path)

    def _export_matplotlib(self, mesh_path: str, output_path: str) -> dict:
        """Export using Matplotlib 3D rendering."""
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        import matplotlib.animation as animation

        # Load mesh
        vertices, faces = self._load_obj(mesh_path)

        if len(vertices) == 0:
            return {"frames": 0, "error": "No mesh data"}

        # Create figure
        fig = plt.figure(figsize=(self.resolution[0] / self.dpi, self.resolution[1] / self.dpi), dpi=self.dpi)
        ax = fig.add_subplot(111, projection="3d")

        # Set up axes
        center = vertices.mean(axis=0)
        extent = np.max(np.ptp(vertices, axis=0)) / 2 * 1.1

        def render_frame(azim):
            ax.clear()
            ax.set_xlim(center[0] - extent, center[0] + extent)
            ax.set_ylim(center[1] - extent, center[1] + extent)
            ax.set_zlim(center[2] - extent, center[2] + extent)
            ax.set_axis_off()
            ax.view_init(elev=self.elevation, azim=azim)

            # Render mesh faces
            for face in faces[:5000]:  # Limit for performance
                tri = [vertices[v] for v in face if v < len(vertices)]
                if len(tri) >= 3:
                    poly = Poly3DCollection([tri], alpha=0.85)
                    poly.set_facecolor("lightgray")
                    poly.set_edgecolor("gray")
                    ax.add_collection3d(poly)

        # Generate rotation frames
        angles = np.linspace(0, 360, self.num_frames, endpoint=False)

        frames = []
        for angle in angles:
            render_frame(angle)
            fig.canvas.draw()
            # Convert to image array
            buf = fig.canvas.buffer_rgba()
            image = np.asarray(buf).copy()
            frames.append(image)

        plt.close(fig)

        # Save as GIF using Pillow
        from PIL import Image

        pil_frames = [Image.fromarray(frame) for frame in frames]
        pil_frames[0].save(
            output_path,
            save_all=True,
            append_images=pil_frames[1:],
            duration=int(1000 / self.fps),
            loop=0,
        )

        stats = {
            "method": "matplotlib",
            "frames": len(frames),
            "fps": self.fps,
            "resolution": list(self.resolution),
            "rotation_axis": self.rotation_axis,
            "output_path": output_path,
        }

        logger.info(f"GIF exported: {len(frames)} frames at {self.fps}fps")
        return stats

    def _export_pillow(self, mesh_path: str, output_path: str) -> dict:
        """Fallback GIF export using Pillow (creates placeholder frames)."""
        from PIL import Image, ImageDraw

        width, height = self.resolution
        frames = []

        for i in range(self.num_frames):
            angle = (360 / self.num_frames) * i

            img = Image.new("RGB", (width, height), color=(30, 30, 40))
            draw = ImageDraw.Draw(img)

            # Draw a simple rotating placeholder
            cx, cy = width // 2, height // 2
            r = min(width, height) // 3
            x1 = cx + int(r * 0.8 * np.cos(np.radians(angle)))
            y1 = cy + int(r * 0.4 * np.sin(np.radians(angle)))

            draw.ellipse([cx - r, cy - r//2, cx + r, cy + r//2], outline=(100, 150, 200), width=2)
            draw.text((10, 10), f"Brain_Scape — Rotation {angle:.0f}°", fill=(200, 200, 200))

            frames.append(img)

        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=int(1000 / self.fps),
            loop=0,
        )

        return {"method": "pillow_placeholder", "frames": len(frames)}

    @staticmethod
    def _load_obj(path: str) -> tuple[np.ndarray, list]:
        """Load vertices and faces from OBJ file."""
        vertices = []
        faces = []

        with open(path) as f:
            for line in f:
                if line.startswith("v "):
                    parts = line.strip().split()[1:4]
                    vertices.append([float(x) for x in parts])
                elif line.startswith("f "):
                    parts = line.strip().split()[1:]
                    face_verts = [int(p.split("/")[0]) - 1 for p in parts]
                    faces.append(face_verts)

        return np.array(vertices), faces
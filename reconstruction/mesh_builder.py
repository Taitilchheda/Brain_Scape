"""
Brain_Scape — Mesh Builder

Converts 3D voxel volumes into surface meshes using the marching cubes
algorithm (VTK). Produces high-resolution polygonal representations of
the brain surface for interactive 3D rendering in the browser.

Applies quadric decimation for web-ready meshes (100k-200k polygons)
while retaining full-resolution meshes for .stl surgical export.
"""

import logging
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


class MeshBuilder:
    """
    Builds 3D surface meshes from brain voxel volumes.

    Uses VTK marching cubes for isosurface extraction, followed by
    quadric decimation for web-optimized meshes.
    """

    def __init__(
        self,
        decimation_target: int = 150000,
        iso_value: float = 0.5,
        smooth_iterations: int = 50,
    ):
        """
        Args:
            decimation_target: Target polygon count for web mesh.
            iso_value: Isosurface value for marching cubes.
            smooth_iterations: Number of Laplacian smoothing iterations.
        """
        self.decimation_target = decimation_target
        self.iso_value = iso_value
        self.smooth_iterations = smooth_iterations

    def build(
        self,
        input_path: str,
        output_dir: str,
        output_prefix: str = "brain",
    ) -> dict:
        """
        Build 3D meshes from a brain volume.

        Args:
            input_path: Path to the registered NIfTI file.
            output_dir: Directory to write mesh files.
            output_prefix: Prefix for output filenames.

        Returns:
            Dictionary with mesh generation statistics.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        try:
            return self._build_vtk(input_path, out, output_prefix)
        except ImportError:
            logger.warning("VTK not available. Falling back to scikit-image.")
            return self._build_skimage(input_path, out, output_prefix)

    def _build_vtk(
        self, input_path: str, output_dir: Path, prefix: str
    ) -> dict:
        """Build mesh using VTK (preferred — higher quality)."""
        import vtk
        from vtk.util.numpy_support import numpy_to_vtk

        logger.info("Building mesh with VTK...")

        # Load NIfTI
        img = nib.load(input_path)
        data = img.get_fdata()

        # Create VTK image from numpy array
        vtk_data = numpy_to_vtk(data.ravel(), deep=True)
        vtk_image = vtk.vtkImageData()
        vtk_image.SetDimensions(*data.shape)
        vtk_image.GetPointData().SetScalars(vtk_data)

        # Set spacing from NIfTI header
        voxel_sizes = img.header.get_zooms()[:3]
        vtk_image.SetSpacing(voxel_sizes)

        # Marching cubes
        marching = vtk.vtkMarchingCubes()
        marching.SetInputData(vtk_image)
        marching.SetValue(0, self.iso_value)
        marching.Update()

        mesh = marching.GetOutput()
        original_polys = mesh.GetNumberOfCells()

        logger.info(f"Full-resolution mesh: {original_polys:,} polygons")

        # Smooth the mesh
        if self.smooth_iterations > 0:
            smoother = vtk.vtkWindowedSincPolyDataFilter()
            smoother.SetInputData(mesh)
            smoother.SetNumberOfIterations(self.smooth_iterations)
            smoother.Update()
            mesh = smoother.GetOutput()

        # Save full-resolution mesh (.stl for surgical planning)
        full_path = str(output_dir / f"{prefix}_full.stl")
        self._write_vtk_mesh(mesh, full_path)

        # Decimate for web rendering
        decimated = self._decimate_vtk(mesh)
        web_polys = decimated.GetNumberOfCells()

        # Save web-resolution mesh (.obj for preview)
        web_path = str(output_dir / f"{prefix}_web.obj")
        self._write_vtk_mesh(decimated, web_path)

        stats = {
            "method": "vtk",
            "original_polygons": int(original_polys),
            "decimated_polygons": int(web_polys),
            "decimation_ratio": round(web_polys / original_polys, 3),
            "smooth_iterations": self.smooth_iterations,
            "full_mesh_path": full_path,
            "web_mesh_path": web_path,
        }

        logger.info(
            f"Mesh built: {original_polys:,} -> {web_polys:,} polygons "
            f"({stats['decimation_ratio']:.1%} retention)"
        )
        return stats

    def _decimate_vtk(self, mesh) -> "vtkPolyData":
        """Apply quadric decimation to reduce polygon count."""
        import vtk

        target_reduction = 1.0 - (self.decimation_target / mesh.GetNumberOfCells())
        target_reduction = max(0.0, min(0.99, target_reduction))

        decimator = vtk.vtkQuadricDecimation()
        decimator.SetInputData(mesh)
        decimator.SetTargetReduction(target_reduction)
        decimator.Update()

        return decimator.GetOutput()

    @staticmethod
    def _write_vtk_mesh(mesh, output_path: str) -> None:
        """Write a VTK mesh to file (auto-detect format from extension)."""
        import vtk

        ext = Path(output_path).suffix.lower()
        if ext == ".stl":
            writer = vtk.vtkSTLWriter()
        elif ext == ".obj":
            writer = vtk.vtkOBJWriter()
        elif ext == ".vtp":
            writer = vtk.vtkXMLPolyDataWriter()
        else:
            writer = vtk.vtkSTLWriter()

        writer.SetFileName(output_path)
        writer.SetInputData(mesh)
        writer.Write()

    def _build_skimage(
        self, input_path: str, output_dir: Path, prefix: str
    ) -> dict:
        """Fallback mesh building using scikit-image."""
        from skimage import measure

        logger.info("Building mesh with scikit-image...")

        img = nib.load(input_path)
        data = img.get_fdata()
        voxel_sizes = img.header.get_zooms()[:3]

        # Marching cubes
        verts, faces, normals, values = measure.marching_cubes(
            data, level=self.iso_value, spacing=voxel_sizes
        )

        original_polys = len(faces)
        logger.info(f"Full-resolution mesh: {original_polys:,} polygons")

        # Save as .obj (simple text format)
        obj_path = str(output_dir / f"{prefix}_web.obj")
        with open(obj_path, "w") as f:
            for v in verts:
                f.write(f"v {v[0]} {v[1]} {v[2]}\n")
            for face in faces:
                # OBJ is 1-indexed
                f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")

        stats = {
            "method": "scikit-image",
            "original_polygons": int(original_polys),
            "decimated_polygons": int(original_polys),
            "decimation_ratio": 1.0,
            "web_mesh_path": obj_path,
        }

        logger.info(f"Mesh built (no decimation): {original_polys:,} polygons")
        return stats
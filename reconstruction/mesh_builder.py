"""
Brain_Scape — Mesh Builder

Converts 3D voxel volumes into surface meshes using the marching cubes
algorithm (VTK). Produces high-resolution polygonal representations of
the brain surface for interactive 3D rendering in the browser.

Applies quadric decimation for web-ready meshes (100k-200k polygons)
while retaining full-resolution meshes for .stl surgical export.
"""

import logging
import math
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np
from scipy import ndimage

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
        except Exception as exc:
            logger.warning(f"VTK mesh build unavailable ({exc}). Falling back to scikit-image.")

        try:
            return self._build_skimage(input_path, out, output_prefix)
        except ImportError as exc:
            raise RuntimeError(
                "Mesh reconstruction requires either VTK or scikit-image. "
                "Install 'vtk' or 'scikit-image'."
            ) from exc

    def _build_vtk(
        self, input_path: str, output_dir: Path, prefix: str
    ) -> dict:
        """Build mesh using VTK (preferred — higher quality)."""
        import vtk
        from vtk.util.numpy_support import numpy_to_vtk

        logger.info("Building mesh with VTK...")

        high_detail_mode = self.decimation_target >= 250000
        volume, voxel_sizes, source_modality = self._prepare_volume_for_surface(
            input_path,
            preserve_detail=high_detail_mode,
        )
        volume, voxel_sizes, resample_factor = self._upsample_surface_volume(
            volume,
            voxel_sizes,
            enabled=high_detail_mode,
        )

        surface_level = self.iso_value
        if high_detail_mode:
            surface_level = max(0.28, min(0.42, self.iso_value * 0.78))

        # Create VTK image from numpy array
        # VTK expects x-fastest memory layout, which matches Fortran ordering.
        vtk_data = numpy_to_vtk(volume.ravel(order="F"), deep=True)
        vtk_data.SetNumberOfComponents(1)
        vtk_image = vtk.vtkImageData()
        vtk_image.SetDimensions(*volume.shape)
        vtk_image.GetPointData().SetScalars(vtk_data)

        # Set spacing from source volume/header.
        vtk_image.SetSpacing(voxel_sizes)

        # Marching cubes
        marching = vtk.vtkMarchingCubes()
        marching.SetInputData(vtk_image)
        marching.SetValue(0, surface_level)
        marching.Update()

        mesh = marching.GetOutput()

        # Keep the preview surface watertight and consistently oriented for shading.
        cleaner = vtk.vtkCleanPolyData()
        cleaner.SetInputData(mesh)
        cleaner.Update()
        mesh = cleaner.GetOutput()

        filler = vtk.vtkFillHolesFilter()
        filler.SetInputData(mesh)
        filler.SetHoleSize(1000.0)
        filler.Update()
        mesh = filler.GetOutput()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(mesh)
        normals.ConsistencyOn()
        normals.AutoOrientNormalsOn()
        normals.SplittingOff()
        normals.Update()
        mesh = normals.GetOutput()

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
            "source_modality": source_modality,
            "detail_mode": "high" if high_detail_mode else "standard",
            "resample_factor": float(round(resample_factor, 3)),
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

        high_detail_mode = self.decimation_target >= 250000
        volume, voxel_sizes, source_modality = self._prepare_volume_for_surface(
            input_path,
            preserve_detail=high_detail_mode,
        )
        volume, voxel_sizes, resample_factor = self._upsample_surface_volume(
            volume,
            voxel_sizes,
            enabled=high_detail_mode,
        )

        surface_level = self.iso_value
        if high_detail_mode:
            # High-detail mode uses a continuous scalar field; a slightly lower
            # level preserves gyral contours instead of over-smoothing to a blob.
            surface_level = max(0.28, min(0.42, self.iso_value * 0.78))

        # Marching cubes
        verts, faces, normals, values = measure.marching_cubes(
            volume,
            level=surface_level,
            spacing=voxel_sizes,
            allow_degenerate=False,
        )

        # Center and scale to unit-space so the viewer receives consistent geometry.
        verts = self._normalize_vertices(verts)

        # Lightweight decimation for web rendering if the mesh is very dense.
        full_faces = len(faces)
        faces = self._decimate_faces(faces)
        web_faces = len(faces)

        logger.info(f"Full-resolution mesh: {full_faces:,} polygons")

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
            "source_modality": source_modality,
            "detail_mode": "high" if high_detail_mode else "standard",
            "resample_factor": float(round(resample_factor, 3)),
            "original_polygons": int(full_faces),
            "decimated_polygons": int(web_faces),
            "decimation_ratio": round((web_faces / full_faces), 3) if full_faces else 1.0,
            "web_mesh_path": obj_path,
        }

        logger.info(f"Mesh built: {full_faces:,} -> {web_faces:,} polygons")
        return stats

    def _prepare_volume_for_surface(
        self,
        input_path: str,
        preserve_detail: bool = False,
    ) -> tuple[np.ndarray, tuple[float, float, float], str]:
        """Prepare a stable brain surface scalar field from MRI or fMRI NIfTI inputs."""
        img = nib.load(input_path)
        raw = np.asarray(img.get_fdata(dtype=np.float32))
        voxel_sizes = tuple(float(v) for v in img.header.get_zooms()[:3])

        modality = "MRI"
        if raw.ndim == 4:
            modality = "fMRI"
            # Collapse time into a structural-like target while preserving active regions.
            temporal_mean = np.mean(raw, axis=3)
            temporal_std = np.std(raw, axis=3)
            raw = temporal_mean + (0.25 * temporal_std)
        elif raw.ndim != 3:
            raise ValueError(f"Unsupported NIfTI dimensionality for reconstruction: {raw.shape}")

        raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)

        non_zero = raw[raw > 0]
        if non_zero.size == 0:
            raise ValueError("Input volume is empty after preprocessing")

        p_low = float(np.percentile(non_zero, 2))
        p_high = float(np.percentile(non_zero, 99))
        if p_high <= p_low:
            p_high = p_low + 1e-6

        clipped = np.clip(raw, p_low, p_high)
        norm = (clipped - p_low) / (p_high - p_low)

        # Smooth noise while preserving boundaries.
        detail_sigma = 0.4 if preserve_detail else 0.7
        norm = ndimage.gaussian_filter(norm, sigma=detail_sigma)

        tissue_values = norm[norm > 0.05]
        if tissue_values.size == 0:
            threshold = 0.2
        else:
            threshold_quantile = 0.3 if preserve_detail else 0.35
            threshold = float(np.quantile(tissue_values, threshold_quantile))
            threshold = max(0.12, min(0.48, threshold))

        brain_mask = norm >= threshold
        brain_mask = ndimage.binary_opening(brain_mask, iterations=1)
        closing_iterations = 1 if preserve_detail else 2
        brain_mask = ndimage.binary_closing(brain_mask, iterations=closing_iterations)
        brain_mask = ndimage.binary_fill_holes(brain_mask)
        brain_mask = self._largest_component(brain_mask)

        # Slight smoothing of the mask gives less jagged cortical surface.
        mask_sigma = 0.6 if preserve_detail else 0.8
        smooth_mask = ndimage.gaussian_filter(brain_mask.astype(np.float32), sigma=mask_sigma)
        if preserve_detail:
            detail_field = np.clip((smooth_mask * 0.62) + (norm * 0.38), 0.0, 1.0)
            detail_field *= brain_mask.astype(np.float32)
            surface_volume = ndimage.gaussian_filter(detail_field, sigma=0.28)
            support_voxels = np.count_nonzero(surface_volume > 0.08)
        else:
            mask_level = 0.5
            surface_volume = (smooth_mask >= mask_level).astype(np.float32)
            support_voxels = np.count_nonzero(surface_volume)

        if support_voxels < 1024:
            raise ValueError("Brain surface mask too small for mesh extraction")

        return surface_volume, voxel_sizes, modality

    @staticmethod
    def _upsample_surface_volume(
        volume: np.ndarray,
        voxel_sizes: tuple[float, float, float],
        enabled: bool,
    ) -> tuple[np.ndarray, tuple[float, float, float], float]:
        if not enabled:
            return volume, voxel_sizes, 1.0

        min_spacing = max(1e-6, min(float(v) for v in voxel_sizes))
        target_spacing = max(0.7, min(1.0, min_spacing * 0.82))

        zoom_factors = tuple(max(1.0, min(1.65, float(v) / target_spacing)) for v in voxel_sizes)
        if max(zoom_factors) <= 1.05:
            return volume, voxel_sizes, 1.0

        upsampled = ndimage.zoom(volume.astype(np.float32), zoom=zoom_factors, order=1)
        upsampled = ndimage.gaussian_filter(upsampled, sigma=0.18)
        upsampled_spacing = tuple(float(v) / float(z) for v, z in zip(voxel_sizes, zoom_factors))
        return upsampled, upsampled_spacing, float(max(zoom_factors))

    @staticmethod
    def _largest_component(mask: np.ndarray) -> np.ndarray:
        labeled, count = ndimage.label(mask)
        if count <= 1:
            return mask

        component_sizes = np.bincount(labeled.ravel())
        component_sizes[0] = 0
        largest = int(np.argmax(component_sizes))
        return labeled == largest

    def _decimate_faces(self, faces: np.ndarray) -> np.ndarray:
        if len(faces) <= self.decimation_target:
            return faces

        step = max(1, math.ceil(len(faces) / float(self.decimation_target)))
        reduced = faces[::step]
        logger.info(f"Decimated faces: {len(faces):,} -> {len(reduced):,}")
        return reduced

    @staticmethod
    def _normalize_vertices(verts: np.ndarray) -> np.ndarray:
        mins = np.min(verts, axis=0)
        maxs = np.max(verts, axis=0)
        center = (mins + maxs) / 2.0
        extent = np.max(maxs - mins)
        if extent <= 1e-6:
            return verts - center
        return (verts - center) / (extent / 2.0)
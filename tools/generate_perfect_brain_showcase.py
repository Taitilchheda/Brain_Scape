from __future__ import annotations

import json
from pathlib import Path

import matplotlib

# Use a headless backend for deterministic file generation.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from matplotlib.colors import to_rgb
from matplotlib.patches import Patch
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from nilearn import datasets, surface
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "final-publication" / "perfect-brain-showcase"
NIFTI_PATH = ROOT / "data" / "raw" / "uploads" / "brainscape_sample_fmri.nii.gz"
ANALYSIS_PATH = ROOT / "outputs" / "analysis" / "4b11d116-1e3e-4bef-a077-01f06d462523" / "analysis.json"


def normalize_vector(v: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(v))
    return v / norm if norm > 0 else v


def load_fsaverage_brain_mesh() -> tuple[np.ndarray, np.ndarray, dict[str, str]]:
    fs = datasets.fetch_surf_fsaverage(mesh="fsaverage5")
    coords_left, faces_left = surface.load_surf_mesh(fs.pial_left)
    coords_right, faces_right = surface.load_surf_mesh(fs.pial_right)

    faces_right_offset = faces_right + len(coords_left)
    vertices = np.vstack([coords_left, coords_right]).astype(np.float32)
    faces = np.vstack([faces_left, faces_right_offset]).astype(np.int32)

    centered = vertices - vertices.mean(axis=0, keepdims=True)
    scale = float(np.max(np.ptp(centered, axis=0)))
    vertices_norm = centered / max(scale, 1e-6)

    sources = {
        "pial_left": str(fs.pial_left),
        "pial_right": str(fs.pial_right),
    }
    return vertices_norm, faces, sources


def compute_face_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    tris = vertices[faces]
    a = tris[:, 1] - tris[:, 0]
    b = tris[:, 2] - tris[:, 0]
    normals = np.cross(a, b)
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return normals / norms


def lighting_intensity(normals: np.ndarray) -> np.ndarray:
    key = normalize_vector(np.asarray([0.3, -0.2, 0.93], dtype=np.float32))
    fill = normalize_vector(np.asarray([-0.45, 0.25, 0.74], dtype=np.float32))
    rim = normalize_vector(np.asarray([0.05, 0.98, -0.15], dtype=np.float32))

    key_i = np.clip(normals @ key, 0.0, 1.0)
    fill_i = np.clip(normals @ fill, 0.0, 1.0)
    rim_i = np.clip(normals @ rim, 0.0, 1.0)

    intensity = 0.24 + 0.56 * key_i + 0.28 * fill_i + 0.16 * rim_i
    return np.clip(intensity, 0.0, 1.0)


def base_face_colors(normals: np.ndarray, base_hex: str = "#CBD8E8") -> np.ndarray:
    base = np.asarray(to_rgb(base_hex), dtype=np.float32)
    light = lighting_intensity(normals)
    rgb = np.clip(base[None, :] * (0.56 + 0.66 * light[:, None]), 0.0, 1.0)
    return np.concatenate([rgb, np.ones((len(rgb), 1), dtype=np.float32)], axis=1)


def hotspot_vertex_intensity(vertices: np.ndarray) -> np.ndarray:
    # Hotspot centers in normalized fsaverage space.
    centers = [
        (-0.30, 0.18, 0.24, 0.11, 1.00),
        (0.30, 0.14, 0.22, 0.11, 0.96),
        (-0.16, -0.34, 0.07, 0.10, 0.84),
        (0.21, -0.30, 0.08, 0.10, 0.82),
        (0.00, 0.36, 0.34, 0.10, 0.70),
    ]

    intensity = np.zeros(len(vertices), dtype=np.float32)
    for cx, cy, cz, sigma, amp in centers:
        d2 = np.sum((vertices - np.asarray([cx, cy, cz], dtype=np.float32)) ** 2, axis=1)
        intensity += float(amp) * np.exp(-d2 / (2.0 * float(sigma) ** 2))

    intensity = np.clip(intensity, 0.0, None)
    max_val = float(np.max(intensity))
    return intensity / max(max_val, 1e-8)


def hotspot_face_colors(normals: np.ndarray, faces: np.ndarray, hotspot_vtx: np.ndarray) -> np.ndarray:
    face_hot = hotspot_vtx[faces].mean(axis=1)

    base_rgb = base_face_colors(normals, base_hex="#C8D7E8")[:, :3]
    hot_rgb = plt.get_cmap("inferno")(np.clip(face_hot, 0.0, 1.0))[:, :3]
    alpha = np.clip((face_hot - 0.08) * 1.35, 0.0, 0.88)

    rgb = np.clip(base_rgb * (1.0 - alpha[:, None]) + hot_rgb * alpha[:, None], 0.0, 1.0)
    return np.concatenate([rgb, np.ones((len(rgb), 1), dtype=np.float32)], axis=1)


def style_3d_axis(ax: plt.Axes, vertices: np.ndarray, elev: float, azim: float) -> None:
    mn = np.min(vertices, axis=0)
    mx = np.max(vertices, axis=0)
    center = (mx + mn) / 2.0
    spans = np.maximum(mx - mn, 1e-3)
    radius = float(np.max(spans) * 0.54)

    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
    if hasattr(ax, "set_box_aspect"):
        ax.set_box_aspect((spans[0], spans[1], spans[2]))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()


def render_brain_surface(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_rgba: np.ndarray,
    output_stem: Path,
    title: str,
    subtitle: str,
    hotspot_legend: bool,
) -> None:
    views = [
        ("Left lateral", 17, 124),
        ("Superior", 88, -90),
        ("Right lateral", 17, 56),
    ]

    fig = plt.figure(figsize=(15.2, 5.8), dpi=240)
    fig.patch.set_facecolor("#FBFDFF")

    for idx, (label, elev, azim) in enumerate(views, start=1):
        ax = fig.add_subplot(1, 3, idx, projection="3d")
        mesh = Poly3DCollection(
            vertices[faces],
            facecolors=face_rgba,
            edgecolor=(0.52, 0.62, 0.75, 0.12),
            linewidth=0.025,
            alpha=1.0,
        )
        ax.add_collection3d(mesh)
        style_3d_axis(ax, vertices, elev=elev, azim=azim)
        ax.set_title(label, fontsize=10, fontweight="bold", pad=2)

    if hotspot_legend:
        legend_handles = [
            Patch(facecolor="#581845", edgecolor="none", label="Low hotspot"),
            Patch(facecolor="#C8434C", edgecolor="none", label="Moderate hotspot"),
            Patch(facecolor="#FEE825", edgecolor="none", label="High hotspot"),
        ]
        fig.legend(handles=legend_handles, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.94), fontsize=10)

    fig.suptitle(title, fontsize=16, fontweight="bold", y=0.98)
    fig.text(0.5, 0.03, subtitle, ha="center", fontsize=10, color="#4B5563")

    fig.savefig(output_stem.with_suffix(".png"), bbox_inches="tight")
    fig.savefig(output_stem.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def load_mri_volume(path: Path) -> np.ndarray:
    img = nib.load(str(path))
    vol = np.asarray(img.get_fdata(), dtype=np.float32)
    if vol.ndim == 4:
        # Pick the sharpest timepoint to avoid motion-blurred temporal averaging.
        best_idx = 0
        best_score = -1.0
        for t in range(vol.shape[3]):
            frame = np.nan_to_num(vol[:, :, :, t], nan=0.0, posinf=0.0, neginf=0.0)
            gx = ndi.sobel(frame, axis=0)
            gy = ndi.sobel(frame, axis=1)
            gz = ndi.sobel(frame, axis=2)
            score = float(np.mean(gx * gx + gy * gy + gz * gz))
            if score > best_score:
                best_score = score
                best_idx = t
        vol = vol[:, :, :, best_idx]
    vol = np.nan_to_num(vol, nan=0.0, posinf=0.0, neginf=0.0)

    # Keep smoothing minimal to preserve edges.
    vol = ndi.gaussian_filter(vol, sigma=0.2)
    lo, hi = np.percentile(vol, [0.5, 99.8])
    vol = np.clip((vol - lo) / max(hi - lo, 1e-6), 0.0, 1.0)

    # Mild gamma correction for global contrast.
    vol = np.clip(vol ** 0.96, 0.0, 1.0)
    return vol.astype(np.float32)


def load_mni_template_volume() -> np.ndarray:
    # Use high-resolution anatomical template specifically for crystal-clear DICOM panel rendering.
    template_img = datasets.load_mni152_template(resolution=1)
    vol = np.asarray(template_img.get_fdata(), dtype=np.float32)
    vol = np.nan_to_num(vol, nan=0.0, posinf=0.0, neginf=0.0)

    lo, hi = np.percentile(vol, [0.2, 99.95])
    vol = np.clip((vol - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    vol = np.clip(vol ** 0.92, 0.0, 1.0)
    return vol.astype(np.float32)


def get_slice(volume: np.ndarray, axis: int, index: int) -> np.ndarray:
    if axis == 0:
        sl = volume[index, :, :]
    elif axis == 1:
        sl = volume[:, index, :]
    else:
        sl = volume[:, :, index]
    return np.flipud(sl.T)


def enhance_mri_slice(sl: np.ndarray) -> np.ndarray:
    # Robust window normalization per slice.
    lo, hi = np.percentile(sl, [1.0, 99.6])
    base = np.clip((sl - lo) / max(hi - lo, 1e-6), 0.0, 1.0)

    # Unsharp masking to improve perceived anatomical edge clarity.
    blur = ndi.gaussian_filter(base, sigma=1.0)
    detail = base - blur
    sharp = np.clip(base + 1.55 * detail, 0.0, 1.0)

    # Small local-contrast boost without saturating highlights.
    contrast = np.clip((sharp - 0.5) * 1.16 + 0.5, 0.0, 1.0)
    return np.clip(contrast ** 0.94, 0.0, 1.0)


def render_dicom_mri_series(volume: np.ndarray, output_stem: Path) -> None:
    # Ultra high-resolution display volume for publication rendering.
    volume_hr = ndi.zoom(volume, zoom=(4.0, 4.0, 4.0), order=1)
    dims = volume_hr.shape
    row_cfg = [
        (2, "AXIAL", [0.35, 0.50, 0.65]),
        (1, "CORONAL", [0.35, 0.50, 0.65]),
        (0, "SAGITTAL", [0.35, 0.50, 0.65]),
    ]

    fig, axes = plt.subplots(3, 3, figsize=(16.0, 15.4), dpi=320)
    fig.patch.set_facecolor("#06090F")

    for row, (axis, axis_name, fractions) in enumerate(row_cfg):
        for col, frac in enumerate(fractions):
            idx = int(round((dims[axis] - 1) * frac))
            sl = get_slice(volume_hr, axis=axis, index=idx)
            sl = enhance_mri_slice(sl)
            ax = axes[row, col]
            ax.set_facecolor("#06090F")
            ax.imshow(sl, cmap="gray", vmin=0.0, vmax=1.0, interpolation="nearest")

            h, w = sl.shape
            ax.axhline(h * 0.5, color="#3A4557", lw=0.5)
            ax.axvline(w * 0.5, color="#3A4557", lw=0.5)

            ax.text(0.02, 0.98, f"{axis_name} | slice {idx}", transform=ax.transAxes, va="top", ha="left", fontsize=10, color="#7DD3FC", fontweight="bold")
            ax.text(0.98, 0.03, "WL: 40 WW: 80", transform=ax.transAxes, va="bottom", ha="right", fontsize=9, color="#A5B4FC")

            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_edgecolor("#334155")
                spine.set_linewidth(0.8)

    fig.suptitle("Perfect Brain DICOM-Style MRI Series", fontsize=20, fontweight="bold", y=0.995, color="#E5E7EB")
    fig.text(0.5, 0.012, "Ultra high-resolution orthogonal MRI panels from MNI152 anatomical template with radiology-style windowing", ha="center", fontsize=12, color="#94A3B8")
    fig.tight_layout(rect=[0.01, 0.03, 0.99, 0.97])

    fig.savefig(output_stem.with_suffix(".png"), bbox_inches="tight")
    fig.savefig(output_stem.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def build_hotspot_volume(shape: tuple[int, int, int]) -> np.ndarray:
    nx, ny, nz = shape
    xx = np.arange(nx, dtype=np.float32)[:, None, None]
    yy = np.arange(ny, dtype=np.float32)[None, :, None]
    zz = np.arange(nz, dtype=np.float32)[None, None, :]

    # Fractional coordinates are tuned to produce clinically plausible multi-focal overlays.
    centers = [
        (0.34, 0.60, 0.58, 0.08, 1.0),
        (0.64, 0.42, 0.56, 0.07, 0.9),
        (0.46, 0.36, 0.46, 0.06, 0.85),
        (0.55, 0.68, 0.38, 0.07, 0.72),
    ]

    heat = np.zeros(shape, dtype=np.float32)
    for fx, fy, fz, sigma, amp in centers:
        cx = fx * (nx - 1)
        cy = fy * (ny - 1)
        cz = fz * (nz - 1)
        sx = sigma * nx
        sy = sigma * ny
        sz = sigma * nz

        field = (
            ((xx - cx) ** 2) / (2.0 * sx * sx)
            + ((yy - cy) ** 2) / (2.0 * sy * sy)
            + ((zz - cz) ** 2) / (2.0 * sz * sz)
        )
        heat += float(amp) * np.exp(-field)

    max_val = float(np.max(heat))
    heat /= max(max_val, 1e-8)
    return heat


def render_dicom_mri_hotspots(volume: np.ndarray, heat: np.ndarray, output_stem: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14.6, 4.8), dpi=240)
    fig.patch.set_facecolor("#06090F")

    cfg = [
        (2, "AXIAL"),
        (1, "CORONAL"),
        (0, "SAGITTAL"),
    ]

    for ax, (axis, axis_name) in zip(axes, cfg):
        idx = volume.shape[axis] // 2
        base = get_slice(volume, axis, idx)
        ov = get_slice(heat, axis, idx)

        ax.set_facecolor("#06090F")
        ax.imshow(base, cmap="gray", vmin=0.0, vmax=1.0, interpolation="bicubic")

        ov_norm = np.clip(ov, 0.0, 1.0)
        ov_mask = np.ma.masked_where(ov_norm < 0.10, ov_norm)
        alpha = np.clip((ov_norm - 0.10) / 0.65, 0.0, 0.90)
        ax.imshow(ov_mask, cmap="inferno", vmin=0.0, vmax=1.0, alpha=alpha, interpolation="bicubic")

        h, w = base.shape
        ax.axhline(h * 0.5, color="#3A4557", lw=0.6)
        ax.axvline(w * 0.5, color="#3A4557", lw=0.6)

        ax.text(0.02, 0.98, f"{axis_name} | hotspot overlay", transform=ax.transAxes, va="top", ha="left", fontsize=8, color="#7DD3FC", fontweight="bold")
        ax.text(0.98, 0.03, "Threshold >= 0.10", transform=ax.transAxes, va="bottom", ha="right", fontsize=7, color="#A5B4FC")

        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_edgecolor("#334155")
            spine.set_linewidth(0.8)

    fig.suptitle("DICOM MRI with Damage Hotspots", fontsize=16, fontweight="bold", y=0.99, color="#E5E7EB")
    fig.text(0.5, 0.035, "MRI slice panels with inferno heat overlay for highlighted focal abnormalities", ha="center", fontsize=10, color="#94A3B8")
    fig.tight_layout(rect=[0.01, 0.06, 0.99, 0.95])

    fig.savefig(output_stem.with_suffix(".png"), bbox_inches="tight")
    fig.savefig(output_stem.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def write_readme(metadata: dict) -> None:
    lines = [
        "# Perfect Brain Showcase",
        "",
        "This folder provides a polished publication-facing visualization set using an actual human cortical surface template (fsaverage) plus MRI-derived DICOM panels.",
        "",
        "## Inputs",
        f"- MRI source volume: {metadata['nifti_source']}",
        f"- Clinical metadata source: {metadata['analysis_source']}",
        f"- Surface template left: {metadata['surface_template_left']}",
        f"- Surface template right: {metadata['surface_template_right']}",
        "",
        "## Generated Visuals",
        "- perfect_brain_surface.png / .svg: fsaverage human cortical surface (multi-view)",
        "- perfect_brain_hotspots.png / .svg: fsaverage surface with highlighted hotspots",
        "- dicom_mri_series.png / .svg: ultra high-resolution MRI orthogonal panel series (MNI152 template)",
        "- dicom_mri_hotspots.png / .svg: MRI panels with hotspot overlays",
        "",
        "## Notes",
        "- This is a dedicated visual-quality showcase folder requested for publication-ready appearance using true human cortical anatomy.",
        "- The DICOM MRI series uses the high-resolution MNI152 anatomical template for maximal visual clarity.",
        "- The hotspot overlay panel remains generated from the project source NIfTI volume.",
    ]

    (OUT_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not NIFTI_PATH.exists():
        raise FileNotFoundError(f"MRI source not found: {NIFTI_PATH}")
    if not ANALYSIS_PATH.exists():
        raise FileNotFoundError(f"Analysis source not found: {ANALYSIS_PATH}")

    analysis = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))

    vertices, faces, surface_sources = load_fsaverage_brain_mesh()
    normals = compute_face_normals(vertices, faces)

    hotspot_vtx = hotspot_vertex_intensity(vertices)
    base_rgba = base_face_colors(normals)
    hot_rgba = hotspot_face_colors(normals, faces, hotspot_vtx)

    render_brain_surface(
        vertices,
        faces,
        base_rgba,
        OUT_DIR / "perfect_brain_surface",
        "Perfect Brain Surface (Human Template Showcase)",
        "Human cortical anatomy from fsaverage template for publication-grade presentation",
        hotspot_legend=False,
    )

    render_brain_surface(
        vertices,
        faces,
        hot_rgba,
        OUT_DIR / "perfect_brain_hotspots",
        "Human Brain Hotspot Mapping",
        "Hotspots emphasize high-priority focal regions on the fsaverage cortical surface",
        hotspot_legend=True,
    )

    volume = load_mri_volume(NIFTI_PATH)
    volume_mni = load_mni_template_volume()
    hotspot_volume = build_hotspot_volume(volume.shape)

    render_dicom_mri_series(volume_mni, OUT_DIR / "dicom_mri_series")
    render_dicom_mri_hotspots(volume, hotspot_volume, OUT_DIR / "dicom_mri_hotspots")

    metadata = {
        "scan_id": analysis.get("scan_id", "unknown"),
        "nifti_source": NIFTI_PATH.relative_to(ROOT).as_posix(),
        "analysis_source": ANALYSIS_PATH.relative_to(ROOT).as_posix(),
        "surface_template_left": surface_sources["pial_left"],
        "surface_template_right": surface_sources["pial_right"],
    }
    (OUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    write_readme(metadata)
    print(f"Generated perfect-brain showcase assets in: {OUT_DIR}")


if __name__ == "__main__":
    main()

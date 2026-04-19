from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib

# Use a headless backend for reproducible generation from terminal sessions.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgb
from matplotlib.patches import Patch
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "outputs" / "export"
ANALYSIS_DIR = ROOT / "outputs" / "analysis"

DOCS_DIR = ROOT / "docs" / "final-publication"
CASES_DIR = DOCS_DIR / "cases"

PRIMARY_SCAN_ID = "088b7515-bcfb-441c-85d0-f0e24f2f7300"
PREFERRED_MESH_NAMES = (
    "brain_xq_v2_web.obj",
    "brain_hq_v2_web.obj",
    "brain_v2_web.obj",
)

SEVERITY_COLORS = {
    "BLUE": "#3B82F6",
    "GREEN": "#22C55E",
    "YELLOW": "#EAB308",
    "ORANGE": "#F97316",
    "RED": "#EF4444",
}

SEVERITY_WEIGHTS = {
    "BLUE": 0.0,
    "GREEN": 0.35,
    "YELLOW": 0.55,
    "ORANGE": 0.78,
    "RED": 1.0,
}


@dataclass(frozen=True)
class CaseAsset:
    scan_id: str
    patient_label: str
    case_dir: Path
    mesh_path: Path
    analysis_path: Path


def parse_obj(obj_path: Path) -> tuple[np.ndarray, np.ndarray]:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []

    with obj_path.open("r", encoding="utf-8", errors="ignore") as file:
        for line in file:
            if line.startswith("v "):
                parts = line.strip().split()
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif line.startswith("f "):
                parts = line.strip().split()[1:]
                raw_idx: list[int] = []
                for token in parts:
                    idx_token = token.split("/")[0]
                    if not idx_token:
                        continue
                    idx = int(idx_token)
                    if idx < 0:
                        idx = len(vertices) + idx
                    else:
                        idx -= 1
                    raw_idx.append(idx)

                if len(raw_idx) == 3:
                    faces.append(raw_idx)
                elif len(raw_idx) > 3:
                    # Fan triangulation for polygonal faces.
                    for i in range(1, len(raw_idx) - 1):
                        faces.append([raw_idx[0], raw_idx[i], raw_idx[i + 1]])

    if not vertices or not faces:
        raise ValueError(f"Invalid OBJ mesh or empty geometry: {obj_path}")

    return np.asarray(vertices, dtype=np.float32), np.asarray(faces, dtype=np.int32)


def normalize_vertices(vertices: np.ndarray) -> np.ndarray:
    centered = vertices - vertices.mean(axis=0, keepdims=True)
    scale = float(np.max(np.ptp(centered, axis=0)))
    if scale <= 0:
        return centered
    return centered / scale


def align_vertices_pca(vertices: np.ndarray) -> np.ndarray:
    centered = vertices - vertices.mean(axis=0, keepdims=True)
    covariance = np.cov(centered.T)
    eig_vals, eig_vecs = np.linalg.eigh(covariance)
    order = np.argsort(eig_vals)[::-1]
    basis = eig_vecs[:, order]

    aligned = centered @ basis

    # Keep orientation deterministic across runs.
    for axis in range(3):
        if float(np.median(aligned[:, axis])) < 0:
            aligned[:, axis] *= -1.0
    return aligned


def normalize_vector(v: np.ndarray) -> np.ndarray:
    denom = float(np.linalg.norm(v))
    return v / denom if denom > 0 else v


def compute_face_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    tris = vertices[faces]
    edges_a = tris[:, 1] - tris[:, 0]
    edges_b = tris[:, 2] - tris[:, 0]
    normals = np.cross(edges_a, edges_b)

    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    return normals / lengths


def compute_light_intensity(normals: np.ndarray) -> np.ndarray:
    key = normalize_vector(np.asarray([0.36, -0.14, 0.92], dtype=np.float32))
    fill = normalize_vector(np.asarray([-0.4, 0.3, 0.7], dtype=np.float32))
    rim = normalize_vector(np.asarray([0.0, 0.9, -0.2], dtype=np.float32))

    key_i = np.clip(normals @ key, 0.0, 1.0)
    fill_i = np.clip(normals @ fill, 0.0, 1.0)
    rim_i = np.clip(normals @ rim, 0.0, 1.0)

    intensity = 0.24 + 0.52 * key_i + 0.26 * fill_i + 0.18 * rim_i
    return np.clip(intensity, 0.0, 1.0)


def shaded_base_face_colors(normals: np.ndarray, base_hex: str) -> np.ndarray:
    base = np.asarray(to_rgb(base_hex), dtype=np.float32)
    intensity = compute_light_intensity(normals)
    shaded_rgb = np.clip(base[None, :] * (0.58 + 0.62 * intensity[:, None]), 0.0, 1.0)
    alpha = np.ones((len(shaded_rgb), 1), dtype=np.float32)
    return np.concatenate([shaded_rgb, alpha], axis=1)


def face_range(region: dict, n_faces: int) -> tuple[int, int]:
    start = int(region.get("start_face", 0) or 0)
    end_raw = region.get("end_face", region.get("end_frame", start))
    end = int(end_raw or start)

    s = max(0, min(start, n_faces))
    e = max(0, min(end, n_faces))
    if e < s:
        s, e = e, s
    return s, e


def severity_face_colors(normals: np.ndarray, n_faces: int, damage_summary: list[dict]) -> np.ndarray:
    base_colors = shaded_base_face_colors(normals, "#C9D5E3")[:, :3]
    overlay = base_colors.copy()

    for region in damage_summary:
        label = str(region.get("severity_label", "BLUE")).upper()
        target = np.asarray(to_rgb(SEVERITY_COLORS.get(label, "#9CA3AF")), dtype=np.float32)
        blend = 0.45 if label == "BLUE" else 0.86
        s, e = face_range(region, n_faces)
        if e > s:
            overlay[s:e] = np.clip((1.0 - blend) * base_colors[s:e] + blend * target, 0.0, 1.0)

    alpha = np.ones((n_faces, 1), dtype=np.float32)
    return np.concatenate([overlay, alpha], axis=1)


def severity_face_weights(n_faces: int, damage_summary: list[dict]) -> np.ndarray:
    weights = np.zeros(n_faces, dtype=np.float32)
    for region in damage_summary:
        label = str(region.get("severity_label", "BLUE")).upper()
        score = float(SEVERITY_WEIGHTS.get(label, 0.0))
        s, e = face_range(region, n_faces)
        if e > s:
            weights[s:e] = np.maximum(weights[s:e], score)
    return weights


def vertex_damage_weights(n_vertices: int, faces: np.ndarray, face_weights: np.ndarray) -> np.ndarray:
    weights = np.zeros(n_vertices, dtype=np.float32)
    counts = np.zeros(n_vertices, dtype=np.float32)

    for idx, tri in enumerate(faces):
        score = float(face_weights[idx])
        if score <= 0:
            continue
        weights[tri] += score
        counts[tri] += 1.0

    valid = counts > 0
    weights[valid] /= counts[valid]
    return weights


def cortical_face_mask(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    centers = vertices[faces].mean(axis=1)
    low_z = float(np.percentile(centers[:, 2], 8.0))
    radial = np.linalg.norm(centers[:, :2], axis=1)
    radial_hi = float(np.percentile(radial, 99.6))

    mask = (centers[:, 2] >= low_z) & (radial <= radial_hi)
    if int(np.count_nonzero(mask)) < int(0.55 * len(faces)):
        return np.ones(len(faces), dtype=bool)
    return mask


def style_3d_axis(ax: plt.Axes, vertices: np.ndarray, elev: float, azim: float) -> None:
    xyz_min = np.min(vertices, axis=0)
    xyz_max = np.max(vertices, axis=0)
    center = (xyz_max + xyz_min) / 2.0
    spans = np.maximum(xyz_max - xyz_min, 1e-3)
    radius = float(np.max(spans) * 0.54)

    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
    if hasattr(ax, "set_box_aspect"):
        ax.set_box_aspect((spans[0], spans[1], spans[2]))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()


def render_3d_surface(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_rgba: np.ndarray,
    output_stem: Path,
    title: str,
) -> None:
    views = [("Left lateral", 18, 130), ("Superior", 82, -90), ("Right lateral", 18, 40)]

    fig = plt.figure(figsize=(15.0, 5.2), dpi=240)
    fig.patch.set_facecolor("#FBFDFF")

    for idx, (label, elev, azim) in enumerate(views, start=1):
        ax = fig.add_subplot(1, 3, idx, projection="3d")
        mesh = Poly3DCollection(
            vertices[faces],
            facecolors=face_rgba,
            edgecolor=(0.55, 0.62, 0.72, 0.11),
            linewidth=0.04,
            alpha=1.0,
        )
        ax.add_collection3d(mesh)
        style_3d_axis(ax, vertices, elev=elev, azim=azim)
        ax.set_title(label, fontsize=10, fontweight="bold", pad=2)

    fig.suptitle(title, fontsize=15, fontweight="bold", y=0.965)
    fig.text(0.5, 0.03, "Shaded multi-view surface from actual OBJ mesh", ha="center", fontsize=10, color="#4B5563")

    fig.savefig(output_stem.with_suffix(".png"), bbox_inches="tight")
    fig.savefig(output_stem.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def render_3d_region_overlay(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_rgba: np.ndarray,
    output_stem: Path,
    title: str,
) -> None:
    views = [("Clinical lateral", 18, 130), ("Dorsal", 84, -90), ("Contralateral", 18, 40)]

    fig = plt.figure(figsize=(15.0, 5.6), dpi=240)
    fig.patch.set_facecolor("#FBFDFF")

    for idx, (label, elev, azim) in enumerate(views, start=1):
        ax = fig.add_subplot(1, 3, idx, projection="3d")
        mesh = Poly3DCollection(
            vertices[faces],
            facecolors=face_rgba,
            edgecolor=(0.48, 0.54, 0.62, 0.12),
            linewidth=0.04,
            alpha=1.0,
        )
        ax.add_collection3d(mesh)
        style_3d_axis(ax, vertices, elev=elev, azim=azim)
        ax.set_title(label, fontsize=10, fontweight="bold", pad=2)

    handles = [Patch(facecolor=color, edgecolor="none", label=label) for label, color in SEVERITY_COLORS.items()]
    fig.legend(handles=handles, loc="upper center", ncol=5, bbox_to_anchor=(0.5, 0.94), frameon=False, fontsize=10)

    fig.suptitle(title, fontsize=15, fontweight="bold", y=0.99)
    fig.text(0.5, 0.03, "Severity color mapping projected from region face ranges", ha="center", fontsize=10, color="#4B5563")

    fig.savefig(output_stem.with_suffix(".png"), bbox_inches="tight")
    fig.savefig(output_stem.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def density_projection(a: np.ndarray, b: np.ndarray, bins: int = 320, weights: np.ndarray | None = None) -> np.ndarray:
    hist, _, _ = np.histogram2d(a, b, bins=bins, range=[[0.0, 1.0], [0.0, 1.0]], weights=weights)
    return np.log1p(hist.T)


def compute_projection_maps(vertices: np.ndarray, weights: np.ndarray | None = None, bins: int = 320) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    verts01 = (vertices - vertices.min(axis=0)) / np.maximum(vertices.max(axis=0) - vertices.min(axis=0), 1e-8)
    axial = density_projection(verts01[:, 0], verts01[:, 1], bins=bins, weights=weights)
    coronal = density_projection(verts01[:, 0], verts01[:, 2], bins=bins, weights=weights)
    sagittal = density_projection(verts01[:, 1], verts01[:, 2], bins=bins, weights=weights)
    return axial, coronal, sagittal


def render_dicom_like_projections(vertices: np.ndarray, analysis: dict, output_stem: Path) -> None:
    axial, coronal, sagittal = compute_projection_maps(vertices, weights=None, bins=320)

    fig, axes = plt.subplots(2, 2, figsize=(11.8, 9.2), dpi=220)
    fig.patch.set_facecolor("#F8FBFF")

    panels = [
        (axes[0, 0], axial, "Axial projection"),
        (axes[0, 1], coronal, "Coronal projection"),
        (axes[1, 0], sagittal, "Sagittal projection"),
    ]

    for ax, img, panel_title in panels:
        ax.imshow(img, cmap="gray", origin="lower")
        h, w = img.shape
        ax.axhline(h * 0.5, color="#D1D5DB", lw=0.7)
        ax.axvline(w * 0.5, color="#D1D5DB", lw=0.7)
        ax.set_title(panel_title, fontsize=11, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])

    info_ax = axes[1, 1]
    info_ax.axis("off")

    dicom_profile = analysis.get("dicom_profile", {}) if isinstance(analysis.get("dicom_profile"), dict) else {}
    modality = dicom_profile.get("modality", "unknown")
    series = dicom_profile.get("series", []) if isinstance(dicom_profile.get("series"), list) else []
    slice_counts = [int(s.get("slice_count", 0)) for s in series if s.get("slice_count") is not None]
    matrix = series[0].get("matrix", ["n/a", "n/a"]) if series else ["n/a", "n/a"]
    tools = dicom_profile.get("tools", []) if isinstance(dicom_profile.get("tools"), list) else []

    info_lines = [
        "DICOM Workstation-style View",
        f"Scan: {analysis.get('scan_id', 'unknown')}",
        f"Modality: {modality}",
        f"Matrix: {matrix[0]} x {matrix[1]}",
        f"Slices: {min(slice_counts) if slice_counts else 0} to {max(slice_counts) if slice_counts else 0}",
        "Tools:",
        ", ".join(tools[:6]) if tools else "n/a",
    ]

    y = 0.95
    for idx, line in enumerate(info_lines):
        fs = 12 if idx == 0 else 10
        weight = "bold" if idx == 0 else "normal"
        info_ax.text(0.02, y, line, fontsize=fs, fontweight=weight, va="top", color="#111827")
        y -= 0.13 if idx == 0 else 0.1

    fig.suptitle("Mesh-derived DICOM-style Orthogonal Projections", fontsize=14, fontweight="bold", y=0.98)
    fig.tight_layout(rect=[0.0, 0.02, 1.0, 0.96])

    fig.savefig(output_stem.with_suffix(".png"), bbox_inches="tight")
    fig.savefig(output_stem.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def render_dicom_damage_overlay(vertices: np.ndarray, damage_weights: np.ndarray, output_stem: Path) -> None:
    base_maps = compute_projection_maps(vertices, weights=None, bins=320)
    damage_maps = compute_projection_maps(vertices, weights=damage_weights, bins=320)

    fig, axes = plt.subplots(1, 3, figsize=(14.8, 4.6), dpi=240)
    fig.patch.set_facecolor("#F8FBFF")

    labels = ["Axial damage overlay", "Coronal damage overlay", "Sagittal damage overlay"]
    max_damage = max(float(np.max(m)) for m in damage_maps)
    max_damage = max(max_damage, 1e-8)

    for ax, base_img, damage_img, panel_title in zip(axes, base_maps, damage_maps, labels):
        ax.imshow(base_img, cmap="gray", origin="lower")
        normalized_damage = damage_img / max_damage
        masked = np.ma.masked_where(normalized_damage < 0.06, normalized_damage)
        ax.imshow(masked, cmap="inferno", origin="lower", alpha=np.clip(normalized_damage * 0.9, 0.0, 0.9))
        h, w = base_img.shape
        ax.axhline(h * 0.5, color="#E5E7EB", lw=0.6)
        ax.axvline(w * 0.5, color="#E5E7EB", lw=0.6)
        ax.set_title(panel_title, fontsize=11, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])

    fig.suptitle("DICOM Projections with Highlighted Damage Regions", fontsize=14, fontweight="bold", y=0.98)
    fig.text(0.5, 0.03, "Heat overlay is weighted by region severity and mapped from mesh face ranges", ha="center", fontsize=10, color="#4B5563")
    fig.tight_layout(rect=[0.0, 0.07, 1.0, 0.93])

    fig.savefig(output_stem.with_suffix(".png"), bbox_inches="tight")
    fig.savefig(output_stem.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def slug(scan_id: str) -> str:
    return scan_id.split("-")[0]


def pick_mesh_file(scan_id: str) -> Path:
    scan_dir = EXPORT_DIR / scan_id
    if not scan_dir.exists():
        raise FileNotFoundError(f"Export folder not found for scan: {scan_id}")

    for name in PREFERRED_MESH_NAMES:
        candidate = scan_dir / name
        if candidate.exists():
            return candidate

    all_obj = sorted(scan_dir.glob("*.obj"))
    if not all_obj:
        raise FileNotFoundError(f"No OBJ mesh found for scan: {scan_id}")
    return all_obj[0]


def analysis_file(scan_id: str) -> Path:
    path = ANALYSIS_DIR / scan_id / "analysis.json"
    if not path.exists():
        raise FileNotFoundError(f"Analysis not found: {path}")
    return path


def available_scans() -> list[str]:
    ids: list[str] = []
    for path in sorted(EXPORT_DIR.iterdir()):
        if not path.is_dir():
            continue
        has_obj = any(path.glob("*.obj"))
        if not has_obj:
            continue
        if not (ANALYSIS_DIR / path.name / "analysis.json").exists():
            continue
        ids.append(path.name)
    return ids


def pick_case_ids() -> list[str]:
    ids = available_scans()
    if not ids:
        raise RuntimeError("No export scans with paired analysis were found.")

    chosen: list[str] = []
    if PRIMARY_SCAN_ID in ids:
        chosen.append(PRIMARY_SCAN_ID)
    else:
        chosen.append(ids[0])

    candidates: list[tuple[float, str]] = []
    for scan_id in ids:
        if scan_id in chosen:
            continue
        payload = json.loads(analysis_file(scan_id).read_text(encoding="utf-8"))
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        triage = float(metrics.get("triage_score", 0.0) or 0.0)
        severe = float(metrics.get("severe_regions", 0.0) or 0.0)
        confidence = float(payload.get("overall_confidence", 0.0) or 0.0)
        score = triage + (severe * 0.2) + (confidence * 0.01)
        candidates.append((score, scan_id))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        chosen.append(candidates[0][1])

    return chosen


def patient_label(analysis: dict, scan_id: str) -> str:
    name = str(analysis.get("patient_name") or "Patient")
    code = str(analysis.get("patient_code") or scan_id[:8])
    return f"{name} ({code})"


def write_case_readme(case: CaseAsset, analysis: dict) -> None:
    metrics = analysis.get("metrics", {}) if isinstance(analysis.get("metrics"), dict) else {}
    damage_summary = analysis.get("damage_summary", []) if isinstance(analysis.get("damage_summary"), list) else []

    top_regions = sorted(
        damage_summary,
        key=lambda row: float(row.get("pct_region", 0.0) or 0.0),
        reverse=True,
    )[:3]
    top_line = ", ".join(
        f"{r.get('anatomical_name', 'unknown')} ({float(r.get('pct_region', 0.0) or 0.0):.1f}%)"
        for r in top_regions
    )
    if not top_line:
        top_line = "n/a"

    lines = [
        f"# Case Visuals: {case.patient_label}",
        "",
        f"- Scan ID: {case.scan_id}",
        f"- Risk band: {analysis.get('risk_band', 'unknown')}",
        f"- Triage score: {float(metrics.get('triage_score', 0.0) or 0.0):.2f}",
        f"- Mesh source: {case.mesh_path.relative_to(ROOT).as_posix()}",
        f"- Analysis source: {case.analysis_path.relative_to(ROOT).as_posix()}",
        f"- Top burdened regions: {top_line}",
        "",
        "## 1) 3D Reconstruction Surface",
        "![3D Reconstruction](3d_reconstruction.png)",
        "",
        "## 2) 3D Reconstruction with Region Severity Marking",
        "![3D Region Marking](3d_region_marking.png)",
        "",
        "## 3) DICOM-style Orthogonal Projections",
        "![DICOM Projections](dicom_projections.png)",
        "",
        "## 4) DICOM Damage Highlight Overlay",
        "![DICOM Damage Overlay](dicom_damage_overlay.png)",
        "",
        "## Files",
        "- 3d_reconstruction.png",
        "- 3d_reconstruction.svg",
        "- 3d_region_marking.png",
        "- 3d_region_marking.svg",
        "- dicom_projections.png",
        "- dicom_projections.svg",
        "- dicom_damage_overlay.png",
        "- dicom_damage_overlay.svg",
    ]

    (case.case_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_cases_index(cases: list[CaseAsset], analyses: dict[str, dict]) -> None:
    lines = [
        "# Reconstruction Case Library",
        "",
        "This folder contains case-scoped actual reconstruction and DICOM visual assets.",
        "",
    ]

    for case in cases:
        analysis = analyses[case.scan_id]
        metrics = analysis.get("metrics", {}) if isinstance(analysis.get("metrics"), dict) else {}
        lines.extend(
            [
                f"## {case.patient_label}",
                f"- Scan ID: {case.scan_id}",
                f"- Risk: {analysis.get('risk_band', 'unknown')}",
                f"- Triage score: {float(metrics.get('triage_score', 0.0) or 0.0):.2f}",
                f"- Gallery: {case.scan_id}/README.md",
                "",
            ]
        )

    (CASES_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def write_master_gallery(cases: list[CaseAsset], analyses: dict[str, dict]) -> None:
    lines = [
        "# Actual Reconstruction and DICOM Projection Gallery",
        "",
        "These are real visualization outputs rendered from exported OBJ meshes and paired analysis metadata.",
        "",
        "## Case Overview",
    ]

    for case in cases:
        analysis = analyses[case.scan_id]
        metrics = analysis.get("metrics", {}) if isinstance(analysis.get("metrics"), dict) else {}
        lines.extend(
            [
                f"- {case.patient_label} | scan {case.scan_id} | risk {analysis.get('risk_band', 'unknown')} | triage {float(metrics.get('triage_score', 0.0) or 0.0):.2f}",
            ]
        )

    lines.append("")
    for idx, case in enumerate(cases, start=1):
        lines.extend(
            [
                f"## Case {idx}: {case.patient_label}",
                f"- Scan ID: {case.scan_id}",
                f"- Mesh: {case.mesh_path.relative_to(ROOT).as_posix()}",
                f"- Analysis: {case.analysis_path.relative_to(ROOT).as_posix()}",
                f"- Case folder: cases/{case.scan_id}/README.md",
                "",
                "### 3D Reconstruction Surface",
                f"![Case {idx} Reconstruction](cases/{case.scan_id}/3d_reconstruction.png)",
                "",
                "### 3D Severity Region Marking",
                f"![Case {idx} Region Marking](cases/{case.scan_id}/3d_region_marking.png)",
                "",
                "### DICOM Orthogonal Projections",
                f"![Case {idx} DICOM Projections](cases/{case.scan_id}/dicom_projections.png)",
                "",
                "### DICOM Damage Overlay",
                f"![Case {idx} DICOM Damage Overlay](cases/{case.scan_id}/dicom_damage_overlay.png)",
                "",
            ]
        )

    (DOCS_DIR / "ACTUAL_RECON_DICOM_GALLERY.md").write_text("\n".join(lines), encoding="utf-8")


def generate_case_assets(scan_id: str, analyses: dict[str, dict]) -> CaseAsset:
    analysis_path = analysis_file(scan_id)
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analyses[scan_id] = analysis

    mesh_path = pick_mesh_file(scan_id)
    case = CaseAsset(
        scan_id=scan_id,
        patient_label=patient_label(analysis, scan_id),
        case_dir=CASES_DIR / scan_id,
        mesh_path=mesh_path,
        analysis_path=analysis_path,
    )
    case.case_dir.mkdir(parents=True, exist_ok=True)

    vertices, faces = parse_obj(mesh_path)
    vertices_aligned = align_vertices_pca(vertices)
    vertices_norm = normalize_vertices(vertices_aligned)
    normals = compute_face_normals(vertices_norm, faces)

    damage_summary = analysis.get("damage_summary", []) if isinstance(analysis.get("damage_summary"), list) else []
    surface_colors = shaded_base_face_colors(normals, "#CBD5E1")
    region_colors = severity_face_colors(normals, len(faces), damage_summary)

    view_mask = cortical_face_mask(vertices_norm, faces)
    faces_view = faces[view_mask]
    surface_colors_view = surface_colors[view_mask]
    region_colors_view = region_colors[view_mask]

    face_weights = severity_face_weights(len(faces), damage_summary)
    vtx_damage = vertex_damage_weights(len(vertices_norm), faces, face_weights)

    render_3d_surface(
        vertices_norm,
        faces_view,
        surface_colors_view,
        case.case_dir / "3d_reconstruction",
        f"Actual 3D Reconstruction: {case.patient_label}",
    )

    render_3d_region_overlay(
        vertices_norm,
        faces_view,
        region_colors_view,
        case.case_dir / "3d_region_marking",
        f"3D Region Severity Mapping: {case.patient_label}",
    )

    render_dicom_like_projections(vertices_norm, analysis, case.case_dir / "dicom_projections")
    render_dicom_damage_overlay(vertices_norm, vtx_damage, case.case_dir / "dicom_damage_overlay")

    write_case_readme(case, analysis)
    return case


def write_root_images_readme(cases: list[CaseAsset]) -> None:
    # Keep a compatibility note for any existing references to docs/final-publication/images.
    legacy_dir = DOCS_DIR / "images"
    legacy_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Actual Reconstruction Visuals",
        "",
        "Assets are now organized by patient under docs/final-publication/cases/.",
        "",
        "Available case folders:",
    ]
    for case in cases:
        lines.append(f"- ../cases/{case.scan_id}/README.md")

    lines.append("")
    lines.append("Master gallery: ../ACTUAL_RECON_DICOM_GALLERY.md")

    (legacy_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    CASES_DIR.mkdir(parents=True, exist_ok=True)

    analyses: dict[str, dict] = {}
    case_ids = pick_case_ids()
    cases = [generate_case_assets(scan_id, analyses) for scan_id in case_ids]

    write_cases_index(cases, analyses)
    write_master_gallery(cases, analyses)
    write_root_images_readme(cases)

    case_text = ", ".join(case.scan_id for case in cases)
    print(f"Generated reconstruction and DICOM assets for scans: {case_text}")


if __name__ == "__main__":
    main()
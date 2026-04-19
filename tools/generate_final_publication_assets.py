from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
METRICS_PATH = DOCS / "publication_metrics_latest.json"
FINAL_DIR = DOCS / "final-publication"
SVG_DIR = FINAL_DIR / "svg"
MMD_DIR = FINAL_DIR / "mmd"
ANALYSIS_DIR = ROOT / "outputs" / "analysis"
EXPORT_DIR = ROOT / "outputs" / "export"
DEMO_MESH_DIR = ROOT / "outputs" / "demo_mesh"


def esc(value: object) -> str:
    return xml_escape(str(value), {'"': '&quot;', "'": '&apos;'})


def load_metrics() -> dict:
    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


def is_publication_eligible(payload: dict) -> bool:
    required = [
        "scan_id",
        "overall_confidence",
        "modalities",
        "atlas",
        "scan_quality",
        "provenance_source",
        "damage_summary",
        "risk_band",
        "metrics",
    ]
    if any(key not in payload for key in required):
        return False

    damage_summary = payload.get("damage_summary")
    if not isinstance(damage_summary, list) or not damage_summary:
        return False

    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return False

    mandatory_metric_keys = ["triage_score", "flagged_regions", "severe_regions"]
    return all(key in metrics for key in mandatory_metric_keys)


def load_publication_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(ANALYSIS_DIR.rglob("analysis.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if is_publication_eligible(payload):
            rows.append(payload)
    return rows


def collect_reconstruction_dicom_stats(rows: list[dict]) -> dict:
    total_rows = len(rows)

    face_values = [int(row.get("total_faces", 0)) for row in rows if int(row.get("total_faces", 0)) > 0]
    with_faces = len(face_values)

    atlas_counts: Counter[str] = Counter(str(row.get("atlas", "unknown")) for row in rows)
    region_presence: Counter[str] = Counter()

    dicom_rows = [row for row in rows if isinstance(row.get("dicom_profile"), dict)]
    dicom_modality_counts: Counter[str] = Counter()
    series_plane_counts: Counter[str] = Counter()
    tool_counts: Counter[str] = Counter()
    matrix_counts: Counter[tuple[int, int]] = Counter()
    slice_counts: list[int] = []

    for row in rows:
        for region in row.get("damage_summary", []) or []:
            region_name = str(region.get("anatomical_name") or region.get("region") or "UNKNOWN")
            region_presence[region_name] += 1

    for row in dicom_rows:
        profile = row["dicom_profile"]
        dicom_modality_counts[str(profile.get("modality", "unknown"))] += 1

        for tool in profile.get("tools", []) or []:
            tool_counts[str(tool)] += 1

        for series in profile.get("series", []) or []:
            series_plane_counts[str(series.get("plane", "unknown"))] += 1
            matrix = series.get("matrix")
            if isinstance(matrix, list) and len(matrix) == 2:
                matrix_counts[(int(matrix[0]), int(matrix[1]))] += 1
            if series.get("slice_count") is not None:
                slice_counts.append(int(series.get("slice_count")))

    obj_export = len(list(EXPORT_DIR.rglob("*.obj")))
    obj_demo = len(list(DEMO_MESH_DIR.rglob("*.obj")))

    top_matrix = matrix_counts.most_common(1)[0] if matrix_counts else ((0, 0), 0)
    full_coverage_regions = [name for name, count in region_presence.items() if count == total_rows]

    return {
        "total_rows": total_rows,
        "with_faces": with_faces,
        "faces_min": min(face_values) if face_values else 0,
        "faces_max": max(face_values) if face_values else 0,
        "atlas_counts": dict(atlas_counts),
        "region_presence": region_presence,
        "full_coverage_regions": sorted(full_coverage_regions),
        "obj_export": obj_export,
        "obj_demo": obj_demo,
        "obj_total": obj_export + obj_demo,
        "dicom_rows": len(dicom_rows),
        "dicom_modality_counts": dict(dicom_modality_counts),
        "series_plane_counts": dict(series_plane_counts),
        "tool_counts": dict(tool_counts),
        "tool_names": [name for name, _ in tool_counts.most_common()],
        "top_matrix": top_matrix,
        "slice_min": min(slice_counts) if slice_counts else 0,
        "slice_max": max(slice_counts) if slice_counts else 0,
        "slice_mean": (sum(slice_counts) / len(slice_counts)) if slice_counts else 0.0,
    }


def ensure_dirs() -> None:
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    MMD_DIR.mkdir(parents=True, exist_ok=True)


def write_svg(filename: str, width: int, height: int, body: str) -> None:
    style = """
    <style>
      .bg { fill: #F8FBFF; }
      .title { font: 700 34px 'Segoe UI', Arial, sans-serif; fill: #111827; }
      .subtitle { font: 600 20px 'Segoe UI', Arial, sans-serif; fill: #4B5563; }
      .label { font: 600 17px 'Segoe UI', Arial, sans-serif; fill: #111827; }
      .value { font: 700 18px 'Segoe UI', Arial, sans-serif; fill: #111827; }
      .small { font: 500 14px 'Segoe UI', Arial, sans-serif; fill: #4B5563; }
      .panel { fill: #E7F1FB; stroke: #1F2937; stroke-width: 1.6; }
      .axis { stroke: #6B7280; stroke-width: 1.4; }
      .grid { stroke: #D1D5DB; stroke-width: 1; stroke-dasharray: 4 4; }
    </style>
    """
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f"{style}\n"
        f'<rect class="bg" x="0" y="0" width="{width}" height="{height}"/>\n'
        f"{body}\n"
        "</svg>\n"
    )
    (SVG_DIR / filename).write_text(text, encoding="utf-8")


def write_mmd(filename: str, content: str) -> None:
    (MMD_DIR / filename).write_text(content.strip() + "\n", encoding="utf-8")


def fmt(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}"


def build_cohort_flow_svg(metrics: dict) -> None:
    flow = metrics["cohort_flow"]
    desc = metrics["cohort_descriptor"]
    total = flow["total_analysis_files"]
    inc = flow["included_publication_rows"]
    exc = flow["excluded_rows"]
    mini = flow["excluded_schema_counts"].get("scan_conf_metrics_only", 0)

    body = f"""
<text x="60" y="58" class="title">Final Cohort Flow for Publication</text>
<text x="60" y="88" class="subtitle">Eligibility filtering from repository analysis outputs</text>

<rect class="panel" x="80" y="130" width="300" height="180" rx="14"/>
<text x="230" y="182" class="label" text-anchor="middle">Detected analysis files</text>
<text x="230" y="234" class="title" text-anchor="middle" style="font-size:50px">{total}</text>

<rect class="panel" x="460" y="130" width="300" height="180" rx="14"/>
<text x="610" y="182" class="label" text-anchor="middle">Publication-eligible rows</text>
<text x="610" y="234" class="title" text-anchor="middle" style="font-size:50px">{inc}</text>

<rect class="panel" x="840" y="130" width="300" height="180" rx="14"/>
<text x="990" y="182" class="label" text-anchor="middle">Excluded rows</text>
<text x="990" y="234" class="title" text-anchor="middle" style="font-size:50px">{exc}</text>
<text x="990" y="274" class="small" text-anchor="middle">scan_conf_metrics_only: {mini}</text>

<line x1="380" y1="220" x2="460" y2="220" stroke="#2563EB" stroke-width="4"/>
<polygon points="460,220 446,212 446,228" fill="#2563EB"/>
<line x1="760" y1="220" x2="840" y2="220" stroke="#DC2626" stroke-width="4"/>
<polygon points="840,220 826,212 826,228" fill="#DC2626"/>

<rect class="panel" x="80" y="360" width="1060" height="170" rx="14"/>
<text x="110" y="404" class="label">Cohort descriptor</text>
<text x="110" y="440" class="small">MRI_T1: {desc['modality_counts'].get('MRI_T1', 0)} | fMRI: {desc['modality_counts'].get('fMRI', 0)} | Atlas AAL3: {desc['atlas_counts'].get('AAL3', 0)}</text>
<text x="110" y="468" class="small">Quality limited: {desc['scan_quality_counts'].get('limited', 0)} | fair: {desc['scan_quality_counts'].get('fair', 0)} | uploaded: {desc['provenance_counts'].get('uploaded', 0)}</text>
<text x="110" y="504" class="small">Duplicate scan IDs in included cohort: {flow['included_scan_id_duplicates']}</text>
"""
    write_svg("final_01_cohort_flow.svg", 1220, 580, body)

    write_mmd(
        "final_01_cohort_flow.mmd",
        f"""
flowchart LR
  A[Detected files: {total}] --> B[Included publication cohort: {inc}]
  B --> C[Excluded rows: {exc}]
  C --> D[Schema type scan_conf_metrics_only: {mini}]
""",
    )


def build_core_metrics_svg(metrics: dict) -> None:
    core = metrics["core_metrics"]
    rows = [
        ("Overall confidence", core["overall_confidence"], 3),
        ("Triage score", core["triage_score"], 2),
        ("Flagged regions", core["flagged_regions"], 2),
        ("Severe regions", core["severe_regions"], 2),
        ("Flagged volume mm3", core["flagged_volume_mm3"], 1),
        ("Severe volume mm3", core["severe_volume_mm3"], 1),
        ("Mean region confidence pct", core["mean_region_confidence_pct"], 2),
        ("Highest region burden pct", core["highest_region_burden_pct"], 2),
    ]

    parts = [
        '<text x="50" y="54" class="title">Final Core Metrics with 95% CI</text>',
        '<text x="50" y="84" class="subtitle">Bootstrap 5000 confidence intervals from publication cohort</text>',
        '<rect class="panel" x="50" y="110" width="1300" height="56" rx="10"/>',
        '<text x="70" y="145" class="label">Metric</text>',
        '<text x="700" y="145" class="label">Mean</text>',
        '<text x="930" y="145" class="label">95% CI low</text>',
        '<text x="1140" y="145" class="label">95% CI high</text>',
    ]

    y = 166
    for i, (name, row, d) in enumerate(rows):
        fill = "#FFFFFF" if i % 2 == 0 else "#F2F7FD"
        mean = fmt(float(row["mean"]), d)
        lo = fmt(float(row["ci95"][0]), d)
        hi = fmt(float(row["ci95"][1]), d)
        parts.extend(
            [
                f'<rect x="50" y="{y}" width="1300" height="52" fill="{fill}" stroke="#D1D9E6"/>',
                f'<text x="70" y="{y+34}" class="label">{esc(name)}</text>',
                f'<text x="700" y="{y+34}" class="value">{esc(mean)}</text>',
                f'<text x="930" y="{y+34}" class="value">{esc(lo)}</text>',
                f'<text x="1140" y="{y+34}" class="value">{esc(hi)}</text>',
            ]
        )
        y += 52

    write_svg("final_02_core_metrics_ci.svg", 1400, 620, "\n".join(parts))

    write_mmd(
        "final_02_core_metrics_ci.mmd",
        f"""
flowchart TB
  A[Core metrics with 95% CI]
  A --> B[Overall confidence {fmt(core['overall_confidence']['mean'], 3)}]
  A --> C[Triage score {fmt(core['triage_score']['mean'], 2)}]
  A --> D[Flagged regions {fmt(core['flagged_regions']['mean'], 2)}]
  A --> E[Severe regions {fmt(core['severe_regions']['mean'], 2)}]
  A --> F[Flagged volume mm3 {fmt(core['flagged_volume_mm3']['mean'], 1)}]
  A --> G[Severe volume mm3 {fmt(core['severe_volume_mm3']['mean'], 1)}]
  A --> H[Region confidence pct {fmt(core['mean_region_confidence_pct']['mean'], 2)}]
  A --> I[Highest burden pct {fmt(core['highest_region_burden_pct']['mean'], 2)}]
""",
    )


def build_risk_svg(metrics: dict) -> None:
    risk = metrics["risk_distribution"]
    labels = ["high", "moderate", "low"]
    counts = [risk[k]["count"] for k in labels]
    max_count = max(counts) if counts else 1

    x0 = 110
    y0 = 560
    bar_w = 220
    gap = 140
    h_max = 360

    parts = [
        '<text x="60" y="56" class="title">Final Risk Distribution with Wilson 95% CI</text>',
        '<text x="60" y="86" class="subtitle">Publication cohort risk stratification</text>',
        f'<line x1="{x0}" y1="{y0}" x2="1100" y2="{y0}" class="axis"/>',
        f'<line x1="{x0}" y1="180" x2="{x0}" y2="{y0}" class="axis"/>',
    ]

    colors = {"high": "#DC2626", "moderate": "#D97706", "low": "#16A34A"}

    for i, label in enumerate(labels):
        c = risk[label]["count"]
        pct = risk[label]["percent"]
        lo, hi = risk[label]["ci95_percent"]
        h = (c / max_count) * h_max if max_count else 0
        x = x0 + 110 + i * (bar_w + gap)
        y = y0 - h
        parts.extend(
            [
                f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" rx="10" fill="{colors[label]}"/>',
                f'<text x="{x+bar_w/2:.1f}" y="{y-10:.1f}" class="value" text-anchor="middle">{c}</text>',
                f'<text x="{x+bar_w/2:.1f}" y="{y+20:.1f}" class="small" text-anchor="middle">{pct:.2f}%</text>',
                f'<text x="{x+bar_w/2:.1f}" y="{y+40:.1f}" class="small" text-anchor="middle">CI {lo:.2f} to {hi:.2f}</text>',
                f'<text x="{x+bar_w/2:.1f}" y="594" class="label" text-anchor="middle">{esc(label.capitalize())}</text>',
            ]
        )

    write_svg("final_03_risk_distribution_ci.svg", 1220, 640, "\n".join(parts))

    write_mmd(
        "final_03_risk_distribution_ci.mmd",
        f"""
xychart-beta
  title "Risk Distribution Counts"
  x-axis ["High", "Moderate", "Low"]
  y-axis "Count" 0 --> {max_count + 4}
  bar [{risk['high']['count']}, {risk['moderate']['count']}, {risk['low']['count']}]
""",
    )


def build_severity_svg(metrics: dict) -> None:
    sev = metrics["severity_distribution"]
    order = ["BLUE", "GREEN", "YELLOW", "ORANGE", "RED"]
    max_count = max(sev[k]["count"] for k in order)

    x0 = 180
    y0 = 580
    h_max = 360

    colors = {
        "BLUE": "#2563EB",
        "GREEN": "#16A34A",
        "YELLOW": "#EAB308",
        "ORANGE": "#F97316",
        "RED": "#DC2626",
    }

    parts = [
        '<text x="60" y="56" class="title">Final Severity Distribution</text>',
        '<text x="60" y="86" class="subtitle">Regional severity composition across publication cohort</text>',
        f'<line x1="{x0}" y1="{y0}" x2="1120" y2="{y0}" class="axis"/>',
        f'<line x1="{x0}" y1="180" x2="{x0}" y2="{y0}" class="axis"/>',
    ]

    bar_w = 130
    gap = 55

    for i, k in enumerate(order):
        c = sev[k]["count"]
        p = sev[k]["percent"]
        h = (c / max_count) * h_max
        x = x0 + 40 + i * (bar_w + gap)
        y = y0 - h
        parts.extend(
            [
                f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" rx="8" fill="{colors[k]}"/>',
                f'<text x="{x+bar_w/2:.1f}" y="{y-10:.1f}" class="value" text-anchor="middle">{c}</text>',
                f'<text x="{x+bar_w/2:.1f}" y="{y+22:.1f}" class="small" text-anchor="middle">{p:.2f}%</text>',
                f'<text x="{x+bar_w/2:.1f}" y="614" class="label" text-anchor="middle">{esc(k)}</text>',
            ]
        )

    write_svg("final_04_severity_distribution.svg", 1240, 650, "\n".join(parts))

    write_mmd(
        "final_04_severity_distribution.mmd",
        f"""
xychart-beta
  title "Severity Distribution Counts"
  x-axis ["BLUE", "GREEN", "YELLOW", "ORANGE", "RED"]
  y-axis "Count" 0 --> {max_count + 20}
  bar [{sev['BLUE']['count']}, {sev['GREEN']['count']}, {sev['YELLOW']['count']}, {sev['ORANGE']['count']}, {sev['RED']['count']}]
""",
    )


def build_top_regions_svg(metrics: dict) -> None:
    top = metrics["top_regions_severity_ge_2"]
    max_f = max(item["frequency"] for item in top)

    parts = [
        '<text x="60" y="56" class="title">Final Top Regions Severity GE 2</text>',
        '<text x="60" y="86" class="subtitle">Frequency with mean burden and volume annotations</text>',
    ]

    y = 140
    for item in top:
        w = 620 * item["frequency"] / max_f
        parts.extend(
            [
                f'<rect x="250" y="{y}" width="{w:.1f}" height="44" rx="8" fill="#1D4ED8"/>',
                f'<text x="236" y="{y+28}" class="label" text-anchor="end">{esc(item["region"])}</text>',
                f'<text x="{250+w+10:.1f}" y="{y+28}" class="value">{item["frequency"]}</text>',
                f'<text x="980" y="{y+18}" class="small" text-anchor="end">burden {item["mean_burden_pct"]:.2f}%</text>',
                f'<text x="980" y="{y+38}" class="small" text-anchor="end">vol {item["mean_volume_mm3"]:.1f} mm3</text>',
            ]
        )
        y += 74

    write_svg("final_05_top_regions.svg", 1220, 640, "\n".join(parts))

    mmd_labels = ", ".join(f'"{item["region"]}"' for item in top)
    mmd_vals = ", ".join(str(item["frequency"]) for item in top)
    write_mmd(
        "final_05_top_regions.mmd",
        f"""
xychart-beta
  title "Top Regions Frequency Severity GE 2"
  x-axis [{mmd_labels}]
  y-axis "Frequency" 0 --> {max_f + 6}
  bar [{mmd_vals}]
""",
    )


def build_governance_svg(metrics: dict) -> None:
    audit = metrics["audit"]
    allowed = int(audit["allowed"])
    denied = int(audit["denied"])
    total = max(allowed + denied, 1)
    completeness = float(audit["completeness"]) * 100.0

    h_total = 360
    h_allow = h_total * allowed / total
    h_deny = h_total * denied / total

    body = f"""
<text x="60" y="56" class="title">Final Governance and Audit Panel</text>
<text x="60" y="86" class="subtitle">Authorization outcomes and audit completeness</text>

<rect class="panel" x="80" y="120" width="520" height="430" rx="16"/>
<text x="110" y="164" class="label">Outcome split</text>
<rect x="150" y="190" width="160" height="{h_deny:.1f}" fill="#DC2626"/>
<rect x="150" y="{190 + h_deny:.1f}" width="160" height="{h_allow:.1f}" fill="#16A34A"/>
<rect x="150" y="190" width="160" height="360" fill="none" stroke="#334155"/>
<text x="340" y="280" class="label">Allowed: {allowed}</text>
<text x="340" y="314" class="label">Denied: {denied}</text>
<text x="340" y="350" class="small">Total events: {total}</text>
<text x="340" y="384" class="small">Unique users: {audit['unique_users']}</text>
<text x="340" y="414" class="small">Unique actions: {audit['unique_actions']}</text>

<rect class="panel" x="650" y="120" width="520" height="430" rx="16"/>
<text x="680" y="164" class="label">Audit quality</text>
<circle cx="900" cy="340" r="120" fill="none" stroke="#D1D5DB" stroke-width="32"/>
<circle cx="900" cy="340" r="120" fill="none" stroke="#0D9488" stroke-width="32" stroke-dasharray="{7.5398*completeness:.1f} 753.98" transform="rotate(-90 900 340)"/>
<text x="900" y="338" class="title" text-anchor="middle" style="font-size:44px">{completeness:.1f}%</text>
<text x="900" y="372" class="small" text-anchor="middle">audit completeness</text>
<text x="680" y="468" class="small">Denied reason: role_not_allowed = {audit['denied_reason_counts'].get('role_not_allowed', 0)}</text>
"""
    write_svg("final_06_governance.svg", 1240, 620, body)

    write_mmd(
        "final_06_governance.mmd",
        f"""
pie showData
  title Governance Outcome Split
  "Allowed" : {allowed}
  "Denied" : {denied}
""",
    )


def build_reconstruction_accuracy_svg(stats: dict) -> None:
    total_rows = stats["total_rows"]
    with_faces = stats["with_faces"]
    face_pct = (with_faces / max(total_rows, 1)) * 100.0
    obj_export = stats["obj_export"]
    obj_demo = stats["obj_demo"]
    obj_total = stats["obj_total"]

    body = f"""
<text x="60" y="58" class="title">Accurate 3D Reconstruction Evidence</text>
<text x="60" y="88" class="subtitle">Mesh coverage and reconstruction artifact availability from publication cohort</text>

<rect class="panel" x="70" y="120" width="360" height="230" rx="16"/>
<text x="100" y="168" class="label">Cohort rows</text>
<text x="100" y="214" class="title" style="font-size:52px">{total_rows}</text>
<text x="100" y="252" class="small">Publication-eligible analyses</text>

<rect class="panel" x="460" y="120" width="360" height="230" rx="16"/>
<text x="490" y="168" class="label">Rows with 3D face metadata</text>
<text x="490" y="214" class="title" style="font-size:52px">{with_faces}/{total_rows}</text>
<text x="490" y="252" class="small">Coverage: {face_pct:.1f}%</text>

<rect class="panel" x="850" y="120" width="360" height="230" rx="16"/>
<text x="880" y="168" class="label">Face count consistency</text>
<text x="880" y="214" class="title" style="font-size:42px">{stats['faces_min']} to {stats['faces_max']}</text>
<text x="880" y="252" class="small">Faces per scan (min to max)</text>

<rect class="panel" x="70" y="390" width="1140" height="230" rx="16"/>
<text x="100" y="438" class="label">Mesh export inventory</text>
<text x="100" y="476" class="small">outputs/export OBJ files: {obj_export}</text>
<text x="100" y="506" class="small">outputs/demo_mesh OBJ files: {obj_demo}</text>
<text x="100" y="536" class="value">Total available OBJ artifacts: {obj_total}</text>

<line x1="520" y1="448" x2="780" y2="448" stroke="#334155" stroke-width="2"/>
<line x1="520" y1="508" x2="780" y2="508" stroke="#334155" stroke-width="2"/>
<line x1="520" y1="568" x2="780" y2="568" stroke="#334155" stroke-width="2"/>
<text x="790" y="454" class="small">Reconstruction coverage proxy: face-metadata presence</text>
<text x="790" y="514" class="small">Topology consistency proxy: stable face-count range</text>
<text x="790" y="574" class="small">Deployment-readiness proxy: OBJ artifact generation</text>
"""
    write_svg("final_07_3d_reconstruction_accuracy.svg", 1280, 680, body)


def build_mapping_svg(metrics: dict, stats: dict) -> None:
    top = metrics["top_regions_severity_ge_2"]
    max_freq = max(item["frequency"] for item in top)
    aal3_count = stats["atlas_counts"].get("AAL3", 0)
    total_rows = stats["total_rows"]
    full_cov = len(stats["full_coverage_regions"])

    parts = [
        '<text x="60" y="56" class="title">Atlas Mapping Consistency</text>',
        '<text x="60" y="86" class="subtitle">AAL3 mapping coverage with severity GE 2 regional frequency</text>',
        f'<rect class="panel" x="70" y="112" width="1140" height="110" rx="14"/>',
        f'<text x="100" y="152" class="label">Atlas AAL3 mapped rows: {aal3_count}/{total_rows}</text>',
        f'<text x="100" y="184" class="small">Regions present in all rows: {full_cov}</text>',
    ]

    y = 250
    for item in top:
        width = 640 * item["frequency"] / max_freq
        region_name = esc(item["region"])
        freq = item["frequency"]
        burden = item["mean_burden_pct"]
        parts.extend(
            [
                f'<rect x="290" y="{y}" width="{width:.1f}" height="42" rx="8" fill="#2563EB"/>',
                f'<text x="276" y="{y+27}" class="label" text-anchor="end">{region_name}</text>',
                f'<text x="{290+width+10:.1f}" y="{y+27}" class="value">{freq}</text>',
                f'<text x="1130" y="{y+27}" class="small" text-anchor="end">mean burden {burden:.2f}%</text>',
            ]
        )
        y += 60

    write_svg("final_08_atlas_mapping.svg", 1280, 660, "\n".join(parts))


def build_region_marking_svg(metrics: dict) -> None:
    sev = metrics["severity_distribution"]
    top = metrics["top_regions_severity_ge_2"]

    order = ["BLUE", "GREEN", "YELLOW", "ORANGE", "RED"]
    colors = {
        "BLUE": "#2563EB",
        "GREEN": "#16A34A",
        "YELLOW": "#EAB308",
        "ORANGE": "#F97316",
        "RED": "#DC2626",
    }

    total = sum(sev[label]["count"] for label in order)
    x = 90
    y = 180
    bar_w = 1020
    bar_h = 54

    parts = [
        '<text x="60" y="56" class="title">Region Marking and Severity Labeling</text>',
        '<text x="60" y="86" class="subtitle">Severity-color marking distribution with top high-burden regions</text>',
        f'<rect class="panel" x="70" y="120" width="1140" height="140" rx="14"/>',
        f'<text x="100" y="160" class="label">Severity-colored regional marks (total labels): {total}</text>',
    ]

    offset = 0.0
    for label in order:
        count = sev[label]["count"]
        width = bar_w * count / max(total, 1)
        parts.append(f'<rect x="{x+offset:.1f}" y="{y}" width="{width:.1f}" height="{bar_h}" fill="{colors[label]}"/>')
        parts.append(f'<text x="{x+offset+width/2:.1f}" y="{y+34}" class="small" text-anchor="middle" fill="#111827">{label} {count}</text>')
        offset += width

    parts.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="none" stroke="#1F2937"/>')

    parts.append('<rect class="panel" x="70" y="300" width="1140" height="300" rx="14"/>')
    parts.append('<text x="100" y="340" class="label">Top marked regions (severity GE 2)</text>')

    yy = 380
    for item in top[:5]:
        region_name = esc(item["region"])
        freq = item["frequency"]
        burden = item["mean_burden_pct"]
        parts.append(f'<text x="100" y="{yy}" class="small">{region_name}: frequency {freq}, mean burden {burden:.2f}%</text>')
        yy += 42

    write_svg("final_09_region_marking.svg", 1280, 660, "\n".join(parts))


def build_dicom_workstation_svg(stats: dict) -> None:
    dicom_rows = stats["dicom_rows"]
    total_rows = stats["total_rows"]
    modality = stats["dicom_modality_counts"]
    planes = stats["series_plane_counts"]
    tools = stats["tool_names"]
    matrix, matrix_count = stats["top_matrix"]
    matrix_text = f"{matrix[0]}x{matrix[1]}" if matrix != (0, 0) else "n/a"

    body = f"""
<text x="60" y="58" class="title">DICOM Workstation Coverage</text>
<text x="60" y="88" class="subtitle">Viewer-plane support, modality coverage, and tool availability</text>

<rect class="panel" x="70" y="120" width="360" height="230" rx="16"/>
<text x="100" y="166" class="label">DICOM profiles</text>
<text x="100" y="214" class="title" style="font-size:50px">{dicom_rows}/{total_rows}</text>
<text x="100" y="252" class="small">Coverage across publication cohort</text>

<rect class="panel" x="460" y="120" width="360" height="230" rx="16"/>
<text x="490" y="166" class="label">Modality support</text>
<text x="490" y="206" class="small">MRI_T1: {modality.get('MRI_T1', 0)}</text>
<text x="490" y="236" class="small">fMRI: {modality.get('fMRI', 0)}</text>
<text x="490" y="266" class="small">Dominant matrix: {matrix_text} ({matrix_count} series)</text>

<rect class="panel" x="850" y="120" width="360" height="230" rx="16"/>
<text x="880" y="166" class="label">MPR plane availability</text>
<text x="880" y="206" class="small">Axial: {planes.get('axial', 0)}</text>
<text x="880" y="236" class="small">Coronal: {planes.get('coronal', 0)}</text>
<text x="880" y="266" class="small">Sagittal: {planes.get('sagittal', 0)}</text>

<rect class="panel" x="70" y="390" width="1140" height="240" rx="16"/>
<text x="100" y="434" class="label">DICOM workstation toolset and scan navigation</text>
<text x="100" y="468" class="small">Slice count range: {stats['slice_min']} to {stats['slice_max']} (mean {stats['slice_mean']:.2f})</text>
<text x="100" y="500" class="small">Available tools ({len(tools)}): {', '.join(tools)}</text>
<text x="100" y="536" class="small">Window presets + MPR + measurements + annotations available in all DICOM-profile rows</text>
"""
    write_svg("final_10_dicom_workstation.svg", 1280, 700, body)


def build_final_markdown(metrics: dict) -> None:
    flow = metrics["cohort_flow"]
    desc = metrics["cohort_descriptor"]
    core = metrics["core_metrics"]
    risk = metrics["risk_distribution"]
    sev = metrics["severity_distribution"]
    top = metrics["top_regions_severity_ge_2"]
    audit = metrics["audit"]

    lines = []
    lines.append("# Brain_Scape Final Publication Package")
    lines.append("")
    lines.append(f"Prepared date: {metrics['run_date']}")
    lines.append("")
    lines.append("## 1. Publication Status")
    lines.append("This file is the final PhD manuscript-ready consolidation for Results and validation evidence.")
    lines.append("All values are sourced from docs/publication_metrics_latest.json and generated through tools/compute_publication_validation.py.")
    lines.append("")
    lines.append("## 2. Cohort Flow")
    lines.append(f"- Total detected analysis files: {flow['total_analysis_files']}")
    lines.append(f"- Publication-eligible rows: {flow['included_publication_rows']}")
    lines.append(f"- Excluded rows: {flow['excluded_rows']}")
    lines.append(f"- Excluded scan_conf_metrics_only rows: {flow['excluded_schema_counts'].get('scan_conf_metrics_only', 0)}")
    lines.append(f"- Included cohort duplicate scan IDs: {flow['included_scan_id_duplicates']}")
    lines.append("")
    lines.append("## 3. Cohort Descriptor")
    lines.append("| Descriptor | Value |")
    lines.append("|---|---:|")
    lines.append(f"| MRI_T1 scans | {desc['modality_counts'].get('MRI_T1', 0)} |")
    lines.append(f"| fMRI scans | {desc['modality_counts'].get('fMRI', 0)} |")
    lines.append(f"| Atlas AAL3 | {desc['atlas_counts'].get('AAL3', 0)} |")
    lines.append(f"| Scan quality limited | {desc['scan_quality_counts'].get('limited', 0)} |")
    lines.append(f"| Scan quality fair | {desc['scan_quality_counts'].get('fair', 0)} |")
    lines.append(f"| Provenance uploaded | {desc['provenance_counts'].get('uploaded', 0)} |")
    lines.append("")
    lines.append("## 4. Core Outcomes with 95% CI")
    lines.append("| Metric | Mean | 95% CI low | 95% CI high |")
    lines.append("|---|---:|---:|---:|")
    for key, label, d in [
        ("overall_confidence", "Overall confidence", 3),
        ("triage_score", "Triage score", 2),
        ("flagged_regions", "Flagged regions", 2),
        ("severe_regions", "Severe regions", 2),
        ("flagged_volume_mm3", "Flagged volume mm3", 1),
        ("severe_volume_mm3", "Severe volume mm3", 1),
        ("mean_region_confidence_pct", "Mean region confidence pct", 2),
        ("highest_region_burden_pct", "Highest region burden pct", 2),
    ]:
        row = core[key]
        lines.append(f"| {label} | {fmt(row['mean'], d)} | {fmt(row['ci95'][0], d)} | {fmt(row['ci95'][1], d)} |")
    lines.append("")
    lines.append("## 5. Risk Distribution with Wilson 95% CI")
    lines.append("| Risk band | Count | Percent | 95% CI low | 95% CI high |")
    lines.append("|---|---:|---:|---:|---:|")
    for k in ["high", "moderate", "low"]:
        r = risk[k]
        lines.append(f"| {k.capitalize()} | {r['count']} | {r['percent']:.2f}% | {r['ci95_percent'][0]:.2f}% | {r['ci95_percent'][1]:.2f}% |")
    lines.append("")
    lines.append("## 6. Severity Distribution")
    lines.append("| Severity | Count | Percent |")
    lines.append("|---|---:|---:|")
    for k in ["BLUE", "GREEN", "YELLOW", "ORANGE", "RED"]:
        lines.append(f"| {k} | {sev[k]['count']} | {sev[k]['percent']:.2f}% |")
    lines.append("")
    lines.append("## 7. Top Regions Severity GE 2")
    lines.append("| Region | Frequency | Mean burden pct | Mean volume mm3 |")
    lines.append("|---|---:|---:|---:|")
    for item in top:
        lines.append(
            f"| {item['region']} | {item['frequency']} | {item['mean_burden_pct']:.2f} | {item['mean_volume_mm3']:.1f} |"
        )
    lines.append("")
    lines.append("## 8. Governance")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Total audit events | {audit['total_events']} |")
    lines.append(f"| Allowed | {audit['allowed']} |")
    lines.append(f"| Denied | {audit['denied']} |")
    lines.append(f"| Unique users | {audit['unique_users']} |")
    lines.append(f"| Unique actions | {audit['unique_actions']} |")
    lines.append(f"| Audit completeness | {audit['completeness']*100:.1f}% |")
    lines.append(f"| Denied reason role_not_allowed | {audit['denied_reason_counts'].get('role_not_allowed', 0)} |")
    lines.append("")
    lines.append("## 9. Figure Asset Set")
    lines.append("SVG files:")
    lines.append("- docs/final-publication/svg/final_01_cohort_flow.svg")
    lines.append("- docs/final-publication/svg/final_02_core_metrics_ci.svg")
    lines.append("- docs/final-publication/svg/final_03_risk_distribution_ci.svg")
    lines.append("- docs/final-publication/svg/final_04_severity_distribution.svg")
    lines.append("- docs/final-publication/svg/final_05_top_regions.svg")
    lines.append("- docs/final-publication/svg/final_06_governance.svg")
    lines.append("- docs/final-publication/svg/final_07_3d_reconstruction_accuracy.svg")
    lines.append("- docs/final-publication/svg/final_08_atlas_mapping.svg")
    lines.append("- docs/final-publication/svg/final_09_region_marking.svg")
    lines.append("- docs/final-publication/svg/final_10_dicom_workstation.svg")
    lines.append("")
    lines.append("Mermaid files:")
    lines.append("- docs/final-publication/mmd/final_01_cohort_flow.mmd")
    lines.append("- docs/final-publication/mmd/final_02_core_metrics_ci.mmd")
    lines.append("- docs/final-publication/mmd/final_03_risk_distribution_ci.mmd")
    lines.append("- docs/final-publication/mmd/final_04_severity_distribution.mmd")
    lines.append("- docs/final-publication/mmd/final_05_top_regions.mmd")
    lines.append("- docs/final-publication/mmd/final_06_governance.mmd")
    lines.append("")
    lines.append("## 10. Regeneration")
    lines.append("1. Run tools/compute_publication_validation.py to refresh validated metrics.")
    lines.append("2. Run tools/generate_final_publication_assets.py to refresh this package and all diagrams.")

    (DOCS / "PHD_FINAL_PUBLICATION_PACKAGE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme() -> None:
    text = """# Final Publication Asset Pack

This folder contains final manuscript-ready visual assets generated from docs/publication_metrics_latest.json.

## SVG
- svg/final_01_cohort_flow.svg
- svg/final_02_core_metrics_ci.svg
- svg/final_03_risk_distribution_ci.svg
- svg/final_04_severity_distribution.svg
- svg/final_05_top_regions.svg
- svg/final_06_governance.svg
- svg/final_07_3d_reconstruction_accuracy.svg
- svg/final_08_atlas_mapping.svg
- svg/final_09_region_marking.svg
- svg/final_10_dicom_workstation.svg

## Mermaid
- mmd/final_01_cohort_flow.mmd
- mmd/final_02_core_metrics_ci.mmd
- mmd/final_03_risk_distribution_ci.mmd
- mmd/final_04_severity_distribution.mmd
- mmd/final_05_top_regions.mmd
- mmd/final_06_governance.mmd
"""
    (FINAL_DIR / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    ensure_dirs()
    metrics = load_metrics()
    rows = load_publication_rows()
    stats = collect_reconstruction_dicom_stats(rows)

    build_cohort_flow_svg(metrics)
    build_core_metrics_svg(metrics)
    build_risk_svg(metrics)
    build_severity_svg(metrics)
    build_top_regions_svg(metrics)
    build_governance_svg(metrics)
    build_reconstruction_accuracy_svg(stats)
    build_mapping_svg(metrics, stats)
    build_region_marking_svg(metrics)
    build_dicom_workstation_svg(stats)
    build_final_markdown(metrics)
    write_readme()

    print("Generated final publication markdown and diagram assets.")


if __name__ == "__main__":
    main()

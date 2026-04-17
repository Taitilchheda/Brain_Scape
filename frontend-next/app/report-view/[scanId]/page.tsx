"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

type MetricRow = {
  label?: string;
  value?: number | string | null;
  unit?: string;
};

type FindingRow = {
  region?: string;
  severity_label?: string;
  severity_level?: number;
  confidence_pct?: number;
  volume_mm3?: number;
  volume_pct_of_region?: number;
};

type DifferentialRow = {
  etiology?: string;
  probability_pct?: number;
  rationale?: string | null;
};

type CriticalFinding = {
  finding_id?: string;
  severity?: string;
  category?: string;
  title?: string;
  description?: string;
  requires_acknowledgement?: boolean;
};

type UncertaintyRegion = {
  anatomical_name?: string;
  uncertainty?: number;
  confidence?: number;
  severity_level?: number;
  volume_pct_of_region?: number;
};

type NeurologySections = {
  indication?: string;
  technique?: string;
  key_findings?: string[];
  impression?: string;
  limitations?: string[];
  recommended_actions?: string[];
  structured_summary?: string;
};

type ReportPayload = {
  scan_id?: string;
  summary?: string;
  generated_at?: string;
  report_mode_notice?: string;
  quantitative_metrics?: Record<string, number | string | null>;
  metric_rows?: MetricRow[];
  finding_rows?: FindingRow[];
  differential_diagnosis?: DifferentialRow[];
  critical_findings?: CriticalFinding[];
  uncertainty_profile?: {
    global_uncertainty?: number;
    high_uncertainty_regions?: UncertaintyRegion[];
  };
  neurology_standard_sections?: NeurologySections;
  report_sections?: {
    impression?: string;
    largest_region?: { name?: string; volume_mm3?: number | null };
    risk_statement?: string;
    technique?: string;
    limitations?: string[];
  };
  report_workflow?: {
    draft_available?: boolean;
    finalized?: boolean;
    finalized_at?: string | null;
    finalized_by?: string | null;
  };
  pdf_url?: string;
  pdf_available?: boolean;
};

function toDisplayRows(report: ReportPayload | null): MetricRow[] {
  if (!report) return [];
  if (Array.isArray(report.metric_rows) && report.metric_rows.length > 0) return report.metric_rows;

  const metrics = report.quantitative_metrics || {};
  return Object.entries(metrics).map(([key, value]) => ({
    label: key.replace(/_/g, " "),
    value,
    unit: key.endsWith("_pct") ? "%" : (key.endsWith("_mm3") ? "mm3" : ""),
  }));
}

function formatValue(value: number | string | null | undefined, unit = ""): string {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "string") return unit ? `${value} ${unit}` : value;
  if (!Number.isFinite(value)) return "n/a";

  const rounded = Math.abs(value) >= 100 ? Math.round(value) : Number(value.toFixed(2));
  if (unit === "%") return `${rounded}%`;
  if (unit) return `${rounded} ${unit}`;
  return String(rounded);
}

function riskBadgeStyle(riskBand: string): { background: string; border: string; color: string; label: string } {
  if (riskBand === "high") {
    return {
      background: "rgba(255, 232, 230, 0.95)",
      border: "1px solid #efb0a9",
      color: "#7e1f18",
      label: "High Risk",
    };
  }
  if (riskBand === "moderate") {
    return {
      background: "rgba(255, 245, 226, 0.95)",
      border: "1px solid #e8c48f",
      color: "#7a4f12",
      label: "Moderate Risk",
    };
  }
  if (riskBand === "low") {
    return {
      background: "rgba(233, 248, 238, 0.95)",
      border: "1px solid #8bc6a2",
      color: "#1f5b38",
      label: "Low Risk",
    };
  }
  return {
    background: "rgba(236, 244, 255, 0.95)",
    border: "1px solid #b9d0f2",
    color: "#274f80",
    label: "Risk Pending",
  };
}

function asNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return parsed;
}

function normalizeText(value: string | null | undefined): string {
  return String(value || "").trim();
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

export default function ReportViewPage() {
  const params = useParams<{ scanId: string }>();
  const searchParams = useSearchParams();

  const scanId = decodeURIComponent(String(params?.scanId || "")).trim();
  const mode = (searchParams.get("mode") || "clinician").toLowerCase() === "patient" ? "patient" : "clinician";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [report, setReport] = useState<ReportPayload | null>(null);

  const apiBase = useMemo(() => {
    if (typeof window === "undefined") {
      return process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
    }
    return (
      (window as any).__BRAINGSCAPE_API_BASE__ ||
      (window as any).__BRAINSCAPE_API_BASE__ ||
      process.env.NEXT_PUBLIC_API_BASE ||
      "http://127.0.0.1:8000"
    );
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      if (!scanId) {
        setError("Missing scan id.");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError("");
      try {
        const requestReport = async (tokenValue = "") => {
          return fetch(
            `${apiBase}/report/${encodeURIComponent(scanId)}?mode=${encodeURIComponent(mode)}&detailed=true`,
            {
              headers: tokenValue ? { Authorization: `Bearer ${tokenValue}` } : {},
            }
          );
        };

        let token = typeof window !== "undefined" ? window.localStorage.getItem("brainscape_token") || "" : "";
        let response = await requestReport(token);

        if (response.status === 401) {
          const authResp = await fetch(`${apiBase}/auth/token`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: "demo-clinician", role: "clinician" }),
          });

          if (authResp.ok) {
            const authPayload = await authResp.json();
            token = String(authPayload?.access_token || "");
            if (token && typeof window !== "undefined") {
              window.localStorage.setItem("brainscape_token", token);
            }
            response = await requestReport(token);
          }
        }

        if (!response.ok) {
          const detail = await response.text();
          throw new Error(`Report request failed (${response.status}). ${detail.slice(0, 180)}`);
        }

        const payload = (await response.json()) as ReportPayload;
        if (!cancelled) {
          setReport(payload);
          setLoading(false);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setError(fetchError instanceof Error ? fetchError.message : "Failed to load report.");
          setLoading(false);
        }
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [apiBase, mode, scanId]);

  const rows = toDisplayRows(report);
  const findingRows = Array.isArray(report?.finding_rows) ? report.finding_rows : [];
  const differentialRows = Array.isArray(report?.differential_diagnosis) ? report.differential_diagnosis : [];
  const criticalFindings = Array.isArray(report?.critical_findings) ? report.critical_findings : [];
  const uncertaintyRows = Array.isArray(report?.uncertainty_profile?.high_uncertainty_regions)
    ? report.uncertainty_profile?.high_uncertainty_regions
    : [];
  const neurologySections = report?.neurology_standard_sections;
  const largestRegion = report?.report_sections?.largest_region;
  const quantitative = report?.quantitative_metrics || {};
  const riskBand = normalizeText(String(quantitative.risk_band || "unknown")).toLowerCase();
  const riskStyle = riskBadgeStyle(riskBand);

  const pdfHref = useMemo(() => {
    const raw = normalizeText(report?.pdf_url);
    if (!raw) return "";
    if (raw.startsWith("http://") || raw.startsWith("https://")) return raw;
    return `${apiBase}${raw}`;
  }, [apiBase, report?.pdf_url]);

  const uncertaintyIndex = asNumber(report?.uncertainty_profile?.global_uncertainty);
  const cardStyle = {
    border: "1px solid #d9e7f8",
    borderRadius: 12,
    padding: "0.66rem 0.72rem",
    background: "#f8fbff",
  };
  const chartCardStyle = {
    border: "1px solid #d6e6fa",
    borderRadius: 12,
    padding: "0.66rem 0.72rem",
    background: "#fbfdff",
  };

  const severityDistribution = useMemo(() => {
    const counts = {
      Severe: 0,
      Moderate: 0,
      Mild: 0,
      Healthy: 0,
    };

    findingRows.forEach((row) => {
      const level = Number(row.severity_level || 0);
      if (level >= 4) counts.Severe += 1;
      else if (level === 3) counts.Moderate += 1;
      else if (level === 2) counts.Mild += 1;
      else counts.Healthy += 1;
    });

    return [
      { label: "Severe", value: counts.Severe, color: "#e45b51" },
      { label: "Moderate", value: counts.Moderate, color: "#df8a31" },
      { label: "Mild", value: counts.Mild, color: "#d3b535" },
      { label: "Healthy", value: counts.Healthy, color: "#4fbf78" },
    ];
  }, [findingRows]);

  const totalSeverityCount = severityDistribution.reduce((sum, entry) => sum + entry.value, 0);
  const severitySegments = useMemo(() => {
    let cursor = 0;
    return severityDistribution.map((entry) => {
      const width = totalSeverityCount > 0 ? (entry.value / totalSeverityCount) * 100 : 0;
      const segment = { ...entry, x: cursor, width };
      cursor += width;
      return segment;
    });
  }, [severityDistribution, totalSeverityCount]);

  const burdenRows = useMemo(() => {
    return [...findingRows]
      .filter((row) => asNumber(row.volume_mm3) !== null || asNumber(row.volume_pct_of_region) !== null)
      .map((row) => ({
        label: row.region || "Unknown",
        value: asNumber(row.volume_pct_of_region) ?? 0,
        volume: asNumber(row.volume_mm3) ?? 0,
      }))
      .sort((left, right) => {
        const leftRank = left.value > 0 ? left.value : left.volume;
        const rightRank = right.value > 0 ? right.value : right.volume;
        return rightRank - leftRank;
      })
      .slice(0, 7);
  }, [findingRows]);

  const maxBurdenValue = burdenRows.reduce((maxValue, row) => {
    const rank = row.value > 0 ? row.value : row.volume;
    return Math.max(maxValue, rank);
  }, 0);

  const differentialChartRows = useMemo(() => {
    return [...differentialRows]
      .map((row) => ({
        label: row.etiology || "Unspecified",
        probability: clampPercent(asNumber(row.probability_pct) ?? 0),
      }))
      .sort((left, right) => right.probability - left.probability)
      .slice(0, 6);
  }, [differentialRows]);

  const confidencePercent = clampPercent(asNumber(quantitative.overall_confidence_pct as number | string | null | undefined) ?? 0);
  const uncertaintyPercent = clampPercent((uncertaintyIndex ?? 0) * 100);

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "linear-gradient(160deg, #f7fbff 0%, #edf4ff 60%, #e9f7f3 100%)",
        padding: "1.3rem",
        color: "#193047",
        fontFamily: "'Segoe UI', 'Aptos', sans-serif",
      }}
    >
      <section
        style={{
          margin: "0 auto",
          maxWidth: 1060,
          borderRadius: 16,
          border: "1px solid rgba(168, 195, 230, 0.75)",
          background: "rgba(255, 255, 255, 0.85)",
          backdropFilter: "blur(10px)",
          padding: "1rem 1.1rem",
          boxShadow: "0 18px 40px rgba(26, 64, 110, 0.12)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.8rem", flexWrap: "wrap" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: "1.22rem" }}>Neurology Clinical Report</h1>
            <p style={{ margin: "0.2rem 0 0", color: "#507091", fontSize: "0.88rem" }}>
              Scan {scanId || "-"} | Mode: {mode}
            </p>
          </div>
          <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
            {pdfHref && (
              <a
                href={pdfHref}
                target="_blank"
                rel="noreferrer"
                style={{
                  border: "1px solid #6f9fd6",
                  borderRadius: 10,
                  padding: "0.46rem 0.74rem",
                  background: "#e8f2ff",
                  color: "#18456d",
                  textDecoration: "none",
                  fontWeight: 700,
                }}
              >
                Open generated PDF
              </a>
            )}
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{
                border: "1px solid #88b5e1",
                borderRadius: 10,
                padding: "0.46rem 0.7rem",
                background: "#f0f7ff",
                color: "#174165",
                cursor: "pointer",
                fontWeight: 600,
              }}
            >
              Refresh
            </button>
          </div>
        </div>

        {loading && <p style={{ marginTop: "1rem" }}>Loading report...</p>}
        {!loading && error && <p style={{ marginTop: "1rem", color: "#9a2130" }}>{error}</p>}

        {!loading && !error && report && (
          <>
            <div style={{ marginTop: "0.9rem", fontSize: "0.9rem", color: "#3f5e7f", lineHeight: 1.5 }}>
              <div><strong>Generated:</strong> {report.generated_at || "n/a"}</div>
              <div><strong>Notice:</strong> {report.report_mode_notice || "-"}</div>
              <div><strong>Summary:</strong> {report.summary || neurologySections?.structured_summary || "-"}</div>
              <div><strong>Workflow:</strong> {report.report_workflow?.finalized ? "Finalized" : "Draft"}</div>
              {report.report_workflow?.finalized_at && (
                <div><strong>Finalized at:</strong> {report.report_workflow.finalized_at}</div>
              )}
              {!report.pdf_available && (
                <div style={{ marginTop: "0.25rem", color: "#8d5317" }}>
                  PDF is being prepared. Refresh in a moment if the link is unavailable.
                </div>
              )}
            </div>

            <div
              style={{
                marginTop: "0.9rem",
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                gap: "0.62rem",
              }}
            >
              <div style={{ ...cardStyle, ...riskStyle }}>
                <div style={{ fontSize: "0.74rem", textTransform: "uppercase", letterSpacing: "0.06em", opacity: 0.86 }}>Risk band</div>
                <div style={{ fontSize: "1.02rem", fontWeight: 700 }}>{riskStyle.label}</div>
              </div>
              <div style={cardStyle}>
                <div style={{ fontSize: "0.74rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "#5c7a9c" }}>Triage score</div>
                <div style={{ fontSize: "1.02rem", fontWeight: 700, color: "#194069" }}>
                  {formatValue(quantitative.triage_score as number | string | null | undefined, "score")}
                </div>
              </div>
              <div style={cardStyle}>
                <div style={{ fontSize: "0.74rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "#5c7a9c" }}>Overall confidence</div>
                <div style={{ fontSize: "1.02rem", fontWeight: 700, color: "#194069" }}>
                  {formatValue(quantitative.overall_confidence_pct as number | string | null | undefined, "%")}
                </div>
              </div>
              <div style={cardStyle}>
                <div style={{ fontSize: "0.74rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "#5c7a9c" }}>Scan quality</div>
                <div style={{ fontSize: "1.02rem", fontWeight: 700, color: "#194069" }}>
                  {String(quantitative.scan_quality || "unknown")}
                </div>
              </div>
            </div>

            {(findingRows.length > 0 || differentialRows.length > 0) && (
              <div style={{ marginTop: "0.9rem", border: "1px solid #d6e6fa", borderRadius: 12, background: "#f8fbff", padding: "0.66rem 0.72rem" }}>
                <h2 style={{ margin: 0, fontSize: "1rem" }}>Visual Analytics and Graphs</h2>
                <div
                  style={{
                    marginTop: "0.56rem",
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                    gap: "0.58rem",
                  }}
                >
                  <div style={chartCardStyle}>
                    <h3 style={{ margin: 0, fontSize: "0.9rem", color: "#2a4f77" }}>Severity Distribution</h3>
                    <svg viewBox="0 0 100 12" preserveAspectRatio="none" style={{ width: "100%", height: 24, marginTop: "0.44rem", borderRadius: 8, overflow: "hidden" }}>
                      {severitySegments.map((segment) => (
                        <rect
                          key={segment.label}
                          x={segment.x}
                          y={0}
                          width={segment.width}
                          height={12}
                          fill={segment.color}
                          opacity={segment.width > 0 ? 0.92 : 0.15}
                        />
                      ))}
                    </svg>
                    <div style={{ marginTop: "0.38rem", display: "grid", gap: "0.18rem" }}>
                      {severityDistribution.map((row) => (
                        <div key={row.label} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.45rem", fontSize: "0.8rem", color: "#4f6f92" }}>
                          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.34rem" }}>
                            <span style={{ width: 10, height: 10, borderRadius: 999, background: row.color }} />
                            {row.label}
                          </span>
                          <strong style={{ color: "#1f4e7d" }}>
                            {row.value}
                            {totalSeverityCount > 0 ? ` (${Math.round((row.value / totalSeverityCount) * 100)}%)` : ""}
                          </strong>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div style={chartCardStyle}>
                    <h3 style={{ margin: 0, fontSize: "0.9rem", color: "#2a4f77" }}>Top Regional Burden</h3>
                    <div style={{ marginTop: "0.42rem", display: "grid", gap: "0.3rem" }}>
                      {burdenRows.length === 0 && (
                        <div style={{ fontSize: "0.82rem", color: "#59789b" }}>Regional burden bars will appear when finding rows include burden values.</div>
                      )}
                      {burdenRows.map((row, index) => {
                        const score = row.value > 0 ? row.value : row.volume;
                        const width = maxBurdenValue > 0 ? clampPercent((score / maxBurdenValue) * 100) : 0;
                        return (
                          <div key={`${row.label}-${index}`} style={{ display: "grid", gap: "0.14rem" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.45rem", fontSize: "0.77rem", color: "#537396" }}>
                              <span>{row.label}</span>
                              <strong style={{ color: "#1f4f7d" }}>
                                {row.value > 0 ? `${row.value.toFixed(1)}%` : `${row.volume.toFixed(1)} mm3`}
                              </strong>
                            </div>
                            <div style={{ width: "100%", height: 9, borderRadius: 999, background: "#e7f0fb", overflow: "hidden" }}>
                              <div style={{ width: `${width}%`, height: "100%", background: "linear-gradient(90deg, #2c83d6, #59b6ff)" }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div style={chartCardStyle}>
                    <h3 style={{ margin: 0, fontSize: "0.9rem", color: "#2a4f77" }}>Differential Probability Profile</h3>
                    <div style={{ marginTop: "0.42rem", display: "grid", gap: "0.3rem" }}>
                      {differentialChartRows.length === 0 && (
                        <div style={{ fontSize: "0.82rem", color: "#59789b" }}>Differential graph appears once ranked etiologies are available.</div>
                      )}
                      {differentialChartRows.map((row, index) => (
                        <div key={`${row.label}-${index}`} style={{ display: "grid", gap: "0.14rem" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.45rem", fontSize: "0.77rem", color: "#537396" }}>
                            <span>{row.label}</span>
                            <strong style={{ color: "#1f4f7d" }}>{row.probability.toFixed(1)}%</strong>
                          </div>
                          <div style={{ width: "100%", height: 9, borderRadius: 999, background: "#eef4fb", overflow: "hidden" }}>
                            <div style={{ width: `${row.probability}%`, height: "100%", background: "linear-gradient(90deg, #4e83da, #72c1ff)" }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div style={chartCardStyle}>
                    <h3 style={{ margin: 0, fontSize: "0.9rem", color: "#2a4f77" }}>Confidence and Uncertainty Gauge</h3>
                    <div style={{ marginTop: "0.5rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                      <div style={{ display: "grid", justifyItems: "center", gap: "0.26rem" }}>
                        <div
                          style={{
                            width: 78,
                            height: 78,
                            borderRadius: "50%",
                            background: `conic-gradient(#2d88dc 0 ${confidencePercent}%, #d7e6f8 ${confidencePercent}% 100%)`,
                            display: "grid",
                            placeItems: "center",
                          }}
                        >
                          <div style={{ width: 52, height: 52, borderRadius: "50%", background: "#fbfdff", display: "grid", placeItems: "center", fontSize: "0.8rem", color: "#26517f", fontWeight: 700 }}>
                            {confidencePercent.toFixed(0)}%
                          </div>
                        </div>
                        <div style={{ fontSize: "0.76rem", color: "#4d6f93" }}>Confidence</div>
                      </div>

                      <div style={{ display: "grid", justifyItems: "center", gap: "0.26rem" }}>
                        <div
                          style={{
                            width: 78,
                            height: 78,
                            borderRadius: "50%",
                            background: `conic-gradient(#f29b38 0 ${uncertaintyPercent}%, #f5e7d6 ${uncertaintyPercent}% 100%)`,
                            display: "grid",
                            placeItems: "center",
                          }}
                        >
                          <div style={{ width: 52, height: 52, borderRadius: "50%", background: "#fbfdff", display: "grid", placeItems: "center", fontSize: "0.8rem", color: "#7b4f1a", fontWeight: 700 }}>
                            {uncertaintyPercent.toFixed(0)}%
                          </div>
                        </div>
                        <div style={{ fontSize: "0.76rem", color: "#4d6f93" }}>Uncertainty</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div style={{ marginTop: "0.9rem", border: "1px solid #d8e6f7", borderRadius: 12, padding: "0.65rem", background: "#f9fcff" }}>
              <div><strong>Impression:</strong> {report.report_sections?.impression || neurologySections?.impression || "-"}</div>
              <div style={{ marginTop: "0.26rem" }}>
                <strong>Largest region:</strong> {largestRegion?.name || "-"}
                {largestRegion?.volume_mm3 !== undefined && largestRegion?.volume_mm3 !== null
                  ? ` (${largestRegion.volume_mm3} mm3)`
                  : ""}
              </div>
              <div style={{ marginTop: "0.26rem" }}><strong>Risk:</strong> {report.report_sections?.risk_statement || "-"}</div>
              {(neurologySections?.technique || report.report_sections?.technique) && (
                <div style={{ marginTop: "0.26rem" }}>
                  <strong>Technique:</strong> {neurologySections?.technique || report.report_sections?.technique}
                </div>
              )}
            </div>

            {neurologySections && (
              <div style={{ marginTop: "0.9rem", border: "1px solid #d8e6f7", borderRadius: 12, padding: "0.65rem", background: "#fcfdff" }}>
                <h2 style={{ margin: 0, fontSize: "1rem" }}>Neurology-Structured Sections</h2>
                <div style={{ marginTop: "0.45rem", fontSize: "0.9rem", color: "#284564", lineHeight: 1.5 }}>
                  {neurologySections.indication && <div><strong>Indication:</strong> {neurologySections.indication}</div>}
                  {neurologySections.technique && <div><strong>Technique:</strong> {neurologySections.technique}</div>}
                </div>

                {Array.isArray(neurologySections.key_findings) && neurologySections.key_findings.length > 0 && (
                  <div style={{ marginTop: "0.6rem" }}>
                    <h3 style={{ margin: "0 0 0.3rem", fontSize: "0.92rem", color: "#214465" }}>Key Findings</h3>
                    <ul style={{ margin: 0, paddingLeft: "1.15rem", color: "#355778", fontSize: "0.88rem", lineHeight: 1.45 }}>
                      {neurologySections.key_findings.map((entry, index) => (
                        <li key={`key-finding-${index}`}>{entry}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {Array.isArray(neurologySections.limitations) && neurologySections.limitations.length > 0 && (
                  <div style={{ marginTop: "0.6rem" }}>
                    <h3 style={{ margin: "0 0 0.3rem", fontSize: "0.92rem", color: "#214465" }}>Limitations</h3>
                    <ul style={{ margin: 0, paddingLeft: "1.15rem", color: "#355778", fontSize: "0.88rem", lineHeight: 1.45 }}>
                      {neurologySections.limitations.map((entry, index) => (
                        <li key={`limitation-${index}`}>{entry}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {Array.isArray(neurologySections.recommended_actions) && neurologySections.recommended_actions.length > 0 && (
                  <div style={{ marginTop: "0.6rem" }}>
                    <h3 style={{ margin: "0 0 0.3rem", fontSize: "0.92rem", color: "#214465" }}>Recommended Actions</h3>
                    <ul style={{ margin: 0, paddingLeft: "1.15rem", color: "#355778", fontSize: "0.88rem", lineHeight: 1.45 }}>
                      {neurologySections.recommended_actions.map((entry, index) => (
                        <li key={`recommendation-${index}`}>{entry}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {findingRows.length > 0 && (
              <>
                <h2 style={{ marginTop: "1rem", marginBottom: "0.4rem", fontSize: "1rem" }}>Top Regional Findings</h2>
                <div style={{ overflowX: "auto", border: "1px solid #d7e5f6", borderRadius: 12, background: "#fbfdff" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.88rem" }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: "left", padding: "0.44rem", borderBottom: "1px solid #cfe0f4" }}>Region</th>
                        <th style={{ textAlign: "left", padding: "0.44rem", borderBottom: "1px solid #cfe0f4" }}>Severity</th>
                        <th style={{ textAlign: "left", padding: "0.44rem", borderBottom: "1px solid #cfe0f4" }}>Confidence</th>
                        <th style={{ textAlign: "left", padding: "0.44rem", borderBottom: "1px solid #cfe0f4" }}>Volume</th>
                        <th style={{ textAlign: "left", padding: "0.44rem", borderBottom: "1px solid #cfe0f4" }}>Regional burden</th>
                      </tr>
                    </thead>
                    <tbody>
                      {findingRows.map((row, index) => (
                        <tr key={`${row.region || "region"}-${index}`}>
                          <td style={{ padding: "0.44rem", borderBottom: "1px solid #ebf2fa" }}>{row.region || "Unknown"}</td>
                          <td style={{ padding: "0.44rem", borderBottom: "1px solid #ebf2fa" }}>
                            {row.severity_label || "UNKNOWN"} (L{row.severity_level ?? "-"})
                          </td>
                          <td style={{ padding: "0.44rem", borderBottom: "1px solid #ebf2fa" }}>
                            {formatValue(row.confidence_pct ?? null, "%")}
                          </td>
                          <td style={{ padding: "0.44rem", borderBottom: "1px solid #ebf2fa" }}>
                            {formatValue(row.volume_mm3 ?? null, "mm3")}
                          </td>
                          <td style={{ padding: "0.44rem", borderBottom: "1px solid #ebf2fa" }}>
                            {formatValue(row.volume_pct_of_region ?? null, "%")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {differentialRows.length > 0 && (
              <>
                <h2 style={{ marginTop: "1rem", marginBottom: "0.4rem", fontSize: "1rem" }}>Differential Diagnosis</h2>
                <div style={{ border: "1px solid #d7e5f6", borderRadius: 12, background: "#fbfdff", padding: "0.65rem" }}>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.88rem" }}>
                      <thead>
                        <tr>
                          <th style={{ textAlign: "left", padding: "0.44rem", borderBottom: "1px solid #cfe0f4" }}>Etiology</th>
                          <th style={{ textAlign: "left", padding: "0.44rem", borderBottom: "1px solid #cfe0f4" }}>Probability</th>
                          <th style={{ textAlign: "left", padding: "0.44rem", borderBottom: "1px solid #cfe0f4" }}>Rationale</th>
                        </tr>
                      </thead>
                      <tbody>
                        {differentialRows.map((item, index) => (
                          <tr key={`${item.etiology || "dx"}-${index}`}>
                            <td style={{ padding: "0.44rem", borderBottom: "1px solid #ebf2fa" }}>{item.etiology || "Unspecified"}</td>
                            <td style={{ padding: "0.44rem", borderBottom: "1px solid #ebf2fa" }}>
                              {formatValue(item.probability_pct ?? null, "%")}
                            </td>
                            <td style={{ padding: "0.44rem", borderBottom: "1px solid #ebf2fa" }}>
                              {item.rationale || "-"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}

            <h2 style={{ marginTop: "1rem", marginBottom: "0.4rem", fontSize: "1rem" }}>Quantitative Metrics</h2>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.88rem" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", padding: "0.44rem", borderBottom: "1px solid #cfe0f4" }}>Metric</th>
                    <th style={{ textAlign: "left", padding: "0.44rem", borderBottom: "1px solid #cfe0f4" }}>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={2} style={{ padding: "0.55rem", color: "#5a7696" }}>No quantitative metrics available.</td>
                    </tr>
                  )}
                  {rows.map((row, index) => (
                    <tr key={`${row.label || "metric"}-${index}`}>
                      <td style={{ padding: "0.44rem", borderBottom: "1px solid #ebf2fa" }}>{row.label || "Metric"}</td>
                      <td style={{ padding: "0.44rem", borderBottom: "1px solid #ebf2fa" }}>{formatValue(row.value, row.unit || "")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {(criticalFindings.length > 0 || uncertaintyRows.length > 0 || uncertaintyIndex !== null) && (
              <div style={{ marginTop: "1rem", border: "1px solid #d7e5f6", borderRadius: 12, background: "#fbfdff", padding: "0.65rem" }}>
                <h2 style={{ margin: 0, fontSize: "1rem" }}>Safety and Uncertainty Review</h2>
                {uncertaintyIndex !== null && (
                  <div style={{ marginTop: "0.45rem", fontSize: "0.9rem", color: "#34587a" }}>
                    <strong>Global uncertainty index:</strong> {uncertaintyIndex.toFixed(3)}
                  </div>
                )}

                {uncertaintyRows.length > 0 && (
                  <div style={{ marginTop: "0.55rem", overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.86rem" }}>
                      <thead>
                        <tr>
                          <th style={{ textAlign: "left", padding: "0.42rem", borderBottom: "1px solid #cfe0f4" }}>Region</th>
                          <th style={{ textAlign: "left", padding: "0.42rem", borderBottom: "1px solid #cfe0f4" }}>Uncertainty</th>
                          <th style={{ textAlign: "left", padding: "0.42rem", borderBottom: "1px solid #cfe0f4" }}>Confidence</th>
                          <th style={{ textAlign: "left", padding: "0.42rem", borderBottom: "1px solid #cfe0f4" }}>Severity</th>
                        </tr>
                      </thead>
                      <tbody>
                        {uncertaintyRows.map((row, index) => (
                          <tr key={`${row.anatomical_name || "uncertainty"}-${index}`}>
                            <td style={{ padding: "0.42rem", borderBottom: "1px solid #ebf2fa" }}>{row.anatomical_name || "Unknown"}</td>
                            <td style={{ padding: "0.42rem", borderBottom: "1px solid #ebf2fa" }}>{formatValue((row.uncertainty ?? 0) * 100, "%")}</td>
                            <td style={{ padding: "0.42rem", borderBottom: "1px solid #ebf2fa" }}>{formatValue((row.confidence ?? 0) * 100, "%")}</td>
                            <td style={{ padding: "0.42rem", borderBottom: "1px solid #ebf2fa" }}>L{row.severity_level ?? "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {criticalFindings.length > 0 && (
                  <div style={{ marginTop: "0.65rem" }}>
                    <h3 style={{ margin: "0 0 0.3rem", fontSize: "0.92rem", color: "#214465" }}>Critical Findings</h3>
                    <ul style={{ margin: 0, paddingLeft: "1.15rem", color: "#355778", fontSize: "0.88rem", lineHeight: 1.45 }}>
                      {criticalFindings.map((item, index) => (
                        <li key={`${item.finding_id || "critical"}-${index}`}>
                          <strong>{item.title || item.category || "Critical item"}:</strong> {item.description || "No description."}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </section>
    </main>
  );
}

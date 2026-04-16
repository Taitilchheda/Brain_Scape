"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

type MetricRow = {
  label?: string;
  value?: number | string | null;
  unit?: string;
};

type ReportPayload = {
  scan_id?: string;
  summary?: string;
  generated_at?: string;
  report_mode_notice?: string;
  quantitative_metrics?: Record<string, number | string | null>;
  metric_rows?: MetricRow[];
  report_sections?: {
    impression?: string;
    largest_region?: { name?: string; volume_mm3?: number | null };
    risk_statement?: string;
  };
  pdf_url?: string;
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
        const token = typeof window !== "undefined" ? window.localStorage.getItem("brainscape_token") || "" : "";
        const response = await fetch(
          `${apiBase}/report/${encodeURIComponent(scanId)}?mode=${encodeURIComponent(mode)}&detailed=true`,
          {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          }
        );

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
  const largestRegion = report?.report_sections?.largest_region;

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
          maxWidth: 980,
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
            <h1 style={{ margin: 0, fontSize: "1.22rem" }}>Clinical Report</h1>
            <p style={{ margin: "0.2rem 0 0", color: "#507091", fontSize: "0.88rem" }}>
              Scan {scanId || "-"} | Mode: {mode}
            </p>
          </div>
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

        {loading && <p style={{ marginTop: "1rem" }}>Loading report...</p>}
        {!loading && error && <p style={{ marginTop: "1rem", color: "#9a2130" }}>{error}</p>}

        {!loading && !error && report && (
          <>
            <div style={{ marginTop: "0.9rem", fontSize: "0.9rem", color: "#3f5e7f" }}>
              <div><strong>Generated:</strong> {report.generated_at || "n/a"}</div>
              <div><strong>Notice:</strong> {report.report_mode_notice || "-"}</div>
              <div><strong>Summary:</strong> {report.summary || "-"}</div>
            </div>

            <div style={{ marginTop: "0.9rem", border: "1px solid #d8e6f7", borderRadius: 12, padding: "0.65rem", background: "#f9fcff" }}>
              <div><strong>Impression:</strong> {report.report_sections?.impression || "-"}</div>
              <div style={{ marginTop: "0.26rem" }}>
                <strong>Largest region:</strong> {largestRegion?.name || "-"}
                {largestRegion?.volume_mm3 !== undefined && largestRegion?.volume_mm3 !== null
                  ? ` (${largestRegion.volume_mm3} mm3)`
                  : ""}
              </div>
              <div style={{ marginTop: "0.26rem" }}><strong>Risk:</strong> {report.report_sections?.risk_statement || "-"}</div>
            </div>

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

            {report.pdf_url && (
              <div style={{ marginTop: "0.8rem" }}>
                <a
                  href={`${apiBase}${report.pdf_url}`}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: "#1168af", fontWeight: 600 }}
                >
                  Open generated PDF
                </a>
              </div>
            )}
          </>
        )}
      </section>
    </main>
  );
}

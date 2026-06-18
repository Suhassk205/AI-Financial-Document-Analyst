import { useState, useRef, useCallback } from "react";
import PageHeader from "@/components/PageHeader";
import { useReports } from "@/hooks/useReports";
import { useQueryClient } from "@tanstack/react-query";
import {
  UploadCloud,
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
  Info,
} from "lucide-react";
import { clsx } from "clsx";
import { API_BASE_URL } from "@/services/api";

const REPORT_TYPES = ["10-K", "10-Q", "TRANSCRIPT", "OTHER"] as const;
type ReportType = (typeof REPORT_TYPES)[number];

interface UploadResult {
  report_id: string;
  status: string;
}

/** Premium PDF Upload Page — drag-drop, file validation, async status polling. */
export default function UploadPage() {
  const { data: reportsData, refetch: refetchReports } = useReports(20, 0);
  const qc = useQueryClient();

  // Form state
  const [file, setFile] = useState<File | null>(null);
  const [reportType, setReportType] = useState<ReportType>("10-K");
  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [quarter, setQuarter] = useState<number | "">("");
  const [ticker, setTicker] = useState("");
  const [companyName, setCompanyName] = useState("");

  // UI state
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((f: File) => {
    if (!f.type.includes("pdf")) {
      setError("Only PDF files are supported.");
      return;
    }
    if (f.size > 50 * 1024 * 1024) {
      setError("File size must be under 50 MB.");
      return;
    }
    setError(null);
    setFile(f);
    setResult(null);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const dropped = e.dataTransfer.files[0];
      if (dropped) handleFile(dropped);
    },
    [handleFile],
  );

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const handleDragLeave = () => setIsDragging(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setUploading(true);
    setError(null);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("report_type", reportType);
      formData.append("year", String(year));
      if (quarter !== "") formData.append("quarter", String(quarter));
      if (ticker.trim()) formData.append("ticker", ticker.trim().toUpperCase());
      if (companyName.trim()) formData.append("company_name", companyName.trim());

      // Use fetch directly for multipart; our api helper only sends JSON
      const resp = await fetch(`${API_BASE_URL}/reports/upload`, {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData?.detail ?? `Upload failed: HTTP ${resp.status}`);
      }

      const data: UploadResult = await resp.json();
      setResult(data);
      setFile(null);
      // Refresh the reports list
      await qc.invalidateQueries({ queryKey: ["reports"] });
      await refetchReports();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const reports = reportsData?.items ?? [];

  const statusColor = (status: string) => {
    if (status === "FAILED") return "text-danger-dark bg-danger-light";
    if (
      [
        "EMBEDDED",
        "EXTRACTED",
        "COMPARED",
        "ANALYZED",
        "RISK_EXTRACTED",
        "TONE_EXTRACTED",
        "COMPLETED",
        "READY",
        "METRICS_READY",
        "COMPARISON_READY",
        "ANALYTICS_READY",
        "RISKS_READY",
      ].includes(status)
    )
      return "text-success-dark bg-success-light";
    return "text-warning-dark bg-warning-light";
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-6 animate-slide-up">
      <PageHeader
        title="Ingest Financial Document"
        subtitle="Upload SEC filings (10-K, 10-Q) for AI-powered extraction and analysis"
      />

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Upload Form */}
        <div className="lg:col-span-3 space-y-6">
          <form onSubmit={handleSubmit} className="glass-panel p-6 space-y-6">
            {/* Drop zone */}
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
              className={clsx(
                "border-2 border-dashed rounded-xl p-10 flex flex-col items-center justify-center gap-3 cursor-pointer transition-all duration-200",
                isDragging
                  ? "border-brand-500 bg-brand-50"
                  : file
                    ? "border-success bg-success-light/20"
                    : "border-surface-250 bg-surface-50/30 hover:border-brand-400 hover:bg-brand-50/30",
              )}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFile(f);
                }}
              />
              {file ? (
                <>
                  <CheckCircle2 className="w-10 h-10 text-success" />
                  <div className="text-center">
                    <p className="font-semibold text-surface-900 text-sm">{file.name}</p>
                    <p className="text-xs text-surface-500 mt-0.5">{formatSize(file.size)}</p>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setFile(null);
                    }}
                    className="text-xs text-surface-400 hover:text-danger flex items-center gap-1 mt-1"
                  >
                    <X className="w-3 h-3" /> Remove file
                  </button>
                </>
              ) : (
                <>
                  <UploadCloud
                    className={clsx(
                      "w-10 h-10 transition-colors",
                      isDragging ? "text-brand-600" : "text-surface-350",
                    )}
                  />
                  <div className="text-center">
                    <p className="font-semibold text-surface-800 text-sm">
                      Drop PDF here or{" "}
                      <span className="text-brand-600 underline underline-offset-2">browse files</span>
                    </p>
                    <p className="text-xs text-surface-450 mt-1">PDF only · Max 50 MB</p>
                  </div>
                </>
              )}
            </div>

            {/* Metadata Fields */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-surface-450 block mb-1.5">
                  Report Type *
                </label>
                <select
                  value={reportType}
                  onChange={(e) => setReportType(e.target.value as ReportType)}
                  className="w-full text-sm border border-surface-200 rounded-lg px-3 py-2 bg-white focus:ring-2 focus:ring-brand-500 focus:outline-none"
                  required
                >
                  {REPORT_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-surface-450 block mb-1.5">
                  Fiscal Year *
                </label>
                <input
                  type="number"
                  value={year}
                  onChange={(e) => setYear(Number(e.target.value))}
                  min={1900}
                  max={2200}
                  className="w-full text-sm border border-surface-200 rounded-lg px-3 py-2 bg-white focus:ring-2 focus:ring-brand-500 focus:outline-none"
                  required
                />
              </div>
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-surface-450 block mb-1.5">
                  Quarter (Optional)
                </label>
                <select
                  value={quarter}
                  onChange={(e) => setQuarter(e.target.value === "" ? "" : Number(e.target.value))}
                  className="w-full text-sm border border-surface-200 rounded-lg px-3 py-2 bg-white focus:ring-2 focus:ring-brand-500 focus:outline-none"
                >
                  <option value="">N/A (Annual)</option>
                  <option value="1">Q1</option>
                  <option value="2">Q2</option>
                  <option value="3">Q3</option>
                  <option value="4">Q4</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-surface-450 block mb-1.5">
                  Ticker Symbol
                </label>
                <input
                  type="text"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  placeholder="e.g. AAPL"
                  maxLength={16}
                  className="w-full text-sm border border-surface-200 rounded-lg px-3 py-2 bg-white focus:ring-2 focus:ring-brand-500 focus:outline-none placeholder-surface-350"
                />
              </div>
              <div className="col-span-2">
                <label className="text-xs font-bold uppercase tracking-wider text-surface-450 block mb-1.5">
                  Company Name
                </label>
                <input
                  type="text"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="e.g. Apple Inc."
                  maxLength={255}
                  className="w-full text-sm border border-surface-200 rounded-lg px-3 py-2 bg-white focus:ring-2 focus:ring-brand-500 focus:outline-none placeholder-surface-350"
                />
              </div>
            </div>

            {/* Error state */}
            {error && (
              <div className="flex items-start gap-3 p-4 rounded-xl bg-red-50 border border-red-200 text-red-700">
                <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
                <p className="text-sm font-medium">{error}</p>
              </div>
            )}

            {/* Success state */}
            {result && (
              <div className="flex items-start gap-3 p-4 rounded-xl bg-success-light border border-success/40 text-success-dark">
                <CheckCircle2 className="w-5 h-5 text-success shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-bold">Upload accepted — processing queued</p>
                  <p className="text-xs mt-0.5 font-mono text-success-dark/70">
                    Report ID: {result.report_id}
                  </p>
                  <p className="text-xs mt-1">
                    The extraction pipeline will process your document asynchronously. Check the{" "}
                    <strong>Recent Uploads</strong> panel to track progress.
                  </p>
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={!file || uploading}
              className="w-full py-3 px-4 bg-brand-600 hover:bg-brand-700 disabled:bg-surface-250 disabled:cursor-not-allowed text-white font-bold rounded-xl shadow-md shadow-brand-200 hover:shadow-brand-300 transition-all flex items-center justify-center gap-2"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Uploading & Queuing…
                </>
              ) : (
                <>
                  <UploadCloud className="w-4 h-4" />
                  Upload & Start Processing
                </>
              )}
            </button>
          </form>

          {/* Pipeline Info */}
          <div className="glass-panel p-5 bg-brand-50/20 border-brand-200/50">
            <h3 className="text-sm font-bold text-surface-900 flex items-center gap-2 mb-3">
              <Info className="w-4 h-4 text-brand-600" />
              What happens after upload?
            </h3>
            <ol className="space-y-2 text-xs text-surface-600 leading-relaxed">
              {[
                ["CHUNKED", "Document is parsed and text segments extracted from PDF structure"],
                ["EXTRACTED", "Financial metrics (revenue, margins, EBITDA) are identified by AI"],
                ["COMPARED", "Period-over-period comparisons (YoY/QoQ) are generated"],
                ["ANALYZED", "Financial signals and anomalies flagged by the analytics engine"],
                ["RISK_EXTRACTED", "Risk factors are classified by category and severity"],
                ["TONE_EXTRACTED", "Management discussion is scored for sentiment and hedging"],
                ["EMBEDDED", "Semantic embeddings indexed for Agent RAG queries"],
              ].map(([status, desc]) => (
                <li key={status} className="flex items-start gap-2">
                  <span className="font-mono font-bold text-brand-700 shrink-0 w-28">{status}</span>
                  <span>{desc}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>

        {/* Recent Uploads Panel */}
        <div className="lg:col-span-2">
          <div className="glass-panel overflow-hidden">
            <div className="px-5 py-4 border-b border-surface-100 flex items-center justify-between bg-surface-50/50">
              <h3 className="font-bold text-surface-800 text-sm flex items-center gap-2">
                <FileText className="w-4 h-4 text-brand-600" />
                Recent Uploads
              </h3>
              <span className="text-xs font-mono text-surface-400">
                {reports.length} filing{reports.length !== 1 ? "s" : ""}
              </span>
            </div>
            <div className="divide-y divide-surface-100 max-h-[600px] overflow-y-auto">
              {reports.length === 0 ? (
                <div className="p-8 text-center">
                  <UploadCloud className="w-10 h-10 text-surface-300 mx-auto mb-3" />
                  <p className="text-sm font-semibold text-surface-500">No filings ingested yet</p>
                  <p className="text-xs text-surface-400 mt-1">Upload your first document to begin</p>
                </div>
              ) : (
                reports.map((r) => (
                  <div
                    key={r.id}
                    className="px-5 py-3.5 hover:bg-surface-50/50 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-bold text-surface-900 truncate">
                          {r.original_filename ?? `Report ${r.id.slice(0, 8)}`}
                        </p>
                        <p className="text-[10px] text-surface-450 font-mono mt-0.5">
                          {r.report_type} · {r.year}
                          {r.quarter ? ` Q${r.quarter}` : ""}
                        </p>
                        {r.status !== "READY" && r.status !== "FAILED" && (
                          <div className="mt-2 w-full">
                            <div className="flex justify-between items-center mb-1">
                              <span className="text-[9px] text-surface-450">
                                {r.completed_stage ? `Last: ${r.completed_stage}` : "Starting..."}
                              </span>
                              <span className="text-[9px] font-mono text-brand-600 font-bold">
                                {r.progress ?? 0}%
                              </span>
                            </div>
                            <div className="w-full bg-surface-100 rounded-full h-1.5 overflow-hidden">
                              <div
                                className="bg-brand-500 h-1.5 rounded-full transition-all duration-500 ease-out"
                                style={{ width: `${r.progress ?? 0}%` }}
                              />
                            </div>
                          </div>
                        )}
                      </div>
                      <span
                        className={clsx(
                          "text-[9px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide shrink-0",
                          statusColor(r.status),
                        )}
                      >
                        {r.status}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

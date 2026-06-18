import PageHeader from "@/components/PageHeader";
import MetricCard from "@/components/MetricCard";
import Skeleton from "@/design-system/components/Skeleton";
import ErrorFallback from "@/design-system/patterns/ErrorFallback";
import EmptyState from "@/components/EmptyState";
import { useReports } from "@/hooks/useReports";
import { useObservability } from "@/hooks/useObservability";
import {
  BarChart3,
  ShieldAlert,
  Users,
  FileText,
  Clock,
  Activity,
  Pin,
  ExternalLink,
  PlusCircle,
} from "lucide-react";
import { Link } from "react-router-dom";

// Pinned examples for hacker/presentation demo speed
const PINNED_EXAMPLES = [
  {
    name: "Apple Inc. (AAPL)",
    type: "10-K (Annual)",
    year: "2025",
    desc: "Premium consumer tech filing featuring complex segment analysis.",
    badge: "Tech Leader",
  },
  {
    name: "Tesla Inc. (TSLA)",
    type: "10-Q (Q3)",
    year: "2025",
    desc: "High volatility risks, ESG evolution, and intense capex allocations.",
    badge: "Auto & Energy",
  },
];

/** Executive Dashboard — high-level company intelligence overview. */
export default function DashboardPage() {
  const { data, isLoading, isError, refetch } = useReports(20, 0);
  const { trackInteraction } = useObservability();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton variant="text" className="w-1/3 h-8" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Skeleton variant="card" />
          <Skeleton variant="card" />
          <Skeleton variant="card" />
          <Skeleton variant="card" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Skeleton variant="table" />
          <Skeleton variant="table" />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorFallback
        title="Dashboard Failure"
        message="Could not establish connection to the company data registers."
        resetErrorBoundary={refetch}
      />
    );
  }

  const reports = data?.items ?? [];
  const processed = reports.filter((r) =>
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
    ].includes(r.status)
  );
  const failed = reports.filter((r) => r.status === "FAILED");
  const latestReport = reports[0];

  const handlePinnedClick = (companyName: string) => {
    trackInteraction("Pinned Example Clicked", companyName);
  };

  return (
    <div className="space-y-6 animate-slide-up">
      <PageHeader
        title="Executive Dashboard"
        subtitle="AI Financial Document Analyst — Intelligence Overview"
      />

      {/* Quick Stats */}
      <div className="card-grid">
        <MetricCard
          label="Total Filings"
          value={data?.total ?? 0}
          icon={<BarChart3 className="w-5 h-5 text-brand-600" />}
        />
        <MetricCard
          label="Processed & Indexed"
          value={processed.length}
          icon={<Activity className="w-5 h-5 text-success" />}
        />
        <MetricCard
          label="Extraction Errors"
          value={failed.length}
          icon={<ShieldAlert className="w-5 h-5 text-danger" />}
        />
        <MetricCard
          label="Latest Filing Type"
          value={latestReport?.report_type ?? "—"}
          icon={<FileText className="w-5 h-5 text-warning" />}
        />
      </div>

      {/* Demo Guidance and Pinned Examples */}
      <div className="grid gap-6 md:grid-cols-3">
        <div className="md:col-span-2 space-y-6">
          {/* Pinned Examples */}
          <div className="glass-panel p-5">
            <h3 className="section-title flex items-center gap-2 mb-4">
              <Pin className="w-4 h-4 text-brand-600" />
              Demo Pinned Examples
            </h3>
            <div className="grid gap-4 sm:grid-cols-2">
              {PINNED_EXAMPLES.map((ex) => (
                <div
                  key={ex.name}
                  className="border border-surface-200 rounded-lg p-4 hover:border-brand-300 transition-colors bg-white flex flex-col justify-between"
                >
                  <div>
                    <div className="flex justify-between items-start">
                      <span className="text-xs font-semibold px-2 py-0.5 rounded bg-brand-50 text-brand-700">
                        {ex.badge}
                      </span>
                      <span className="text-[11px] text-surface-400 font-mono">
                        FY {ex.year}
                      </span>
                    </div>
                    <h4 className="text-sm font-bold text-surface-900 mt-2">{ex.name}</h4>
                    <p className="text-xs text-surface-500 mt-1">{ex.desc}</p>
                  </div>
                  <div className="mt-4 pt-3 border-t border-surface-100 flex justify-between items-center">
                    <span className="text-xs text-surface-400 font-medium">{ex.type}</span>
                    <Link
                      to="/financial"
                      onClick={() => handlePinnedClick(ex.name)}
                      className="text-xs font-semibold text-brand-600 hover:text-brand-700 flex items-center gap-1"
                    >
                      Analyze <ExternalLink className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Quick Upload Action */}
        <div className="glass-panel p-5 bg-gradient-to-br from-brand-600 to-brand-800 text-white flex flex-col justify-between">
          <div>
            <span className="text-[10px] font-bold tracking-wider uppercase opacity-75">
              Workspace Tool
            </span>
            <h3 className="text-lg font-bold mt-1">Ingest Financial Report</h3>
            <p className="text-xs text-brand-100 mt-2 leading-relaxed">
              Upload PDF SEC filings (10-K, 10-Q) directly. Our extraction service will capture, index, embed, and normalise all metrics automatically.
            </p>
          </div>
          <div className="mt-6">
            <Link
              to="/upload"
              onClick={() => trackInteraction("Upload Report Clicked", "Quick Upload")}
              className="w-full justify-center flex items-center gap-2 bg-white/20 hover:bg-white/30 text-white font-semibold text-sm py-2.5 px-4 rounded-lg transition-colors border border-white/30"
            >
              <PlusCircle className="w-4 h-4" />
              Upload Filing PDF
            </Link>
          </div>
        </div>
      </div>

      {/* Quick Navigation */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[
          {
            to: "/financial",
            label: "Financial Analysis",
            desc: "Revenue trends, margins, growth metrics",
            icon: BarChart3,
            color: "bg-brand-50 text-brand-600",
          },
          {
            to: "/risks",
            label: "Risk Intelligence",
            desc: "Risk factors, evolution tracking, severity",
            icon: ShieldAlert,
            color: "bg-danger-light text-danger-dark",
          },
          {
            to: "/management",
            label: "Management Tone",
            desc: "Sentiment, confidence, hedging analysis",
            icon: Users,
            color: "bg-success-light text-success-dark",
          },
        ].map(({ to, label, desc, icon: Icon, color }) => (
          <Link
            key={to}
            to={to}
            className="glass-panel-hover p-5 flex items-start gap-4 group bg-white"
          >
            <div
              className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${color}`}
            >
              <Icon className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-surface-800 group-hover:text-brand-700 transition-colors">
                {label}
              </h3>
              <p className="text-xs text-surface-500 mt-0.5">{desc}</p>
            </div>
          </Link>
        ))}
      </div>

      {/* Recent Activity Feed */}
      <div className="glass-panel">
        <div className="px-5 py-4 border-b border-surface-100 flex justify-between items-center">
          <h3 className="section-title flex items-center gap-2">
            <Clock className="w-4 h-4 text-surface-400" />
            Recent Activity
          </h3>
          <span className="text-xs text-surface-400 font-mono">Real-time status updates</span>
        </div>
        <div className="divide-y divide-surface-100">
          {reports.length === 0 ? (
            <div className="p-8">
              <EmptyState
                title="No reports processed yet"
                description="Upload a filing PDF using the quick actions to begin analysis."
              />
            </div>
          ) : (
            reports.slice(0, 8).map((r) => (
              <div
                key={r.id}
                className="px-5 py-3.5 flex items-center justify-between hover:bg-surface-50/50 transition-colors"
              >
                <div className="flex-1 min-w-0 mr-4">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                        r.status === "FAILED"
                          ? "bg-danger"
                          : [
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
                            ].includes(r.status)
                            ? "bg-success animate-pulse"
                            : "bg-warning"
                      }`}
                    />
                    <div className="min-w-0">
                      <span className="text-sm font-semibold text-surface-900 truncate block">
                        {r.original_filename ?? `Report ${r.id.slice(0, 8)}`}
                      </span>
                      <span className="text-xs text-surface-500 block">
                        {r.report_type} · {r.year}
                        {r.quarter ? ` Q${r.quarter}` : ""}
                      </span>
                    </div>
                  </div>
                  {r.status !== "READY" && r.status !== "FAILED" && (
                    <div className="mt-2 pl-[22px] max-w-md">
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
                <div className="flex items-center gap-4 shrink-0">
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      r.status === "FAILED"
                        ? "bg-danger-light text-danger-dark"
                        : [
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
                          ].includes(r.status)
                        ? "bg-success-light text-success-dark"
                        : "bg-warning-light text-warning-dark"
                    }`}
                  >
                    {r.status}
                  </span>
                  <Link
                    to="/financial"
                    onClick={() => trackInteraction("Analyze Action Clicked", r.id)}
                    className="text-xs font-semibold text-brand-600 hover:underline"
                  >
                    Open View
                  </Link>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

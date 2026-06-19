import PageHeader from "@/components/PageHeader";
import SectionPanel from "@/components/SectionPanel";
import DataTable, { type Column } from "@/components/DataTable";
import Skeleton from "@/design-system/components/Skeleton";
import ErrorFallback from "@/design-system/patterns/ErrorFallback";
import BenchmarkBadge from "@/components/BenchmarkBadge";
import BenchmarkRadarChart from "@/components/charts/BenchmarkRadarChart";
import BenchmarkBarChart from "@/components/charts/BenchmarkBarChart";
import { useBenchmarkRun, useBenchmarkSummary, useCreateBenchmarkRun } from "@/hooks/useBenchmark";
import { useReports } from "@/hooks/useReports";
import type { BenchmarkSummary } from "@/types/api";
import { useState } from "react";
import { Trophy, Award, Medal, PlusCircle } from "lucide-react";
import { clsx } from "clsx";

export default function BenchmarkPage() {
  const [runId, setRunId] = useState("");
  const { data: run } = useBenchmarkRun(runId || undefined);
  const { data: summaries, isLoading, isError, refetch } = useBenchmarkSummary(
    runId || undefined,
    run?.status === "COMPLETED"
  );
  const { data: reportsData } = useReports();
  const reportsList = reportsData?.items ?? [];
  const createMutation = useCreateBenchmarkRun();
  const [newRunName, setNewRunName] = useState("Competitor Cohort Benchmark");
  const [selectedCompanyIds, setSelectedCompanyIds] = useState<string[]>([]);

  const getCompanyTicker = (companyId: string) => {
    const report = reportsList.find((r) => r.company_id === companyId);
    if (!report || !report.original_filename) return companyId.slice(0, 8);
    const parts = report.original_filename.split("_");
    return parts[0] || companyId.slice(0, 8);
  };

  const uniqueCompanies = Array.from(
    new Map<string, string>(
      reportsList
        .filter((r) => r.company_id)
        .map((r) => [r.company_id as string, getCompanyTicker(r.company_id as string)])
    ).entries()
  ).map(([id, ticker]) => ({ id: id as string, ticker }));

  const handleCreateRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedCompanyIds.length < 2) return;
    try {
      const res = await createMutation.mutateAsync({
        run_name: newRunName,
        company_ids: selectedCompanyIds,
      });
      setRunId(res.id);
    } catch (err) {
      console.error(err);
    }
  };

  const handleToggleCompany = (companyId: string) => {
    setSelectedCompanyIds((prev) =>
      prev.includes(companyId)
        ? prev.filter((id) => id !== companyId)
        : [...prev, companyId]
    );
  };

  const summaryList = summaries ?? [];

  const columns: Column<BenchmarkSummary>[] = [
    { key: "company_id", header: "Company", render: (s) => <span className="font-semibold text-surface-900">{getCompanyTicker(s.company_id)}</span> },
    { key: "financial_score", header: "Financial Score", align: "center", sortable: true, render: (s) => s.financial_score?.toFixed(1) ?? "—" },
    { key: "risk_score", header: "Risk Mitigation", align: "center", sortable: true, render: (s) => s.risk_score?.toFixed(1) ?? "—" },
    { key: "tone_score", header: "Sentiment Score", align: "center", sortable: true, render: (s) => s.tone_score?.toFixed(1) ?? "—" },
    { key: "capital_allocation_score", header: "Capital Allocation", align: "center", sortable: true, render: (s) => s.capital_allocation_score?.toFixed(1) ?? "—" },
    { key: "overall_score", header: "Overall Rating", align: "center", sortable: true, render: (s) => <span className="font-bold text-brand-700">{s.overall_score?.toFixed(1) ?? "—"}</span> },
    { key: "rank", header: "Current Rank", align: "center", render: (s) => <BenchmarkBadge rank={s.rank} /> },
  ];

  const radarIndicators = ["Financial", "Risk", "Tone", "Capital Allocation"];
  const radarSeries = summaryList.map((s) => ({
    name: getCompanyTicker(s.company_id),
    values: [s.financial_score ?? 0, s.risk_score ?? 0, s.tone_score ?? 0, s.capital_allocation_score ?? 0],
  }));

  const barCompanies = summaryList.map((s) => getCompanyTicker(s.company_id));
  const barScores = summaryList.map((s) => s.overall_score ?? 0);

  // Sorting for the podium presentation
  const sortedPodium = [...summaryList].sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99)).slice(0, 3);
  
  // Arrange top 3 as: 2nd place, 1st place, 3rd place for visual podium
  const arrangedPodium = [];
  if (sortedPodium[1]) arrangedPodium.push({ ...sortedPodium[1], place: 2 });
  if (sortedPodium[0]) arrangedPodium.push({ ...sortedPodium[0], place: 1 });
  if (sortedPodium[2]) arrangedPodium.push({ ...sortedPodium[2], place: 3 });

  if (runId && isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton variant="text" className="w-1/3 h-8" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Skeleton variant="card" />
          <Skeleton variant="card" />
          <Skeleton variant="card" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Skeleton variant="chart" />
          <Skeleton variant="chart" />
        </div>
        <Skeleton variant="table" />
      </div>
    );
  }

  if (runId && isError) {
    return (
      <ErrorFallback
        title="Benchmarking Engine Failure"
        message="Failed to retrieve cross-company normalization scores."
        resetErrorBoundary={refetch}
      />
    );
  }

  return (
    <div className="space-y-6 animate-slide-up">
      <PageHeader
        title="Benchmark Analysis"
        subtitle="Competitor comparison, rankings, and dimension scores"
        actions={
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Enter benchmark run ID (e.g. run-01)…"
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
              className="text-sm border border-surface-200 rounded-lg px-3 py-2 bg-white w-64 focus:ring-2 focus:ring-brand-500 focus:outline-none"
              aria-label="Benchmark run ID"
            />
          </div>
        }
      />

      {!runId && (
        <div className="max-w-xl mx-auto animate-slide-up">
          {/* Run Cohort Benchmark */}
          <div className="glass-panel p-6 bg-white border border-surface-200 shadow-sm rounded-xl">
            <h3 className="text-base font-bold text-surface-900 flex items-center gap-2 mb-2">
              <PlusCircle className="w-5 h-5 text-brand-600" />
              Run Cohort Benchmark
            </h3>
            <p className="text-sm text-surface-500 mb-4">
              Select 2 or more processed companies to run a comparative cohort benchmark analysis.
            </p>

            <form onSubmit={handleCreateRun} className="space-y-4">
              <div>
                <label className="text-xs font-bold text-surface-450 block mb-1">
                  Benchmark Run Name
                </label>
                <input
                  type="text"
                  value={newRunName}
                  onChange={(e) => setNewRunName(e.target.value)}
                  className="w-full text-sm border border-surface-200 rounded-lg px-3 py-2 bg-white focus:ring-2 focus:ring-brand-500 focus:outline-none"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-bold text-surface-450 block mb-2">
                  Select Companies (Min 2)
                </label>
                <div className="border border-surface-150 rounded-lg p-3 max-h-40 overflow-y-auto space-y-2 bg-surface-50/50">
                  {uniqueCompanies.length === 0 ? (
                    <span className="text-xs text-surface-400 italic">No processed filings found.</span>
                  ) : (
                    uniqueCompanies.map((comp) => (
                      <label key={comp.id} className="flex items-center gap-2 text-sm text-surface-700 hover:text-surface-900 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedCompanyIds.includes(comp.id)}
                          onChange={() => handleToggleCompany(comp.id)}
                          className="rounded border-surface-300 text-brand-600 focus:ring-brand-500"
                        />
                        <span className="font-mono font-semibold">{comp.ticker}</span>
                      </label>
                    ))
                  )}
                </div>
              </div>

              <button
                type="submit"
                disabled={selectedCompanyIds.length < 2 || createMutation.isPending}
                className="w-full py-2.5 px-4 bg-brand-600 hover:bg-brand-700 disabled:bg-surface-250 text-white font-semibold rounded-lg shadow-sm transition-colors flex items-center justify-center gap-2"
              >
                {createMutation.isPending ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Enqueuing...
                  </>
                ) : (
                  "Enqueue Benchmark Run"
                )}
              </button>
            </form>
          </div>
        </div>
      )}

      {runId && run && run.status !== "COMPLETED" && (
        <div className="space-y-6">
          <div className="glass-panel p-4 text-sm text-surface-700 bg-brand-50/20 border-brand-200/50 flex items-center justify-between">
            <div>
              <span className="font-bold text-surface-900">{run.run_name}</span> · Status:{" "}
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-brand-100 text-brand-700 font-mono">
                {run.status}
              </span>
            </div>
            <span className="text-xs text-surface-450 font-mono">
              {run.company_ids.length} companies benchmarked
            </span>
          </div>

          {(run.status === "PENDING" || run.status === "PROCESSING") && (
            <div className="glass-panel p-8 flex flex-col items-center justify-center text-center bg-white border border-surface-200 animate-slide-up">
              <div className="w-12 h-12 rounded-full border-4 border-brand-200 border-t-brand-600 animate-spin mb-4" />
              <h3 className="text-base font-bold text-surface-900">AI Benchmarking in Progress</h3>
              <p className="text-sm text-surface-500 mt-2 max-w-md">
                Our competitor benchmarking engine is evaluating risk profiles, normalized financial metrics, and management sentiment weights across the company cohort. This usually takes 15–30 seconds.
              </p>
            </div>
          )}

          {run.status === "FAILED" && (
            <div className="glass-panel p-8 flex flex-col items-center justify-center text-center bg-red-50 border border-red-200 animate-slide-up">
              <div className="text-red-500 text-lg font-bold mb-2">⚠ Benchmark Run Failed</div>
              <p className="text-sm text-red-700 max-w-md">
                {run.error_message || "An error occurred during benchmarking calculations. Please verify your company data and try again."}
              </p>
            </div>
          )}
        </div>
      )}

      {summaryList.length > 0 && (
        <>
          {run && (
            <div className="glass-panel p-4 text-sm text-surface-700 bg-brand-50/20 border-brand-200/50 flex items-center justify-between">
              <div>
                <span className="font-bold text-surface-900">{run.run_name}</span> · Status:{" "}
                <span className="text-xs font-semibold px-2 py-0.5 rounded bg-success-light text-success-dark">
                  {run.status}
                </span>
              </div>
              <span className="text-xs text-surface-450 font-mono">
                {run.company_ids.length} companies benchmarked
              </span>
            </div>
          )}

          {/* Visual Podium for top 3 companies */}
          {sortedPodium.length > 0 && (
            <div className="glass-panel p-6">
              <h3 className="section-title flex items-center gap-2 mb-6 justify-center">
                <Trophy className="w-5 h-5 text-warning" />
                Benchmark Leaderboard Podium
              </h3>
              
              <div className="flex flex-col sm:flex-row items-end justify-center gap-6 pt-8 pb-4">
                {arrangedPodium.map((comp) => {
                  const isFirst = comp.place === 1;
                  const isSecond = comp.place === 2;
                  
                  return (
                    <div
                      key={comp.id}
                      className={clsx(
                        "flex flex-col items-center justify-end w-full sm:w-48 transition-all hover:scale-[1.02] duration-200",
                        isFirst ? "order-2 sm:-translate-y-4" : isSecond ? "order-1" : "order-3"
                      )}
                    >
                      {/* Avatar/Trophy Icon */}
                      <div className="mb-3 relative">
                        {isFirst && (
                          <div className="absolute -top-6 left-1/2 -translate-x-1/2 text-warning animate-bounce">
                            <Trophy className="w-6 h-6 fill-warning/20" />
                          </div>
                        )}
                        <div
                          className={clsx(
                            "w-12 h-12 rounded-full flex items-center justify-center border-2 shadow-md",
                            isFirst
                              ? "bg-warning-light border-warning text-warning-dark"
                              : isSecond
                                ? "bg-slate-100 border-slate-400 text-slate-700"
                                : "bg-orange-50 border-orange-350 text-orange-700"
                          )}
                        >
                          {isFirst ? (
                            <Award className="w-6 h-6" />
                          ) : (
                            <Medal className="w-6 h-6" />
                          )}
                        </div>
                      </div>

                      {/* Bar Podium */}
                      <div
                        className={clsx(
                          "w-full rounded-t-lg p-4 text-center border-t border-x shadow-sm flex flex-col justify-between items-center",
                          isFirst
                            ? "h-40 bg-gradient-to-b from-warning-light/40 to-warning-light/10 border-warning"
                            : isSecond
                              ? "h-32 bg-gradient-to-b from-slate-100/60 to-slate-50/20 border-slate-300"
                              : "h-24 bg-gradient-to-b from-orange-50/40 to-orange-50/10 border-orange-200"
                        )}
                      >
                        <div>
                          <span className="text-[10px] font-bold text-surface-450 uppercase block">
                            Rank {comp.place}
                          </span>
                          <span className="text-xs font-semibold text-surface-800 block truncate max-w-[140px] mt-1 font-mono">
                            {getCompanyTicker(comp.company_id)}
                          </span>
                        </div>
                        <div className="mt-2">
                          <span className="text-2xl font-bold text-surface-900">
                            {comp.overall_score?.toFixed(1)}
                          </span>
                          <span className="text-[10px] text-surface-450 block">Overall Rating</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-2">
            <SectionPanel title="Performance Dimension Overlays">
              <BenchmarkRadarChart indicators={radarIndicators} series={radarSeries} />
            </SectionPanel>
            <SectionPanel title="Overall Rating Benchmarks">
              <BenchmarkBarChart companies={barCompanies} scores={barScores} label="Overall Score" />
            </SectionPanel>
          </div>

          <SectionPanel title="Leaderboard Registry" badge={<span className="badge-neutral">{summaryList.length} companies</span>}>
            <DataTable columns={columns} data={summaryList} keyExtractor={(s) => s.id} />
          </SectionPanel>
        </>
      )}
    </div>
  );
}

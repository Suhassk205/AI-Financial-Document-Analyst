/**
 * TypeScript interfaces mirroring backend Pydantic schemas.
 *
 * These types are the ONLY contract between frontend and backend.
 * The frontend never computes business logic — it renders what the API returns.
 */

// ─── Common ──────────────────────────────────────────────────────────────────

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
}

// ─── Companies ───────────────────────────────────────────────────────────────

export interface Company {
  id: string;
  name: string;
  ticker: string | null;
  created_at: string;
  updated_at: string;
}

// ─── Reports ─────────────────────────────────────────────────────────────────

export interface ReportListItem {
  id: string;
  company_id: string | null;
  report_type: string;
  year: number;
  quarter: number | null;
  status: string;
  original_filename: string | null;
  page_count: number | null;
  created_at: string;
  updated_at: string;
  progress?: number;
  failed_stage?: string | null;
  completed_stage?: string | null;
  retry_count?: number;
}

export interface ReportListResponse {
  items: ReportListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ReportDetail extends ReportListItem {
  storage_path: string | null;
  company_name: string | null;
  ticker: string | null;
}

// ─── Financial Metrics (Phase 3A) ────────────────────────────────────────────

export interface FinancialMetric {
  id: string;
  report_id: string;
  source_chunk_id: string | null;
  metric_name: string;
  normalized_metric_name: string;
  metric_category: string;
  value: number;
  currency: string | null;
  unit: string | null;
  fiscal_year: number | null;
  fiscal_quarter: number | null;
  confidence_score: number;
  extraction_method: string;
  source_text: string | null;
  extraction_metadata: Record<string, unknown>;
}

export interface MetricListResponse {
  report_id: string;
  count: number;
  items: FinancialMetric[];
}

export interface MetricSummaryResponse {
  report_id: string;
  total: number;
  avg_confidence: number;
  by_category: Record<string, number>;
  by_method: Record<string, number>;
  by_metric: Record<string, number>;
}

// ─── Period Comparisons (Phase 3B) ───────────────────────────────────────────

export interface MetricComparison {
  id: string;
  metric_id: string;
  company_id: string;
  metric_name: string;
  comparison_type: string; // YOY | QOQ | YTD | TTM
  current_period: string;
  previous_period: string;
  current_value: number;
  previous_value: number;
  absolute_change: number | null;
  percentage_change: number | null;
}

export interface ComparisonListResponse {
  count: number;
  items: MetricComparison[];
}

export interface ComparisonSummaryResponse {
  company_id: string;
  total: number;
  by_type: Record<string, number>;
  by_metric: Record<string, number>;
  items: MetricComparison[];
}

// ─── Financial Analytics (Phase 3C) ──────────────────────────────────────────

export interface FinancialAnalytics {
  id: string;
  company_id: string;
  report_id: string;
  metric_name: string;
  signal_type: string;
  signal_code: string;
  value: number | null;
  classification: string;
  severity: string;
  supporting_metric_ids: string[];
  explanation: string | null;
}

export interface AnalyticsListResponse {
  count: number;
  items: FinancialAnalytics[];
}

export interface AnalyticsSummaryResponse {
  company_id: string;
  total: number;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  items: FinancialAnalytics[];
}

// ─── Risk Intelligence (Phase 4) ────────────────────────────────────────────

export interface RiskFactor {
  id: string;
  company_id: string;
  report_id: string;
  source_chunk_id: string | null;
  risk_name: string;
  normalized_risk_name: string;
  risk_description: string;
  category: string;
  severity: string;
  confidence_score: number;
  extraction_method: string;
  source_text: string | null;
  extraction_metadata: Record<string, unknown>;
}

export interface RiskEvolution {
  id: string;
  company_id: string;
  current_risk_id: string;
  previous_risk_id: string | null;
  evolution_type: string; // NEW | REMOVED | MODIFIED | UNCHANGED
  confidence_score: number;
  explanation: string | null;
}

export interface RiskListResponse {
  report_id: string | null;
  count: number;
  items: RiskFactor[];
}

export interface RiskEvolutionListResponse {
  company_id: string;
  count: number;
  items: RiskEvolution[];
}

export interface RiskSummaryResponse {
  company_id: string;
  total_risks: number;
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
  evolution_counts: Record<string, number>;
}

// ─── Management Tone (Phase 5) ──────────────────────────────────────────────

export interface ManagementTone {
  id: string;
  company_id: string;
  report_id: string;
  source_chunk_id: string | null;
  source_type: string;
  sentiment: string;
  confidence_level: string;
  hedging_score: number;
  positive_score: number;
  negative_score: number;
  confidence_score: number;
  extraction_method: string;
  source_text: string | null;
  extraction_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ToneEvolution {
  id: string;
  company_id: string;
  current_tone_id: string;
  previous_tone_id: string | null;
  evolution_type: string;
  confidence_score: number;
  explanation: string | null;
  created_at: string;
  updated_at: string;
}

export interface ToneSectionSummary {
  source_type: string;
  average_positive_score: number;
  average_negative_score: number;
  average_hedging_score: number;
  average_confidence_score: number;
  dominant_sentiment: string;
  record_count: number;
}

export interface CompanyToneSummary {
  company_id: string;
  total_tone_records: number;
  overall_average_positive: number;
  overall_average_negative: number;
  overall_average_hedging: number;
  overall_average_confidence: number;
  sections: ToneSectionSummary[];
}

// ─── Benchmark (Phase 8) ────────────────────────────────────────────────────

export interface BenchmarkRun {
  id: string;
  run_name: string;
  company_ids: string[];
  benchmark_type: string;
  configuration: Record<string, unknown>;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface BenchmarkResult {
  id: string;
  benchmark_run_id: string;
  company_id: string;
  benchmark_dimension: string;
  metric_name: string;
  metric_value: number | null;
  rank: number | null;
  percentile: number | null;
  score: number | null;
  created_at: string;
}

export interface BenchmarkSummary {
  id: string;
  benchmark_run_id: string;
  company_id: string;
  financial_score: number | null;
  risk_score: number | null;
  tone_score: number | null;
  capital_allocation_score: number | null;
  overall_score: number | null;
  rank: number | null;
  created_at: string;
}

export interface CompanySummaryPoint {
  company_id: string;
  company_name: string;
  ticker: string | null;
  scores: Record<string, number | null>;
  rank: number | null;
}

export interface CohortComparisonPoint {
  metric_name: string;
  dimension: string;
  values: Record<string, number | null>;
  ranks: Record<string, number | null>;
  percentiles: Record<string, number | null>;
  scores: Record<string, number | null>;
}

export interface BenchmarkComparisonResponse {
  cohort_summaries: CompanySummaryPoint[];
  cohort_results: CohortComparisonPoint[];
  configuration: Record<string, unknown>;
}

// ─── Investment Memo (Phase 9) ──────────────────────────────────────────────

export interface Citation {
  report_id: string;
  chunk_id: string | null;
  page_number: number | null;
  section_name: string | null;
  source_type: string;
  text_snippet: string | null;
}

export interface MemoSection {
  id: string;
  memo_id: string;
  section_name: string;
  section_order: number;
  content: string;
  citations: Citation[];
  created_at: string;
  updated_at: string;
}

export interface MemoDetails {
  id: string;
  company_id: string;
  report_id: string;
  benchmark_run_id: string | null;
  memo_type: string;
  status: string;
  title: string;
  executive_summary: string | null;
  content: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  sections: MemoSection[];
}

export interface MemoGenerationResponse {
  memo_id: string;
  status: string;
  message: string;
}

export interface MemoExportResponse {
  memo_id: string;
  title: string;
  format: string;
  exported_content: string;
}

// ─── Agent / Chat (Phase 7) ─────────────────────────────────────────────────

export interface Thread {
  id: string;
  thread_id: string;
  company_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  thread_id: string;
  role: string;
  content: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface AgentCitation {
  source_text: string;
  citation_id: string | null;
  page_number: number | null;
  section_name: string | null;
}

export interface ChatResponse {
  answer: string;
  key_findings: string[];
  citations: AgentCitation[];
}

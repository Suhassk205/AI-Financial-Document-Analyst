/**
 * TanStack Query hooks for report data.
 */

import { useQuery } from "@tanstack/react-query";
import { getReports } from "@/services/dashboardService";
import type { ReportListResponse } from "@/types/api";

export function useReports(limit = 20, offset = 0) {
  return useQuery<ReportListResponse>({
    queryKey: ["reports", limit, offset],
    queryFn: ({ signal }) => getReports(limit, offset, signal),
    staleTime: 5 * 60 * 1000,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data || !data.items) return false;
      const hasActive = data.items.some(
        (item) => item.status !== "READY" && item.status !== "FAILED"
      );
      return hasActive ? 2000 : false;
    },
  });
}

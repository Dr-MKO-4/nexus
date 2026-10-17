import { useQuery } from "@tanstack/react-query";

import { getReportDetail } from "@/services/api";
import type { ReportDetail } from "@/types";

/** GET /analytics/reports/{id} jamais exposé côté frontend jusqu'ici : la
 * liste des rapports (Analytics.tsx) n'ouvrait aucun détail. */
export function useReportDetail(reportId: string | undefined) {
  return useQuery<ReportDetail>({
    queryKey: ["report-detail", reportId],
    queryFn: () => getReportDetail(reportId!),
    enabled: Boolean(reportId),
  });
}

import { useQuery } from "@tanstack/react-query";

import { getReports } from "@/services/api";
import type { Report } from "@/types";

/** Ajouté pour Prompt 8.3 (route /analytics, absente du spec 8.2 mais
 * requise par la navigation/le routing de ce prompt-ci)  l'endpoint
 * GET /analytics/reports existe depuis le Prompt 7.1. */
export function useReports(clientId: string | undefined, reportType?: string) {
  return useQuery<Report[]>({
    queryKey: ["reports", clientId, reportType],
    queryFn: () => getReports(clientId!, reportType),
    enabled: Boolean(clientId),
  });
}

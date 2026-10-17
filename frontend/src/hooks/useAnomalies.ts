import { useQuery } from "@tanstack/react-query";

import { getAnomalies } from "@/services/api";
import type { Anomaly } from "@/types";

/** GET /analytics/anomalies jamais exposé côté frontend jusqu'ici bien que
 * l'endpoint existe (lit AgentDecision où decision_type="anomaly_detected"). */
export function useAnomalies(clientId: string | undefined) {
  return useQuery<Anomaly[]>({
    queryKey: ["anomalies", clientId],
    queryFn: () => getAnomalies(clientId!),
    enabled: Boolean(clientId),
  });
}

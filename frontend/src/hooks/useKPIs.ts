import { useQuery } from "@tanstack/react-query";

import { getKPIs } from "@/services/api";
import type { KPIMetric } from "@/types";

/** Bornes ISO 8601 optionnelles  miroir de `GetKPIsParams` (api.ts) : le
 * backend applique sa propre fenêtre par défaut (7 derniers jours, voir
 * analytics.py: `_default_period`) si omises. */
export interface Period {
  start?: string;
  end?: string;
}

export function useKPIs(clientId: string | undefined, period?: Period) {
  return useQuery<KPIMetric[]>({
    queryKey: ["kpis", clientId, period?.start, period?.end],
    queryFn: () => getKPIs({ client_id: clientId!, period_start: period?.start, period_end: period?.end }),
    enabled: Boolean(clientId),
  });
}

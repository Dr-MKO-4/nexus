import { useQuery } from "@tanstack/react-query";

import { getChannelPerformance } from "@/services/api";
import type { ChannelPerformance } from "@/types";

/** Ajouté au-delà de la liste explicite du spec 8.1 : Prompt 8.2
 * (ContentManagement.tsx, onglet "Campagnes SEA") en a besoin pour lire
 * /analytics/channels. */
export function useChannelPerformanceQuery(clientId: string | undefined) {
  return useQuery<ChannelPerformance[]>({
    queryKey: ["channel-performance", clientId],
    queryFn: () => getChannelPerformance({ client_id: clientId! }),
    enabled: Boolean(clientId),
  });
}

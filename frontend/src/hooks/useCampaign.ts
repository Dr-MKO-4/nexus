import { useQuery, type UseQueryOptions } from "@tanstack/react-query";

import { getCampaign } from "@/services/api";
import type { Campaign } from "@/types";

/** `options` (ex. `refetchInterval`) : ajouté pour NewObjective.tsx, qui a
 * besoin de re-poller une campagne fraîchement créée tant qu'elle est
 * active  aucun événement WebSocket fiable pour ça (CAMPAIGN_UPDATE n'est
 * émis par aucun code backend, voir le rapport d'audit). */
export function useCampaign(id: string | undefined, options?: Partial<UseQueryOptions<Campaign>>) {
  return useQuery<Campaign>({
    queryKey: ["campaign", id],
    queryFn: () => getCampaign(id!),
    enabled: Boolean(id),
    ...options,
  });
}

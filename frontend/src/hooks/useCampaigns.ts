import { useQuery } from "@tanstack/react-query";

import { getCampaigns } from "@/services/api";
import type { Campaign } from "@/types";

/** "Refetch automatique" (spec) : `refetchInterval`  pas de valeur imposée
 * par le spec, 15s choisi comme compromis raisonnable entre fraîcheur et
 * charge. CAMPAIGN_UPDATE (voir campaignStore.ts) n'est actuellement émis
 * par aucun code backend (vérifié) : ce polling est donc le SEUL mécanisme
 * de fraîcheur réellement actif pour les campagnes, pas un simple filet de
 * sécurité en complément d'un temps réel qui n'existe pas encore. */
const REFETCH_INTERVAL_MS = 15_000;

export function useCampaigns(clientId: string | undefined) {
  return useQuery<Campaign[]>({
    queryKey: ["campaigns", clientId],
    queryFn: () => getCampaigns(clientId!),
    enabled: Boolean(clientId),
    refetchInterval: REFETCH_INTERVAL_MS,
  });
}

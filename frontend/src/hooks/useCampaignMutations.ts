import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { archiveCampaign, getCampaignHistory, updateCampaign, type UpdateCampaignPayload } from "@/services/api";
import type { CampaignHistorySnapshot } from "@/types";

/** Time-travel LangGraph (GET /campaigns/{id}/history) — jamais exposé côté
 * frontend jusqu'ici bien que l'endpoint existe depuis le Prompt 7.1. */
export function useCampaignHistory(campaignId: string | undefined) {
  return useQuery<CampaignHistorySnapshot[]>({
    queryKey: ["campaign-history", campaignId],
    queryFn: () => getCampaignHistory(campaignId!),
    enabled: Boolean(campaignId),
  });
}

export function useUpdateCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UpdateCampaignPayload }) => updateCampaign(id, payload),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      queryClient.invalidateQueries({ queryKey: ["campaign", id] });
    },
  });
}

export function useArchiveCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => archiveCampaign(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
  });
}

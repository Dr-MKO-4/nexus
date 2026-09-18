import { create } from "zustand";

import type { Campaign } from "@/types";

/**
 * Ce store coexiste avec `hooks/useCampaigns.ts` (React Query) plutôt que de
 * le remplacer : React Query gère le fetch/cache/refetch HTTP, ce store est
 * conçu pour tenir l'état qu'une mise à jour WEBSOCKET (CAMPAIGN_UPDATE)
 * pourrait modifier en temps réel entre deux cycles de refetch 
 * `upsertCampaign` est l'action prévue à cet effet.
 *
 * État réel (vérifié, pas supposé) : `upsertCampaign` n'est appelé NULLE
 * PART dans ce frontend à ce jour, et `CAMPAIGN_UPDATE`/`BUDGET_UPDATE` ne
 * sont émis par AUCUN code backend (recherche exhaustive dans backend/ :
 * `AgentBroadcaster.broadcast_campaign_update`/`broadcast_budget_update`
 * n'ont aucun appelant en dehors de leur propre définition, contrairement à
 * `broadcast_hitl_request`/`broadcast_alert`/`broadcast_report_ready`/
 * `broadcast_hitl_resolved`, qui ont tous un vrai point d'appel). Ce store
 * reste donc alimenté uniquement par `setCampaigns` (React Query) tant que
 * ce câblage temps réel n'est pas construit ailleurs.
 */
interface CampaignState {
  campaigns: Campaign[];
  currentCampaign: Campaign | null;
  loading: boolean;
  error: string | null;
  setCampaigns: (campaigns: Campaign[]) => void;
  setCurrentCampaign: (campaign: Campaign | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  /** Insère ou remplace une campagne par id  utilisé pour les mises à jour
   * WebSocket ponctuelles (une seule campagne à la fois), pas un refetch complet. */
  upsertCampaign: (campaign: Campaign) => void;
}

export const useCampaignStore = create<CampaignState>((set) => ({
  campaigns: [],
  currentCampaign: null,
  loading: false,
  error: null,

  setCampaigns: (campaigns) => set({ campaigns }),
  setCurrentCampaign: (campaign) => set({ currentCampaign: campaign }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),

  upsertCampaign: (campaign) =>
    set((state) => {
      const index = state.campaigns.findIndex((c) => c.id === campaign.id);
      const campaigns =
        index >= 0
          ? state.campaigns.map((c, i) => (i === index ? campaign : c))
          : [...state.campaigns, campaign];
      const currentCampaign = state.currentCampaign?.id === campaign.id ? campaign : state.currentCampaign;
      return { campaigns, currentCampaign };
    }),
}));

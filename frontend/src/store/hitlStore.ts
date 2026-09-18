import { create } from "zustand";

import type { HITLRequest } from "@/types";

interface HITLState {
  pendingValidations: HITLRequest[];
  count: number;
  setPendingValidations: (validations: HITLRequest[]) => void;
  /** Ajout d'une validation reçue en direct via HITL_INTERRUPT (WebSocket). */
  addPendingValidation: (validation: HITLRequest) => void;
  /** Retrait après approve/reject/modify, ou événement HITL_RESOLVED. */
  removePendingValidation: (campaignId: string) => void;
}

export const useHITLStore = create<HITLState>((set) => ({
  pendingValidations: [],
  count: 0,

  setPendingValidations: (validations) => set({ pendingValidations: validations, count: validations.length }),

  addPendingValidation: (validation) =>
    set((state) => {
      if (state.pendingValidations.some((v) => v.campaign_id === validation.campaign_id)) {
        return state;
      }
      const pendingValidations = [...state.pendingValidations, validation];
      return { pendingValidations, count: pendingValidations.length };
    }),

  removePendingValidation: (campaignId) =>
    set((state) => {
      const pendingValidations = state.pendingValidations.filter((v) => v.campaign_id !== campaignId);
      return { pendingValidations, count: pendingValidations.length };
    }),
}));

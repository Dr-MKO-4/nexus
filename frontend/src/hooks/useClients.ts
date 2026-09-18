import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getClientDetail, getClients, updateClientBrand, updateClientIntegrations,
  type UpdateClientBrandPayload,
} from "@/services/api";
import type { ClientDetail, ClientSummary } from "@/types";

/** GET /clients (ADMIN uniquement)  sélecteur de client dans Header.tsx. */
export function useClients(enabled: boolean) {
  return useQuery<ClientSummary[]>({
    queryKey: ["clients"],
    queryFn: getClients,
    enabled,
  });
}

export function useClientDetail(clientId: string | undefined) {
  return useQuery<ClientDetail>({
    queryKey: ["client-detail", clientId],
    queryFn: () => getClientDetail(clientId!),
    enabled: Boolean(clientId),
  });
}

export function useUpdateClientBrand() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ clientId, payload }: { clientId: string; payload: UpdateClientBrandPayload }) =>
      updateClientBrand(clientId, payload),
    onSuccess: (_data, { clientId }) => queryClient.invalidateQueries({ queryKey: ["client-detail", clientId] }),
  });
}

export function useUpdateClientIntegrations() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ clientId, integrations }: { clientId: string; integrations: Record<string, unknown> }) =>
      updateClientIntegrations(clientId, integrations),
    onSuccess: (_data, { clientId }) => queryClient.invalidateQueries({ queryKey: ["client-detail", clientId] }),
  });
}

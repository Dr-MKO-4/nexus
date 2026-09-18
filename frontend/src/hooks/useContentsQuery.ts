import { useQuery } from "@tanstack/react-query";

import { getContents, type GetContentsParams } from "@/services/api";
import type { Content } from "@/types";

/** Nommé différemment de `getContents` (services/api.ts) pour ne pas
 * entrer en conflit  ajouté au-delà de la liste explicite du spec 8.1
 * (qui ne nommait que des hooks de lecture pour campaigns/agents/hitl/kpis/
 * calendar) : Prompt 8.2 (ContentManagement.tsx, onglets Bibliothèque/
 * Visuels) en a réellement besoin pour la data-fetching de contenus. */
export function useContentsQuery(clientId: string | undefined, params?: Omit<GetContentsParams, "client_id">) {
  return useQuery<Content[]>({
    queryKey: ["contents", clientId, params],
    queryFn: () => getContents({ client_id: clientId!, ...params }),
    enabled: Boolean(clientId),
  });
}

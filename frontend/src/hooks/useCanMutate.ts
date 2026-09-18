import { useAuthStore } from "@/store";

/**
 * Reflète EXACTEMENT `_MUTATE_ROLES`/`_ACTION_ROLES` (ADMIN, MANAGER) du
 * backend (routes/campaigns.py, routes/hitl.py, routes/content.py,
 * routes/agents.py: POST /trigger)  trouvé manquant lors d'un audit
 * frontend/backend : AUCUN composant ne vérifiait le rôle avant d'afficher
 * un bouton d'action, alors que le backend rejette ces mêmes actions en 403
 * pour un VIEWER. Un seul hook partagé plutôt qu'un rôle codé en dur dans
 * chaque page, pour rester synchronisé si la liste de rôles change un jour.
 */
export function useCanMutate(): boolean {
  const role = useAuthStore((s) => s.user?.role);
  return role === "admin" || role === "manager";
}

/** GET /agents/{name}/logs (routes/agents.py) restreint spécifiquement à
 * ADMIN/MANAGER  même liste que `useCanMutate` aujourd'hui, mais exposé
 * séparément car ce n'est pas une action de MUTATION (c'est un GET) : les
 * deux pourraient diverger si le backend change l'un sans l'autre. */
export function useCanViewAgentLogs(): boolean {
  const role = useAuthStore((s) => s.user?.role);
  return role === "admin" || role === "manager";
}

import { useQuery } from "@tanstack/react-query";

import { getAgentLogs, type AgentLogEntry } from "@/services/api";

/**
 * `enabled` : GET /agents/{name}/logs restreint ADMIN/MANAGER côté backend
 * (routes/agents.py)  trouvé manquant lors d'un audit frontend/backend :
 * ce hook était appelé sans condition pour CHAQUE carte d'agent, y compris
 * pour un VIEWER, qui recevait un 403 silencieux (masqué par l'écran
 * "Aucune décision enregistrée", trompeur). L'appelant doit passer
 * `enabled: useCanViewAgentLogs()` pour n'exécuter la requête que pour les
 * rôles autorisés.
 */
export function useAgentLogs(agentName: string, limit = 5, enabled = true) {
  return useQuery<AgentLogEntry[]>({
    queryKey: ["agent-logs", agentName, limit],
    queryFn: () => getAgentLogs(agentName, limit),
    enabled,
  });
}

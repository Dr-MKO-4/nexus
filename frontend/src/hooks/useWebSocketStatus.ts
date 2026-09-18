import { useEffect, useState } from "react";

import { websocketService, type ConnectionStatus } from "@/services/websocket";

/** Statut réel de la connexion WebSocket  utilisé par l'indicateur
 * "Système actif" (Sidebar.tsx, Prompt 8.3). */
export function useWebSocketStatus(): ConnectionStatus {
  const [status, setStatus] = useState<ConnectionStatus>(websocketService.getStatus());

  useEffect(() => websocketService.subscribeToStatus(setStatus), []);

  return status;
}

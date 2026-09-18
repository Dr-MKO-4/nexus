import { useEffect, useRef } from "react";

import { websocketService } from "@/services/websocket";
import type { EventType, WebSocketMessage } from "@/types";

/**
 * Abonnement à un type d'événement WebSocket  PAS le cycle de vie de la
 * connexion elle-même (`websocketService.connect()`/`disconnect()`) :
 * plusieurs composants utilisent ce hook simultanément pour des
 * `EventType` différents, connecter/déconnecter à chaque montage/démontage
 * de CHACUN d'eux casserait le partage de la connexion unique (singleton).
 * La connexion est établie une fois, au niveau de l'application (layout
 * racine, quand `useAuthStore.token` devient disponible  Prompt 8.2+, pas
 * encore construit) ; ce hook ne fait que s'abonner/se désabonner d'un
 * canal d'événements déjà ouvert.
 *
 * `callback` est conservé dans une ref pour que l'identité de la fonction
 * passée par l'appelant (souvent recréée à chaque rendu si non mémoïsée
 * avec `useCallback`) ne force pas un nouvel abonnement à chaque rendu.
 */
export function useWebSocket<TPayload = Record<string, unknown>>(
  eventType: EventType,
  callback: (message: WebSocketMessage<TPayload>) => void,
): void {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    const unsubscribe = websocketService.subscribe(eventType, (message) => {
      callbackRef.current(message as WebSocketMessage<TPayload>);
    });
    return unsubscribe;
  }, [eventType]);
}

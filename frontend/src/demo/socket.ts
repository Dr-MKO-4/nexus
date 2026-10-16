/**
 * Service WebSocket de la démo : même interface publique que
 * `WebSocketService` (services/websocket.ts), alimenté par le bus
 * d'événements du moteur au lieu de `/ws/{client_id}`.
 */
import type { EventType, WebSocketMessage } from "@/types";
import type { ConnectionStatus } from "@/services/websocket";

import { onMessage, startBackgroundActivity } from "./engine";

type Listener = (message: WebSocketMessage) => void;
type StatusListener = (status: ConnectionStatus) => void;

export class DemoWebSocketService {
  private status: ConnectionStatus = "disconnected";
  private statusListeners = new Set<StatusListener>();
  private listeners = new Map<EventType, Set<Listener>>();
  private unsubscribeBus: (() => void) | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;

  connect(_token: string): void {
    this.setStatus("connecting");
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.unsubscribeBus?.();
      this.unsubscribeBus = onMessage((m) => this.listeners.get(m.event_type)?.forEach((l) => l(m)));
      startBackgroundActivity();
      this.setStatus("connected");
    }, 350);
  }

  disconnect(): void {
    if (this.timer) clearTimeout(this.timer);
    this.unsubscribeBus?.();
    this.unsubscribeBus = null;
    this.setStatus("disconnected");
  }

  getStatus(): ConnectionStatus {
    return this.status;
  }

  subscribeToStatus(callback: StatusListener): () => void {
    this.statusListeners.add(callback);
    callback(this.status);
    return () => {
      this.statusListeners.delete(callback);
    };
  }

  subscribe(eventType: EventType, callback: Listener): () => void {
    if (!this.listeners.has(eventType)) this.listeners.set(eventType, new Set());
    this.listeners.get(eventType)!.add(callback);
    return () => {
      this.listeners.get(eventType)?.delete(callback);
    };
  }

  send(_data: object): void {
    /* aucune action côté serveur en démo */
  }

  private setStatus(status: ConnectionStatus) {
    if (this.status === status) return;
    this.status = status;
    this.statusListeners.forEach((l) => l(status));
  }
}

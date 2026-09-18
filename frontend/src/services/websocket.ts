/**
 * Service WebSocket (singleton)  Prompt 8.1.
 *
 * `connect(token)` : le endpoint backend réel est `/ws/{client_id}?token=...`
 * (backend/api/websocket/handlers.py, Prompt 7.2)  un `client_id` dans le
 * CHEMIN, pas seulement un token en query. Le spec ne demande que
 * `connect(token)` : ce `client_id` est donc extrait directement du JWT
 * (claim `client_id`, voir `auth.create_access_token`) en décodant son
 * payload côté client (base64url du 2e segment  PAS une vérification de
 * signature, inutile ici : le serveur revalidera le token de toute façon à
 * la connexion ; ce décodage sert uniquement à construire l'URL).
 *
 * Heartbeat : le serveur envoie `{"type": "ping", ...}` toutes les 30s
 * (connection_manager.py)  ce service répond automatiquement par
 * `{"type": "pong"}`, en interne, jamais exposé aux abonnés `subscribe()`
 * (qui ne reçoivent que de vrais `WebSocketMessage`, avec un `event_type`
 * parmi les 9 valeurs de `EventType`).
 */

import { EventType, type WebSocketMessage } from "@/types";

type Listener = (message: WebSocketMessage) => void;
export type ConnectionStatus = "connected" | "connecting" | "disconnected";
type StatusListener = (status: ConnectionStatus) => void;

const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 30_000;

function decodeJwtClientId(token: string): string | null {
  try {
    const payloadSegment = token.split(".")[1];
    if (!payloadSegment) return null;
    const base64 = payloadSegment.replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "="));
    const payload = JSON.parse(json) as { client_id?: string | null };
    return payload.client_id ?? null;
  } catch {
    return null;
  }
}

class WebSocketService {
  private socket: WebSocket | null = null;
  private token: string | null = null;
  private listeners: Map<EventType, Set<Listener>> = new Map();
  private outgoingQueue: object[] = [];
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private manuallyDisconnected = false;
  private status: ConnectionStatus = "disconnected";
  private statusListeners: Set<StatusListener> = new Set();

  connect(token: string): void {
    this.manuallyDisconnected = false;
    this.token = token;
    this._open();
  }

  disconnect(): void {
    this.manuallyDisconnected = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
    this._setStatus("disconnected");
  }

  getStatus(): ConnectionStatus {
    return this.status;
  }

  /** Utilisé par le "Système actif" (Sidebar, Prompt 8.3)  un statut réel
   * de connexion, pas une valeur inventée. */
  subscribeToStatus(callback: StatusListener): () => void {
    this.statusListeners.add(callback);
    callback(this.status);
    return () => {
      this.statusListeners.delete(callback);
    };
  }

  private _setStatus(status: ConnectionStatus): void {
    if (this.status === status) return;
    this.status = status;
    for (const listener of this.statusListeners) listener(status);
  }

  subscribe(eventType: EventType, callback: Listener): () => void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(callback);
    return () => {
      this.listeners.get(eventType)?.delete(callback);
    };
  }

  /** Envoie un message au serveur  mis en file si la connexion est
   * perdue, vidée automatiquement à la reconnexion (spec : "queue des
   * messages si connexion perdue"). */
  send(data: object): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(data));
    } else {
      this.outgoingQueue.push(data);
    }
  }

  private _open(): void {
    if (!this.token) return;
    const clientId = decodeJwtClientId(this.token);
    if (!clientId) {
      console.error("websocket.ts: impossible d'extraire client_id du token JWT  connexion annulée.");
      this._setStatus("disconnected");
      return;
    }

    this._setStatus("connecting");
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const base = import.meta.env.VITE_WS_BASE_URL ?? `${wsProtocol}//${window.location.host}`;
    const url = `${base}/ws/${clientId}?token=${encodeURIComponent(this.token)}`;

    const socket = new WebSocket(url);
    this.socket = socket;

    socket.onopen = () => {
      this.reconnectAttempts = 0;
      this._setStatus("connected");
      this._flushQueue();
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      if (data.type === "ping") {
        this.send({ type: "pong" });
        return;
      }
      if (data.type === "ack" || data.type === "error") {
        // Réponse à une action envoyée via send() (ex. hitl_approve)  pas
        // un événement de diffusion, rien à notifier aux abonnés EventType.
        return;
      }

      const message = data as unknown as WebSocketMessage;
      if (message.event_type && this.listeners.has(message.event_type)) {
        for (const listener of this.listeners.get(message.event_type)!) {
          listener(message);
        }
      }
    };

    socket.onclose = () => {
      this.socket = null;
      if (!this.manuallyDisconnected) {
        this._setStatus("connecting");
        this._scheduleReconnect();
      } else {
        this._setStatus("disconnected");
      }
    };

    socket.onerror = () => {
      socket.close();
    };
  }

  private _scheduleReconnect(): void {
    const delay = Math.min(RECONNECT_BASE_DELAY_MS * 2 ** this.reconnectAttempts, RECONNECT_MAX_DELAY_MS);
    this.reconnectAttempts += 1;
    this.reconnectTimer = setTimeout(() => this._open(), delay);
  }

  private _flushQueue(): void {
    while (this.outgoingQueue.length > 0 && this.socket?.readyState === WebSocket.OPEN) {
      const data = this.outgoingQueue.shift()!;
      this.socket.send(JSON.stringify(data));
    }
  }
}

export const websocketService = new WebSocketService();

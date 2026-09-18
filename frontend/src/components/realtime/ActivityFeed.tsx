import { useCallback, useRef, useState } from "react";

import { useWebSocket } from "@/hooks";
import { EventType, type WebSocketMessage } from "@/types";
import { cn } from "@/lib/utils";

const MAX_ENTRIES = 50;
/** Distance (px) au bas du conteneur en dessous de laquelle on considère
 * l'utilisateur "au bas" du flux  au-delà, on considère qu'il a scrollé
 * manuellement et on met l'auto-scroll en pause (spec). */
const BOTTOM_THRESHOLD_PX = 32;

type Severity = "success" | "warning" | "error" | "info";

const SEVERITY_CLASS: Record<Severity, string> = {
  success: "text-green-700 dark:text-green-400",
  warning: "text-amber-700 dark:text-amber-400",
  error: "text-red-700 dark:text-red-400",
  info: "text-blue-700 dark:text-blue-400",
};

interface FeedEntry {
  id: string;
  timestamp: string;
  agent: string;
  message: string;
  severity: Severity;
}

/**
 * Classement par sévérité  aucun champ "severity" n'existe sur
 * `WebSocketMessage` (events.py) : dérivé du `event_type` et, pour `ALERT`,
 * du `level` réel du payload (Alert.level, voir state_models.py) plutôt que
 * d'un champ inventé.
 */
function classify(message: WebSocketMessage): { severity: Severity; label: string } {
  switch (message.event_type) {
    case EventType.HITL_RESOLVED:
      return { severity: "success", label: "Validation résolue" };
    case EventType.HITL_INTERRUPT:
      return { severity: "warning", label: "Validation requise" };
    case EventType.ALERT: {
      const level = (message.payload as { level?: string }).level;
      if (level === "critical") return { severity: "error", label: String((message.payload as { message?: string }).message ?? "Alerte critique") };
      if (level === "warning") return { severity: "warning", label: String((message.payload as { message?: string }).message ?? "Alerte") };
      return { severity: "info", label: String((message.payload as { message?: string }).message ?? "Alerte") };
    }
    case EventType.TASK_PROGRESS:
      return { severity: "info", label: `Tâche : ${(message.payload as { celery_event_type?: string }).celery_event_type ?? "progression"}` };
    case EventType.AGENT_STATUS:
      return { severity: "info", label: `Statut : ${(message.payload as { status?: string }).status ?? "changement"}` };
    case EventType.BUDGET_UPDATE:
      return { severity: "info", label: "Mise à jour budget" };
    case EventType.CAMPAIGN_UPDATE:
      return { severity: "info", label: "Mise à jour campagne" };
    case EventType.REPORT_READY:
      return { severity: "success", label: "Rapport disponible" };
    case EventType.CONTENT_STREAM:
      return { severity: "info", label: "Génération de contenu" };
    default:
      return { severity: "info", label: String(message.event_type) };
  }
}

/**
 * Fil d'activité temps réel  Prompt 8.3, extrait en composant réutilisable
 * (utilisé par AgentControl.tsx). Nouveaux événements ajoutés en FIN de
 * liste (ordre chronologique, "scroll inversé" par rapport à un flux qui
 * empilerait le plus récent en haut) ; le conteneur défile automatiquement
 * vers le bas à chaque nouvel événement, SAUF si l'utilisateur a scrollé
 * manuellement vers le haut (pause de l'auto-scroll jusqu'à ce qu'il
 * revienne en bas lui-même).
 */
export default function ActivityFeed() {
  const [entries, setEntries] = useState<FeedEntry[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);

  const handleEvent = useCallback((message: WebSocketMessage) => {
    const { severity, label } = classify(message);
    const entry: FeedEntry = {
      id: crypto.randomUUID(),
      timestamp: message.timestamp,
      agent: message.agent_name ?? "système",
      message: label,
      severity,
    };
    setEntries((prev) => [...prev, entry].slice(-MAX_ENTRIES));

    requestAnimationFrame(() => {
      if (autoScrollRef.current && containerRef.current) {
        containerRef.current.scrollTop = containerRef.current.scrollHeight;
      }
    });
  }, []);

  // Appels dépliés (Rules of Hooks  pas de boucle sur les EventType).
  useWebSocket(EventType.AGENT_STATUS, handleEvent);
  useWebSocket(EventType.TASK_PROGRESS, handleEvent);
  useWebSocket(EventType.HITL_INTERRUPT, handleEvent);
  useWebSocket(EventType.HITL_RESOLVED, handleEvent);
  useWebSocket(EventType.CONTENT_STREAM, handleEvent);
  useWebSocket(EventType.ALERT, handleEvent);
  useWebSocket(EventType.BUDGET_UPDATE, handleEvent);
  useWebSocket(EventType.CAMPAIGN_UPDATE, handleEvent);
  useWebSocket(EventType.REPORT_READY, handleEvent);

  function handleScroll() {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    autoScrollRef.current = distanceFromBottom <= BOTTOM_THRESHOLD_PX;
  }

  return (
    <div ref={containerRef} onScroll={handleScroll} className="h-64 space-y-0.5 overflow-y-auto rounded-md border border-border p-2 font-mono text-xs">
      {entries.length === 0 ? (
        <p className="text-muted-foreground">Aucun événement reçu pour l'instant.</p>
      ) : (
        entries.map((entry) => (
          <p key={entry.id} className={cn(SEVERITY_CLASS[entry.severity])}>
            [{new Date(entry.timestamp).toLocaleTimeString()}] [{entry.agent}] {entry.message}
          </p>
        ))
      )}
    </div>
  );
}

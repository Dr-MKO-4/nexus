import { cn } from "@/lib/utils";

export interface TimelineEntry {
  id: string;
  timestamp: string;
  title: string;
  description?: string;
}

export interface TimelineProps {
  entries: TimelineEntry[];
  className?: string;
}

/** Affichage chronologique des actions (spec)  générique : consommé aussi
 * bien pour l'historique d'une campagne (DecisionLog, AgentDecision) que
 * pour un flux d'événements WebSocket, sans dépendre d'une forme métier
 * précise (seuls `timestamp`/`title` sont requis). */
export function Timeline({ entries, className }: TimelineProps) {
  return (
    <ol className={cn("relative space-y-4 border-l border-neutral-200 pl-4 dark:border-neutral-800", className)}>
      {entries.map((entry) => (
        <li key={entry.id} className="relative">
          <span className="absolute -left-[1.28rem] top-1 h-2 w-2 rounded-full bg-neutral-400" />
          <p className="text-xs text-neutral-400">{new Date(entry.timestamp).toLocaleString()}</p>
          <p className="text-sm font-medium text-neutral-900 dark:text-neutral-50">{entry.title}</p>
          {entry.description && <p className="text-sm text-neutral-500 dark:text-neutral-400">{entry.description}</p>}
        </li>
      ))}
    </ol>
  );
}

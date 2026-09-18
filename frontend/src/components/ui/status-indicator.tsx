import type { AgentStatus } from "@/types";
import { cn } from "@/lib/utils";

const STATUS_COLOR: Record<AgentStatus, string> = {
  active: "bg-green-500",
  idle: "bg-neutral-400",
  error: "bg-red-500",
  paused: "bg-amber-500",
};

export interface StatusIndicatorProps {
  status: AgentStatus;
  /** Anime le point (pulse)  désactivé pour "idle"/"paused" par défaut :
   * une animation constante sur un état non-actif serait trompeuse. */
  animated?: boolean;
  className?: string;
}

/** Point coloré animé pour les statuts temps réel (spec). */
export function StatusIndicator({ status, animated = status === "active", className }: StatusIndicatorProps) {
  return (
    <span className={cn("relative inline-flex h-2.5 w-2.5", className)} role="status" aria-label={status}>
      {animated && (
        <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-75", STATUS_COLOR[status])} />
      )}
      <span className={cn("relative inline-flex h-2.5 w-2.5 rounded-full", STATUS_COLOR[status])} />
    </span>
  );
}

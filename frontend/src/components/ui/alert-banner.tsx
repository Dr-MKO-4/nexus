import { AlertTriangle, Info, OctagonAlert, X } from "lucide-react";

import type { Alert, AlertLevel } from "@/types";
import { cn } from "@/lib/utils";

const LEVEL_STYLE: Record<AlertLevel, string> = {
  info: "border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-100",
  warning: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100",
  critical: "border-red-200 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-100",
};

const LEVEL_ICON: Record<AlertLevel, typeof Info> = {
  info: Info,
  warning: AlertTriangle,
  critical: OctagonAlert,
};

export interface AlertBannerProps {
  alert: Alert;
  /** Action associée (ex. "Approuver"/"Voir la campagne")  `action_required`
   * (backend) indique SEULEMENT qu'une action est attendue, il ne dit pas
   * LAQUELLE ni ne fournit de handler : à fournir par l'appelant, qui seul
   * connaît le contexte (quelle campagne, quel écran). */
  action?: { label: string; onClick: () => void };
  onDismiss?: () => void;
  className?: string;
}

export function AlertBanner({ alert, action, onDismiss, className }: AlertBannerProps) {
  const Icon = LEVEL_ICON[alert.level];

  return (
    <div role="alert" className={cn("flex items-start gap-3 rounded-lg border p-3 text-sm", LEVEL_STYLE[alert.level], className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1">
        <p className="font-medium">{alert.message}</p>
        <p className="mt-0.5 text-xs opacity-70">
          {alert.source} · {new Date(alert.timestamp).toLocaleString()}
        </p>
        {action && (
          <button
            type="button"
            onClick={action.onClick}
            className="mt-2 rounded-md border border-current px-2 py-1 text-xs font-medium hover:bg-white/40"
          >
            {action.label}
          </button>
        )}
      </div>
      {onDismiss && (
        <button type="button" onClick={onDismiss} aria-label="Fermer" className="shrink-0 opacity-60 hover:opacity-100">
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

import { Inbox } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface EmptyStateProps {
  message?: string;
  icon?: ReactNode;
  action?: { label: string; onClick: () => void };
  className?: string;
}

export function EmptyState({ message = "Rien à afficher pour le moment.", icon, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 py-12 text-neutral-400", className)}>
      {icon ?? <Inbox className="h-6 w-6" />}
      <p className="text-sm">{message}</p>
      {action && (
        <button type="button" onClick={action.onClick} className="mt-1 rounded-md border border-neutral-300 px-3 py-1 text-xs font-medium hover:bg-neutral-50">
          {action.label}
        </button>
      )}
    </div>
  );
}

import { CircleAlert } from "lucide-react";

import { cn } from "@/lib/utils";

export interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({ message = "Une erreur est survenue.", onRetry, className }: ErrorStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 py-12 text-red-600", className)}>
      <CircleAlert className="h-6 w-6" />
      <p className="text-sm">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-1 rounded-md border border-red-300 px-3 py-1 text-xs font-medium hover:bg-red-50">
          Réessayer
        </button>
      )}
    </div>
  );
}

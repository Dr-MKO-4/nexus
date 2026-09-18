import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

export interface LoadingStateProps {
  label?: string;
  className?: string;
}

export function LoadingState({ label = "Chargement...", className }: LoadingStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 py-12 text-neutral-500", className)}>
      <Loader2 className="h-6 w-6 animate-spin" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

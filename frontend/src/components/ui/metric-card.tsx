import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

export interface MetricCardProps {
  label: string;
  value: string | number;
  variation?: number;
  trend?: "up" | "down" | "stable";
  className?: string;
}

const TREND_ICON = { up: TrendingUp, down: TrendingDown, stable: Minus } as const;

function variationColor(variation: number): string {
  if (variation > 0) return "text-[#16a34a]";
  if (variation < 0) return "text-destructive";
  return "text-muted-foreground";
}

export function MetricCard({ label, value, variation, trend, className }: MetricCardProps) {
  const TrendIcon = trend ? TREND_ICON[trend] : null;

  return (
    <div className={cn(
      "border-2 border-border bg-background p-5",
      className
    )}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        {label}
      </p>
      <div className="mt-2 flex items-baseline gap-2">
        <p className="text-[28px] font-black leading-none text-foreground">{value}</p>
        {variation !== undefined && (
          <span className={cn("flex items-center gap-0.5 text-xs font-semibold", variationColor(variation))}>
            {TrendIcon && <TrendIcon className="h-3 w-3" />}
            {variation > 0 ? "+" : ""}
            {variation.toFixed(1)}%
          </span>
        )}
      </div>
    </div>
  );
}

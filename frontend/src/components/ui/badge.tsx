import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * Variants "active"/"idle"/"error"/"paused" (spec 8.1 : "Badge avec variants
 * pour les statuts agents") en plus des variants shadcn/ui standard 
 * couleurs alignées sur les tokens CSS `--color-status-*` (src/index.css),
 * partagés avec `StatusIndicator` pour rester visuellement cohérents.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-neutral-900 text-white",
        secondary: "border-transparent bg-neutral-100 text-neutral-900",
        destructive: "border-transparent bg-red-600 text-white",
        outline: "border-neutral-300 text-neutral-900",
        active: "border-transparent bg-green-100 text-green-800",
        idle: "border-transparent bg-neutral-100 text-neutral-600",
        error: "border-transparent bg-red-100 text-red-800",
        paused: "border-transparent bg-amber-100 text-amber-800",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

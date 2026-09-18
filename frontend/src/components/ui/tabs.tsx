import * as TabsPrimitive from "@radix-ui/react-tabs";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

export function TabsList({ className, ...props }: ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn("inline-flex h-9 items-center rounded-lg bg-neutral-100 p-1 dark:bg-neutral-800", className)}
      {...props}
    />
  );
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "inline-flex items-center rounded-md px-3 py-1 text-sm font-medium text-neutral-600 transition-colors",
        "data-[state=active]:bg-white data-[state=active]:text-neutral-900 data-[state=active]:shadow-sm",
        "dark:text-neutral-300 dark:data-[state=active]:bg-neutral-950 dark:data-[state=active]:text-neutral-50",
        className,
      )}
      {...props}
    />
  );
}

export function TabsContent({ className, ...props }: ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={cn("mt-4 focus-visible:outline-none", className)} {...props} />;
}

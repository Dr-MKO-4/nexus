import * as SwitchPrimitive from "@radix-ui/react-switch";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function Switch({ className, ...props }: ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full bg-neutral-300 transition-colors data-[state=checked]:bg-neutral-900 dark:bg-neutral-700 dark:data-[state=checked]:bg-neutral-50",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb className="block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[18px] dark:bg-neutral-900" />
    </SwitchPrimitive.Root>
  );
}

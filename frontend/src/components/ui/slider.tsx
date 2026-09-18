import * as SliderPrimitive from "@radix-ui/react-slider";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function Slider({ className, ...props }: ComponentProps<typeof SliderPrimitive.Root>) {
  return (
    <SliderPrimitive.Root className={cn("relative flex w-full touch-none select-none items-center", className)} {...props}>
      <SliderPrimitive.Track className="relative h-1.5 w-full grow rounded-full bg-neutral-200 dark:bg-neutral-700">
        <SliderPrimitive.Range className="absolute h-full rounded-full bg-neutral-900 dark:bg-neutral-50" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb className="block h-4 w-4 rounded-full border-2 border-neutral-900 bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400 dark:border-neutral-50 dark:bg-neutral-900" />
    </SliderPrimitive.Root>
  );
}

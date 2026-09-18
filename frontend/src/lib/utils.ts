import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Fusionne des classes Tailwind conditionnelles (convention shadcn/ui standard). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

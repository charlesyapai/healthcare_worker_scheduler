import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Concatenate Tailwind classes, merging conflicting ones last-wins. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

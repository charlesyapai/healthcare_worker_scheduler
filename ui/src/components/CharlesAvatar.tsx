/**
 * Circular avatar showing Charles's headshot.
 *
 * The image is served from `ui/public/charles.jpg` (bundled by Vite
 * at build time). If the file isn't on disk yet, we fall back to an
 * indigo circle with "C" so the top bar never breaks.
 */

import { useState } from "react";

import { cn } from "@/lib/utils";

interface Props {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE: Record<NonNullable<Props["size"]>, string> = {
  sm: "h-7 w-7 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-14 w-14 text-base",
};

export function CharlesAvatar({ size = "sm", className }: Props) {
  const [broken, setBroken] = useState(false);
  const cls = cn(
    "flex-shrink-0 rounded-full ring-2 ring-indigo-200 dark:ring-indigo-900 object-cover",
    SIZE[size],
    className,
  );

  if (broken) {
    return (
      <span
        aria-label="Charles"
        className={cn(
          "inline-flex items-center justify-center bg-indigo-100 font-bold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300",
          cls,
        )}
      >
        C
      </span>
    );
  }

  return (
    <img
      src="/charles.jpg"
      alt="Charles"
      onError={() => setBroken(true)}
      className={cls}
      draggable={false}
    />
  );
}

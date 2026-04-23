/**
 * Pixel-safe toggle switch.
 *
 * The earlier ad-hoc inline toggle relied on `translate-x-[22px]` and the
 * thumb could render outside the track in some browsers / when a parent
 * layout nudged the track by a pixel or two. This uses flex + padding
 * math so the thumb is clamped to the inner-padded box regardless of
 * browser rounding. No translate math, no overflow.
 */

import { cn } from "@/lib/utils";

interface ToggleProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  id?: string;
  ariaLabel?: string;
  disabled?: boolean;
  size?: "sm" | "md";
}

export function Toggle({
  checked,
  onChange,
  id,
  ariaLabel,
  disabled,
  size = "md",
}: ToggleProps) {
  const track =
    size === "sm"
      ? "h-5 w-9 p-0.5"
      : "h-6 w-11 p-0.5";
  const thumb = size === "sm" ? "h-4 w-4" : "h-5 w-5";

  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "inline-flex flex-shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:opacity-50 dark:focus-visible:ring-offset-slate-950",
        track,
        checked
          ? "justify-end bg-indigo-600 dark:bg-indigo-500"
          : "justify-start bg-slate-300 dark:bg-slate-700",
      )}
    >
      <span
        className={cn(
          "rounded-full bg-white shadow-sm transition-transform",
          thumb,
        )}
      />
    </button>
  );
}

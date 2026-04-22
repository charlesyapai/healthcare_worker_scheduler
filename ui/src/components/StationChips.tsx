/**
 * Tick-style multiselect. Used on the Doctors table for eligible_stations
 * and anywhere else we need a compact on/off-per-item picker.
 *
 * - `options` is the canonical list (e.g., the current stations).
 * - `value` is what the row currently has selected. If it includes a name
 *   that's not in options (stale reference from an imported YAML), it's
 *   rendered as a dimmed "unknown" chip the user can click to remove.
 */

import { cn } from "@/lib/utils";

interface Props {
  value: string[];
  options: string[];
  onChange: (next: string[]) => void;
  size?: "sm" | "md";
  className?: string;
}

export function StationChips({ value, options, onChange, size = "sm", className }: Props) {
  const selected = new Set(value);
  const orphans = value.filter((v) => !options.includes(v));
  const all = [...options, ...orphans];

  const toggle = (name: string) => {
    if (selected.has(name)) onChange(value.filter((n) => n !== name));
    else onChange([...value, name]);
  };

  const pad = size === "sm" ? "px-1.5 py-0.5 text-[11px]" : "px-2 py-1 text-xs";

  return (
    <div className={cn("flex flex-wrap gap-1", className)}>
      {all.map((name) => {
        const on = selected.has(name);
        const isOrphan = !options.includes(name);
        return (
          <button
            key={name}
            type="button"
            onClick={() => toggle(name)}
            aria-pressed={on}
            title={isOrphan ? `${name} (station no longer exists)` : undefined}
            className={cn(
              "rounded-md border font-medium leading-tight transition-colors",
              pad,
              on
                ? isOrphan
                  ? "border-amber-300 bg-amber-100 text-amber-800 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200"
                  : "border-indigo-500 bg-indigo-600 text-white hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-400"
                : "border-slate-300 bg-white text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800",
            )}
          >
            {name}
          </button>
        );
      })}
      {all.length === 0 && (
        <span className="text-xs text-slate-400">Add stations in Rules → Stations first.</span>
      )}
    </div>
  );
}

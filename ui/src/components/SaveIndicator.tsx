import { useIsMutating } from "@tanstack/react-query";
import { Check, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

/**
 * Small top-bar pill that surfaces PATCH-based auto-save activity. Shows
 * "Saving…" while any mutation is in flight and briefly confirms "Saved"
 * after each one finishes, then fades back to a neutral state. Gives
 * users visible confirmation that their edits are being persisted.
 */
export function SaveIndicator() {
  const count = useIsMutating();
  const [showSaved, setShowSaved] = useState(false);
  const [prev, setPrev] = useState(0);

  useEffect(() => {
    if (prev > 0 && count === 0) {
      setShowSaved(true);
      const t = setTimeout(() => setShowSaved(false), 1800);
      return () => clearTimeout(t);
    }
    setPrev(count);
  }, [count, prev]);

  if (count > 0) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
        <Loader2 className="h-3 w-3 animate-spin" />
        Saving…
      </span>
    );
  }
  if (showSaved) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
        <Check className="h-3 w-3" />
        Saved
      </span>
    );
  }
  return (
    <span className="hidden rounded-full px-2 py-0.5 text-[11px] text-slate-400 sm:inline">
      All changes saved
    </span>
  );
}

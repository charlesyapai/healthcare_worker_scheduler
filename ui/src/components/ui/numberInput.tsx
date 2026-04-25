import {
  forwardRef,
  useEffect,
  useRef,
  useState,
  type FocusEvent,
  type InputHTMLAttributes,
  type KeyboardEvent,
} from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface NumberInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "onChange"> {
  value: number | "" | null | undefined;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  /** Snap to integer on commit. Default true; set false for floats. */
  integer?: boolean;
  className?: string;
}

const toDraft = (value: number | "" | null | undefined): string => {
  if (value === "" || value === null || value === undefined) return "";
  if (Number.isFinite(value as number)) return String(value);
  return "";
};

/**
 * Number input that holds a free-form draft string while the field is
 * focused, only validating + clamping on blur or Enter. Empty input is
 * allowed mid-edit, so backspacing the last digit no longer re-clamps
 * the value to the floor and bumps the cursor to the end.
 *
 * Commits via `onChange(numericValue)` when the user blurs or hits Enter
 * with a parseable value. If the field is empty on commit, falls back
 * to `min` (or 0 if no min set).
 */
export const NumberInput = forwardRef<HTMLInputElement, NumberInputProps>(
  (
    {
      value,
      onChange,
      min,
      max,
      integer = true,
      className,
      onBlur,
      onKeyDown,
      ...props
    },
    ref,
  ) => {
    const [draft, setDraft] = useState<string>(() => toDraft(value));
    const focused = useRef(false);

    // When the controlled value changes externally (and we're not editing),
    // resync the draft. While focused, leave the draft alone so the user's
    // in-progress text isn't yanked out from under them.
    useEffect(() => {
      if (!focused.current) {
        setDraft(toDraft(value));
      }
    }, [value]);

    const commit = () => {
      const trimmed = draft.trim();
      if (trimmed === "" || trimmed === "-" || trimmed === ".") {
        // Empty / partial input on commit: fall back to floor (or 0).
        const fallback = typeof min === "number" ? min : 0;
        onChange(fallback);
        setDraft(toDraft(fallback));
        return;
      }
      let parsed = integer ? parseInt(trimmed, 10) : parseFloat(trimmed);
      if (!Number.isFinite(parsed)) {
        const fallback = typeof min === "number" ? min : 0;
        onChange(fallback);
        setDraft(toDraft(fallback));
        return;
      }
      if (typeof min === "number" && parsed < min) parsed = min;
      if (typeof max === "number" && parsed > max) parsed = max;
      onChange(parsed);
      setDraft(toDraft(parsed));
    };

    const handleBlur = (e: FocusEvent<HTMLInputElement>) => {
      focused.current = false;
      commit();
      onBlur?.(e);
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        commit();
      }
      onKeyDown?.(e);
    };

    return (
      <Input
        ref={ref}
        type="text"
        inputMode={integer ? "numeric" : "decimal"}
        pattern={integer ? "-?[0-9]*" : undefined}
        value={draft}
        onFocus={() => {
          focused.current = true;
        }}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        className={cn(className)}
        {...props}
      />
    );
  },
);
NumberInput.displayName = "NumberInput";

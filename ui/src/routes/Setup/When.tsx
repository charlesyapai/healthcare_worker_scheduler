import { addDays, addMonths, endOfMonth, format, isSameMonth, isWithinInterval, startOfMonth, startOfWeek } from "date-fns";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useMemo, useState } from "react";

import { useAutoSavePatch } from "@/api/autosave";
import { useSessionState } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/** Pick a horizon by dragging across the calendar. Click any day that
 *  falls INSIDE the current horizon to toggle it as a public holiday —
 *  holidays follow weekend coverage rules. */
export function When() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const horizon = data?.horizon ?? {
    n_days: 21,
    public_holidays: [] as string[],
    start_date: null as string | null,
  };

  const setHorizon = (patch: Partial<NonNullable<typeof horizon>>) => {
    save({ horizon: { ...horizon, ...patch } });
  };

  const addHoliday = (iso: string) => {
    if (!iso || horizon.public_holidays?.includes(iso)) return;
    setHorizon({
      public_holidays: [...(horizon.public_holidays ?? []), iso].sort(),
    });
  };
  const removeHoliday = (iso: string) => {
    setHorizon({
      public_holidays: (horizon.public_holidays ?? []).filter((d) => d !== iso),
    });
  };
  const toggleHoliday = (iso: string) => {
    if ((horizon.public_holidays ?? []).includes(iso)) removeHoliday(iso);
    else addHoliday(iso);
  };

  const startDate = horizon.start_date
    ? new Date(`${horizon.start_date}T00:00`)
    : null;
  const endDate =
    startDate && horizon.n_days > 0
      ? addDays(startDate, horizon.n_days - 1)
      : null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>When</CardTitle>
          <CardDescription>
            Drag across the calendar to set the horizon. Click any day inside
            the highlighted range to toggle it as a public holiday (handled
            like a Sunday).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Start date
              </span>
              <Input
                type="date"
                value={horizon.start_date ?? ""}
                onChange={(e) =>
                  setHorizon({ start_date: e.target.value || null })
                }
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Number of days
              </span>
              <Input
                type="number"
                min={1}
                max={90}
                value={horizon.n_days ?? 21}
                onChange={(e) =>
                  setHorizon({
                    n_days: Math.max(1, Math.min(90, Number(e.target.value))),
                  })
                }
              />
            </label>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Ends
              </span>
              <div className="flex h-9 items-center rounded-md border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                {endDate ? format(endDate, "d MMM yyyy") : "—"}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <HorizonCalendar
        startDate={startDate}
        endDate={endDate}
        holidays={horizon.public_holidays ?? []}
        onSetHorizon={(iso, nDays) =>
          setHorizon({ start_date: iso, n_days: nDays })
        }
        onToggleHoliday={toggleHoliday}
      />

      {(horizon.public_holidays ?? []).length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Public holidays</CardTitle>
            <CardDescription className="text-xs">
              Click a holiday pill or a calendar cell to remove it.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {(horizon.public_holidays ?? []).map((iso) => (
                <span
                  key={iso}
                  className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300"
                >
                  {format(new Date(iso), "d MMM yyyy")}
                  <button
                    type="button"
                    aria-label={`Remove ${iso}`}
                    className="rounded-full p-0.5 hover:bg-amber-200 dark:hover:bg-amber-900"
                    onClick={() => removeHoliday(iso)}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/** Two-month strip. Drag to set horizon; single-click inside horizon toggles
 *  holiday. Single-click outside the current horizon sets it as the new
 *  start date (keeping length) — cheap way to "scroll forward" without
 *  re-typing dates. */
function HorizonCalendar({
  startDate,
  endDate,
  holidays,
  onSetHorizon,
  onToggleHoliday,
}: {
  startDate: Date | null;
  endDate: Date | null;
  holidays: string[];
  onSetHorizon: (startIso: string, nDays: number) => void;
  onToggleHoliday: (iso: string) => void;
}) {
  const today = new Date();
  const [viewAnchor, setViewAnchor] = useState<Date>(
    startDate ? startOfMonth(startDate) : startOfMonth(today),
  );
  const [dragFrom, setDragFrom] = useState<Date | null>(null);
  const [dragTo, setDragTo] = useState<Date | null>(null);
  const [dragging, setDragging] = useState(false);

  const holidaySet = useMemo(() => new Set(holidays), [holidays]);

  const visibleMonths = [viewAnchor, addMonths(viewAnchor, 1)];

  const horizonInterval =
    startDate && endDate
      ? { start: startDate, end: endDate }
      : null;
  const dragInterval = (() => {
    if (!dragFrom || !dragTo) return null;
    const [a, b] = dragFrom <= dragTo ? [dragFrom, dragTo] : [dragTo, dragFrom];
    return { start: a, end: b };
  })();

  const isoOf = (d: Date) => format(d, "yyyy-MM-dd");

  const handlePointerDown = (d: Date) => {
    setDragFrom(d);
    setDragTo(d);
    setDragging(true);
  };
  const handlePointerEnter = (d: Date) => {
    if (dragging) setDragTo(d);
  };
  const finishDrag = () => {
    if (!dragging || !dragFrom || !dragTo) {
      setDragging(false);
      setDragFrom(null);
      setDragTo(null);
      return;
    }
    const [a, b] = dragFrom <= dragTo ? [dragFrom, dragTo] : [dragTo, dragFrom];
    const spanDays =
      Math.round((b.getTime() - a.getTime()) / (24 * 3600 * 1000)) + 1;
    if (spanDays === 1) {
      // Single click — treat as horizon-set or holiday-toggle.
      const iso = isoOf(a);
      if (horizonInterval && isWithinInterval(a, horizonInterval)) {
        onToggleHoliday(iso);
      } else {
        // Outside current horizon → set as start, keep length.
        const n =
          startDate && endDate
            ? Math.round(
                (endDate.getTime() - startDate.getTime()) / (24 * 3600 * 1000),
              ) + 1
            : 21;
        onSetHorizon(iso, n);
      }
    } else {
      onSetHorizon(isoOf(a), Math.min(90, spanDays));
    }
    setDragging(false);
    setDragFrom(null);
    setDragTo(null);
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-sm">Pick the horizon visually</CardTitle>
            <CardDescription className="text-xs">
              Drag across days to set start + length. Click a day inside the
              indigo range to toggle public holiday.
            </CardDescription>
          </div>
          <div className="flex items-center gap-1">
            <Button
              size="icon"
              variant="ghost"
              aria-label="Previous month"
              onClick={() => setViewAnchor((d) => addMonths(d, -1))}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setViewAnchor(startOfMonth(new Date()))}
            >
              Today
            </Button>
            <Button
              size="icon"
              variant="ghost"
              aria-label="Next month"
              onClick={() => setViewAnchor((d) => addMonths(d, 1))}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent
        onMouseUp={finishDrag}
        onMouseLeave={() => {
          if (dragging) finishDrag();
        }}
        onTouchEnd={finishDrag}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          {visibleMonths.map((m) => (
            <MonthGrid
              key={m.toISOString()}
              month={m}
              holidaySet={holidaySet}
              horizonInterval={horizonInterval}
              dragInterval={dragInterval}
              onPointerDown={handlePointerDown}
              onPointerEnter={handlePointerEnter}
              today={today}
            />
          ))}
        </div>
        <Legend />
      </CardContent>
    </Card>
  );
}

function MonthGrid({
  month,
  holidaySet,
  horizonInterval,
  dragInterval,
  onPointerDown,
  onPointerEnter,
  today,
}: {
  month: Date;
  holidaySet: Set<string>;
  horizonInterval: { start: Date; end: Date } | null;
  dragInterval: { start: Date; end: Date } | null;
  onPointerDown: (d: Date) => void;
  onPointerEnter: (d: Date) => void;
  today: Date;
}) {
  const gridStart = startOfWeek(startOfMonth(month), { weekStartsOn: 1 });
  const monthEnd = endOfMonth(month);
  // Always render 6 rows so month heights align.
  const cells: Date[] = [];
  let cursor = gridStart;
  for (let i = 0; i < 42; i++) {
    cells.push(cursor);
    cursor = addDays(cursor, 1);
  }

  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-sm font-semibold">{format(month, "MMMM yyyy")}</h3>
      </div>
      <div className="grid grid-cols-7 text-center text-[10px] font-medium uppercase tracking-wide text-slate-500">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <div key={d}>{d}</div>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-7 gap-0.5">
        {cells.map((d) => {
          const iso = format(d, "yyyy-MM-dd");
          const inMonth = isSameMonth(d, month);
          const inHorizon = Boolean(
            horizonInterval && isWithinInterval(d, horizonInterval),
          );
          const inDrag = Boolean(
            dragInterval && isWithinInterval(d, dragInterval),
          );
          const isWeekend = d.getDay() === 0 || d.getDay() === 6;
          const isHoliday = holidaySet.has(iso);
          const isToday =
            d.getFullYear() === today.getFullYear() &&
            d.getMonth() === today.getMonth() &&
            d.getDate() === today.getDate();
          return (
            <button
              key={iso}
              type="button"
              draggable={false}
              onMouseDown={(e) => {
                e.preventDefault();
                onPointerDown(d);
              }}
              onMouseEnter={() => onPointerEnter(d)}
              onTouchStart={(e) => {
                e.preventDefault();
                onPointerDown(d);
              }}
              onTouchMove={(e) => {
                const touch = e.touches[0];
                if (!touch) return;
                const el = document.elementFromPoint(
                  touch.clientX,
                  touch.clientY,
                ) as HTMLElement | null;
                const iso2 = el?.dataset?.iso;
                if (iso2) onPointerEnter(new Date(`${iso2}T00:00`));
              }}
              data-iso={iso}
              aria-label={format(d, "EEEE d MMMM yyyy")}
              className={cn(
                "relative h-9 select-none rounded-md text-xs transition-colors",
                !inMonth && "text-slate-300 dark:text-slate-700",
                inMonth &&
                  !inHorizon &&
                  "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
                inHorizon &&
                  !isHoliday &&
                  "bg-indigo-100 text-indigo-800 hover:bg-indigo-200 dark:bg-indigo-950/60 dark:text-indigo-200 dark:hover:bg-indigo-900/60",
                isHoliday &&
                  "bg-amber-200 text-amber-900 hover:bg-amber-300 dark:bg-amber-900/60 dark:text-amber-100 dark:hover:bg-amber-800/60",
                isWeekend &&
                  !inHorizon &&
                  !isHoliday &&
                  "text-rose-500 dark:text-rose-400/70",
                inDrag && "ring-2 ring-indigo-400 ring-offset-0",
                isToday && "font-semibold",
              )}
            >
              {d.getDate()}
              {isToday && (
                <span className="absolute left-1/2 top-1 h-1 w-1 -translate-x-1/2 rounded-full bg-indigo-500" />
              )}
            </button>
          );
        })}
      </div>
      <div className="sr-only">{format(monthEnd, "yyyy-MM-dd")}</div>
    </div>
  );
}

function Legend() {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-slate-500 dark:text-slate-400">
      <span className="inline-flex items-center gap-1">
        <span className="h-3 w-3 rounded-sm bg-indigo-200 dark:bg-indigo-900/60" />
        In horizon
      </span>
      <span className="inline-flex items-center gap-1">
        <span className="h-3 w-3 rounded-sm bg-amber-200 dark:bg-amber-900/60" />
        Public holiday
      </span>
      <span className="inline-flex items-center gap-1">
        <span className="h-3 w-3 rounded-sm border border-rose-300 text-rose-500" />
        Weekend
      </span>
    </div>
  );
}

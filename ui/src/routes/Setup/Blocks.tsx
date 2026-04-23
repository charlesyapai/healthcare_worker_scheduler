import { addDays, format, isSameDay, parseISO } from "date-fns";
import { ChevronDown, ChevronRight, Plus, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { useAutoSavePatch } from "@/api/autosave";
import { type BlockEntry, useSessionState } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";

const BLOCK_TYPES = [
  "Leave",
  "No on-call",
  "No AM",
  "No PM",
  "Prefer AM",
  "Prefer PM",
] as const;

type BlockType = BlockEntry["type"];

const TYPE_COLOR: Record<BlockType, { bg: string; label: string }> = {
  Leave: {
    bg: "bg-amber-400 dark:bg-amber-600",
    label: "text-amber-900 dark:text-amber-100",
  },
  "No on-call": {
    bg: "bg-rose-400 dark:bg-rose-600",
    label: "text-rose-900 dark:text-rose-100",
  },
  "No AM": {
    bg: "bg-sky-400 dark:bg-sky-600",
    label: "text-sky-900 dark:text-sky-100",
  },
  "No PM": {
    bg: "bg-violet-400 dark:bg-violet-600",
    label: "text-violet-900 dark:text-violet-100",
  },
  "Prefer AM": {
    bg: "bg-emerald-300 dark:bg-emerald-700",
    label: "text-emerald-900 dark:text-emerald-100",
  },
  "Prefer PM": {
    bg: "bg-teal-300 dark:bg-teal-700",
    label: "text-teal-900 dark:text-teal-100",
  },
};

const TYPE_SHORT: Record<BlockType, string> = {
  Leave: "L",
  "No on-call": "NC",
  "No AM": "−A",
  "No PM": "−P",
  "Prefer AM": "+A",
  "Prefer PM": "+P",
};

export function Blocks() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const blocks = data?.blocks ?? [];
  const doctors = data?.doctors ?? [];
  const doctorNames = doctors.map((d) => d.name);
  const horizon = data?.horizon;

  const updateBlocks = (next: BlockEntry[]) => save({ blocks: next });

  const [activeType, setActiveType] = useState<BlockType>("Leave");
  const [search, setSearch] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const horizonDates = useMemo(() => {
    if (!horizon?.start_date || !horizon.n_days) return [] as Date[];
    const start = parseISO(horizon.start_date);
    const out: Date[] = [];
    for (let i = 0; i < horizon.n_days; i++) out.push(addDays(start, i));
    return out;
  }, [horizon]);

  const filteredDoctors = useMemo(() => {
    if (!search.trim()) return doctorNames;
    const needle = search.toLowerCase();
    return doctorNames.filter((n) => n.toLowerCase().includes(needle));
  }, [doctorNames, search]);

  // Map (doctor, ISO day) → list of block types touching it.
  const cellMap = useMemo(() => {
    const out = new Map<string, BlockEntry[]>();
    for (const b of blocks) {
      const start = parseISO(b.date);
      const end = b.end_date ? parseISO(b.end_date) : start;
      let cur = start;
      while (cur <= end) {
        const key = `${b.doctor}|${format(cur, "yyyy-MM-dd")}`;
        const list = out.get(key) ?? [];
        list.push(b);
        out.set(key, list);
        cur = addDays(cur, 1);
      }
    }
    return out;
  }, [blocks]);

  const applyDragRange = (
    doctor: string,
    startIso: string,
    endIso: string,
    type: BlockType,
  ) => {
    const a = startIso <= endIso ? startIso : endIso;
    const b = startIso <= endIso ? endIso : startIso;
    // If the drag was a single click on a cell that already holds a block
    // of this type, toggle (remove) it.
    if (a === b) {
      const existing = cellMap.get(`${doctor}|${a}`) ?? [];
      const hit = existing.find((x) => x.type === type);
      if (hit) {
        removeBlockOnDay(hit, a);
        return;
      }
    }
    const next: BlockEntry = {
      doctor,
      date: a,
      end_date: a === b ? null : b,
      type,
    };
    updateBlocks([...blocks, next]);
    toast.success(
      `${type} for ${doctor}${a === b ? "" : ` (${a} → ${b})`} added`,
    );
  };

  // Remove one day's coverage from a block. If the block was a single day,
  // drop it outright; otherwise trim or split as needed.
  const removeBlockOnDay = (b: BlockEntry, isoDay: string) => {
    const start = parseISO(b.date);
    const end = b.end_date ? parseISO(b.end_date) : start;
    const day = parseISO(isoDay);
    const others = blocks.filter((x) => x !== b);
    const replacements: BlockEntry[] = [];
    if (isSameDay(start, end)) {
      // Single-day block: just drop.
    } else if (isSameDay(day, start)) {
      replacements.push({
        ...b,
        date: format(addDays(start, 1), "yyyy-MM-dd"),
      });
    } else if (isSameDay(day, end)) {
      const newEnd = addDays(end, -1);
      replacements.push({
        ...b,
        end_date: isSameDay(start, newEnd)
          ? null
          : format(newEnd, "yyyy-MM-dd"),
      });
    } else {
      // Split into two.
      const before = addDays(day, -1);
      const after = addDays(day, 1);
      replacements.push({
        ...b,
        end_date: isSameDay(start, before)
          ? null
          : format(before, "yyyy-MM-dd"),
      });
      replacements.push({
        doctor: b.doctor,
        date: format(after, "yyyy-MM-dd"),
        end_date: isSameDay(after, end) ? null : format(end, "yyyy-MM-dd"),
        type: b.type,
      });
    }
    updateBlocks([...others, ...replacements]);
  };

  const removeBlockIndex = (idx: number) =>
    updateBlocks(blocks.filter((_, i) => i !== idx));

  const updateRow = (idx: number, patch: Partial<BlockEntry>) =>
    updateBlocks(blocks.map((b, i) => (i === idx ? { ...b, ...patch } : b)));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Leave, blocks, and preferences</CardTitle>
          <CardDescription>
            Pick a block type, then drag across a doctor's row to apply it.
            Click a single cell of the same type to remove it.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Block type">
              {BLOCK_TYPES.map((t) => (
                <button
                  key={t}
                  type="button"
                  role="radio"
                  aria-checked={activeType === t}
                  onClick={() => setActiveType(t)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
                    activeType === t
                      ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                      : "border-slate-300 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800",
                  )}
                >
                  <span
                    className={cn("h-2 w-2 rounded-full", TYPE_COLOR[t].bg)}
                  />
                  {t}
                </button>
              ))}
            </div>
            <div className="relative ml-auto">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter doctors…"
                className="h-8 w-48 pl-7 text-xs"
              />
            </div>
          </div>

          {horizonDates.length === 0 ? (
            <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-4 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
              Set a horizon on the <strong>When</strong> tab to see the grid.
            </div>
          ) : filteredDoctors.length === 0 ? (
            <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-4 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
              {doctorNames.length === 0
                ? "Add doctors first, then come back to assign leave / blocks."
                : "No doctors match this filter."}
            </div>
          ) : (
            <BlocksGrid
              doctors={filteredDoctors}
              dates={horizonDates}
              cellMap={cellMap}
              activeType={activeType}
              onApplyRange={applyDragRange}
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader
          className="cursor-pointer select-none hover:bg-slate-50 dark:hover:bg-slate-900/50"
          onClick={() => setShowAdvanced((v) => !v)}
        >
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-sm">
                {showAdvanced ? (
                  <ChevronDown className="mr-1 inline h-3.5 w-3.5" />
                ) : (
                  <ChevronRight className="mr-1 inline h-3.5 w-3.5" />
                )}
                Advanced: table + CSV paste
              </CardTitle>
              <CardDescription className="text-xs">
                Fine-tune individual rows, or bulk-import from CSV. Most users
                won't need this.
              </CardDescription>
            </div>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {blocks.length} row{blocks.length === 1 ? "" : "s"}
            </span>
          </div>
        </CardHeader>
        {showAdvanced && (
          <CardContent>
            <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
              <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                <thead className="sticky top-0 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-600 dark:bg-slate-900 dark:text-slate-300">
                  <tr>
                    <th className="px-2 py-2">Person</th>
                    <th className="px-2 py-2">Start date</th>
                    <th className="px-2 py-2">End date</th>
                    <th className="px-2 py-2">Type</th>
                    <th className="w-10 px-2 py-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {blocks.map((b, i) => (
                    <tr
                      key={i}
                      className="hover:bg-slate-50 dark:hover:bg-slate-900/50"
                    >
                      <td className="px-2 py-1">
                        <Select
                          className="h-8"
                          value={b.doctor}
                          onChange={(e) =>
                            updateRow(i, { doctor: e.target.value })
                          }
                        >
                          {!doctorNames.includes(b.doctor) && (
                            <option value={b.doctor}>{b.doctor}</option>
                          )}
                          {doctorNames.map((n) => (
                            <option key={n} value={n}>
                              {n}
                            </option>
                          ))}
                        </Select>
                      </td>
                      <td className="px-2 py-1">
                        <Input
                          className="h-8"
                          type="date"
                          value={b.date}
                          onChange={(e) =>
                            updateRow(i, { date: e.target.value })
                          }
                        />
                      </td>
                      <td className="px-2 py-1">
                        <Input
                          className="h-8"
                          type="date"
                          value={b.end_date ?? ""}
                          onChange={(e) =>
                            updateRow(i, { end_date: e.target.value || null })
                          }
                        />
                      </td>
                      <td className="px-2 py-1">
                        <Select
                          className="h-8"
                          value={b.type}
                          onChange={(e) =>
                            updateRow(i, {
                              type: e.target.value as BlockEntry["type"],
                            })
                          }
                        >
                          {BLOCK_TYPES.map((t) => (
                            <option key={t} value={t}>
                              {t}
                            </option>
                          ))}
                        </Select>
                      </td>
                      <td className="px-2 py-1 text-right">
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label="remove"
                          onClick={() => removeBlockIndex(i)}
                        >
                          <Trash2 className="h-4 w-4 text-slate-400" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {blocks.length === 0 && (
                    <tr>
                      <td
                        colSpan={5}
                        className="px-2 py-6 text-center text-xs text-slate-500 dark:text-slate-400"
                      >
                        No blocks yet. Use the grid above or paste CSV below.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex items-center justify-between">
              <Button
                variant="secondary"
                size="sm"
                disabled={doctorNames.length === 0}
                onClick={() =>
                  updateBlocks([
                    ...blocks,
                    {
                      doctor: doctorNames[0] ?? "",
                      date: new Date().toISOString().slice(0, 10),
                      end_date: null,
                      type: "Leave",
                    },
                  ])
                }
              >
                <Plus className="h-4 w-4" />
                Add manual row
              </Button>
            </div>

            <CsvPasteDrawer
              doctorNames={doctorNames}
              onImport={(incoming) =>
                updateBlocks([...blocks, ...incoming])
              }
            />
          </CardContent>
        )}
      </Card>
    </div>
  );
}

function BlocksGrid({
  doctors,
  dates,
  cellMap,
  activeType,
  onApplyRange,
}: {
  doctors: string[];
  dates: Date[];
  cellMap: Map<string, BlockEntry[]>;
  activeType: BlockType;
  onApplyRange: (
    doctor: string,
    startIso: string,
    endIso: string,
    type: BlockType,
  ) => void;
}) {
  const [drag, setDrag] = useState<{
    doctor: string;
    fromIso: string;
    toIso: string;
  } | null>(null);

  const finish = () => {
    if (!drag) return;
    onApplyRange(drag.doctor, drag.fromIso, drag.toIso, activeType);
    setDrag(null);
  };

  // First-of-month tick to help scanning long horizons.
  const monthTickIso = useMemo(() => {
    const s = new Set<string>();
    for (const d of dates) {
      if (d.getDate() === 1) s.add(format(d, "yyyy-MM-dd"));
    }
    return s;
  }, [dates]);

  return (
    <div
      className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800"
      onMouseUp={finish}
      onMouseLeave={() => drag && finish()}
      onTouchEnd={finish}
    >
      <table
        className="min-w-full border-separate"
        style={{ borderSpacing: 0 }}
      >
        <thead>
          <tr className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
            <th
              className="sticky left-0 z-20 border-b border-slate-200 bg-slate-50 px-2 py-1 text-left dark:border-slate-800 dark:bg-slate-900"
              style={{ minWidth: 140 }}
            >
              Doctor
            </th>
            {dates.map((d) => {
              const iso = format(d, "yyyy-MM-dd");
              const isWeekend = d.getDay() === 0 || d.getDay() === 6;
              return (
                <th
                  key={iso}
                  className={cn(
                    "border-b border-slate-200 px-0.5 py-1 text-center font-mono text-[10px] dark:border-slate-800",
                    isWeekend
                      ? "bg-slate-100 text-rose-500 dark:bg-slate-900 dark:text-rose-400/70"
                      : "bg-slate-50 text-slate-600 dark:bg-slate-900 dark:text-slate-300",
                    monthTickIso.has(iso) &&
                      "border-l border-l-slate-300 dark:border-l-slate-700",
                  )}
                  style={{ minWidth: 22 }}
                >
                  <div>{format(d, "d")}</div>
                  <div className="text-[9px] opacity-70">{format(d, "EEEEE")}</div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {doctors.map((doc, rowIdx) => (
            <tr key={doc}>
              <td
                className={cn(
                  "sticky left-0 z-10 border-b border-slate-100 px-2 py-1 text-xs font-medium dark:border-slate-800",
                  rowIdx % 2 === 0
                    ? "bg-white dark:bg-slate-950"
                    : "bg-slate-50 dark:bg-slate-900/50",
                )}
                style={{ minWidth: 140 }}
              >
                {doc}
              </td>
              {dates.map((d) => {
                const iso = format(d, "yyyy-MM-dd");
                const isWeekend = d.getDay() === 0 || d.getDay() === 6;
                const cellBlocks = cellMap.get(`${doc}|${iso}`) ?? [];
                const primary = cellBlocks[0];
                const isDragging =
                  drag?.doctor === doc &&
                  iso >=
                    (drag.fromIso <= drag.toIso ? drag.fromIso : drag.toIso) &&
                  iso <=
                    (drag.fromIso <= drag.toIso ? drag.toIso : drag.fromIso);

                return (
                  <td
                    key={iso}
                    className={cn(
                      "border-b border-slate-100 p-0 text-center dark:border-slate-800",
                      isWeekend && "bg-slate-50/60 dark:bg-slate-900/30",
                      monthTickIso.has(iso) &&
                        "border-l border-l-slate-200 dark:border-l-slate-800",
                    )}
                    style={{ minWidth: 22 }}
                  >
                    <button
                      type="button"
                      data-doctor={doc}
                      data-iso={iso}
                      draggable={false}
                      onMouseDown={(e) => {
                        e.preventDefault();
                        setDrag({ doctor: doc, fromIso: iso, toIso: iso });
                      }}
                      onMouseEnter={() => {
                        setDrag((cur) =>
                          cur && cur.doctor === doc
                            ? { ...cur, toIso: iso }
                            : cur,
                        );
                      }}
                      onTouchStart={(e) => {
                        e.preventDefault();
                        setDrag({ doctor: doc, fromIso: iso, toIso: iso });
                      }}
                      onTouchMove={(e) => {
                        const touch = e.touches[0];
                        if (!touch) return;
                        const el = document.elementFromPoint(
                          touch.clientX,
                          touch.clientY,
                        ) as HTMLElement | null;
                        const iso2 = el?.dataset?.iso;
                        const doc2 = el?.dataset?.doctor;
                        if (iso2 && doc2) {
                          setDrag((cur) =>
                            cur && cur.doctor === doc2
                              ? { ...cur, toIso: iso2 }
                              : cur,
                          );
                        }
                      }}
                      aria-label={`${doc} on ${iso}${
                        primary ? ` — ${primary.type}` : ""
                      }`}
                      className={cn(
                        "block h-7 w-full text-[10px] leading-none transition-colors",
                        primary
                          ? cn(
                              TYPE_COLOR[primary.type].bg,
                              TYPE_COLOR[primary.type].label,
                            )
                          : "hover:bg-indigo-100 dark:hover:bg-indigo-950/40",
                        isDragging && "ring-1 ring-inset ring-indigo-500",
                      )}
                    >
                      {primary ? TYPE_SHORT[primary.type] : ""}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CsvPasteDrawer({
  doctorNames,
  onImport,
}: {
  doctorNames: string[];
  onImport: (blocks: BlockEntry[]) => void;
}) {
  const [csv, setCsv] = useState("");
  const [open, setOpen] = useState(false);

  const parse = (): BlockEntry[] => {
    const lines = csv
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    const out: BlockEntry[] = [];
    for (const line of lines) {
      const parts = line.split(",").map((s) => s.trim());
      if (parts.length < 3 || parts.length > 4) continue;
      const [doctor, start, ...rest] = parts;
      const isFour = rest.length === 2;
      const end = isFour ? rest[0] : null;
      const typeRaw = isFour ? rest[1] : rest[0];
      const type = normaliseType(typeRaw);
      if (!type) continue;
      if (!doctorNames.includes(doctor)) continue;
      out.push({ doctor, date: start, end_date: end || null, type });
    }
    return out;
  };

  const apply = () => {
    const parsed = parse();
    if (parsed.length === 0) {
      toast.error(
        "No rows parsed — check column order: doctor,start,end?,type",
      );
      return;
    }
    onImport(parsed);
    setCsv("");
    setOpen(false);
    toast.success(
      `Imported ${parsed.length} block row${parsed.length === 1 ? "" : "s"}`,
    );
  };

  return (
    <div className="mt-3 rounded-md border border-slate-200 dark:border-slate-800">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left text-xs hover:bg-slate-50 dark:hover:bg-slate-900/50"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="font-medium">
          {open ? (
            <ChevronDown className="mr-1 inline h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="mr-1 inline h-3.5 w-3.5" />
          )}
          Bulk-add from CSV
        </span>
        <span className="text-[11px] text-slate-500 dark:text-slate-400">
          <code>doctor,start,end?,type</code>
        </span>
      </button>
      {open && (
        <div className="space-y-2 p-3">
          <textarea
            className="h-32 w-full rounded-md border border-slate-300 bg-white p-2 font-mono text-xs shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900"
            placeholder={
              "Dr A, 2026-05-01, 2026-05-03, Leave\nDr B, 2026-05-02, No on-call"
            }
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
          />
          <div className="flex gap-2">
            <Button size="sm" onClick={apply} disabled={!csv.trim()}>
              Import
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setCsv("")}>
              Clear
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function normaliseType(raw: string): BlockEntry["type"] | null {
  const k = raw.toUpperCase().replace(/[\s_-]+/g, "_");
  const map: Record<string, BlockEntry["type"]> = {
    LEAVE: "Leave",
    OFF: "Leave",
    ANNUAL_LEAVE: "Leave",
    NO_ONCALL: "No on-call",
    NO_CALL: "No on-call",
    CALL_BLOCK: "No on-call",
    NO_AM: "No AM",
    NO_PM: "No PM",
    PREFER_AM: "Prefer AM",
    PREF_AM: "Prefer AM",
    PREFER_PM: "Prefer PM",
    PREF_PM: "Prefer PM",
  };
  return map[k] ?? null;
}

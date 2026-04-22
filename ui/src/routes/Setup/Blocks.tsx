import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
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

const BLOCK_TYPES = [
  "Leave",
  "No on-call",
  "No AM",
  "No PM",
  "Prefer AM",
  "Prefer PM",
] as const;

export function Blocks() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const blocks = data?.blocks ?? [];
  const doctors = data?.doctors ?? [];
  const doctorNames = doctors.map((d) => d.name);

  const updateBlocks = (next: BlockEntry[]) => save({ blocks: next });
  const updateRow = (idx: number, patch: Partial<BlockEntry>) =>
    updateBlocks(blocks.map((b, i) => (i === idx ? { ...b, ...patch } : b)));

  const addRow = () =>
    updateBlocks([
      ...blocks,
      {
        doctor: doctorNames[0] ?? "",
        date: new Date().toISOString().slice(0, 10),
        end_date: null,
        type: "Leave",
      },
    ]);

  const removeRow = (idx: number) =>
    updateBlocks(blocks.filter((_, i) => i !== idx));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Leave, blocks, and preferences</CardTitle>
          <CardDescription>
            Leave is a whole-day block. Call blocks keep AM/PM work. Prefer AM/PM
            are soft bonuses.
          </CardDescription>
        </CardHeader>
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
                  <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-900/50">
                    <td className="px-2 py-1">
                      <Select
                        className="h-8"
                        value={b.doctor}
                        onChange={(e) => updateRow(i, { doctor: e.target.value })}
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
                        onChange={(e) => updateRow(i, { date: e.target.value })}
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
                        onClick={() => removeRow(i)}
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
                      No blocks yet. Click "Add block" or paste CSV below.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-3 flex items-center justify-between">
            <Button variant="secondary" size="sm" onClick={addRow} disabled={doctorNames.length === 0}>
              <Plus className="h-4 w-4" />
              Add block
            </Button>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {blocks.length} row{blocks.length === 1 ? "" : "s"}
            </span>
          </div>
        </CardContent>
      </Card>

      <CsvPasteDrawer
        doctorNames={doctorNames}
        onImport={(incoming) => save({ blocks: [...blocks, ...incoming] })}
      />
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
      toast.error("No rows parsed — check column order: doctor,start,end?,type");
      return;
    }
    onImport(parsed);
    setCsv("");
    setOpen(false);
    toast.success(`Imported ${parsed.length} block row${parsed.length === 1 ? "" : "s"}`);
  };

  return (
    <Card>
      <CardHeader
        className="cursor-pointer select-none hover:bg-slate-50 dark:hover:bg-slate-900/50"
        onClick={() => setOpen((o) => !o)}
      >
        <CardTitle className="text-sm">
          {open ? "▼" : "▶"} Bulk-add from CSV
        </CardTitle>
        <CardDescription>
          Paste lines of the form <code>doctor,start,end?,type</code>.
        </CardDescription>
      </CardHeader>
      {open && (
        <CardContent>
          <textarea
            className="h-32 w-full rounded-md border border-slate-300 bg-white p-2 font-mono text-xs shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900"
            placeholder={"Dr A, 2026-05-01, 2026-05-03, Leave\nDr B, 2026-05-02, No on-call"}
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={apply} disabled={!csv.trim()}>
              Import
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setCsv("")}>
              Clear
            </Button>
          </div>
        </CardContent>
      )}
    </Card>
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

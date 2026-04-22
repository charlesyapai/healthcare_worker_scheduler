import { Plus, Trash2, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useAutoSavePatch } from "@/api/autosave";
import {
  type DoctorEntry,
  useLoadSample,
  useSessionState,
} from "@/api/hooks";
import { EmptyState } from "@/components/EmptyState";
import { StationChips } from "@/components/StationChips";
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

const TIERS = ["junior", "senior", "consultant"] as const;

export function Doctors() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const sample = useLoadSample({
    onSuccess: () => toast.success("Sample loaded"),
    onError: () => toast.error("Failed to load sample"),
  });
  const doctors = data?.doctors ?? [];
  const stations = data?.stations ?? [];
  const subspecs = data?.subspecs ?? [];
  const stationNames = stations.map((s) => s.name).filter(Boolean) as string[];

  const updateDoctors = (next: DoctorEntry[]) => save({ doctors: next });

  const updateRow = (idx: number, patch: Partial<DoctorEntry>) => {
    const next = doctors.map((d, i) => (i === idx ? { ...d, ...patch } : d));
    updateDoctors(next);
  };

  const addRow = () => {
    const letter = String.fromCharCode(65 + doctors.length);
    const name = doctors.length < 26 ? `Dr ${letter}` : `Dr ${doctors.length + 1}`;
    const eligible = stationNames.length > 0 ? stationNames.slice(0, 2) : [];
    updateDoctors([
      ...doctors,
      {
        name,
        tier: "junior",
        subspec: null,
        eligible_stations: eligible,
        prev_workload: 0,
        fte: 1,
        max_oncalls: null,
      },
    ]);
  };

  const removeRow = (idx: number) => {
    updateDoctors(doctors.filter((_, i) => i !== idx));
  };

  const importCsv = (rows: DoctorEntry[]) => {
    const existingNames = new Set(doctors.map((d) => d.name));
    const dedup = rows.filter((r) => !existingNames.has(r.name));
    updateDoctors([...doctors, ...dedup]);
    return dedup.length;
  };

  if (doctors.length === 0) {
    return (
      <div className="space-y-4">
        <EmptyState
          icon={Users}
          title="No people yet"
          description={
            <>
              Add one person at a time, paste a CSV, or load a pre-built
              scenario if you just want to see the solver work. "People" can
              be doctors, nurses, or any three-tier rota.
            </>
          }
          actions={
            <>
              <Button onClick={addRow} variant="primary" disabled={stationNames.length === 0}>
                <Plus className="h-4 w-4" />
                Add first person
              </Button>
              <Button onClick={() => sample.mutate()} variant="secondary" disabled={sample.isPending}>
                {sample.isPending ? "Loading…" : "Load sample scenario"}
              </Button>
            </>
          }
        />
        <DoctorsCsvDrawer subspecs={subspecs} stationNames={stationNames} onImport={importCsv} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
    <Card>
      <CardHeader>
        <CardTitle>People</CardTitle>
        <CardDescription>
          One row per person on the rota (doctor, nurse, etc.). Tier drives
          station eligibility; FTE scales workload; leave max on-calls blank
          for no cap.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {stationNames.length === 0 && (
          <p className="mb-2 text-xs text-amber-700 dark:text-amber-400">
            No stations configured. Go to Department rules → Stations first.
          </p>
        )}
        <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
          Click a station chip to toggle whether a doctor is eligible for it.
        </p>

        <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
          <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
            <thead className="sticky top-0 z-10 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              <tr>
                <th className="px-2 py-2">Name</th>
                <th className="px-2 py-2">Tier</th>
                <th className="px-2 py-2">Sub-spec</th>
                <th className="px-2 py-2">Eligible stations</th>
                <th
                  className="px-2 py-2"
                  title="Prior-period workload score — carry-in from last month so doctors who did more then get less this period. Leave at 0 if none."
                >
                  Prev wl
                </th>
                <th
                  className="px-2 py-2"
                  title="Full-time equivalent, 0.1–1.0. 0.5 means half a full-timer's workload."
                >
                  FTE
                </th>
                <th
                  className="px-2 py-2"
                  title="Optional hard cap on on-call nights this doctor can receive. Blank = no cap."
                >
                  Max OC
                </th>
                <th className="px-2 py-2 w-10"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {doctors.map((d, i) => (
                <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-900/50">
                  <td className="px-2 py-1">
                    <Input
                      className="h-8"
                      value={d.name}
                      onChange={(e) => updateRow(i, { name: e.target.value })}
                    />
                  </td>
                  <td className="px-2 py-1">
                    <Select
                      className="h-8"
                      value={d.tier}
                      onChange={(e) =>
                        updateRow(i, {
                          tier: e.target.value as (typeof TIERS)[number],
                          subspec: e.target.value === "consultant" ? d.subspec : null,
                        })
                      }
                    >
                      {TIERS.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </Select>
                  </td>
                  <td className="px-2 py-1">
                    {d.tier === "consultant" ? (
                      <Select
                        className="h-8"
                        value={d.subspec ?? ""}
                        onChange={(e) =>
                          updateRow(i, { subspec: e.target.value || null })
                        }
                      >
                        <option value="" disabled>
                          pick…
                        </option>
                        {subspecs.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-2 py-1 min-w-[14rem]">
                    <StationChips
                      value={d.eligible_stations ?? []}
                      options={stationNames}
                      onChange={(next) => updateRow(i, { eligible_stations: next })}
                    />
                  </td>
                  <td className="px-2 py-1 w-20">
                    <Input
                      className="h-8 text-right"
                      type="number"
                      min={0}
                      value={d.prev_workload ?? 0}
                      onChange={(e) =>
                        updateRow(i, { prev_workload: Number(e.target.value) || 0 })
                      }
                    />
                  </td>
                  <td className="px-2 py-1 w-20">
                    <Input
                      className="h-8 text-right"
                      type="number"
                      min={0.1}
                      max={1}
                      step={0.1}
                      value={d.fte ?? 1}
                      onChange={(e) =>
                        updateRow(i, { fte: Number(e.target.value) || 1 })
                      }
                    />
                  </td>
                  <td className="px-2 py-1 w-20">
                    <Input
                      className="h-8 text-right"
                      type="number"
                      min={0}
                      placeholder="—"
                      value={d.max_oncalls ?? ""}
                      onChange={(e) =>
                        updateRow(i, {
                          max_oncalls:
                            e.target.value === "" ? null : Number(e.target.value),
                        })
                      }
                    />
                  </td>
                  <td className="px-2 py-1 text-right">
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`Remove ${d.name}`}
                      onClick={() => removeRow(i)}
                    >
                      <Trash2 className="h-4 w-4 text-slate-400" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-3">
          <Button variant="secondary" onClick={addRow} size="sm">
            <Plus className="h-4 w-4" />
            Add person
          </Button>
          <span className="ml-3 text-xs text-slate-500 dark:text-slate-400">
            {doctors.length} {doctors.length === 1 ? "person" : "people"}
          </span>
        </div>
      </CardContent>
    </Card>

    <DoctorsCsvDrawer subspecs={subspecs} stationNames={stationNames} onImport={importCsv} />
    </div>
  );
}

function DoctorsCsvDrawer({
  // historical name, but the drawer now labels itself "people" in UI copy.
  subspecs,
  stationNames,
  onImport,
}: {
  subspecs: string[];
  stationNames: string[];
  onImport: (rows: DoctorEntry[]) => number;
}) {
  const [csv, setCsv] = useState("");
  const [open, setOpen] = useState(false);

  const parse = (): DoctorEntry[] => {
    const lines = csv
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean)
      // drop a header row if present
      .filter((l) => !/^name\s*,/i.test(l));
    const rows: DoctorEntry[] = [];
    for (const line of lines) {
      const parts = line.split(",").map((s) => s.trim());
      const [name, tierRaw, subspecRaw, eligRaw, prevRaw, fteRaw, maxOcRaw] = parts;
      if (!name) continue;
      const tier = (tierRaw || "junior").toLowerCase() as DoctorEntry["tier"];
      if (!["junior", "senior", "consultant"].includes(tier)) continue;
      const subspec =
        tier === "consultant"
          ? subspecRaw && subspecs.includes(subspecRaw)
            ? subspecRaw
            : subspecs[0] ?? null
          : null;
      const eligible = (eligRaw ?? "")
        .split(/[|; ]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      rows.push({
        name,
        tier,
        subspec,
        eligible_stations:
          eligible.length > 0 ? eligible : stationNames.slice(0, 2),
        prev_workload: parseIntOr(prevRaw, 0),
        fte: parseFloatOr(fteRaw, 1),
        max_oncalls: maxOcRaw && maxOcRaw !== "" ? parseIntOr(maxOcRaw, null) : null,
      });
    }
    return rows;
  };

  const apply = () => {
    const rows = parse();
    if (rows.length === 0) {
      toast.error("No rows parsed. Columns: name, tier, subspec, stations, prev_workload, fte, max_oncalls");
      return;
    }
    const added = onImport(rows);
    setCsv("");
    setOpen(false);
    toast.success(
      added === rows.length
        ? `Added ${added} ${added === 1 ? "person" : "people"}`
        : `Added ${added} new, skipped ${rows.length - added} duplicate${
            rows.length - added === 1 ? "" : "s"
          }`,
    );
  };

  const example = [
    "Dr A, junior, , GEN_AM|US|XR_REPORT, 0, 1.0,",
    "Dr B, senior, , CT|MR|US, 0, 1.0,",
    "Dr C, consultant, Neuro, CT|MR|IR, 0, 0.5, 4",
  ].join("\n");

  return (
    <Card>
      <CardHeader
        className="cursor-pointer select-none hover:bg-slate-50 dark:hover:bg-slate-900/50"
        onClick={() => setOpen((o) => !o)}
      >
        <CardTitle className="text-sm">
          {open ? "▼" : "▶"} Bulk-add people from CSV
        </CardTitle>
        <CardDescription>
          Columns:{" "}
          <code className="rounded bg-slate-100 px-1 py-0.5 dark:bg-slate-800">
            name, tier, subspec, eligible_stations, prev_workload, fte, max_oncalls
          </code>
          . Stations separated by <code>|</code>. Leave subspec blank for
          junior/senior. An existing name is skipped.
        </CardDescription>
      </CardHeader>
      {open && (
        <CardContent>
          <textarea
            className="h-40 w-full rounded-md border border-slate-300 bg-white p-2 font-mono text-xs shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900"
            placeholder={example}
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={apply} disabled={!csv.trim()}>
              Import
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setCsv(example)}>
              Paste example
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

function parseIntOr(s: string | undefined, fallback: number | null): number {
  if (s == null || s === "") return (fallback ?? 0) as number;
  const n = Number(s);
  return Number.isFinite(n) ? Math.trunc(n) : (fallback ?? 0) as number;
}

function parseFloatOr(s: string | undefined, fallback: number): number {
  if (s == null || s === "") return fallback;
  const n = Number(s);
  return Number.isFinite(n) ? n : fallback;
}

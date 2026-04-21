import { Plus, Trash2 } from "lucide-react";

import { useAutoSavePatch } from "@/api/autosave";
import { type DoctorEntry, useSessionState } from "@/api/hooks";
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

  return (
    <Card>
      <CardHeader>
        <CardTitle>Doctors</CardTitle>
        <CardDescription>
          One row per doctor. Tier drives eligibility; FTE scales workload; leave
          max on-calls blank for no cap.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {stationNames.length > 0 ? (
          <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
            Available stations:{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 dark:bg-slate-800">
              {stationNames.join(", ")}
            </code>
          </p>
        ) : (
          <p className="mb-2 text-xs text-amber-700 dark:text-amber-400">
            No stations configured. Go to Department rules → Stations first.
          </p>
        )}

        <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
          <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
            <thead className="sticky top-0 z-10 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              <tr>
                <th className="px-2 py-2">Name</th>
                <th className="px-2 py-2">Tier</th>
                <th className="px-2 py-2">Sub-spec</th>
                <th className="px-2 py-2">Eligible stations</th>
                <th className="px-2 py-2">Prev wl</th>
                <th className="px-2 py-2">FTE</th>
                <th className="px-2 py-2">Max OC</th>
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
                  <td className="px-2 py-1">
                    <Input
                      className="h-8"
                      placeholder="CT,MR,US"
                      value={(d.eligible_stations ?? []).join(",")}
                      onChange={(e) =>
                        updateRow(i, {
                          eligible_stations: e.target.value
                            .split(",")
                            .map((s) => s.trim())
                            .filter(Boolean),
                        })
                      }
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
            Add doctor
          </Button>
          <span className="ml-3 text-xs text-slate-500 dark:text-slate-400">
            {doctors.length} doctor{doctors.length === 1 ? "" : "s"}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

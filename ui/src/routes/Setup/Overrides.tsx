import { Plus, Trash2 } from "lucide-react";

import { useAutoSavePatch } from "@/api/autosave";
import { type OverrideEntry, useSessionState } from "@/api/hooks";
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

export function Overrides() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const overrides = data?.overrides ?? [];
  const doctors = data?.doctors ?? [];
  const stations = data?.stations ?? [];
  const doctorNames = doctors.map((d) => d.name);
  const stationNames = stations.map((s) => s.name).filter(Boolean);

  const updateRow = (idx: number, patch: Partial<OverrideEntry>) =>
    save({
      overrides: overrides.map((o, i) => (i === idx ? { ...o, ...patch } : o)),
    });

  const removeRow = (idx: number) =>
    save({ overrides: overrides.filter((_, i) => i !== idx) });

  const addRow = () =>
    save({
      overrides: [
        ...overrides,
        {
          doctor: doctorNames[0] ?? "",
          date: new Date().toISOString().slice(0, 10),
          role: "ONCALL",
        },
      ],
    });

  const clearAll = () => {
    if (overrides.length === 0) return;
    if (window.confirm(`Remove all ${overrides.length} overrides?`)) {
      save({ overrides: [] });
    }
  };

  const roleOptions = buildRoleOptions(stationNames);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Manual overrides</CardTitle>
        <CardDescription>
          Force a specific (doctor, date, role) — treated as hard constraints.
          Populated by the Roster page's "Lock" button.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
          <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
            <thead className="sticky top-0 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              <tr>
                <th className="px-2 py-2">Doctor</th>
                <th className="px-2 py-2">Date</th>
                <th className="px-2 py-2">Role</th>
                <th className="w-10 px-2 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {overrides.map((o, i) => (
                <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-900/50">
                  <td className="px-2 py-1">
                    <Select
                      className="h-8"
                      value={o.doctor}
                      onChange={(e) => updateRow(i, { doctor: e.target.value })}
                    >
                      {!doctorNames.includes(o.doctor) && (
                        <option value={o.doctor}>{o.doctor}</option>
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
                      value={o.date}
                      onChange={(e) => updateRow(i, { date: e.target.value })}
                    />
                  </td>
                  <td className="px-2 py-1">
                    <Select
                      className="h-8"
                      value={o.role}
                      onChange={(e) => updateRow(i, { role: e.target.value })}
                    >
                      {!roleOptions.includes(o.role) && (
                        <option value={o.role}>{o.role}</option>
                      )}
                      {roleOptions.map((r) => (
                        <option key={r} value={r}>
                          {r}
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
              {overrides.length === 0 && (
                <tr>
                  <td
                    colSpan={4}
                    className="px-2 py-6 text-center text-xs text-slate-500 dark:text-slate-400"
                  >
                    No overrides. "Lock" a solved roster on the Roster page to
                    populate this table.
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
            onClick={addRow}
            disabled={doctorNames.length === 0}
          >
            <Plus className="h-4 w-4" />
            Add override
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={clearAll}
            disabled={overrides.length === 0}
          >
            Clear all
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function buildRoleOptions(stationNames: string[]): string[] {
  const roles = ["ONCALL", "WEEKEND_EXT", "WEEKEND_CONSULT"];
  for (const n of stationNames) {
    roles.push(`STATION_${n}_AM`, `STATION_${n}_PM`);
  }
  return roles;
}

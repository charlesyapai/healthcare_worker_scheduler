/**
 * Setup → Role preferences.
 *
 * Per-doctor bias: "Dr A wants at least N allocations of role R this
 * period, priority P". The solver turns each entry into a soft shortfall
 * penalty (docs/RESEARCH_METRICS.md — S7).
 *
 * This is a bias, not a guarantee — if satisfying a preference would
 * break a hard rule (H1 coverage, H8 weekend, etc.), the solver ships
 * the roster anyway and the shortfall shows up in the score breakdown.
 *
 * Role can be a station name or one of ONCALL / WEEKEND_EXT /
 * WEEKEND_CONSULT. We generate the dropdown options from the current
 * session's station list + the three literal roles so the user can't
 * type a role that doesn't exist.
 */

import { Heart, Plus, Trash2 } from "lucide-react";

import { useAutoSavePatch } from "@/api/autosave";
import {
  type RolePreferenceEntry,
  useSessionState,
} from "@/api/hooks";
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

const NON_STATION_ROLES = [
  { value: "ONCALL", label: "Night on-call" },
  { value: "WEEKEND_EXT", label: "Weekend extended" },
  { value: "WEEKEND_CONSULT", label: "Weekend consultant" },
] as const;

export function Preferences() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const preferences = data?.role_preferences ?? [];
  const doctors = data?.doctors ?? [];
  const stations = data?.stations ?? [];
  const doctorNames = doctors.map((d) => d.name);

  const update = (next: RolePreferenceEntry[]) =>
    save({ role_preferences: next });
  const updateRow = (idx: number, patch: Partial<RolePreferenceEntry>) =>
    update(
      preferences.map((p, i) => (i === idx ? { ...p, ...patch } : p)),
    );
  const remove = (idx: number) =>
    update(preferences.filter((_, i) => i !== idx));
  const add = () => {
    const defaultRole =
      stations[0]?.name ?? NON_STATION_ROLES[0].value;
    update([
      ...preferences,
      {
        doctor: doctorNames[0] ?? "",
        role: defaultRole,
        min_allocations: 1,
        priority: 5,
      },
    ]);
  };

  return (
    <div className="space-y-4">
      <Card className="border-indigo-200 bg-indigo-50/40 dark:border-indigo-900 dark:bg-indigo-950/20">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <Heart className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
            <CardTitle className="text-sm">How role preferences work</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
          <p>
            Each row says{" "}
            <em>
              "Dr X wants at least <strong>N</strong> of role <strong>R</strong>
            </em>{" "}
            this period, with priority <strong>P</strong>".
          </p>
          <p>
            The solver adds a penalty of <code>priority × shortfall</code> to
            the objective — high-priority preferences are more expensive to
            miss, so the solver works harder to meet them. Preferences are{" "}
            <strong>soft</strong>: if the only way to honour one would be to
            break a hard rule (coverage, weekend H8, post-call), the solver
            will short the preference instead.
          </p>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            Priority scale: 1 = "would be nice", 5 = default, 10 = "please
            try hard". An unreachable preference (doctor isn't eligible for
            the role) shows up as a permanent shortfall in the score
            breakdown rather than failing the solve.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Per-doctor role preferences</CardTitle>
          <CardDescription>
            Applies across the whole horizon. Use this for "Dr A likes
            covering the cath lab", "Dr B wants 3 on-calls this month",
            or "consultant X prefers the OR list".
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-600 dark:bg-slate-900 dark:text-slate-300">
                <tr>
                  <th className="px-2 py-2">Doctor</th>
                  <th className="px-2 py-2">Role</th>
                  <th className="px-2 py-2 text-right">Min allocations</th>
                  <th className="px-2 py-2 text-right">Priority (1–10)</th>
                  <th className="w-10 px-2 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {preferences.map((p, i) => (
                  <tr
                    key={i}
                    className="hover:bg-slate-50 dark:hover:bg-slate-900/50"
                  >
                    <td className="px-2 py-1">
                      <Select
                        className="h-8"
                        value={p.doctor}
                        onChange={(e) =>
                          updateRow(i, { doctor: e.target.value })
                        }
                      >
                        {!doctorNames.includes(p.doctor) && (
                          <option value={p.doctor}>{p.doctor}</option>
                        )}
                        {doctorNames.map((n) => (
                          <option key={n} value={n}>
                            {n}
                          </option>
                        ))}
                      </Select>
                    </td>
                    <td className="px-2 py-1">
                      <Select
                        className="h-8"
                        value={p.role}
                        onChange={(e) => updateRow(i, { role: e.target.value })}
                      >
                        <optgroup label="Stations">
                          {stations.map((s) => (
                            <option key={s.name} value={s.name}>
                              {s.name}
                            </option>
                          ))}
                        </optgroup>
                        <optgroup label="Other roles">
                          {NON_STATION_ROLES.map((r) => (
                            <option key={r.value} value={r.value}>
                              {r.label}
                            </option>
                          ))}
                        </optgroup>
                      </Select>
                    </td>
                    <td className="px-2 py-1 text-right">
                      <Input
                        type="number"
                        min={1}
                        max={90}
                        className="h-8 w-20 text-right"
                        value={p.min_allocations}
                        onChange={(e) =>
                          updateRow(i, {
                            min_allocations: Math.max(
                              1,
                              Math.min(90, Number(e.target.value) || 1),
                            ),
                          })
                        }
                      />
                    </td>
                    <td className="px-2 py-1 text-right">
                      <Input
                        type="number"
                        min={1}
                        max={10}
                        className="h-8 w-20 text-right"
                        value={p.priority}
                        onChange={(e) =>
                          updateRow(i, {
                            priority: Math.max(
                              1,
                              Math.min(10, Number(e.target.value) || 5),
                            ),
                          })
                        }
                      />
                    </td>
                    <td className="px-2 py-1 text-right">
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="remove"
                        onClick={() => remove(i)}
                      >
                        <Trash2 className="h-4 w-4 text-slate-400" />
                      </Button>
                    </td>
                  </tr>
                ))}
                {preferences.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-2 py-6 text-center text-xs text-slate-500 dark:text-slate-400"
                    >
                      No preferences yet. Click "Add preference" below to
                      bias the solver toward a particular role for a
                      particular doctor.
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
              onClick={add}
              disabled={doctorNames.length === 0 || stations.length === 0}
            >
              <Plus className="h-4 w-4" />
              Add preference
            </Button>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {preferences.length} row
              {preferences.length === 1 ? "" : "s"}
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

import { Plus, Trash2 } from "lucide-react";

import { useAutoSavePatch } from "@/api/autosave";
import { type StationEntry, useSessionState } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const TIERS = ["junior", "senior", "consultant"] as const;
const SESSIONS = ["AM", "PM"] as const;

export function StationsEditor() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const stations = data?.stations ?? [];

  const update = (idx: number, patch: Partial<StationEntry>) =>
    save({ stations: stations.map((s, i) => (i === idx ? { ...s, ...patch } : s)) });

  const remove = (idx: number) =>
    save({ stations: stations.filter((_, i) => i !== idx) });

  const add = () =>
    save({
      stations: [
        ...stations,
        {
          name: `STATION_${stations.length + 1}`,
          sessions: ["AM", "PM"],
          required_per_session: 1,
          eligible_tiers: ["junior", "senior", "consultant"],
          is_reporting: false,
        },
      ],
    });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Stations</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {stations.length} station{stations.length === 1 ? "" : "s"}.
          </p>
        </div>
        <Button size="sm" onClick={add} variant="secondary">
          <Plus className="h-4 w-4" />
          Add station
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {stations.map((raw, i) => {
          const s = {
            ...raw,
            sessions: raw.sessions ?? [],
            eligible_tiers: raw.eligible_tiers ?? [],
          };
          return (
          <Card key={i}>
            <CardHeader className="flex-row items-start justify-between gap-2">
              <div className="flex-1">
                <CardTitle>
                  <Input
                    value={s.name}
                    onChange={(e) => update(i, { name: e.target.value })}
                    className="h-7 text-base font-semibold"
                  />
                </CardTitle>
                <CardDescription className="mt-1 flex gap-1.5">
                  {s.sessions.map((sess) => (
                    <span
                      key={sess}
                      className="rounded-md bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                    >
                      {sess}
                    </span>
                  ))}
                  <span className="text-xs text-slate-500">
                    × {s.required_per_session}
                  </span>
                </CardDescription>
              </div>
              <Button
                size="icon"
                variant="ghost"
                aria-label={`Remove ${s.name}`}
                onClick={() => remove(i)}
              >
                <Trash2 className="h-4 w-4 text-slate-400" />
              </Button>
            </CardHeader>
            <CardContent className="grid gap-3 text-sm">
              <div>
                <label className="text-xs font-medium">Sessions</label>
                <div className="mt-1 flex gap-2">
                  {SESSIONS.map((sess) => {
                    const on = s.sessions.includes(sess);
                    return (
                      <button
                        key={sess}
                        type="button"
                        onClick={() =>
                          update(i, {
                            sessions: on
                              ? s.sessions.filter((x) => x !== sess)
                              : ([...s.sessions, sess].sort() as typeof s.sessions),
                          })
                        }
                        className={
                          "rounded-md border px-2.5 py-1 text-xs font-medium transition-colors " +
                          (on
                            ? "border-emerald-300 bg-emerald-100 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                            : "border-slate-200 text-slate-500 hover:bg-slate-100 dark:border-slate-800 dark:hover:bg-slate-800")
                        }
                      >
                        {sess}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium">Required</span>
                  <Input
                    type="number"
                    min={1}
                    className="h-8 w-20"
                    value={s.required_per_session}
                    onChange={(e) =>
                      update(i, {
                        required_per_session: Math.max(1, Number(e.target.value) || 1),
                      })
                    }
                  />
                </label>
                <label className="flex flex-1 items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={s.is_reporting}
                    onChange={(e) => update(i, { is_reporting: e.target.checked })}
                  />
                  Reporting station (spread consecutive days)
                </label>
              </div>
              <div>
                <label className="text-xs font-medium">Eligible tiers</label>
                <div className="mt-1 flex gap-2">
                  {TIERS.map((t) => {
                    const on = s.eligible_tiers.includes(t);
                    return (
                      <button
                        key={t}
                        type="button"
                        onClick={() =>
                          update(i, {
                            eligible_tiers: on
                              ? s.eligible_tiers.filter((x) => x !== t)
                              : ([...s.eligible_tiers, t] as typeof s.eligible_tiers),
                          })
                        }
                        className={
                          "rounded-md border px-2.5 py-1 text-xs font-medium transition-colors " +
                          (on
                            ? "border-indigo-300 bg-indigo-100 text-indigo-800 dark:border-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                            : "border-slate-200 text-slate-500 hover:bg-slate-100 dark:border-slate-800 dark:hover:bg-slate-800")
                        }
                      >
                        {t}
                      </button>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>
          );
        })}
      </div>
    </div>
  );
}

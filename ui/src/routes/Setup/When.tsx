import { format } from "date-fns";
import { X } from "lucide-react";

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

export function When() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const horizon = data?.horizon ?? { n_days: 21, public_holidays: [], start_date: null };

  const setHorizon = (patch: Partial<NonNullable<typeof horizon>>) => {
    save({ horizon: { ...horizon, ...patch } });
  };

  const addHoliday = (iso: string) => {
    if (!iso || horizon.public_holidays?.includes(iso)) return;
    setHorizon({ public_holidays: [...(horizon.public_holidays ?? []), iso].sort() });
  };

  const removeHoliday = (iso: string) => {
    setHorizon({
      public_holidays: (horizon.public_holidays ?? []).filter((d) => d !== iso),
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>When</CardTitle>
        <CardDescription>Roster start date, length, and public holidays.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className="text-sm font-medium">Start date</span>
          <Input
            type="date"
            value={horizon.start_date ?? ""}
            onChange={(e) => setHorizon({ start_date: e.target.value || null })}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-sm font-medium">Number of days</span>
          <Input
            type="number"
            min={1}
            max={90}
            value={horizon.n_days ?? 21}
            onChange={(e) =>
              setHorizon({ n_days: Math.max(1, Math.min(90, Number(e.target.value))) })
            }
          />
        </label>
        <div className="sm:col-span-2">
          <span className="text-sm font-medium">Public holidays</span>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            Treated like Sundays (weekend coverage rules apply).
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
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
            <AddHolidayInput onAdd={addHoliday} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function AddHolidayInput({ onAdd }: { onAdd: (iso: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="date"
        aria-label="Add public holiday"
        className="h-7 rounded-md border border-slate-300 bg-white px-2 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900"
        onChange={(e) => {
          onAdd(e.target.value);
          e.currentTarget.value = "";
        }}
      />
      <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" disabled>
        add
      </Button>
    </div>
  );
}

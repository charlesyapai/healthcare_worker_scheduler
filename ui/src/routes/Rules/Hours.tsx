import { useAutoSavePatch } from "@/api/autosave";
import { useSessionState } from "@/api/hooks";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const FIELDS: Array<[keyof Hours, string]> = [
  ["weekday_am", "Weekday AM"],
  ["weekday_pm", "Weekday PM"],
  ["weekend_am", "Weekend AM"],
  ["weekend_pm", "Weekend PM"],
  ["weekday_oncall", "Weekday on-call"],
  ["weekend_oncall", "Weekend on-call"],
  ["weekend_ext", "Weekend extended-duty"],
  ["weekend_consult", "Weekend consultant"],
];

type Hours = {
  weekday_am: number;
  weekday_pm: number;
  weekend_am: number;
  weekend_pm: number;
  weekday_oncall: number;
  weekend_oncall: number;
  weekend_ext: number;
  weekend_consult: number;
};

export function HoursEditor() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const hours: Hours = (data?.hours as Hours) ?? {
    weekday_am: 4,
    weekday_pm: 4,
    weekend_am: 4,
    weekend_pm: 4,
    weekday_oncall: 12,
    weekend_oncall: 16,
    weekend_ext: 12,
    weekend_consult: 8,
  };

  const max = Math.max(...FIELDS.map(([k]) => hours[k] as number), 1);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Hours per shift</CardTitle>
        <CardDescription>
          Used for the Hours/week column only. Does NOT affect solver decisions.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="divide-y divide-slate-200 dark:divide-slate-800">
          {FIELDS.map(([k, label]) => {
            const v = hours[k];
            const pct = (Number(v) / max) * 100;
            return (
              <div key={k} className="grid grid-cols-[1fr_auto_5rem] items-center gap-3 py-2">
                <div>
                  <p className="text-sm font-medium">{label}</p>
                  <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                    <div
                      className="h-full bg-indigo-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
                <span className="text-xs text-slate-500">hours</span>
                <Input
                  type="number"
                  min={0}
                  step={0.5}
                  className="h-8 text-right"
                  value={v}
                  onChange={(e) =>
                    save({ hours: { ...hours, [k]: Number(e.target.value) || 0 } })
                  }
                />
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

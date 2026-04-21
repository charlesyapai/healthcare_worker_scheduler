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

type WL = {
  weekday_session: number;
  weekend_session: number;
  weekday_oncall: number;
  weekend_oncall: number;
  weekend_ext: number;
  weekend_consult: number;
};

const FIELDS: Array<[keyof WL, string, string]> = [
  ["weekday_session", "Weekday session", "AM or PM station on a weekday"],
  ["weekend_session", "Weekend session", "AM or PM station on Sat/Sun (if enabled)"],
  ["weekday_oncall", "Weekday on-call", "Junior/senior on-call weeknight"],
  ["weekend_oncall", "Weekend on-call", "Junior/senior on-call Sat/Sun night"],
  ["weekend_ext", "Weekend extended", "Sat/Sun extended duty"],
  ["weekend_consult", "Weekend consultant", "Consultant weekend cover"],
];

export function Fairness() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const wl: WL = (data?.workload_weights as WL) ?? {
    weekday_session: 10,
    weekend_session: 15,
    weekday_oncall: 20,
    weekend_oncall: 35,
    weekend_ext: 20,
    weekend_consult: 25,
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>How fairness is measured</CardTitle>
        <CardDescription>
          Weight each role before the solver balances per tier. Higher = counts
          as more work. Set to 0 to exclude.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {FIELDS.map(([k, label, desc]) => (
          <label key={k} className="grid grid-cols-[1fr_auto] items-center gap-3">
            <div>
              <p className="text-sm font-medium">{label}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">{desc}</p>
            </div>
            <Input
              type="number"
              min={0}
              className="h-8 w-20 text-right"
              value={wl[k]}
              onChange={(e) =>
                save({
                  workload_weights: { ...wl, [k]: Math.max(0, Number(e.target.value) || 0) },
                })
              }
            />
          </label>
        ))}
      </CardContent>
    </Card>
  );
}

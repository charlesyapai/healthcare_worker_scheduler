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

type SW = {
  workload: number;
  sessions: number;
  oncall: number;
  weekend: number;
  reporting: number;
  idle_weekday: number;
  preference: number;
};

const FIELDS: Array<[keyof SW, string, string]> = [
  ["workload", "Fairness: balance weighted workload", "Primary term. Spreads total workload score per tier."],
  ["idle_weekday", "Penalty per day a doctor has no duty", "Heavy — forces full utilisation."],
  ["sessions", "Balance raw session counts", "Secondary — counts AM+PM sessions."],
  ["oncall", "Balance on-call counts", "Absolute on-call spread per tier."],
  ["weekend", "Balance weekend-duty counts", "Absolute weekend spread per tier."],
  ["reporting", "Spread out reporting-desk duty", "Avoids back-to-back reporting days."],
  ["preference", "Honour positive session preferences", "Cost per unmet Prefer AM/PM."],
];

export function Priorities() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const sw: SW = (data?.soft_weights as SW) ?? {
    workload: 40,
    sessions: 5,
    oncall: 10,
    weekend: 10,
    reporting: 5,
    idle_weekday: 100,
    preference: 5,
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Solver priorities</CardTitle>
        <CardDescription>
          How hard the solver tries to achieve each goal. Higher = more important.
          Set to 0 to disable.
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
              value={sw[k]}
              onChange={(e) =>
                save({ soft_weights: { ...sw, [k]: Math.max(0, Number(e.target.value) || 0) } })
              }
            />
          </label>
        ))}
      </CardContent>
    </Card>
  );
}

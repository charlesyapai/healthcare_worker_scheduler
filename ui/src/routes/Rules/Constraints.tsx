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

const RULES = [
  {
    key: "h4_enabled",
    label: "Cap on-call frequency (1-in-N)",
    description: "No doctor has more than one on-call in any N-day window.",
  },
  {
    key: "h5_enabled",
    label: "Day off after a night on-call",
    description: "Post-call: no AM/PM/on-call the day after.",
  },
  {
    key: "h6_enabled",
    label: "Seniors on-call get the whole day off",
    description: "Senior's on-call day has no station work.",
  },
  {
    key: "h7_enabled",
    label: "Juniors on-call work the PM session",
    description: "Junior covers a PM station on their on-call day.",
  },
  {
    key: "h8_enabled",
    label: "Weekend coverage",
    description:
      "Sat/Sun requires 1 junior EXT, 1 senior EXT, 1 junior OC, 1 senior OC, 1 consultant per sub-spec.",
  },
  {
    key: "h9_enabled",
    label: "Day off in lieu after weekend EXT",
    description: "Weekend-EXT doctor gets the Friday-before or Monday-after off.",
  },
  {
    key: "h11_enabled",
    label: "Every doctor has a duty every weekday",
    description: "Soft; penalty per idle doctor-weekday.",
  },
  {
    key: "weekend_am_pm",
    label: "Also roster AM/PM stations on weekends",
    description: "Off by default. Enable only if your hospital staffs weekday-style stations on weekends.",
  },
  {
    key: "weekday_oncall_coverage",
    label: "Weekday on-call coverage",
    description:
      "Require exactly 1 junior + 1 senior on-call every weekday night. Weekends are handled by the weekend-coverage rule. Leave on unless you really want weekdays uncovered.",
  },
] as const;

type ConstraintKey = (typeof RULES)[number]["key"];

export function Constraints() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const cfg = data?.constraints ?? {
    h4_enabled: true,
    h4_gap: 3,
    h5_enabled: true,
    h6_enabled: true,
    h7_enabled: true,
    h8_enabled: true,
    h9_enabled: true,
    h11_enabled: true,
    weekend_am_pm: false,
    weekday_oncall_coverage: true,
  };

  const toggle = (key: ConstraintKey) =>
    save({ constraints: { ...cfg, [key]: !cfg[key] } });

  const setGap = (n: number) =>
    save({ constraints: { ...cfg, h4_gap: Math.max(2, n) } });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Rules for the roster</CardTitle>
        <CardDescription>
          Toggle each hard rule. Defaults match the spec in docs/CONSTRAINTS.md.
        </CardDescription>
      </CardHeader>
      <CardContent className="divide-y divide-slate-200 dark:divide-slate-800">
        {RULES.map(({ key, label, description }) => (
          <div key={key} className="flex items-start justify-between gap-4 py-3 first:pt-0 last:pb-0">
            <div>
              <p className="text-sm font-medium">{label}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">{description}</p>
              {key === "h4_enabled" && cfg.h4_enabled && (
                <div className="mt-2 flex items-center gap-2 text-xs">
                  <span>N =</span>
                  <Input
                    className="h-7 w-16"
                    type="number"
                    min={2}
                    max={14}
                    value={cfg.h4_gap}
                    onChange={(e) => setGap(Number(e.target.value) || 3)}
                  />
                  <span className="text-slate-500">consecutive days</span>
                </div>
              )}
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={cfg[key]}
              onClick={() => toggle(key)}
              className={
                "relative h-6 w-11 flex-shrink-0 rounded-full transition-colors " +
                (cfg[key]
                  ? "bg-indigo-600 dark:bg-indigo-500"
                  : "bg-slate-300 dark:bg-slate-700")
              }
            >
              <span
                className={
                  "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform " +
                  (cfg[key] ? "translate-x-[22px]" : "translate-x-0.5")
                }
              />
            </button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

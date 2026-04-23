/**
 * Combined Hours + Fairness (workload weights) + Solver priorities page.
 *
 * Kept as three distinct cards so each concept stays legible, but on
 * one scrollable page so the user can tune the whole weighted objective
 * in one sitting rather than bouncing between sub-tabs.
 */

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

const HOURS_FIELDS: Array<[keyof Hours, string]> = [
  ["weekday_am", "Weekday AM"],
  ["weekday_pm", "Weekday PM"],
  ["weekend_am", "Weekend AM"],
  ["weekend_pm", "Weekend PM"],
  ["weekday_oncall", "Weekday on-call"],
  ["weekend_oncall", "Weekend on-call"],
  ["weekend_ext", "Weekend extended-duty"],
  ["weekend_consult", "Weekend consultant"],
];

type WL = {
  weekday_session: number;
  weekend_session: number;
  weekday_oncall: number;
  weekend_oncall: number;
  weekend_ext: number;
  weekend_consult: number;
};

const FAIR_FIELDS: Array<[keyof WL, string, string]> = [
  ["weekday_session", "Weekday session", "AM or PM station on a weekday"],
  ["weekend_session", "Weekend session", "AM or PM station on Sat/Sun (if enabled)"],
  ["weekday_oncall", "Weekday on-call", "Junior/senior on-call weeknight"],
  ["weekend_oncall", "Weekend on-call", "Junior/senior on-call Sat/Sun night"],
  ["weekend_ext", "Weekend extended", "Sat/Sun extended duty"],
  ["weekend_consult", "Weekend consultant", "Consultant weekend cover"],
];

type SW = {
  workload: number;
  sessions: number;
  oncall: number;
  weekend: number;
  reporting: number;
  idle_weekday: number;
  preference: number;
};

const PRIO_FIELDS: Array<[keyof SW, string, string]> = [
  ["workload", "Balance weighted workload", "Primary term — spreads total workload score per tier."],
  ["idle_weekday", "Penalty per idle weekday", "Heavy — forces full utilisation."],
  ["sessions", "Balance raw session counts", "Secondary — counts AM+PM sessions."],
  ["oncall", "Balance on-call counts", "Absolute on-call spread per tier."],
  ["weekend", "Balance weekend duty counts", "Absolute weekend spread per tier."],
  ["reporting", "Spread reporting-desk duty", "Avoids back-to-back reporting days."],
  ["preference", "Honour positive preferences", "Cost per unmet Prefer AM/PM."],
];

export function Weights() {
  return (
    <div className="space-y-4">
      <HoursCard />
      <FairnessCard />
      <PrioritiesCard />
    </div>
  );
}

// ---------------------------------------------------------------- Hours

function HoursCard() {
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
  const max = Math.max(...HOURS_FIELDS.map(([k]) => hours[k] as number), 1);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Hours per shift</CardTitle>
        <CardDescription className="text-xs">
          Used for the Hours/week column on the roster. Does <strong>not</strong>{" "}
          affect solver decisions — see Fairness below for that.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="divide-y divide-slate-100 dark:divide-slate-800">
          {HOURS_FIELDS.map(([k, label]) => {
            const v = hours[k];
            const pct = (Number(v) / max) * 100;
            return (
              <div
                key={k}
                className="grid grid-cols-[1fr_auto_5rem] items-center gap-3 py-2"
              >
                <div>
                  <p className="text-sm font-medium">{label}</p>
                  <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                    <div
                      className="h-full bg-indigo-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
                <span className="text-[11px] text-slate-500">hours</span>
                <Input
                  type="number"
                  min={0}
                  step={0.5}
                  className="h-8 text-right"
                  value={v}
                  onChange={(e) =>
                    save({
                      hours: {
                        ...hours,
                        [k]: Number(e.target.value) || 0,
                      },
                    })
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

// ---------------------------------------------------------------- Fairness

function FairnessCard() {
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
      <CardHeader className="pb-3">
        <CardTitle className="text-base">How fairness is measured</CardTitle>
        <CardDescription className="text-xs">
          Weight each role before the solver balances per tier. Higher ={" "}
          counts as more work. Set to 0 to exclude.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2">
        {FAIR_FIELDS.map(([k, label, desc]) => (
          <label
            key={k}
            className="grid grid-cols-[1fr_auto] items-center gap-3"
          >
            <div>
              <p className="text-sm font-medium">{label}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {desc}
              </p>
            </div>
            <Input
              type="number"
              min={0}
              className="h-8 w-20 text-right"
              value={wl[k]}
              onChange={(e) =>
                save({
                  workload_weights: {
                    ...wl,
                    [k]: Math.max(0, Number(e.target.value) || 0),
                  },
                })
              }
            />
          </label>
        ))}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- Priorities

function PrioritiesCard() {
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
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Solver priorities</CardTitle>
        <CardDescription className="text-xs">
          How hard the solver tries to achieve each goal. Higher = more
          important. Set to 0 to disable.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2">
        {PRIO_FIELDS.map(([k, label, desc]) => (
          <label
            key={k}
            className="grid grid-cols-[1fr_auto] items-center gap-3"
          >
            <div>
              <p className="text-sm font-medium">{label}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {desc}
              </p>
            </div>
            <Input
              type="number"
              min={0}
              className="h-8 w-20 text-right"
              value={sw[k]}
              onChange={(e) =>
                save({
                  soft_weights: {
                    ...sw,
                    [k]: Math.max(0, Number(e.target.value) || 0),
                  },
                })
              }
            />
          </label>
        ))}
      </CardContent>
    </Card>
  );
}

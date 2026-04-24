/**
 * Schedule shape — the "what does my week look like" entry point for
 * the Rules section. Pick a rota pattern preset (Clinic AM/PM, 12h
 * Day/Night, Surgical lists, 24/7 shifts) and the UI fills in matching
 * shift labels + hours + constraints. Users who want manual control
 * can edit the shift labels directly below the preset row.
 *
 * This page is cosmetic-plus-presets — it doesn't introduce any new
 * solver capability, but it anchors the mental model. The actual
 * session structure (AM / PM / FULL_DAY) is picked per-station on the
 * Teams tab.
 */

import {
  CalendarClock,
  Moon,
  Scissors,
  Sun,
} from "lucide-react";

import { useAutoSavePatch } from "@/api/autosave";
import {
  DEFAULT_SHIFT_LABELS,
  type SessionState,
  type ShiftLabels,
  useSessionState,
} from "@/api/hooks";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------- presets

type PresetKey = "clinic" | "day_night_12h" | "surgical" | "shift_24_7";

interface Preset {
  key: PresetKey;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
  labels: ShiftLabels;
  hours: {
    weekday_am: number;
    weekday_pm: number;
    weekend_am: number;
    weekend_pm: number;
    weekday_oncall: number;
    weekend_oncall: number;
    weekend_ext: number;
    weekend_consult: number;
  };
  constraints: {
    weekend_am_pm: boolean;
    weekday_oncall_coverage: boolean;
  };
}

const PRESETS: Preset[] = [
  {
    key: "clinic",
    label: "Clinic (AM/PM)",
    icon: Sun,
    description:
      "Mon–Fri daytime. Two half-sessions per day. Good for outpatient clinics, reporting pools, office-hours-only teams.",
    labels: {
      ...DEFAULT_SHIFT_LABELS,
      am: "Morning 08:00–13:00",
      pm: "Afternoon 13:00–18:00",
      oncall: "Night call 20:00–08:00",
    },
    hours: {
      weekday_am: 4,
      weekday_pm: 4,
      weekend_am: 4,
      weekend_pm: 4,
      weekday_oncall: 12,
      weekend_oncall: 16,
      weekend_ext: 12,
      weekend_consult: 8,
    },
    constraints: {
      weekend_am_pm: false,
      weekday_oncall_coverage: false,
    },
  },
  {
    key: "day_night_12h",
    label: "12h Day + Night",
    icon: Moon,
    description:
      "Two shifts per day: Day 08:00–20:00, Night 20:00–08:00. Matches acute hospital wards, paediatrics, ED.",
    labels: {
      ...DEFAULT_SHIFT_LABELS,
      am: "Day 08:00–14:00",
      pm: "Day 14:00–20:00",
      oncall: "Night 20:00–08:00",
    },
    hours: {
      weekday_am: 6,
      weekday_pm: 6,
      weekend_am: 6,
      weekend_pm: 6,
      weekday_oncall: 12,
      weekend_oncall: 12,
      weekend_ext: 12,
      weekend_consult: 12,
    },
    constraints: {
      weekend_am_pm: true,
      weekday_oncall_coverage: true,
    },
  },
  {
    key: "surgical",
    label: "Surgical lists",
    icon: Scissors,
    description:
      "All-day consultant-led theatre lists. Juniors/seniors still split AM/PM for clinic + ward cover. Set OR-list stations to Full-day on the Teams tab.",
    labels: {
      ...DEFAULT_SHIFT_LABELS,
      am: "Morning 08:00–13:00",
      pm: "Afternoon 13:00–17:00",
      full_day: "OR list 08:00–17:00",
      oncall: "Night call 17:00–08:00",
    },
    hours: {
      weekday_am: 4,
      weekday_pm: 4,
      weekend_am: 4,
      weekend_pm: 4,
      weekday_oncall: 15,
      weekend_oncall: 16,
      weekend_ext: 12,
      weekend_consult: 9,
    },
    constraints: {
      weekend_am_pm: false,
      weekday_oncall_coverage: true,
    },
  },
  {
    key: "shift_24_7",
    label: "24/7 shifts",
    icon: CalendarClock,
    description:
      "Round-the-clock cover with weekend AM/PM enabled — every station staffed every day. Heavy demand; use for ICU/ED/inpatient wards.",
    labels: {
      ...DEFAULT_SHIFT_LABELS,
      am: "Early 07:00–15:00",
      pm: "Late 15:00–23:00",
      oncall: "Night 23:00–07:00",
    },
    hours: {
      weekday_am: 8,
      weekday_pm: 8,
      weekend_am: 8,
      weekend_pm: 8,
      weekday_oncall: 8,
      weekend_oncall: 8,
      weekend_ext: 12,
      weekend_consult: 10,
    },
    constraints: {
      weekend_am_pm: true,
      weekday_oncall_coverage: true,
    },
  },
];

function detectActivePreset(labels: ShiftLabels): PresetKey | null {
  for (const p of PRESETS) {
    if (
      p.labels.am === labels.am &&
      p.labels.pm === labels.pm &&
      p.labels.oncall === labels.oncall
    ) {
      return p.key;
    }
  }
  return null;
}

// ---------------------------------------------------------------- page

export function Shape() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const labels: ShiftLabels = (data?.shift_labels as ShiftLabels) ?? DEFAULT_SHIFT_LABELS;
  const activePreset = detectActivePreset(labels);

  const applyPreset = (p: Preset) => {
    // The backend PATCH endpoint does a deep-merge, so passing only
    // the two fields we want to override (inside `constraints`) is
    // enough to leave the other toggles untouched. `Partial<SessionState>`
    // is only shallowly-partial on the TypeScript side though, so we
    // cast through `unknown` to let the nested-partial shape land.
    const patch = {
      shift_labels: p.labels,
      hours: p.hours,
      constraints: {
        weekend_am_pm: p.constraints.weekend_am_pm,
        weekday_oncall_coverage: p.constraints.weekday_oncall_coverage,
      },
    } as unknown as Partial<SessionState>;
    save(patch);
  };

  const updateLabel = (key: keyof ShiftLabels, value: string) =>
    save({ shift_labels: { ...labels, [key]: value } });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">1 · Pick a rota pattern</CardTitle>
          <CardDescription className="text-xs">
            Picks below set shift labels, hours per shift, and
            weekend-coverage toggles in one click. You can still tweak
            any field manually afterwards on the other Rules tabs.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {PRESETS.map((p) => {
            const on = activePreset === p.key;
            const Icon = p.icon;
            return (
              <button
                key={p.key}
                type="button"
                onClick={() => applyPreset(p)}
                className={cn(
                  "flex flex-col gap-1 rounded-md border p-3 text-left transition-colors",
                  on
                    ? "border-indigo-500 bg-indigo-50 ring-1 ring-indigo-200 dark:border-indigo-400 dark:bg-indigo-950 dark:ring-indigo-900"
                    : "border-slate-200 bg-white hover:border-slate-400 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-slate-500 dark:hover:bg-slate-800",
                )}
              >
                <div className="flex items-center gap-2">
                  <Icon
                    className={cn(
                      "h-4 w-4",
                      on
                        ? "text-indigo-600 dark:text-indigo-300"
                        : "text-slate-500 dark:text-slate-400",
                    )}
                  />
                  <span className="text-sm font-semibold">{p.label}</span>
                  {on && (
                    <span className="ml-auto rounded-full bg-indigo-600 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white">
                      active
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-slate-600 dark:text-slate-400">
                  {p.description}
                </p>
              </button>
            );
          })}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">2 · Shift labels</CardTitle>
          <CardDescription className="text-xs">
            Cosmetic names for the internal session keys. Used in the
            Roster grid, Export print-out, and per-doctor mailto body.{" "}
            <strong>Do not</strong> change solver behaviour — the solver
            reasons over AM / PM / FULL_DAY / Night call.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <LabelInput
            title="AM session"
            value={labels.am}
            onChange={(v) => updateLabel("am", v)}
          />
          <LabelInput
            title="PM session"
            value={labels.pm}
            onChange={(v) => updateLabel("pm", v)}
          />
          <LabelInput
            title="Full-day session"
            value={labels.full_day}
            onChange={(v) => updateLabel("full_day", v)}
            hint="Used when a station has Full-day instead of AM/PM."
          />
          <LabelInput
            title="Night on-call"
            value={labels.oncall}
            onChange={(v) => updateLabel("oncall", v)}
          />
          <LabelInput
            title="Weekend extended"
            value={labels.weekend_ext}
            onChange={(v) => updateLabel("weekend_ext", v)}
          />
          <LabelInput
            title="Weekend consultant"
            value={labels.weekend_consult}
            onChange={(v) => updateLabel("weekend_consult", v)}
          />
        </CardContent>
      </Card>

      <Card className="border-indigo-200 bg-indigo-50/60 dark:border-indigo-900 dark:bg-indigo-950/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">
            What the solver supports right now
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
          <p>
            Internally every day has three slots: <strong>AM</strong>,{" "}
            <strong>PM</strong>, <strong>Night on-call</strong>. A station
            can use AM and/or PM, or a <strong>Full-day</strong> booking
            which locks both halves to the same doctor — the right shape
            for a surgical OR list or an all-day clinic.
          </p>
          <p>
            Night shifts are modelled as <em>on-call</em>, with automatic
            post-call rest (configurable on the Rules tab). Weekends have
            their own coverage block (Weekend EXT, Weekend on-call,
            Weekend consultant per sub-spec).
          </p>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            If your rota has more than three shifts per day (e.g. early /
            late / twilight / night on the same day), that's on the
            roadmap — but not in this build.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function LabelInput({
  title,
  value,
  onChange,
  hint,
}: {
  title: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </span>
      <Input
        className="h-9"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && (
        <span className="text-[10px] text-slate-500 dark:text-slate-400">
          {hint}
        </span>
      )}
    </label>
  );
}

import {
  CalendarDays,
  Moon,
  ShieldAlert,
  ShieldCheck,
  Shuffle,
  Sun,
} from "lucide-react";

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
import { Toggle } from "@/components/ui/toggle";
import { cn } from "@/lib/utils";

type ConstraintCfg = {
  h4_enabled: boolean;
  h4_gap: number;
  h5_enabled: boolean;
  h6_enabled: boolean;
  h7_enabled: boolean;
  h8_enabled: boolean;
  h9_enabled: boolean;
  h11_enabled: boolean;
  weekend_am_pm: boolean;
  weekday_oncall_coverage: boolean;
};

const DEFAULTS: ConstraintCfg = {
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

type ToggleKey = Exclude<keyof ConstraintCfg, "h4_gap">;

type RuleGroup = "nights" | "weekends" | "weekdays";

interface RuleDef {
  key: ToggleKey;
  label: string;
  description: string;
  group: RuleGroup;
}

// Rules grouped by the part of the schedule they govern. The user's
// mental model on Rules is "nights / weekends / weekdays", not
// "succession / coverage / utilisation" jargon — those are correct
// but not what a coordinator thinks about first.
const RULES: RuleDef[] = [
  // ---- Nights & on-call ----
  {
    key: "weekday_oncall_coverage",
    label: "Cover every weekday night",
    description:
      "Require exactly 1 junior + 1 senior on-call every weekday night. Turn off only if your department doesn't run overnight weekday cover.",
    group: "nights",
  },
  {
    key: "h4_enabled",
    label: "Cap on-call frequency (1-in-N)",
    description:
      "No doctor does on-call more than once in any N-day window. Default N = 3, i.e. at most one on-call every three days.",
    group: "nights",
  },
  {
    key: "h5_enabled",
    label: "Day off after a night on-call",
    description:
      "Post-call: no AM / PM / on-call on the day after a night on-call. The statutory rest rule.",
    group: "nights",
  },
  {
    key: "h6_enabled",
    label: "Seniors on-call get the whole day off",
    description:
      "On the day a senior is on-call for that night, they do no station work. Reflects the UK model where seniors typically rest before their night shift.",
    group: "nights",
  },
  {
    key: "h7_enabled",
    label: "Juniors on-call work the PM session",
    description:
      "Juniors cover a PM station on their on-call day, then the night on-call. Drops to off if your juniors rest-before-night instead.",
    group: "nights",
  },
  // ---- Weekends ----
  {
    key: "h8_enabled",
    label: "Full weekend coverage on Sat & Sun",
    description:
      "Sat/Sun require: 1 junior EXT, 1 senior EXT, 1 junior on-call, 1 senior on-call, and 1 consultant per sub-spec.",
    group: "weekends",
  },
  {
    key: "weekend_am_pm",
    label: "Also run weekday-style AM/PM stations on weekends",
    description:
      "Off by default — most UK hospitals staff weekends via the EXT + on-call block above, not the weekday station grid. Enable for 24/7-shift patterns.",
    group: "weekends",
  },
  {
    key: "h9_enabled",
    label: "Day in lieu after weekend EXT",
    description:
      "A weekend-EXT doctor gets either the Friday before or the Monday after off. The solver picks whichever is cheaper.",
    group: "weekends",
  },
  // ---- Weekdays ----
  {
    key: "h11_enabled",
    label: "Every doctor has a duty every weekday",
    description:
      "Soft rule — penalises any doctor-weekday with no station, on-call, lieu, or post-call excuse. Turn off if you want a leaner week where people legitimately get free days.",
    group: "weekdays",
  },
];

const GROUP_META: Record<
  RuleGroup,
  {
    label: string;
    description: string;
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  nights: {
    label: "Nights & on-call",
    description:
      "How night shifts work. Set up once for your department; changing these mid-period changes which rosters are legal.",
    icon: Moon,
  },
  weekends: {
    label: "Weekends",
    description:
      "Sat/Sun coverage. Most hospitals run a different pattern from weekdays — this block controls that.",
    icon: CalendarDays,
  },
  weekdays: {
    label: "Weekdays — who must have a duty",
    description:
      "Soft levers that shape how busy each doctor-day looks.",
    icon: Sun,
  },
};

// Strictness presets. "Balanced" matches DEFAULTS; others flip a handful
// of toggles in one click so a new user doesn't need to know which lever
// maps to which real-world behaviour.
type Preset = "strict" | "balanced" | "relaxed";

const PRESETS: Record<Preset, Partial<ConstraintCfg>> = {
  strict: {
    h4_enabled: true,
    h4_gap: 4,
    h5_enabled: true,
    h6_enabled: true,
    h7_enabled: true,
    h8_enabled: true,
    h9_enabled: true,
    h11_enabled: true,
    weekday_oncall_coverage: true,
    weekend_am_pm: false,
  },
  balanced: DEFAULTS,
  relaxed: {
    h4_enabled: true,
    h4_gap: 2,
    h5_enabled: true,
    h6_enabled: false,
    h7_enabled: false,
    h8_enabled: true,
    h9_enabled: false,
    h11_enabled: false,
    weekday_oncall_coverage: false,
    weekend_am_pm: false,
  },
};

function activePreset(cfg: ConstraintCfg): Preset | null {
  for (const name of ["strict", "balanced", "relaxed"] as const) {
    const p = PRESETS[name];
    if (
      Object.entries(p).every(
        ([k, v]) => (cfg as unknown as Record<string, unknown>)[k] === v,
      )
    ) {
      return name;
    }
  }
  return null;
}

export function Constraints() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const cfg: ConstraintCfg = (data?.constraints as ConstraintCfg) ?? DEFAULTS;

  const toggle = (key: ToggleKey) =>
    save({ constraints: { ...cfg, [key]: !cfg[key] } });
  const setGap = (n: number) =>
    save({ constraints: { ...cfg, h4_gap: Math.max(2, n) } });
  const applyPreset = (name: Preset) =>
    save({ constraints: { ...cfg, ...PRESETS[name] } });

  const enabledCount = RULES.filter((r) => cfg[r.key]).length;
  const totalCount = RULES.length;
  const preset = activePreset(cfg);

  const grouped: Record<RuleGroup, RuleDef[]> = {
    nights: [],
    weekends: [],
    weekdays: [],
  };
  for (const r of RULES) grouped[r.group].push(r);

  return (
    <div className="space-y-4">
      <Card className="border-indigo-200 bg-indigo-50/40 dark:border-indigo-900 dark:bg-indigo-950/20">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">
            How to read these rules
          </CardTitle>
          <CardDescription className="text-xs">
            Each toggle controls a part of your week: when night on-call
            happens, how weekends are covered, and what counts as a
            "full" weekday. Pick a strictness preset on the right to
            get a known-good default, then tweak.
          </CardDescription>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base">Rules for the roster</CardTitle>
              <CardDescription className="text-xs">
                {enabledCount} of {totalCount} rules active. Defaults match the
                spec in <code>docs/CONSTRAINTS.md</code>.
              </CardDescription>
            </div>
            <PresetRow active={preset} onPick={applyPreset} />
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          {(["nights", "weekends", "weekdays"] as const).map((group) => {
            const meta = GROUP_META[group];
            const Icon = meta.icon;
            return (
              <section key={group} className="space-y-1">
                <header className="flex items-baseline gap-2">
                  <Icon className="h-3.5 w-3.5 flex-shrink-0 text-indigo-600 dark:text-indigo-300" />
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-200">
                    {meta.label}
                  </h3>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    {meta.description}
                  </p>
                </header>
                <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 px-3 dark:divide-slate-800 dark:border-slate-800">
                  {grouped[group].map((rule) => (
                    <RuleRow
                      key={rule.key}
                      rule={rule}
                      on={cfg[rule.key]}
                      onToggle={() => toggle(rule.key)}
                    >
                      {rule.key === "h4_enabled" && cfg.h4_enabled && (
                        <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-600 dark:text-slate-400">
                          <span>N =</span>
                          <Input
                            className="h-7 w-16 text-xs"
                            type="number"
                            min={2}
                            max={14}
                            value={cfg.h4_gap}
                            onChange={(e) =>
                              setGap(Number(e.target.value) || 3)
                            }
                          />
                        <span>consecutive days</span>
                      </div>
                    )}
                    </RuleRow>
                  ))}
                </ul>
              </section>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}

function RuleRow({
  rule,
  on,
  onToggle,
  children,
}: {
  rule: RuleDef;
  on: boolean;
  onToggle: () => void;
  children?: React.ReactNode;
}) {
  return (
    <li className="flex items-start justify-between gap-4 py-2.5">
      <div className="min-w-0">
        <p className="text-sm font-medium">{rule.label}</p>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {rule.description}
        </p>
        {children}
      </div>
      <Toggle
        checked={on}
        onChange={onToggle}
        ariaLabel={`${on ? "Disable" : "Enable"} ${rule.label}`}
      />
    </li>
  );
}

function PresetRow({
  active,
  onPick,
}: {
  active: ReturnType<typeof activePreset>;
  onPick: (name: Preset) => void;
}) {
  const items: Array<{
    key: Preset;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    hint: string;
  }> = [
    {
      key: "strict",
      label: "Strict",
      icon: ShieldCheck,
      hint: "Full rest; lenient toward no-one. Harder to solve.",
    },
    {
      key: "balanced",
      label: "Balanced",
      icon: Shuffle,
      hint: "Matches the built-in defaults.",
    },
    {
      key: "relaxed",
      label: "Relaxed",
      icon: ShieldAlert,
      hint: "Fewer succession rules — easier to solve but more concentrated work.",
    },
  ];
  return (
    <div
      role="radiogroup"
      aria-label="Preset strictness"
      className="flex flex-wrap gap-1.5"
    >
      {items.map(({ key, label, icon: Icon, hint }) => {
        const on = active === key;
        return (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={on}
            title={hint}
            onClick={() => onPick(key)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
              on
                ? "border-indigo-500 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-950 dark:text-indigo-200"
                : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800",
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        );
      })}
    </div>
  );
}

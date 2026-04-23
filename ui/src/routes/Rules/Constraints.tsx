import { ShieldAlert, ShieldCheck, Shuffle } from "lucide-react";

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

interface RuleDef {
  key: ToggleKey;
  label: string;
  description: string;
  group: "succession" | "coverage" | "utilisation";
}

const RULES: RuleDef[] = [
  {
    key: "h4_enabled",
    label: "Cap on-call frequency (1-in-N)",
    description: "No doctor has more than one on-call in any N-day window.",
    group: "succession",
  },
  {
    key: "h5_enabled",
    label: "Day off after a night on-call",
    description: "Post-call: no AM/PM/on-call the day after.",
    group: "succession",
  },
  {
    key: "h6_enabled",
    label: "Seniors on-call get the whole day off",
    description: "Senior's on-call day has no station work.",
    group: "succession",
  },
  {
    key: "h7_enabled",
    label: "Juniors on-call work the PM session",
    description: "Junior covers a PM station on their on-call day.",
    group: "succession",
  },
  {
    key: "h8_enabled",
    label: "Weekend coverage",
    description:
      "Sat/Sun requires 1 junior EXT, 1 senior EXT, 1 junior OC, 1 senior OC, 1 consultant per sub-spec.",
    group: "coverage",
  },
  {
    key: "weekday_oncall_coverage",
    label: "Weekday on-call coverage",
    description:
      "Require exactly 1 junior + 1 senior on-call every weekday night. Leave on unless you want weekdays uncovered.",
    group: "coverage",
  },
  {
    key: "weekend_am_pm",
    label: "Also roster AM/PM stations on weekends",
    description:
      "Off by default. Enable only if your hospital staffs weekday-style stations on weekends.",
    group: "coverage",
  },
  {
    key: "h9_enabled",
    label: "Day off in lieu after weekend EXT",
    description:
      "Weekend-EXT doctor gets the Friday-before or Monday-after off.",
    group: "utilisation",
  },
  {
    key: "h11_enabled",
    label: "Every doctor has a duty every weekday",
    description: "Soft; penalty per idle doctor-weekday.",
    group: "utilisation",
  },
];

const GROUP_META: Record<
  RuleDef["group"],
  { label: string; description: string }
> = {
  succession: {
    label: "Succession (rest & sequencing)",
    description:
      "When people can / can't work based on what they just did. These are the statutory-flavour rules — disabling any usually needs a good reason.",
  },
  coverage: {
    label: "Coverage (who must be on shift)",
    description:
      "What every day must contain at minimum. Turn off to model a leaner week.",
  },
  utilisation: {
    label: "Utilisation (lieu days & idle-time)",
    description:
      "Soft levers that shape how busy each doctor-day looks.",
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

  const grouped: Record<RuleDef["group"], RuleDef[]> = {
    succession: [],
    coverage: [],
    utilisation: [],
  };
  for (const r of RULES) grouped[r.group].push(r);

  return (
    <div className="space-y-4">
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
        <CardContent className="space-y-4">
          {(["succession", "coverage", "utilisation"] as const).map((group) => (
            <section key={group} className="space-y-1">
              <header>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {GROUP_META[group].label}
                </h3>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  {GROUP_META[group].description}
                </p>
              </header>
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
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
          ))}
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

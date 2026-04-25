/**
 * Phase B placeholder: most legacy hard-rule toggles (H4/H6/H7/H8 +
 * weekday_oncall_coverage + weekend_consultants_required) have moved
 * onto the per-`OnCallType` data model. Until the `/setup/oncall` UI
 * lands (Phase B2), this page only exposes the three master toggles
 * that survive on `ConstraintsConfig`: H5 (post-shift rest), H9 (lieu
 * day for weekend roles), H11 (idle-weekday penalty).
 *
 * Editing on-call types is currently YAML-only — load a scenario via
 * /api/state/scenarios/<id> or paste a YAML config that includes an
 * `on_call_types: [...]` block.
 */

import { Info } from "lucide-react";

import { useAutoSavePatch } from "@/api/autosave";
import { useSessionState } from "@/api/hooks";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Toggle } from "@/components/ui/toggle";

type ConstraintCfg = {
  h5_enabled: boolean;
  h9_enabled: boolean;
  h11_enabled: boolean;
};

const DEFAULTS: ConstraintCfg = {
  h5_enabled: true,
  h9_enabled: true,
  h11_enabled: true,
};

type ToggleKey = keyof ConstraintCfg;

interface RuleDef {
  key: ToggleKey;
  label: string;
  description: string;
}

const RULES: RuleDef[] = [
  {
    key: "h5_enabled",
    label: "Day off after a night on-call (master switch)",
    description:
      "When on, every on-call type's `next_day_off` flag is honoured: no AM / PM / on-call the day after. Off disables post-shift rest entirely (rare).",
  },
  {
    key: "h9_enabled",
    label: "Day in lieu after weekend extended duty",
    description:
      "Doctors holding a weekend-role on-call type (counts_as_weekend_role=True without works_full_day / works_pm_only) get a Friday-before or Monday-after day off.",
  },
  {
    key: "h11_enabled",
    label: "Every doctor has a duty every weekday",
    description:
      "Soft rule — penalises any doctor-weekday with no station, on-call, lieu, or post-call excuse.",
  },
];

export function Constraints() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const cfg: ConstraintCfg = (data?.constraints as ConstraintCfg) ?? DEFAULTS;

  const toggle = (key: ToggleKey) =>
    save({ constraints: { ...cfg, [key]: !cfg[key] } });

  return (
    <div className="space-y-4">
      <Card className="border-amber-200 bg-amber-50/40 dark:border-amber-900 dark:bg-amber-950/20">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Info className="h-4 w-4" />
            On-call rules moved to per-type configuration
          </CardTitle>
          <CardDescription className="text-xs">
            Phase B made on-call shift types user-defined. The 1-in-N cap,
            weekday on-call coverage, weekend consultant count, junior PM
            pattern, and senior full-day-off pattern all live on each
            on-call type now (frequency_cap_days, daily_required,
            works_pm_only, works_full_day). The /setup/oncall editor for
            this is part of the next ship; for now, types are configured
            via YAML import.
          </CardDescription>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Global rules</CardTitle>
          <CardDescription className="text-xs">
            Three master toggles that survive on ConstraintsConfig after
            Phase B. Everything else is per-type.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 px-3 dark:divide-slate-800 dark:border-slate-800">
            {RULES.map((rule) => (
              <li key={rule.key} className="flex items-start justify-between gap-4 py-2.5">
                <div className="min-w-0">
                  <p className="text-sm font-medium">{rule.label}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {rule.description}
                  </p>
                </div>
                <Toggle
                  checked={cfg[rule.key]}
                  onChange={() => toggle(rule.key)}
                  ariaLabel={`${cfg[rule.key] ? "Disable" : "Enable"} ${rule.label}`}
                />
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

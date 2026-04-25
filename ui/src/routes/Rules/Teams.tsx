/**
 * Combined Tiers + Stations page.
 *
 * Stations are the bulk of the density so the card is the most compact
 * of the two — one row per station, all fields on one line on wide
 * screens, wrapping on narrow ones.
 */

import { Building2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { useAutoSavePatch } from "@/api/autosave";
import {
  type StationEntry,
  useLoadSample,
  useSessionState,
} from "@/api/hooks";
import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NumberInput } from "@/components/ui/numberInput";
import { cn } from "@/lib/utils";

const TIERS = ["junior", "senior", "consultant"] as const;
const SESSIONS = ["AM", "PM"] as const;

export function Teams() {
  return (
    <div className="space-y-4">
      <TiersCard />
      <StationsCard />
    </div>
  );
}

// ---------------------------------------------------------------- Tiers

function TiersCard() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const labels = data?.tier_labels ?? {
    junior: "Junior",
    senior: "Senior",
    consultant: "Consultant",
  };
  const update = (key: keyof typeof labels, value: string) =>
    save({ tier_labels: { ...labels, [key]: value } });

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Tier labels</CardTitle>
        <CardDescription className="text-xs">
          Rename the three internal tiers to your hospital's terminology.
          Solver logic still targets <em>junior / senior / consultant</em>.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-3">
        {(["junior", "senior", "consultant"] as const).map((tier) => (
          <label key={tier} className="flex flex-col gap-1">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              {tier}
            </span>
            <Input
              className="h-9"
              value={labels[tier]}
              onChange={(e) => update(tier, e.target.value)}
            />
          </label>
        ))}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- Stations

function StationsCard() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const sample = useLoadSample({
    onSuccess: () => toast.success("Sample loaded"),
    onError: () => toast.error("Failed to load sample"),
  });
  const stations = data?.stations ?? [];

  const update = (idx: number, patch: Partial<StationEntry>) =>
    save({
      stations: stations.map((s, i) => (i === idx ? { ...s, ...patch } : s)),
    });
  const remove = (idx: number) =>
    save({ stations: stations.filter((_, i) => i !== idx) });
  const add = () =>
    save({
      stations: [
        ...stations,
        {
          name: `STATION_${stations.length + 1}`,
          sessions: ["AM", "PM"],
          required_per_session: 1,
          eligible_tiers: ["junior", "senior", "consultant"],
          is_reporting: false,
          weekday_enabled: true,
          weekend_enabled: false,
        },
      ],
    });

  if (stations.length === 0) {
    return (
      <EmptyState
        icon={Building2}
        title="No stations configured"
        description={
          <>
            Stations are the workstations / roles that doctors rotate through
            (e.g. CT, MR, US, on-call). Add the first one, or load the sample
            scenario to see a realistic set-up.
          </>
        }
        actions={
          <>
            <Button onClick={add} variant="primary">
              <Plus className="h-4 w-4" />
              Add first station
            </Button>
            <Button
              onClick={() => sample.mutate()}
              variant="secondary"
              disabled={sample.isPending}
            >
              {sample.isPending ? "Loading…" : "Load sample scenario"}
            </Button>
          </>
        }
      />
    );
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between pb-3">
        <div>
          <CardTitle className="text-base">Stations</CardTitle>
          <CardDescription className="text-xs">
            {stations.length} station{stations.length === 1 ? "" : "s"}. Click
            a chip to toggle its session or eligible tier.
          </CardDescription>
        </div>
        <Button size="sm" onClick={add} variant="secondary">
          <Plus className="h-4 w-4" />
          Add
        </Button>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {stations.map((raw, i) => {
          const s = {
            ...raw,
            sessions: raw.sessions ?? [],
            eligible_tiers: raw.eligible_tiers ?? [],
            weekday_enabled: raw.weekday_enabled ?? true,
            weekend_enabled: raw.weekend_enabled ?? false,
          };
          return (
            <StationRow
              key={i}
              station={s}
              onUpdate={(patch) => update(i, patch)}
              onRemove={() => remove(i)}
            />
          );
        })}
      </CardContent>
    </Card>
  );
}

type StationSession = NonNullable<StationEntry["sessions"]>[number];
type StationTier = NonNullable<StationEntry["eligible_tiers"]>[number];

interface NormalisedStation extends Omit<StationEntry, "sessions" | "eligible_tiers"> {
  sessions: StationSession[];
  eligible_tiers: StationTier[];
  weekday_enabled: boolean;
  weekend_enabled: boolean;
}

function StationRow({
  station,
  onUpdate,
  onRemove,
}: {
  station: NormalisedStation;
  onUpdate: (patch: Partial<StationEntry>) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-slate-200 bg-slate-50/60 px-2 py-1.5 dark:border-slate-800 dark:bg-slate-900/40">
      <Input
        value={station.name}
        onChange={(e) => onUpdate({ name: e.target.value })}
        className="h-8 w-40 flex-shrink-0 text-sm font-medium"
        aria-label="Station name"
      />

      <ChipGroup label="Sessions">
        {SESSIONS.map((sess) => {
          const isFullDay = station.sessions.includes("FULL_DAY");
          const on = station.sessions.includes(sess);
          return (
            <Chip
              key={sess}
              active={on}
              tint="emerald"
              disabled={isFullDay}
              onClick={() => {
                if (isFullDay) return;
                onUpdate({
                  sessions: on
                    ? station.sessions.filter((x) => x !== sess)
                    : ([
                        ...station.sessions,
                        sess,
                      ].sort() as StationEntry["sessions"]),
                });
              }}
            >
              {sess}
            </Chip>
          );
        })}
        <Chip
          active={station.sessions.includes("FULL_DAY")}
          tint="amber"
          onClick={() => {
            const wasFullDay = station.sessions.includes("FULL_DAY");
            onUpdate({
              sessions: wasFullDay
                ? (["AM", "PM"] as StationEntry["sessions"])
                : (["FULL_DAY"] as StationEntry["sessions"]),
            });
          }}
          title="Single all-day booking — one doctor holds the full day (e.g. surgical OR list)."
        >
          Full day
        </Chip>
      </ChipGroup>

      <ChipGroup
        label="Default tiers"
        title="Advisory hint only — when you add a doctor at this tier, the station is pre-checked on their eligibility list. Per-doctor overrides are honoured. Not a hard rule."
      >
        {TIERS.map((t) => {
          const on = station.eligible_tiers.includes(t);
          return (
            <Chip
              key={t}
              active={on}
              tint="indigo"
              onClick={() =>
                onUpdate({
                  eligible_tiers: on
                    ? station.eligible_tiers.filter((x) => x !== t)
                    : ([
                        ...station.eligible_tiers,
                        t,
                      ] as StationEntry["eligible_tiers"]),
                })
              }
            >
              {t[0].toUpperCase()}
              {t.slice(1, 3)}
            </Chip>
          );
        })}
      </ChipGroup>

      <ChipGroup label="Days">
        <Chip
          active={station.weekday_enabled}
          tint="emerald"
          onClick={() => onUpdate({ weekday_enabled: !station.weekday_enabled })}
          title="Run this station on Mon–Fri."
        >
          Wkdy
        </Chip>
        <Chip
          active={station.weekend_enabled}
          tint="emerald"
          onClick={() => onUpdate({ weekend_enabled: !station.weekend_enabled })}
          title="Run this station on Sat/Sun and public holidays."
        >
          Wknd
        </Chip>
      </ChipGroup>

      <label className="flex items-center gap-1 text-[11px] text-slate-600 dark:text-slate-400">
        <span className="hidden sm:inline">Req</span>
        <NumberInput
          min={1}
          className="h-7 w-14 text-right text-xs"
          value={station.required_per_session}
          onChange={(v) =>
            onUpdate({ required_per_session: Math.max(1, v) })
          }
          aria-label="Doctors required per session"
        />
      </label>

      <label className="flex items-center gap-1 text-[11px] text-slate-600 dark:text-slate-400">
        <input
          type="checkbox"
          checked={station.is_reporting}
          onChange={(e) => onUpdate({ is_reporting: e.target.checked })}
          className="h-3.5 w-3.5"
        />
        Reporting
      </label>

      <Button
        size="icon"
        variant="ghost"
        className="ml-auto h-7 w-7"
        aria-label={`Remove ${station.name}`}
        onClick={onRemove}
      >
        <Trash2 className="h-3.5 w-3.5 text-slate-400" />
      </Button>
    </div>
  );
}

function ChipGroup({
  label,
  children,
  title,
}: {
  label: string;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <div className="flex items-center gap-1" title={title}>
      <span className="hidden text-[10px] font-medium uppercase tracking-wide text-slate-400 sm:inline">
        {label}
      </span>
      <div className="flex flex-wrap gap-1">{children}</div>
    </div>
  );
}

function Chip({
  children,
  active,
  tint,
  onClick,
  disabled,
  title,
}: {
  children: React.ReactNode;
  active: boolean;
  tint: "emerald" | "indigo" | "amber";
  onClick: () => void;
  disabled?: boolean;
  title?: string;
}) {
  const activeClass =
    tint === "emerald"
      ? "border-emerald-300 bg-emerald-100 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
      : tint === "amber"
        ? "border-amber-300 bg-amber-100 text-amber-800 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-300"
        : "border-indigo-300 bg-indigo-100 text-indigo-800 dark:border-indigo-700 dark:bg-indigo-950 dark:text-indigo-300";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        "rounded-md border px-1.5 py-0.5 text-[11px] font-medium transition-colors",
        active
          ? activeClass
          : "border-slate-200 text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800",
        disabled && "cursor-not-allowed opacity-40 hover:bg-transparent",
      )}
    >
      {children}
    </button>
  );
}

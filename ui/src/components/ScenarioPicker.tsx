/**
 * Category-grouped scenario picker.
 *
 * Reused by the Setup > Templates page and anywhere else that wants
 * to render the full 17-scenario library with category headers and a
 * build-time-difficulty pill on each card. Fetches `/api/state/scenarios`
 * itself so callers just render the component.
 */

import {
  Beaker,
  Building2,
  Flame,
  Gauge,
  Rocket,
  Sparkles,
  Stethoscope,
} from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import {
  type ScenarioCategory,
  type ScenarioDifficulty,
  type ScenarioSummary,
  useLoadScenario,
  useScenarios,
} from "@/api/hooks";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

const CATEGORY_ORDER: ScenarioCategory[] = [
  "quickstart",
  "specialty",
  "realistic",
  "research",
];

const CATEGORY_META: Record<
  ScenarioCategory,
  {
    label: string;
    description: string;
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  quickstart: {
    label: "Quickstart",
    description:
      "Small teams that solve in seconds. Best for a first look.",
    icon: Rocket,
  },
  specialty: {
    label: "By specialty",
    description:
      "Department-shaped templates with realistic stations, rules, and shift patterns.",
    icon: Stethoscope,
  },
  realistic: {
    label: "Real-world sized",
    description:
      "Mid-to-large teams with leave, public holidays, and part-timers.",
    icon: Building2,
  },
  research: {
    label: "Research & benchmarks",
    description:
      "Reproducible reference shapes + stress tests that probe solver limits.",
    icon: Beaker,
  },
};

const DIFFICULTY_META: Record<
  ScenarioDifficulty,
  {
    label: string;
    tint: string;
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  easy: {
    label: "Solves fast",
    tint:
      "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
    icon: Gauge,
  },
  hard: {
    label: "Long solve",
    tint:
      "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300",
    icon: Gauge,
  },
  stress: {
    label: "Stress test",
    tint:
      "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-300",
    icon: Flame,
  },
};

interface ScenarioPickerProps {
  /** Called after a scenario successfully loads. Use to navigate away
   *  from the picker (e.g. to /setup/doctors) once the user has chosen.
   */
  onLoaded?: (id: string) => void;
  /** Limit the rendering to specific categories. Default shows all. */
  categories?: ScenarioCategory[];
  /** Set to `false` on a secondary surface to drop the top heading. */
  showHeader?: boolean;
}

export function ScenarioPicker({
  onLoaded,
  categories,
  showHeader = true,
}: ScenarioPickerProps) {
  const scenarios = useScenarios();
  const loadScenario = useLoadScenario({
    onSuccess: (_data, id) => {
      toast.success(`Loaded ${id.replaceAll("_", " ")}`);
      onLoaded?.(id);
    },
    onError: (e) =>
      toast.error(
        e instanceof ApiError ? e.message : "Failed to load scenario",
      ),
  });

  const items = scenarios.data ?? [];
  const pendingId = loadScenario.isPending
    ? (loadScenario.variables as string | undefined) ?? null
    : null;
  const visibleCategories = categories ?? CATEGORY_ORDER;

  return (
    <div className="space-y-6">
      {showHeader && (
        <header className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <h2 className="text-sm font-semibold tracking-tight">Templates</h2>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Grouped by use case. Click a card to load.
          </span>
        </header>
      )}
      {scenarios.isLoading ? (
        <p className="text-xs text-slate-500 dark:text-slate-400">Loading…</p>
      ) : (
        <ScenarioGroups
          scenarios={items}
          pendingId={pendingId}
          onLoad={(id) => loadScenario.mutate(id)}
          categories={visibleCategories}
        />
      )}
    </div>
  );
}

function ScenarioGroups({
  scenarios,
  pendingId,
  onLoad,
  categories,
}: {
  scenarios: ScenarioSummary[];
  pendingId: string | null;
  onLoad: (id: string) => void;
  categories: ScenarioCategory[];
}) {
  const grouped: Record<ScenarioCategory, ScenarioSummary[]> = {
    quickstart: [],
    specialty: [],
    realistic: [],
    research: [],
  };
  const ungrouped: ScenarioSummary[] = [];
  for (const s of scenarios) {
    const cat = s.category;
    if (cat && cat in grouped) grouped[cat].push(s);
    else ungrouped.push(s);
  }

  return (
    <div className="space-y-6">
      {categories.map((cat) => {
        const items = grouped[cat];
        if (items.length === 0) return null;
        const meta = CATEGORY_META[cat];
        const Icon = meta.icon;
        return (
          <div key={cat} className="space-y-2">
            <div className="flex items-baseline gap-2">
              <Icon className="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-300" />
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
                {meta.label}
              </h3>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">
                {meta.description}
              </span>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              {items.map((s, idx) => (
                <ScenarioCard
                  key={s.id}
                  s={s}
                  featured={cat === "quickstart" && idx === 0}
                  pending={pendingId === s.id}
                  onLoad={() => onLoad(s.id)}
                />
              ))}
            </div>
          </div>
        );
      })}
      {ungrouped.length > 0 && (
        <div className="grid gap-3 md:grid-cols-3">
          {ungrouped.map((s) => (
            <ScenarioCard
              key={s.id}
              s={s}
              pending={pendingId === s.id}
              onLoad={() => onLoad(s.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ScenarioCard({
  s,
  featured,
  pending,
  onLoad,
}: {
  s: ScenarioSummary;
  featured?: boolean;
  pending: boolean;
  onLoad: () => void;
}) {
  const diff = s.difficulty ? DIFFICULTY_META[s.difficulty] : null;
  const DiffIcon = diff?.icon;
  return (
    <Card
      className={cn(
        "flex flex-col",
        featured &&
          "border-indigo-300 bg-indigo-50/40 dark:border-indigo-900 dark:bg-indigo-950/20",
      )}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm leading-snug">{s.title}</CardTitle>
          <div className="flex flex-shrink-0 items-center gap-1">
            {diff && DiffIcon && (
              <span
                title={
                  s.solve_status && s.solve_time_s != null
                    ? `${s.solve_status} · ${s.solve_time_s}s at build time`
                    : diff.label
                }
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
                  diff.tint,
                )}
              >
                <DiffIcon className="h-3 w-3" />
                {diff.label}
              </span>
            )}
            {featured && (
              <Sparkles className="h-3.5 w-3.5 text-indigo-500 dark:text-indigo-300" />
            )}
          </div>
        </div>
        <CardDescription className="text-xs">{s.description}</CardDescription>
      </CardHeader>
      <CardContent className="mt-auto space-y-3">
        <ul className="flex flex-wrap gap-1">
          {(s.tags ?? s.highlights).slice(0, 4).map((h) => (
            <li
              key={h}
              className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600 dark:bg-slate-800 dark:text-slate-300"
            >
              {h}
            </li>
          ))}
        </ul>
        <Button
          onClick={onLoad}
          disabled={pending}
          variant={featured ? "primary" : "secondary"}
          size="sm"
          className="w-full"
        >
          {pending ? "Loading…" : "Load scenario"}
        </Button>
      </CardContent>
    </Card>
  );
}

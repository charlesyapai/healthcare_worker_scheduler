import { format } from "date-fns";
import {
  ArrowRight,
  Beaker,
  Building2,
  Check,
  ChevronDown,
  Circle,
  Download,
  FileDown,
  FileUp,
  Flame,
  Gauge,
  LayoutDashboard,
  PlayCircle,
  Rocket,
  Sliders,
  Sparkles,
  Stethoscope,
} from "lucide-react";
import { useRef } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import {
  type ScenarioCategory,
  type ScenarioDifficulty,
  type ScenarioSummary,
  useHealth,
  useLoadScenario,
  useScenarios,
  useSessionState,
  useYamlExport,
  useYamlImport,
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
import { useSolveStore } from "@/store/solve";
import { useUIStore } from "@/store/ui";

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
      "Department-shaped templates with subspecialty-aware stations and rules.",
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
  { label: string; tint: string; icon: React.ComponentType<{ className?: string }> }
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

export function Dashboard() {
  const health = useHealth();
  const state = useSessionState();
  const solve = useSolveStore();
  const scenarios = useScenarios();
  const loadScenario = useLoadScenario({
    onSuccess: (_, id) => toast.success(`Loaded ${id.replaceAll("_", " ")}`),
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : "Failed to load scenario"),
  });
  const exporter = useYamlExport();
  const importer = useYamlImport();
  const fileRef = useRef<HTMLInputElement>(null);
  const gsOpen = useUIStore((s) => s.gettingStartedOpen);
  const toggleGs = useUIStore((s) => s.toggleGettingStarted);

  const saveYaml = async () => {
    try {
      const { yaml } = await exporter.mutateAsync();
      const blob = new Blob([yaml], { type: "application/x-yaml" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `roster_config_${new Date().toISOString().slice(0, 10)}.yaml`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
      toast.success("Config downloaded");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to save config");
    }
  };

  const loadYamlFromFile = async (file: File) => {
    try {
      const text = await file.text();
      await importer.mutateAsync(text);
      toast.success(`Loaded ${file.name}`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to load YAML");
    }
  };

  const doctors = state.data?.doctors ?? [];
  const stations = state.data?.stations ?? [];
  const horizon = state.data?.horizon;
  const hasConfig = doctors.length > 0 && stations.length > 0;
  const startDate = horizon?.start_date ?? null;
  const nDays = horizon?.n_days ?? 0;
  const hasResult = !!solve.result;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          Start with a template
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {hasConfig ? (
            <>
              Current config: <strong>{doctors.length}</strong> people,{" "}
              <strong>{stations.length}</strong> stations,{" "}
              <strong>{nDays}</strong>-day horizon
              {startDate
                ? ` starting ${format(new Date(startDate), "d MMM yyyy")}`
                : ""}
              .{" "}
              <Link
                to="/setup"
                className="text-indigo-600 underline decoration-dotted underline-offset-2 dark:text-indigo-300"
              >
                Review in Setup →
              </Link>
            </>
          ) : (
            <>Pick a ready-made scenario, drop a YAML, or skip to Setup.</>
          )}
        </p>
      </header>

      <section className="space-y-6">
        <header className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <h2 className="text-sm font-semibold tracking-tight">Templates</h2>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Grouped by use case. Click a card to load.
          </span>
        </header>
        {scenarios.isLoading ? (
          <p className="text-xs text-slate-500 dark:text-slate-400">Loading…</p>
        ) : (
          <ScenarioGroups
            scenarios={scenarios.data ?? []}
            pendingId={
              loadScenario.isPending
                ? (loadScenario.variables as string | undefined) ?? null
                : null
            }
            onLoad={(id) => loadScenario.mutate(id)}
          />
        )}
      </section>

      <section className="grid gap-3 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Load a YAML</CardTitle>
            <CardDescription className="text-xs">
              Drop a config you exported earlier to resume editing.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div
              className="flex flex-col items-center gap-2 rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 p-4 text-center text-xs transition-colors hover:border-indigo-400 hover:bg-indigo-50/60 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-indigo-700 dark:hover:bg-indigo-950/40"
              onDragOver={(e) => {
                e.preventDefault();
                e.currentTarget.classList.add("border-indigo-500");
              }}
              onDragLeave={(e) =>
                e.currentTarget.classList.remove("border-indigo-500")
              }
              onDrop={(e) => {
                e.preventDefault();
                e.currentTarget.classList.remove("border-indigo-500");
                const f = e.dataTransfer.files?.[0];
                if (f) loadYamlFromFile(f);
              }}
            >
              <FileUp className="h-6 w-6 text-slate-400" />
              <div>
                <p className="font-medium">Drop YAML here</p>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  or use the button below
                </p>
              </div>
              <input
                ref={fileRef}
                type="file"
                accept=".yaml,.yml,text/yaml,application/x-yaml"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) loadYamlFromFile(f);
                  e.target.value = "";
                }}
              />
            </div>
            <div className="mt-2 flex gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => fileRef.current?.click()}
              >
                <FileUp className="h-4 w-4" />
                Load YAML
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={saveYaml}
                disabled={!hasConfig}
              >
                <FileDown className="h-4 w-4" />
                Save current
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Next step</CardTitle>
            <CardDescription className="text-xs">
              Where you are in the flow.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-xs">
            {hasConfig ? (
              hasResult ? (
                <NextAction
                  to="/roster"
                  icon={Download}
                  primary="Open the roster"
                  secondary={`Solver finished: ${solve.result?.status}. Review + export.`}
                />
              ) : (
                <NextAction
                  to="/solve"
                  icon={PlayCircle}
                  primary="Run the solver"
                  secondary="Config is loaded. Press Solve to generate a roster."
                />
              )
            ) : (
              <NextAction
                to="/setup"
                icon={LayoutDashboard}
                primary="Go to Setup"
                secondary="Or load a scenario above — that's the fast path."
              />
            )}
            <button
              type="button"
              onClick={toggleGs}
              className="inline-flex items-center gap-1 text-[11px] text-slate-500 underline decoration-dotted underline-offset-2 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              aria-expanded={gsOpen}
            >
              <ChevronDown
                className={cn(
                  "h-3.5 w-3.5 transition-transform",
                  gsOpen && "rotate-180",
                )}
              />
              {gsOpen ? "Hide" : "Show"} the full 4-step guide
            </button>
          </CardContent>
        </Card>
      </section>

      {gsOpen && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Full guide</CardTitle>
            <CardDescription className="text-xs">
              Reference for each step. Skip at will — nothing here blocks.
            </CardDescription>
          </CardHeader>
          <CardContent className="divide-y divide-slate-200 dark:divide-slate-800">
            <Step
              n={1}
              done={hasConfig}
              active={!hasConfig}
              title="Load or build a configuration"
              body={
                hasConfig ? (
                  <span>
                    {doctors.length} people, {stations.length} stations,{" "}
                    {nDays}-day horizon
                    {startDate
                      ? ` starting ${format(new Date(startDate), "d MMM yyyy")}`
                      : ""}
                    .
                  </span>
                ) : (
                  <span>
                    Pick a scenario above, drop a YAML, or build from scratch in{" "}
                    <Link
                      to="/setup"
                      className="text-indigo-600 underline dark:text-indigo-300"
                    >
                      Setup
                    </Link>
                    .
                  </span>
                )
              }
              action={
                hasConfig && (
                  <Link
                    to="/setup"
                    className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-300"
                  >
                    <LayoutDashboard className="h-3.5 w-3.5" />
                    Review
                  </Link>
                )
              }
            />
            <Step
              n={2}
              done={hasConfig}
              dim={!hasConfig}
              active={hasConfig && !hasResult}
              title="Review rules (optional)"
              body={
                <span>
                  Tweak constraints, fairness weights, or shift hours in{" "}
                  <Link
                    to="/rules"
                    className="text-indigo-600 underline dark:text-indigo-300"
                  >
                    Rules
                  </Link>
                  . Safe to skip.
                </span>
              }
              action={
                hasConfig && (
                  <Link
                    to="/rules"
                    className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-300"
                  >
                    <Sliders className="h-3.5 w-3.5" />
                    Open
                  </Link>
                )
              }
            />
            <Step
              n={3}
              done={hasResult}
              dim={!hasConfig}
              active={hasConfig && !hasResult}
              title="Run the solver"
              body={
                hasResult ? (
                  <span>
                    {solve.result?.status} — snapshots available on the roster
                    page.
                  </span>
                ) : hasConfig ? (
                  <span>
                    Head to{" "}
                    <Link
                      to="/solve"
                      className="text-indigo-600 underline dark:text-indigo-300"
                    >
                      Solve
                    </Link>{" "}
                    and press Solve.
                  </span>
                ) : (
                  <span>Available once step 1 is done.</span>
                )
              }
              action={
                hasConfig &&
                !hasResult && (
                  <Link
                    to="/solve"
                    className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-300"
                  >
                    <PlayCircle className="h-3.5 w-3.5" />
                    Go to Solve <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                )
              }
            />
            <Step
              n={4}
              done={false}
              dim={!hasResult}
              active={hasResult}
              title="Review & publish"
              body={
                hasResult ? (
                  <span>
                    Open{" "}
                    <Link
                      to="/roster"
                      className="text-indigo-600 underline dark:text-indigo-300"
                    >
                      Roster
                    </Link>{" "}
                    to review, then{" "}
                    <Link
                      to="/export"
                      className="text-indigo-600 underline dark:text-indigo-300"
                    >
                      Export
                    </Link>
                    .
                  </span>
                ) : (
                  <span>Available once a solve finishes.</span>
                )
              }
              action={
                hasResult && (
                  <Link
                    to="/roster"
                    className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-300"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Review
                  </Link>
                )
              }
            />
          </CardContent>
        </Card>
      )}

      <p className="text-center text-xs text-slate-400 dark:text-slate-600">
        Backend{" "}
        {health.data ? `ok · ${health.data.scheduler_version}` : "checking…"}
      </p>
    </div>
  );
}

function NextAction({
  to,
  icon: Icon,
  primary,
  secondary,
}: {
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  primary: string;
  secondary: string;
}) {
  return (
    <Link
      to={to}
      className="flex items-start gap-2 rounded-md border border-indigo-200 bg-indigo-50 p-2.5 hover:border-indigo-400 hover:bg-indigo-100 dark:border-indigo-900 dark:bg-indigo-950/40 dark:hover:border-indigo-700 dark:hover:bg-indigo-950"
    >
      <Icon className="mt-0.5 h-4 w-4 flex-shrink-0 text-indigo-600 dark:text-indigo-300" />
      <span className="flex-1">
        <span className="block text-xs font-semibold text-indigo-700 dark:text-indigo-200">
          {primary}
        </span>
        <span className="block text-[11px] text-indigo-600/80 dark:text-indigo-300/70">
          {secondary}
        </span>
      </span>
      <ArrowRight className="mt-1 h-3.5 w-3.5 flex-shrink-0 text-indigo-500 dark:text-indigo-300" />
    </Link>
  );
}

function ScenarioGroups({
  scenarios,
  pendingId,
  onLoad,
}: {
  scenarios: ScenarioSummary[];
  pendingId: string | null;
  onLoad: (id: string) => void;
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
      {CATEGORY_ORDER.map((cat) => {
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

function Step({
  n,
  done,
  active,
  dim,
  title,
  body,
  action,
}: {
  n: number;
  done: boolean;
  active?: boolean;
  dim?: boolean;
  title: string;
  body: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-[auto_1fr_auto] items-start gap-3 py-3 first:pt-0 last:pb-0",
        dim && !done && "opacity-50",
      )}
    >
      <div
        className={cn(
          "mt-0.5 flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold",
          done
            ? "bg-emerald-500 text-white"
            : active
              ? "bg-indigo-600 text-white"
              : "border border-slate-300 bg-white text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400",
        )}
      >
        {done ? <Check className="h-3.5 w-3.5" /> : active ? n : <Circle className="h-2 w-2" />}
      </div>
      <div>
        <p className="text-sm font-medium">
          {title}
          {active && !done && (
            <span className="ml-2 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
              next
            </span>
          )}
        </p>
        <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">{body}</p>
      </div>
      <div className="whitespace-nowrap">{action}</div>
    </div>
  );
}

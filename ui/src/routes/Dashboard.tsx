import { format } from "date-fns";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Circle,
  Download,
  FileDown,
  FileUp,
  FlaskConical,
  LayoutDashboard,
  PlayCircle,
  Sliders,
  Sparkles,
} from "lucide-react";
import { useRef } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import {
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
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Build a roster in four steps. Pick a scenario below to see the flow
          end-to-end in minutes.
        </p>
      </header>

      <Card>
        <button
          type="button"
          onClick={toggleGs}
          className="flex w-full items-center justify-between px-6 py-4 text-left hover:bg-slate-50 dark:hover:bg-slate-900/50"
          aria-expanded={gsOpen}
        >
          <div>
            <CardTitle>Getting started</CardTitle>
            <CardDescription>
              {gsOpen
                ? "Follow the steps in order. This panel updates as you go."
                : hasConfig
                  ? hasResult
                    ? "All four steps complete — expand to jump back in."
                    : "Step 3 next: run the solver."
                  : "Step 1 next: load a scenario or your YAML."}
            </CardDescription>
          </div>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-slate-400 transition-transform",
              gsOpen && "rotate-180",
            )}
          />
        </button>
        {gsOpen && (
          <CardContent className="divide-y divide-slate-200 dark:divide-slate-800">
            <Step
              n={1}
              done={hasConfig}
              active={!hasConfig}
              title="Load or build a configuration"
              body={
                hasConfig ? (
                  <span>
                    {doctors.length} doctors, {stations.length} stations, {nDays}-day horizon
                    {startDate ? ` starting ${format(new Date(startDate), "d MMM yyyy")}` : ""}.
                  </span>
                ) : (
                  <span>
                    Pick a scenario below, drop a YAML, or start from scratch in{" "}
                    <Link to="/setup" className="text-indigo-600 underline dark:text-indigo-300">Setup</Link>.
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
                  Tweak constraint toggles, fairness weights, or shift hours in{" "}
                  <Link to="/rules" className="text-indigo-600 underline dark:text-indigo-300">Rules</Link>.
                  Safe to skip.
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
                  <span>{solve.result?.status} — snapshots available on the roster page.</span>
                ) : hasConfig ? (
                  <span>
                    Head to <Link to="/solve" className="text-indigo-600 underline dark:text-indigo-300">Solve</Link> and press Solve.
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
                    Open <Link to="/roster" className="text-indigo-600 underline dark:text-indigo-300">Roster</Link> to
                    review, then <Link to="/export" className="text-indigo-600 underline dark:text-indigo-300">Export</Link>.
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
        )}
      </Card>

      <section>
        <div className="mb-2 flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <h2 className="text-sm font-semibold tracking-tight">Pre-built scenarios</h2>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Known-feasible starting points — click to load.
          </span>
        </div>
        {scenarios.isLoading ? (
          <p className="text-xs text-slate-500 dark:text-slate-400">Loading…</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-3">
            {(scenarios.data ?? []).map((s, idx) => (
              <ScenarioCard
                key={s.id}
                s={s}
                featured={idx === 0}
                pending={loadScenario.isPending && loadScenario.variables === s.id}
                onLoad={() => loadScenario.mutate(s.id)}
              />
            ))}
          </div>
        )}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Save or reload your configuration</CardTitle>
          <CardDescription>
            YAML captures doctors, stations, rules, hours, weights — everything
            editable in the app. Good for recurring rosters with small tweaks.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div
            className="flex flex-col items-center gap-3 rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 p-6 text-center transition-colors hover:border-indigo-400 hover:bg-indigo-50/60 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-indigo-700 dark:hover:bg-indigo-950/40"
            onDragOver={(e) => {
              e.preventDefault();
              e.currentTarget.classList.add("border-indigo-500");
            }}
            onDragLeave={(e) => e.currentTarget.classList.remove("border-indigo-500")}
            onDrop={(e) => {
              e.preventDefault();
              e.currentTarget.classList.remove("border-indigo-500");
              const f = e.dataTransfer.files?.[0];
              if (f) loadYamlFromFile(f);
            }}
          >
            <FileUp className="h-8 w-8 text-slate-400" />
            <div className="text-sm">
              <p className="font-medium">Drop a YAML config here</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                or use the buttons below
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
          <div className="mt-3 flex flex-wrap gap-2">
            <Button onClick={() => fileRef.current?.click()} variant="secondary">
              <FileUp className="h-4 w-4" />
              Load YAML
            </Button>
            <Button onClick={saveYaml} variant="secondary" disabled={!hasConfig}>
              <FileDown className="h-4 w-4" />
              Save current config
            </Button>
          </div>
        </CardContent>
      </Card>

      <p className="text-center text-xs text-slate-400 dark:text-slate-600">
        Backend {health.data ? `ok · ${health.data.scheduler_version}` : "checking…"}
      </p>
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
          {featured && (
            <Sparkles className="h-3.5 w-3.5 flex-shrink-0 text-indigo-500 dark:text-indigo-300" />
          )}
        </div>
        <CardDescription className="text-xs">{s.description}</CardDescription>
      </CardHeader>
      <CardContent className="mt-auto space-y-3">
        <ul className="flex flex-wrap gap-1">
          {s.highlights.slice(0, 4).map((h) => (
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

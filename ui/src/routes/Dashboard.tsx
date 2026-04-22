import { format } from "date-fns";
import {
  ArrowRight,
  Check,
  Circle,
  Download,
  FileDown,
  FileUp,
  FlaskConical,
  LayoutDashboard,
  PlayCircle,
  Sliders,
} from "lucide-react";
import { useRef } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import {
  useHealth,
  useLoadSample,
  useSeedDefaults,
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

export function Dashboard() {
  const health = useHealth();
  const state = useSessionState();
  const solve = useSolveStore();
  const seed = useSeedDefaults({
    onSuccess: () => toast.success("Loaded default 20-doctor roster"),
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : "Failed to seed defaults"),
  });
  const sample = useLoadSample({
    onSuccess: () =>
      toast.success("Loaded sample — head to Solve to try it out"),
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : "Failed to load sample"),
  });
  const exporter = useYamlExport();
  const importer = useYamlImport();
  const fileRef = useRef<HTMLInputElement>(null);

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
          Build a monthly on-call roster in four steps. Takes about 5 minutes
          with the sample scenario.
        </p>
      </header>

      <Steps
        step1Done={hasConfig}
        step1Counts={{ doctors: doctors.length, stations: stations.length, days: nDays, startDate }}
        step2Done={hasResult}
        step2Status={solve.status === "running" ? "running" : hasResult ? solve.result?.status ?? "done" : null}
        step3Done={hasResult}
      />

      <Card className="border-indigo-300 bg-indigo-50/50 dark:border-indigo-900 dark:bg-indigo-950/30">
        <CardHeader>
          <div className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5 text-indigo-600 dark:text-indigo-300" />
            <CardTitle>Try it out — pre-built scenario</CardTitle>
          </div>
          <CardDescription>
            A curated scenario that's known to solve, so you can see the full
            flow end-to-end before entering your own data.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
            <div className="space-y-3 text-sm">
              <div>
                <p className="font-medium">Small radiology department · 1 week</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Solves to OPTIMAL in about 7 seconds on the default solver
                  settings. A good sanity check if your own config comes back
                  infeasible.
                </p>
              </div>
              <ul className="grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-slate-600 sm:grid-cols-2 dark:text-slate-300">
                <li>
                  <strong>15 doctors</strong>: 5 juniors, 4 seniors, 6 consultants (2 per sub-spec)
                </li>
                <li>
                  <strong>Sub-specs</strong>: Neuro, Body, MSK
                </li>
                <li>
                  <strong>8 stations</strong>: CT, MR, US (×2), XR_REPORT (×2), IR, FLUORO, GEN_AM, GEN_PM
                </li>
                <li>
                  <strong>Horizon</strong>: 7 days starting this Monday
                </li>
                <li>
                  <strong>All default rules on</strong>: 1-in-3 on-call, post-call off, weekend coverage, lieu day, mandatory weekday
                </li>
                <li>
                  <strong>No leave, no overrides</strong> — a clean slate to play with
                </li>
              </ul>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                After loading, head to <strong className="text-slate-700 dark:text-slate-200">Solve</strong> and press the Solve button, then{" "}
                <strong className="text-slate-700 dark:text-slate-200">Roster</strong> to review the result.
              </p>
            </div>
            <div className="flex flex-col gap-2 sm:items-end">
              <Button
                onClick={() => sample.mutate()}
                disabled={sample.isPending}
                variant="primary"
                size="lg"
              >
                <PlayCircle className="h-4 w-4" />
                {sample.isPending ? "Loading…" : "Load this scenario"}
              </Button>
              <Button
                onClick={() => seed.mutate()}
                disabled={seed.isPending}
                variant="ghost"
                size="sm"
              >
                {seed.isPending ? "Loading…" : "Or: 20-doctor randomised"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Save or reload your configuration</CardTitle>
          <CardDescription>
            A YAML file captures doctors, stations, rules, hours, fairness
            weights, and every other setting. Reload it to pick up where you
            left off — great for recurring rosters with small tweaks.
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

function Steps({
  step1Done,
  step1Counts,
  step2Done,
  step2Status,
  step3Done,
}: {
  step1Done: boolean;
  step1Counts: {
    doctors: number;
    stations: number;
    days: number;
    startDate: string | null;
  };
  step2Done: boolean;
  step2Status: string | null;
  step3Done: boolean;
}) {
  // Step 1: config present
  // Step 2: review setup + rules (active once step 1 done, never blocked)
  // Step 3: solve finished
  // Step 4: export (active once step 3 done)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Getting started</CardTitle>
        <CardDescription>Follow the steps in order. This panel updates as you go.</CardDescription>
      </CardHeader>
      <CardContent className="divide-y divide-slate-200 dark:divide-slate-800">
        <Step
          n={1}
          done={step1Done}
          active={!step1Done}
          title="Load or build a configuration"
          body={
            step1Done ? (
              <span>
                {step1Counts.doctors} doctors, {step1Counts.stations} stations,{" "}
                {step1Counts.days}-day horizon
                {step1Counts.startDate
                  ? ` starting ${format(new Date(step1Counts.startDate), "d MMM yyyy")}`
                  : ""}
                .
              </span>
            ) : (
              <span>
                Use <strong>Load this scenario</strong> below, drop a YAML,
                or start from scratch in <Link to="/setup" className="text-indigo-600 underline dark:text-indigo-300">Setup</Link>.
              </span>
            )
          }
          action={
            step1Done && (
              <Link
                to="/setup"
                className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-300"
              >
                <LayoutDashboard className="h-3.5 w-3.5" />
                Review setup
              </Link>
            )
          }
        />
        <Step
          n={2}
          done={step1Done /* implicit review once config exists */ && true}
          dim={!step1Done}
          active={step1Done && !step2Done}
          title="Review rules (optional)"
          body={
            <span>
              Tweak constraint toggles, fairness weights, or shift hours in{" "}
              <Link to="/rules" className="text-indigo-600 underline dark:text-indigo-300">Rules</Link>.
              Safe to skip if you're just trying the scenario.
            </span>
          }
          action={
            step1Done && (
              <Link
                to="/rules"
                className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-300"
              >
                <Sliders className="h-3.5 w-3.5" />
                Open rules
              </Link>
            )
          }
        />
        <Step
          n={3}
          done={step2Done}
          dim={!step1Done}
          active={step1Done && !step2Done}
          title="Run the solver"
          body={
            step2Done ? (
              <span>
                {step2Status}
                {" — "}snapshots available on the roster page.
              </span>
            ) : step1Done ? (
              <span>
                Head to <Link to="/solve" className="text-indigo-600 underline dark:text-indigo-300">Solve</Link> and press Solve. Expect a few seconds of live updates, then a verdict banner.
              </span>
            ) : (
              <span>Available once you have doctors and stations.</span>
            )
          }
          action={
            step1Done &&
            !step2Done && (
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
          dim={!step3Done}
          active={step3Done}
          title="Review & publish"
          body={
            step3Done ? (
              <span>
                Open <Link to="/roster" className="text-indigo-600 underline dark:text-indigo-300">Roster</Link> to
                eyeball the grid, lock cells, or re-solve. Then <Link to="/export" className="text-indigo-600 underline dark:text-indigo-300">Export</Link> as JSON / CSV / ICS / PDF.
              </span>
            ) : (
              <span>Available once a solve finishes.</span>
            )
          }
          action={
            step3Done && (
              <Link
                to="/roster"
                className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-300"
              >
                <Download className="h-3.5 w-3.5" />
                Open roster
              </Link>
            )
          }
        />
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

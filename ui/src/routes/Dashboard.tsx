import { format } from "date-fns";
import { FileDown, FileUp, FlaskConical, PlayCircle } from "lucide-react";
import { useRef } from "react";
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

export function Dashboard() {
  const health = useHealth();
  const state = useSessionState();
  const seed = useSeedDefaults({
    onSuccess: () => toast.success("Loaded default 20-doctor roster"),
    onError: (e) =>
      toast.error(e instanceof ApiError ? e.message : "Failed to seed defaults"),
  });
  const sample = useLoadSample({
    onSuccess: () =>
      toast.success("Loaded sample — head to Solve, it's known-feasible"),
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
  const hasConfig = doctors.length > 0;
  const startDate = horizon?.start_date ?? null;
  const nDays = horizon?.n_days ?? 0;
  const publicHolidays = horizon?.public_holidays ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Overview of the current roster-in-progress.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Configuration</CardTitle>
            <CardDescription>
              {hasConfig
                ? `${doctors.length} doctors, ${stations.length} stations.`
                : "No configuration yet — load a YAML or start with defaults."}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            <Stat label="Horizon">
              {nDays > 0 && startDate
                ? `${nDays} days from ${format(new Date(startDate), "d MMM yyyy")}`
                : nDays > 0
                  ? `${nDays} days (start date not set)`
                  : "—"}
            </Stat>
            <Stat label="Tier mix">{tierSummary(doctors)}</Stat>
            <Stat label="Public holidays">{publicHolidays.length}</Stat>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Backend</CardTitle>
            <CardDescription>FastAPI runtime status.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            <Stat label="API">
              {health.isLoading
                ? "checking…"
                : health.data
                  ? `ok · phase ${health.data.phase}`
                  : "unreachable"}
            </Stat>
            <Stat label="Solver build">
              {health.data?.scheduler_version ?? "—"}
            </Stat>
          </CardContent>
        </Card>
      </div>

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
    </div>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-100 py-1 last:border-0 dark:border-slate-800">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <span className="font-medium">{children}</span>
    </div>
  );
}

function tierSummary(
  doctors: Array<{ tier: "junior" | "senior" | "consultant" }>,
): string {
  if (doctors.length === 0) return "—";
  const counts = { junior: 0, senior: 0, consultant: 0 };
  for (const d of doctors) counts[d.tier]++;
  return `J ${counts.junior} · S ${counts.senior} · C ${counts.consultant}`;
}

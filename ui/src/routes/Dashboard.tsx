import { format } from "date-fns";
import { FileDown, FileUp } from "lucide-react";
import { useRef } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import {
  useHealth,
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
            <Button
              onClick={() => seed.mutate()}
              disabled={seed.isPending}
              variant="primary"
            >
              {seed.isPending ? "Loading…" : "Start with defaults"}
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

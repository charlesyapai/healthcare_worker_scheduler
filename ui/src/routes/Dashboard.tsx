import { format } from "date-fns";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useHealth, useSeedDefaults, useSessionState } from "@/api/hooks";
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
          <CardTitle>Get started</CardTitle>
          <CardDescription>
            Seed the session with a 20-doctor, 21-day sample, or go straight to
            Setup to build one from scratch.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() => seed.mutate()}
              disabled={seed.isPending}
              variant="primary"
            >
              {seed.isPending ? "Loading…" : "Start with defaults"}
            </Button>
            <Button variant="secondary" disabled>
              Load YAML (Phase 3)
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

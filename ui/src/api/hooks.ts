/**
 * TanStack Query hooks for the v2 backend. Kept thin — each hook maps to
 * exactly one endpoint from `api/routes/*`.
 */

import {
  type UseMutationOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch, queryKeys } from "./client";
import type { components, paths } from "./types";

export type SessionState =
  paths["/api/state"]["get"]["responses"]["200"]["content"]["application/json"];
export type DoctorEntry = components["schemas"]["DoctorEntry"];
export type StationEntry = components["schemas"]["StationEntry"];
export type BlockEntry = components["schemas"]["BlockEntry"];
export type OverrideEntry = components["schemas"]["OverrideEntry"];
export type RolePreferenceEntry = components["schemas"]["RolePreferenceEntry"];
export type ShiftLabels = components["schemas"]["ShiftLabels"];
export type HealthResponse = { status: string; phase: number; scheduler_version: string };

/** Default copy for shift labels. Used in two places: the UI's label
 *  editor needs a fallback when a freshly-seeded session hasn't yet
 *  received a `shift_labels` block from the server, and formatters
 *  throughout the app fall back to these defaults when they render
 *  a role token and the server payload is missing a label. */
export const DEFAULT_SHIFT_LABELS: ShiftLabels = {
  am: "AM",
  pm: "PM",
  full_day: "Full day",
  oncall: "Night call",
  weekend_ext: "Weekend extended",
  weekend_consult: "Weekend consultant",
};

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => apiFetch<HealthResponse>("/api/health"),
    staleTime: 30_000,
  });
}

export function useSessionState() {
  return useQuery({
    queryKey: queryKeys.sessionState,
    queryFn: () => apiFetch<SessionState>("/api/state"),
    staleTime: 5_000,
  });
}

export function useSeedDefaults(
  options?: UseMutationOptions<SessionState, Error, void>,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<SessionState>("/api/state/seed", { method: "POST" }),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.sessionState, data);
    },
    ...options,
  });
}

export function useLoadSample(
  options?: UseMutationOptions<SessionState, Error, void>,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<SessionState>("/api/state/sample", { method: "POST" }),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.sessionState, data);
    },
    ...options,
  });
}

export type ScenarioCategory =
  | "quickstart"
  | "specialty"
  | "realistic"
  | "research";

export type ScenarioDifficulty = "easy" | "hard" | "stress";

export interface ScenarioSummary {
  id: string;
  title: string;
  description: string;
  n_doctors: number;
  n_stations: number;
  n_days: number;
  highlights: string[];
  category?: ScenarioCategory;
  tags?: string[];
  solve_status?: string;
  solve_time_s?: number;
  difficulty?: ScenarioDifficulty;
}

export function useScenarios() {
  return useQuery({
    queryKey: ["scenarios"],
    queryFn: () => apiFetch<ScenarioSummary[]>("/api/state/scenarios"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useLoadScenario(
  options?: UseMutationOptions<SessionState, Error, string>,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<SessionState>(`/api/state/scenarios/${id}`, { method: "POST" }),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.sessionState, data);
    },
    ...options,
  });
}

export function usePutState() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (state: SessionState) =>
      apiFetch<SessionState>("/api/state", { method: "PUT", body: state }),
    onSuccess: (data) => qc.setQueryData(queryKeys.sessionState, data),
  });
}

export function usePatchState() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<SessionState>) =>
      apiFetch<SessionState>("/api/state", { method: "PATCH", body: patch }),
    // Don't overwrite the cache on success: auto-save keeps firing rapid
    // PATCHes and a slower in-flight response can otherwise clobber the
    // user's latest optimistic edits. The cache is already up-to-date via
    // `schedule()`'s optimistic setQueryData. On error, re-sync from server.
    onError: () => qc.invalidateQueries({ queryKey: queryKeys.sessionState }),
  });
}

export function useYamlExport() {
  return useMutation({
    mutationFn: () => apiFetch<{ yaml: string }>("/api/state/yaml"),
  });
}

export function useYamlImport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (yaml: string) =>
      apiFetch<SessionState>("/api/state/yaml", { method: "POST", body: { yaml } }),
    onSuccess: (data) => qc.setQueryData(queryKeys.sessionState, data),
  });
}

export interface ValidationResponse {
  ok: boolean;
  violation_count: number;
  violations: Array<{
    rule: string;
    severity: string;
    location: string;
    message: string;
  }>;
  rules_passed: string[];
  rules_failed: string[];
}

export interface AssignmentRow {
  doctor: string;
  date: string;
  role: string;
}

export function useValidateRoster() {
  return useMutation({
    mutationFn: (assignments: AssignmentRow[]) =>
      apiFetch<ValidationResponse>("/api/roster/validate", {
        method: "POST",
        body: { assignments },
      }),
  });
}

// --------------------------------------------------------------- fairness

export interface TierSummary {
  n: number;
  mean: number;
  range: number;
  cv: number;
  gini: number;
  std: number;
}

export interface PerDoctorFairness {
  doctor: string;
  tier: string;
  fte: number;
  weighted_workload: number;
  oncall_workload: number;
  oncall_count: number;
  weekend_count: number;
  station_count: number;
  fte_normalised: number;
  delta_from_median: number;
}

export interface FairnessPayload {
  tier_order: string[];
  per_tier: Record<string, TierSummary>;
  per_tier_oncall: Record<string, TierSummary>;
  per_individual: PerDoctorFairness[];
  dow_load: Record<string, Record<string, number>>;
  horizon_days: number;
}

export function useComputeFairness() {
  return useMutation({
    mutationFn: (assignments: AssignmentRow[]) =>
      apiFetch<FairnessPayload>("/api/metrics/fairness", {
        method: "POST",
        body: { assignments },
      }),
  });
}

// --------------------------------------------------------------- compliance

export interface WtdViolation {
  rule: string;
  severity: "error" | "warning";
  doctor: string;
  message: string;
  detail: Record<string, unknown>;
}

export interface WtdConfig {
  max_avg_weekly_hours: number;
  max_hours_per_7_days: number;
  max_shift_hours: number;
  min_rest_between_hours: number;
  max_consecutive_long_days: number;
  max_consecutive_nights: number;
  long_day_threshold_hours: number;
  reference_period_weeks: number;
}

export interface WtdReport {
  ok: boolean;
  violation_count: number;
  error_count: number;
  warning_count: number;
  by_rule: Record<string, number>;
  config: WtdConfig;
  violations: WtdViolation[];
}

export function useComputeWtd() {
  return useMutation({
    mutationFn: (assignments: AssignmentRow[]) =>
      apiFetch<WtdReport>("/api/compliance/uk_wtd", {
        method: "POST",
        body: { assignments },
      }),
  });
}

// --------------------------------------------------------------- lab batch

export type SolverKey = "cpsat" | "greedy" | "random_repair";

export type SearchBranching =
  | "AUTOMATIC"
  | "FIXED_SEARCH"
  | "PORTFOLIO_SEARCH"
  | "LP_SEARCH"
  | "PSEUDO_COST_SEARCH"
  | "PORTFOLIO_WITH_QUICK_RESTART_SEARCH";

export type DecisionStrategy = "default" | "oncall_first" | "station_first";

export interface RunConfig {
  time_limit_s: number;
  num_workers: number;
  random_seed: number;
  feasibility_only: boolean;
  search_branching: SearchBranching;
  linearization_level: number;
  cp_model_presolve: boolean;
  optimize_with_core: boolean;
  use_lns_only: boolean;
  symmetry_break: boolean;
  decision_strategy: DecisionStrategy;
  redundant_aggregates: boolean;
}

export interface SingleRun {
  run_id: string;
  solver: SolverKey;
  seed: number;
  status: string;
  wall_time_s: number;
  objective: number | null;
  best_bound: number | null;
  headroom: number | null;
  first_feasible_s: number | null;
  self_check_ok: boolean | null;
  violation_count: number | null;
  coverage_shortfall: number;
  coverage_over: number;
  n_assignments: number;
  notes: string;
}

export interface BatchSummary {
  batch_id: string;
  created_at: string;
  instance_label: string;
  n_doctors: number;
  n_stations: number;
  n_days: number;
  run_config: RunConfig;
  runs: SingleRun[];
  feasibility_rate: Record<string, number>;
  mean_objective: Record<string, number | null>;
  mean_shortfall: Record<string, number>;
  quality_ratios: Record<string, number>;
  // Client-synthesised aggregates from the labBatch store — the backend
  // doesn't compute these today, but the streaming batch path does.
  mean_violations?: Record<string, number>;
  runs_by_solver?: Record<string, number>;
  passing_by_solver?: Record<string, number>;
  mean_wall_time?: Record<string, number>;
  mean_assignments?: Record<string, number>;
}

export interface BatchHistoryEntry {
  batch_id: string;
  created_at: string;
  instance_label: string;
  n_runs: number;
  solvers: string[];
  n_seeds: number;
}

export interface BatchRunRequest {
  solvers: SolverKey[];
  seeds: number[];
  run_config: RunConfig;
}

export function useRunBatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: BatchRunRequest) =>
      apiFetch<BatchSummary>("/api/lab/run", { method: "POST", body: req }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lab-runs"] }),
  });
}

export function useBatchHistory() {
  return useQuery({
    queryKey: ["lab-runs"],
    queryFn: () => apiFetch<BatchHistoryEntry[]>("/api/lab/runs"),
    staleTime: 5_000,
  });
}

export interface SingleRunDetail {
  run_id: string;
  batch_id: string;
  solver: SolverKey;
  seed: number;
  result: unknown;
  coverage: {
    shortfall_total: number;
    over_total: number;
    ok: boolean;
    station_gaps: Array<{
      date: string;
      station: string;
      session: string;
      required: number;
      assigned: number;
      shortfall: number;
      over: number;
    }>;
    per_station: Record<string, { required: number; assigned: number; shortfall: number; over: number }>;
  };
  fairness: FairnessPayload;
}

export interface BatchDetail {
  summary: BatchSummary;
  details: Record<string, SingleRunDetail>;
}

export function useBatchDetail(batchId: string | null | undefined) {
  return useQuery({
    queryKey: ["lab-runs", batchId],
    queryFn: () => apiFetch<BatchDetail>(`/api/lab/runs/${batchId}`),
    enabled: !!batchId,
    staleTime: 60_000,
  });
}

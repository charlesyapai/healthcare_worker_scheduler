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
export type HealthResponse = { status: string; phase: number; scheduler_version: string };

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

export interface ScenarioSummary {
  id: string;
  title: string;
  description: string;
  n_doctors: number;
  n_stations: number;
  n_days: number;
  highlights: string[];
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
  subspec: string | null;
  fte: number;
  weighted_workload: number;
  oncall_workload: number;
  oncall_count: number;
  weekend_count: number;
  station_count: number;
  fte_normalised: number;
  delta_from_median: number;
}

export interface SubspecParity {
  subspecs: Record<string, { n: number; mean: number; min: number; max: number }>;
  range: number;
}

export interface FairnessPayload {
  tier_order: string[];
  per_tier: Record<string, TierSummary>;
  per_tier_oncall: Record<string, TierSummary>;
  per_individual: PerDoctorFairness[];
  dow_load: Record<string, Record<string, number>>;
  subspec_parity: SubspecParity;
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

// --------------------------------------------------------------- lab batch

export type SolverKey = "cpsat" | "greedy" | "random_repair";

export interface RunConfig {
  time_limit_s: number;
  num_workers: number;
  random_seed: number;
  feasibility_only: boolean;
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

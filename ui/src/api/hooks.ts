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

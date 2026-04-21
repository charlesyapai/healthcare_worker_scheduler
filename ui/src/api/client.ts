/**
 * Thin fetch wrapper. In prod the SPA is served from the same origin as the
 * FastAPI app, so relative `/api/...` paths work directly. In dev the Vite
 * proxy (see vite.config.ts) forwards them to http://localhost:7860.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export async function apiFetch<T>(
  path: string,
  {
    method = "GET",
    body,
    signal,
  }: { method?: HttpMethod; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const response = await fetch(path, {
    method,
    signal,
    credentials: "include",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = await response.json();
    } catch {
      /* not JSON */
    }
    const message =
      (detail && typeof detail === "object" && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : "") || response.statusText;
    throw new ApiError(response.status, message, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Construct a WebSocket URL for /api/solve that works against the current origin. */
export function wsUrl(path: string): string {
  const { location } = window;
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}${path}`;
}

export const queryKeys = {
  health: ["health"] as const,
  sessionState: ["session-state"] as const,
  yamlExport: ["yaml-export"] as const,
};

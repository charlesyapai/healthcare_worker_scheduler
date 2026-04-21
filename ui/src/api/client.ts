/**
 * Thin fetch wrapper. In prod the SPA is served from the same origin as the
 * FastAPI app, so relative `/api/...` paths work directly. In dev the Vite
 * proxy (see vite.config.ts) forwards them to http://localhost:7860.
 *
 * Session identity travels via an `X-Session-Id` header backed by a
 * localStorage UUID. This avoids browser cookie-blocking inside the
 * cross-site iframe that HF Spaces uses to host the SPA.
 */

const SESSION_KEY = "hws-session-id";

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

function uuidv4(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return (crypto as Crypto & { randomUUID(): string }).randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function getSessionId(): string {
  if (typeof window === "undefined") return "server";
  const stored = window.localStorage.getItem(SESSION_KEY);
  if (stored) return stored;
  const fresh = uuidv4();
  try {
    window.localStorage.setItem(SESSION_KEY, fresh);
  } catch {
    /* storage may be blocked — fall through and return the fresh id anyway */
  }
  return fresh;
}

export async function apiFetch<T>(
  path: string,
  {
    method = "GET",
    body,
    signal,
  }: { method?: HttpMethod; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "X-Session-Id": getSessionId(),
  };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method,
    signal,
    credentials: "include",
    headers,
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

/** WebSocket URL for /api/solve with the session id baked in as a query param. */
export function wsUrl(path: string): string {
  const { location } = window;
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const sep = path.includes("?") ? "&" : "?";
  return `${protocol}//${location.host}${path}${sep}session_id=${encodeURIComponent(getSessionId())}`;
}

export const queryKeys = {
  health: ["health"] as const,
  sessionState: ["session-state"] as const,
  yamlExport: ["yaml-export"] as const,
};

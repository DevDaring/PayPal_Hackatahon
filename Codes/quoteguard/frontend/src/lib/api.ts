// Thin fetch wrapper: same-origin cookies, CSRF header on mutations, typed errors.

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;
  correlationId?: string;
  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}, correlationId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.correlationId = correlationId;
  }
}

function csrf(): string {
  const m = document.cookie.match(/(?:^|; )qg_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export async function api<T = any>(path: string, init: { method?: string; body?: unknown; form?: FormData; signal?: AbortSignal } = {}): Promise<T> {
  const method = init.method ?? (init.body !== undefined || init.form ? "POST" : "GET");
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = csrf();
  let body: BodyInit | undefined;
  if (init.form) body = init.form;
  else if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.body);
  } else if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    body = "{}";
  }
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, { method, headers, body, credentials: "same-origin", signal: init.signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "NETWORK", "Cannot reach QuoteGuard. Check your connection and try again.");
  }
  const ct = res.headers.get("content-type") ?? "";
  const data = ct.includes("application/json") ? await res.json() : null;
  if (!res.ok) {
    const err = data?.error;
    if (res.status === 401 && !path.startsWith("/auth/")) window.dispatchEvent(new CustomEvent("qg:unauthorized"));
    throw new ApiError(res.status, err?.code ?? "HTTP_" + res.status, err?.message ?? res.statusText, err?.details ?? {}, err?.correlation_id);
  }
  return data as T;
}

export const errorText = (e: unknown) => (e instanceof ApiError ? e.message : (e as Error)?.message ?? "Something went wrong");

/** Mutation without a body still needs POST (and therefore the CSRF header). */
export const post = <T = any>(path: string, body?: unknown) => api<T>(path, { method: "POST", body });

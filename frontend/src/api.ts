const BASE = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;

export const TOKEN_KEY = "bm_token";
let token: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setToken(t: string | null) {
  token = t;
}
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

type Opts = { method?: string; body?: unknown; form?: FormData };

export async function request<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: any;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(BASE + path, { method: opts.method ?? (body ? "POST" : "GET"), headers, body });
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    if (res.status === 401 && token && !path.startsWith("/auth/login")) onUnauthorized?.();
    const d = data?.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? `${d[0]?.loc?.slice(-1)[0] ?? ""} ${d[0]?.msg ?? ""}`.trim() : text || `Error ${res.status}`;
    throw new Error(msg);
  }
  return data as T;
}

export const api = {
  get: <T = any>(p: string) => request<T>(p),
  post: <T = any>(p: string, body?: unknown) => request<T>(p, { method: "POST", body: body ?? {} }),
  put: <T = any>(p: string, body?: unknown) => request<T>(p, { method: "PUT", body: body ?? {} }),
  del: <T = any>(p: string) => request<T>(p, { method: "DELETE" }),
};

export async function authenticatedBlob(path: string): Promise<Blob> {
  const res = await fetch(BASE + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) {
    if (res.status === 401) onUnauthorized?.();
    throw new Error("Could not open private document");
  }
  return res.blob();
}

export const fileUrl = (id: string) => `${BASE}/files/${id}?token=${encodeURIComponent(token ?? "")}`;
export const publicReportUrl = (shareToken: string) => `${BASE}/public/reports/${shareToken}`;

export const LOGO_URL =
  "https://customer-assets-lqy194kg.emergentagent.net/job_73724556-664b-45a9-8dc1-ea0e2573ffb5/artifacts/7ad33ebc61f9950d_Britsmaid%20Logo.jpg";

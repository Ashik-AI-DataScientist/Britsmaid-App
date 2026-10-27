export const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || (typeof window !== "undefined" ? window.location.origin : "");
const BASE = `${BACKEND_URL}/api`;
export const TOKEN_KEY = "bm_token";
let token: string | null = null;
let cookieSession = false;
export function setCookieSession(active: boolean) { if (cookieSession !== active) authEpoch++; cookieSession = active; }
let onUnauthorized: (() => void) | null = null;
let authEpoch = 0;
export function getAuthEpoch() { return authEpoch; }
export function setToken(value: string | null) { if (token !== value) authEpoch++; token = value; }
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn; }
type Opts = { method?: string; body?: unknown; form?: FormData; authorization?: string; expectedAuthEpoch?: number };

export async function request<T = any>(path: string, opts: Opts = {}): Promise<T> {
  if (opts.expectedAuthEpoch !== undefined && opts.expectedAuthEpoch !== authEpoch) throw new Error("Your session changed. Sign in to the original account to resume this photo.");
  const epoch = authEpoch;
  const headers: Record<string, string> = {};
  const auth = opts.authorization !== undefined ? opts.authorization : token;
  if (auth) headers.Authorization = `Bearer ${auth}`;
  let body: any;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), opts.form ? 120000 : 20000);
  try {
    const res = await fetch(BASE + path, { method: opts.method ?? (body ? "POST" : "GET"), headers, body, credentials: "include", signal: controller.signal });
    const text = await res.text();
    if (opts.authorization === undefined && epoch !== authEpoch) throw new Error("Your session changed. Please retry from the current account.");
    let data: any = null;
    try { data = text ? JSON.parse(text) : null; } catch { /* Invalid responses are reported below. */ }
    if (!res.ok) {
      if (res.status === 401 && epoch === authEpoch && (token || cookieSession) && opts.authorization === undefined && !path.startsWith("/auth/login")) onUnauthorized?.();
      const detail = data?.detail;
      const message = typeof detail === "string" ? detail : Array.isArray(detail) ? `${detail[0]?.loc?.slice(-1)[0] ?? ""} ${detail[0]?.msg ?? "Please check this field"}`.trim() : "The server is temporarily unavailable. Please try again.";
      throw Object.assign(new Error(message), { status: res.status, code: data?.code });
    }
    if (res.status !== 204 && data === null) throw new Error("The server sent an unexpected response. Please try again.");
    return data as T;
  } catch (error: any) {
    if (error?.name === "AbortError") throw new Error("The request timed out. Check your connection and refresh before trying again.");
    if (error instanceof TypeError || error?.name === "TypeError") throw new Error("Could not connect. Check your connection and try again. If you were saving, refresh first to check whether it was saved.");
    throw error;
  } finally { clearTimeout(timeout); }
}
export const api = {
  get: <T = any>(p: string) => request<T>(p),
  post: <T = any>(p: string, body?: unknown) => request<T>(p, { method: "POST", body: body ?? {} }),
  put: <T = any>(p: string, body?: unknown) => request<T>(p, { method: "PUT", body: body ?? {} }),
  del: <T = any>(p: string) => request<T>(p, { method: "DELETE" }),
};
export async function authenticatedBlob(path: string): Promise<Blob> {
  const blobAuth = token;
  const blobEpoch = authEpoch;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const res = await fetch(BASE + path, { headers: blobAuth ? { Authorization: `Bearer ${blobAuth}` } : {}, credentials: "include", signal: controller.signal });
    if (blobEpoch !== authEpoch) throw new Error("Your session changed. Please open the document from the current account.");
    if (!res.ok) { if (res.status === 401 && blobEpoch === authEpoch) onUnauthorized?.(); throw new Error("Could not open the document. Please try again."); }
    const blob = await res.blob();
    if (blobEpoch !== authEpoch) throw new Error("Your session changed. Please open the document from the current account.");
    return blob;
  } catch (e: any) {
    if (e.name === "AbortError" || e.name === "TypeError") throw new Error("Connection interrupted. Please try opening the document again.");
    throw e;
  } finally { clearTimeout(timeout); }
}
export async function privateFileUrl(id: string): Promise<string> {
  const result = await api.post<{ ticket: string }>(`/files/${encodeURIComponent(id)}/ticket`);
  return `${BASE}/files/${encodeURIComponent(id)}?ticket=${encodeURIComponent(result.ticket)}`;
}
export async function revokeCurrentSession(): Promise<void> {
  const session = token;
  if (!session && !cookieSession) return;
  // Use a direct request: an expired logout response must not trigger recursive sign-out.
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try { await fetch(`${BASE}/auth/logout`, { method: "POST", headers: session ? { Authorization: `Bearer ${session}` } : {}, credentials: "include", signal: controller.signal }); }
  finally { clearTimeout(timeout); }
}
export const publicReportUrl = (shareToken: string) => `${BASE}/public/reports/${shareToken}`;
export const LOGO_URL = "https://customer-assets-lqy194kg.emergentagent.net/job_73724556-664b-45a9-8dc1-ea0e2573ffb5/artifacts/7ad33ebc61f9950d_Britsmaid%20Logo.jpg";

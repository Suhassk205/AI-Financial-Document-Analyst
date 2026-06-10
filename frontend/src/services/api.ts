/**
 * Thin API client foundation.
 *
 * Centralizes the backend base URL and a typed `request` helper. Feature-specific
 * API modules (upload, search, chat, ...) are added under src/services/ in later
 * phases and should build on this — no business calls are implemented yet.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  return (await res.json()) as T;
}

/** Operational helper used by the foundation App to prove connectivity. */
export function getHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/health");
}

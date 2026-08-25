import { ApiError } from './errors'

/** Every backend route hangs under this base path (proxied in vite.config). */
export const API_BASE = '/api'

/** Join an endpoint path with the /api base. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

/** RequestInit for a JSON payload, matching what the stores send today. */
export function jsonRequest(method: string, payload: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
}

/**
 * Typed fetch wrapper for the /api base. Resolves with the raw Response so
 * callers keep their existing ok-check and error-message semantics; abort
 * signals and native network errors pass through untouched.
 */
export async function fetchApi(path: string, init?: RequestInit): Promise<Response> {
  return fetch(apiUrl(path), init)
}

/**
 * Typed fetch wrapper that parses JSON and normalizes non-2xx responses into
 * {@link ApiError}. Use where a caller only needs the decoded payload.
 */
export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetchApi(path, init)
  if (!response.ok) {
    throw new ApiError(`Request failed: ${apiUrl(path)}`, response.status)
  }
  return (await response.json()) as T
}

/**
 * Thin API client wrapper.
 *
 * API_BASE resolution (in priority order):
 * 1. VITE_API_URL environment variable — set at build time (e.g. Render URL)
 * 2. Empty string — all requests use relative URLs (monorepo mode on Vercel,
 *    or Vite dev proxy in local development)
 *
 * Monorepo deployment (Vercel):
 *   Both frontend and backend are served from the same domain (myapp.vercel.app).
 *   API calls to `/api/...` are same-origin, so API_BASE stays empty.
 *   No CORS needed in monorepo mode.
 *
 * Separate deployment (Render):
 *   VITE_API_URL is set to the Render backend URL (e.g. https://autolaw-api.onrender.com).
 *   API calls go cross-origin and CORS is handled by the backend.
 */

const API_BASE: string = import.meta.env.VITE_API_URL ?? ""

/**
 * Return the configured API base URL.
 * Useful when you need to construct a full URL manually (e.g. for XHR uploads).
 */
export function getApiBase(): string {
  return API_BASE
}

/**
 * Perform a JSON API request.
 *
 * Automatically prepends API_BASE to `path`, sets JSON content-type, and
 * throws an `Error` with the server's detail message on non-OK responses.
 */
export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

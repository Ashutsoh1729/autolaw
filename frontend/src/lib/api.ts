/**
 * Thin API client wrapper.
 *
 * Reads VITE_API_URL from the environment (set via .env or Vercel dashboard).
 * When not set, defaults to empty string so all requests use relative URLs
 * (handled by the Vite dev proxy or same-origin production deployment).
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

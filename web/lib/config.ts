/**
 * Runtime settings.
 * - NEXT_PUBLIC_API_URL: the API as the browser reaches it (default http://localhost:8000).
 * - API_URL: the API as the Next.js server reaches it (Docker: http://api:8000). Defaults to NEXT_PUBLIC_API_URL.
 * - NEXT_PUBLIC_USE_MOCKS=1: serve built-in mock data and never call the API (UI work without the backend).
 */
export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

export const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function apiBaseUrl(): string {
  if (typeof window === "undefined") return process.env.API_URL ?? PUBLIC_API_URL;
  return PUBLIC_API_URL;
}

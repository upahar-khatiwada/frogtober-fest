import createClient from "openapi-fetch";

import { apiBaseUrl } from "@/lib/config";

import type { paths } from "./types";

/**
 * Typed fetch client for the Tenderly API.
 *
 * Regenerate lib/api/types.ts with `bun run gen:api` (requires the
 * FastAPI server running locally) whenever api/routers/*.py changes.
 * The base URL differs on the server (API_URL) and in the browser
 * (NEXT_PUBLIC_API_URL); see lib/config.ts. App code should call the
 * functions in lib/api/tenderly.ts, which add the mock fallback.
 */
const clients = new Map<string, ReturnType<typeof createClient<paths>>>();

export function getApiClient() {
  const baseUrl = apiBaseUrl();
  let client = clients.get(baseUrl);
  if (!client) {
    client = createClient<paths>({ baseUrl });
    clients.set(baseUrl, client);
  }
  return client;
}

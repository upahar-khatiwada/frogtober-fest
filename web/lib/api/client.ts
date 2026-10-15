import createClient from "openapi-fetch";

import type { paths } from "./types";

/**
 * Typed fetch client for the Tenderly API.
 *
 * Regenerate lib/api/types.ts with `bun run gen:api` (requires the
 * FastAPI server running locally) whenever api/routers/*.py changes.
 */
export const apiClient = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
});
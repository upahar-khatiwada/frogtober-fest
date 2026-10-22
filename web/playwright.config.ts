import { defineConfig, devices } from "@playwright/test";

/**
 * The one E2E test (e2e/demo.spec.mjs): the demo path on seeded data. Run with `bunx playwright test`.
 *
 * Default: against the running stack (web on E2E_BASE_URL, default http://localhost:3000; API on E2E_API_URL,
 * default http://localhost:8000) with the demo company seeded and the LLM replay cache recorded, so every model
 * answer is pre-cached (see CLAUDE.md "E2E test"). Use a fresh DB: the test approves tender 001, and an approved
 * tender is final.
 *
 * E2E_MOCKS=1: no backend. Playwright starts `next dev` with NEXT_PUBLIC_USE_MOCKS=1 on port 3100 and the same
 * test runs against the built-in mocks (useful for UI work and CI without Ollama).
 */
const MOCKS = process.env.E2E_MOCKS === "1";
const PORT = Number(process.env.E2E_PORT ?? (MOCKS ? 3100 : 3000));
const baseURL = process.env.E2E_BASE_URL ?? `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "e2e",
  // Pre-cached model answers take milliseconds, but Scout -> Compliance -> Proposal -> Review still runs real
  // retrieval and code; a cache miss falls through to Ollama. Generous on the real stack, tight on mocks.
  timeout: MOCKS ? 90_000 : 15 * 60_000,
  expect: { timeout: MOCKS ? 15_000 : 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "laptop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 768 } },
    },
  ],
  webServer: MOCKS
    ? {
        command: `bun run dev --port ${PORT}`,
        url: baseURL,
        reuseExistingServer: true,
        timeout: 180_000,
        env: { NEXT_PUBLIC_USE_MOCKS: "1" },
      }
    : undefined,
});

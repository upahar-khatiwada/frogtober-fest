import { connection } from "next/server";
import { Suspense } from "react";

import { AgentRunsTable } from "@/components/runs/agent-runs-table";
import { PipelineRunsTable } from "@/components/runs/pipeline-runs-table";
import { RunsControls } from "@/components/runs/runs-controls";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import {
  ApiError,
  listAgentRuns,
  listRuns,
  parseAgentRunFilters,
  type AgentRunView,
  type PipelineRunView,
} from "@/lib/api/tenderly";
import { PUBLIC_API_URL } from "@/lib/config";
import { T } from "@/lib/prefs";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

/** Server component: the audit log (GET /agent-runs) with the URL's filters, and recent pipeline runs (GET /runs). */
async function RunsData({ searchParams }: { searchParams: SearchParams }) {
  await connection();
  const filters = parseAgentRunFilters(await searchParams);
  let rows: AgentRunView[];
  let runs: PipelineRunView[];
  try {
    [rows, runs] = await Promise.all([listAgentRuns(filters), listRuns(10)]);
  } catch (e) {
    const httpError = e instanceof ApiError && e.status > 0;
    return (
      <ErrorState>
        {httpError ? (
          <T k="runs.loadFailed" vars={{ error: e.message }} />
        ) : (
          <T k="dashboard.error" vars={{ url: PUBLIC_API_URL }} />
        )}
      </ErrorState>
    );
  }
  const live = runs.some((r) => r.status === "queued" || r.status === "running");
  const filtered = Object.keys(filters).some((k) => k !== "limit");

  return (
    <div className="flex flex-col gap-6">
      <RunsControls live={live} />
      <section className="flex flex-col gap-2" aria-labelledby="audit-title">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="audit-title" className="text-lg font-semibold">
            <T k="runs.audit" />
          </h2>
          <span className="text-xs text-muted-foreground">
            <T k="runs.count" vars={{ n: rows.length }} />
          </span>
        </div>
        {rows.length === 0 ? (
          <EmptyState>
            <T k={filtered ? "runs.emptyFiltered" : "runs.empty"} />
          </EmptyState>
        ) : (
          <AgentRunsTable rows={rows} />
        )}
      </section>
      <section className="flex flex-col gap-2" aria-labelledby="pipeline-title">
        <h2 id="pipeline-title" className="text-lg font-semibold">
          <T k="runs.pipeline" />
        </h2>
        {runs.length === 0 ? (
          <EmptyState>
            <T k="runs.empty" />
          </EmptyState>
        ) : (
          <PipelineRunsTable runs={runs} />
        )}
      </section>
    </div>
  );
}

export default function RunsPage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          <T k="runs.title" />
        </h1>
        <p className="text-sm text-muted-foreground">
          <T k="runs.subtitle" />
        </p>
      </div>
      <Suspense fallback={<LoadingState blocks={["h-8 w-80", "h-96 w-full", "h-40 w-full"]} />}>
        <RunsData searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

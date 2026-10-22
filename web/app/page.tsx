import { connection } from "next/server";
import { Suspense } from "react";

import { LoadTendersButton } from "@/components/tenders/load-tenders-button";
import { TenderFilters } from "@/components/tenders/tender-filters";
import { TenderRow } from "@/components/tenders/tender-row";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { ApiError, listTenders, parseTenderFilters, type TenderListItem } from "@/lib/api/tenderly";
import { PUBLIC_API_URL } from "@/lib/config";
import { T } from "@/lib/prefs";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

/** Server component: GET /tenders with the URL's filters, rendered as ranked rows. */
async function TenderList({ searchParams }: { searchParams: SearchParams }) {
  await connection();
  const filters = parseTenderFilters(await searchParams);
  let tenders: TenderListItem[];
  try {
    tenders = await listTenders(filters);
  } catch (e) {
    // An HTTP error from a reachable API shows its message; anything else means unreachable.
    const httpError = e instanceof ApiError && e.status > 0;
    return (
      <ErrorState>
        {httpError ? <T k="dashboard.loadFailed" vars={{ error: e.message }} /> : <T k="dashboard.error" vars={{ url: PUBLIC_API_URL }} />}
      </ErrorState>
    );
  }
  if (tenders.length === 0) {
    const filtered = Object.keys(filters).length > 0;
    return (
      <EmptyState>
        <T k={filtered ? "dashboard.empty" : "dashboard.emptyNone"} />
      </EmptyState>
    );
  }
  return (
    <section className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">
        <T k="dashboard.count" vars={{ n: tenders.length }} />
      </p>
      <ol className="flex flex-col gap-3">
        {tenders.map((t) => (
          <TenderRow key={t.id} tender={t} />
        ))}
      </ol>
    </section>
  );
}

export default function DashboardPage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            <T k="dashboard.title" />
          </h1>
          <p className="text-sm text-muted-foreground">
            <T k="dashboard.subtitle" />
          </p>
        </div>
        <LoadTendersButton />
      </div>
      <Suspense fallback={<LoadingState blocks={["h-40 w-full"]} />}>
        <TenderFilters />
      </Suspense>
      <Suspense fallback={<LoadingState blocks={["h-36 w-full", "h-36 w-full", "h-36 w-full"]} />}>
        <TenderList searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

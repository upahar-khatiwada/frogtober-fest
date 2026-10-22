import Link from "next/link";
import { connection } from "next/server";
import { Suspense } from "react";

import { ProposalWorkspace } from "@/components/proposal/proposal-workspace";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { buttonVariants } from "@/components/ui/button";
import {
  loadProposalBundle,
  parseTenderId,
  type ProposalBundle,
} from "@/lib/api/tenderly";
import { T } from "@/lib/prefs";

type Params = Promise<{ id: string }>;
type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function BackLink({ id }: { id: string | number }) {
  return (
    <Link
      href={typeof id === "number" ? `/tenders/${id}` : "/"}
      className="w-fit text-sm text-muted-foreground hover:text-foreground"
    >
      ← <T k={typeof id === "number" ? "pp.back" : "td.back"} />
    </Link>
  );
}

/** Server component: tender + versions + the chosen version (?v=<proposal id>) + its cited chunks. */
async function ProposalData({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  await connection();
  const { id: raw } = await params;
  const id = parseTenderId(raw);
  if (id === null) {
    return (
      <div className="flex flex-col gap-3">
        <BackLink id={raw} />
        <EmptyState>
          <T k="td.invalidId" vars={{ id: raw }} />
        </EmptyState>
      </div>
    );
  }
  const v = (await searchParams).v;
  const version = parseTenderId(Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));
  let bundle: ProposalBundle | null;
  try {
    bundle = await loadProposalBundle(id, version);
  } catch (e) {
    return (
      <div className="flex flex-col gap-3">
        <BackLink id={id} />
        <ErrorState
          action={
            <Link href={`/tenders/${id}/proposal`} className={buttonVariants({ variant: "outline", size: "sm" })}>
              <T k="state.retry" />
            </Link>
          }
        >
          <T k="pp.loadFailed" vars={{ error: e instanceof Error ? e.message : String(e) }} />
        </ErrorState>
      </div>
    );
  }
  if (!bundle) {
    return (
      <div className="flex flex-col gap-3">
        <BackLink id="/" />
        <EmptyState>
          <T k="td.notFound" vars={{ id }} />
        </EmptyState>
      </div>
    );
  }
  if (!bundle.proposal) {
    return (
      <div className="flex flex-col gap-3">
        <BackLink id={id} />
        <EmptyState
          action={
            <Link href={`/tenders/${id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
              <T k="pp.back" />
            </Link>
          }
        >
          <T k="pp.none" />
        </EmptyState>
      </div>
    );
  }
  return <ProposalWorkspace key={bundle.proposal.id} initial={bundle} />;
}

export default function ProposalPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  return (
    <Suspense fallback={<LoadingState blocks={["h-6 w-40", "h-10 w-2/3", "h-48 w-full", "h-96 w-full"]} />}>
      <ProposalData params={params} searchParams={searchParams} />
    </Suspense>
  );
}

import Link from "next/link";
import { connection } from "next/server";
import { Suspense } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { TenderWorkspace } from "@/components/tender-detail/tender-workspace";
import {
  listRules,
  loadTenderBundle,
  parseTenderId,
  type RuleView,
  type TenderBundle,
} from "@/lib/api/tenderly";
import { T } from "@/lib/prefs";

type Params = Promise<{ id: string }>;

function Message({
  children,
  tone = "muted",
}: {
  children: React.ReactNode;
  tone?: "muted" | "error";
}) {
  return (
    <div className="flex flex-col gap-3">
      <Link
        href="/"
        className="w-fit text-sm text-muted-foreground hover:text-foreground"
      >
        ← <T k="td.back" />
      </Link>
      {tone === "error" ? <ErrorState>{children}</ErrorState> : <EmptyState>{children}</EmptyState>}
    </div>
  );
}

/** Server component: the tender, its evidence and the rule list, then the interactive workspace. */
async function TenderData({ params }: { params: Params }) {
  await connection();
  const { id: raw } = await params;
  const id = parseTenderId(raw);
  if (id === null) {
    return (
      <Message>
        <T k="td.invalidId" vars={{ id: raw }} />
      </Message>
    );
  }
  let bundle: TenderBundle | null;
  let rules: RuleView[];
  try {
    [bundle, rules] = await Promise.all([
      loadTenderBundle(id),
      listRules().catch((): RuleView[] => []),
    ]);
  } catch (e) {
    return (
      <Message tone="error">
        <T
          k="td.loadFailed"
          vars={{ error: e instanceof Error ? e.message : String(e) }}
        />
      </Message>
    );
  }
  if (!bundle) {
    return (
      <Message>
        <T k="td.notFound" vars={{ id }} />
      </Message>
    );
  }
  return <TenderWorkspace initial={bundle} rules={rules} />;
}

export default function TenderPage({ params }: { params: Params }) {
  return (
    <Suspense
      fallback={<LoadingState />}
    >
      <TenderData params={params} />
    </Suspense>
  );
}

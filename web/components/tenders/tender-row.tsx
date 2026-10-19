import { AlertTriangle, ShieldAlert } from "lucide-react";

import { DeadlineDisplay } from "@/components/deadline-display";
import { Money } from "@/components/money";
import { Badge } from "@/components/ui/badge";
import type { TenderListItem } from "@/lib/api/tenderly";
import { EnumText, T } from "@/lib/prefs";
import { previewReasons } from "@/lib/reasons";
import { cn } from "@/lib/utils";

import { EnumBadge, StatusBadge } from "./badges";

function ScoreBlock({ score, decision }: Pick<TenderListItem, "score" | "decision">) {
  if (score == null) {
    return (
      <div className="text-xs text-muted-foreground">
        <T k="tender.unscored" />
      </div>
    );
  }
  const pursue = decision === "pursue";
  return (
    <div className="flex w-28 flex-col gap-1" aria-label={`score ${score}`}>
      <div className="flex items-baseline justify-between">
        <span className={cn("text-2xl font-semibold tabular-nums", pursue ? "text-foreground" : "text-muted-foreground")}>{score}</span>
        {decision && (
          <span className={cn("text-xs font-medium", pursue ? "text-emerald-700 dark:text-emerald-400" : "text-muted-foreground")}>
            <EnumText kind="decision" value={decision} />
          </span>
        )}
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full", pursue ? "bg-emerald-600" : "bg-muted-foreground/50")} style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
      </div>
    </div>
  );
}

/** One ranked tender (server component; labels and dates are small client leaves). */
export function TenderRow({ tender }: { tender: TenderListItem }) {
  const { shown, more } = previewReasons(tender.reasons, 2);
  return (
    <li className="grid gap-4 rounded-xl border bg-card p-4 md:grid-cols-[auto_1fr_auto] md:items-start" data-testid="tender-row">
      <div className="flex items-center gap-3 md:flex-col md:items-start">
        <span className="text-xs font-medium text-muted-foreground tabular-nums">#{tender.rank}</span>
        <ScoreBlock score={tender.score} decision={tender.decision} />
      </div>

      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap items-start gap-2">
          <h2 className="min-w-0 flex-1 text-base font-semibold leading-snug" lang={tender.language === "ne" ? "ne" : undefined}>
            {tender.title ?? (
              <span className="text-muted-foreground">
                <T k="tender.untitled" />
              </span>
            )}
          </h2>
          <StatusBadge status={tender.status} />
        </div>

        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
          {tender.buyer && <span className="text-foreground">{tender.buyer}</span>}
          {tender.buyer_level && <EnumBadge kind="buyer_level" value={tender.buyer_level} />}
          {(tender.province || tender.district) && (
            <span>
              {tender.province && <EnumText kind="province" value={tender.province} />}
              {tender.province && tender.district && " / "}
              {tender.district}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {tender.procurement_type && <EnumBadge kind="procurement_type" value={tender.procurement_type} className="border-sky-300 dark:border-sky-800" />}
          {tender.method && <EnumBadge kind="method" value={tender.method} className="border-violet-300 dark:border-violet-800" />}
          {tender.language && <EnumBadge kind="language" value={tender.language} className="text-muted-foreground" />}
          {tender.estimated_cost_npr != null && (
            <span className="ml-1 text-sm">
              <span className="text-muted-foreground">
                <T k="tender.cost" />:
              </span>{" "}
              <Money amount={tender.estimated_cost_npr} />
            </span>
          )}
          {tender.hard_failures != null && tender.hard_failures > 0 && (
            <Badge variant="destructive">
              <ShieldAlert aria-hidden="true" />
              <T k="tender.hardFailures" vars={{ n: tender.hard_failures }} />
            </Badge>
          )}
          {tender.needs_review && (
            <Badge className="bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              <AlertTriangle aria-hidden="true" />
              <T k="tender.needsReview" />
            </Badge>
          )}
        </div>

        {shown.length > 0 && (
          <ul className="flex flex-col gap-0.5 text-sm" aria-label="reasons">
            {shown.map((r, i) => (
              <li key={i} className={cn("flex gap-1.5", r.skip ? "text-red-700 dark:text-red-400" : "text-muted-foreground")}>
                {r.source && (
                  <span className="mt-0.5 shrink-0 rounded bg-muted px-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    <T k={r.source === "model" ? "tender.source.model" : "tender.source.deterministic"} />
                  </span>
                )}
                <span className="line-clamp-2">{r.text}</span>
              </li>
            ))}
            {more > 0 && (
              <li className="text-xs text-muted-foreground">
                <T k="tender.moreReasons" vars={{ n: more }} />
              </li>
            )}
          </ul>
        )}
      </div>

      <div className="md:w-56">
        <DeadlineDisplay deadline={tender.deadline} />
      </div>
    </li>
  );
}

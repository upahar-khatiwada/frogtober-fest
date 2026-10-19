"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { MatchResult } from "@/lib/api/tenderly";
import { EnumText, usePrefs } from "@/lib/prefs";
import { parseReason } from "@/lib/reasons";
import { cn } from "@/lib/utils";

/** Score, and every reason tagged as deterministic (code) or model judgement. */
export function MatchPanel({
  match,
}: {
  match: MatchResult | null | undefined;
}) {
  const { t } = usePrefs();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("td.section.match")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!match ? (
          <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
            {t("td.match.none")}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-baseline gap-3">
              <span className="text-3xl font-semibold tabular-nums">
                {match.score}
              </span>
              <Badge
                className={
                  match.decision === "pursue"
                    ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
                    : ""
                }
                variant={match.decision === "pursue" ? "default" : "outline"}
              >
                <EnumText kind="decision" value={match.decision} />
              </Badge>
              <span className="text-sm text-muted-foreground">
                {t("td.match.score", {
                  score: match.score,
                  threshold: match.threshold,
                })}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              {t("td.match.scores", {
                det: match.deterministic_score ?? "-",
                sem: match.semantic_score ?? t("td.match.notAsked"),
                w: match.llm_weight ?? "-",
              })}
            </p>
            <ul className="flex flex-col gap-2" aria-label="reasons">
              {match.reasons.map((raw, i) => {
                const r = parseReason(raw);
                const model = r.source === "model";
                return (
                  <li
                    key={i}
                    data-source={r.source ?? "none"}
                    className={cn(
                      "flex flex-col gap-1 rounded-lg border-l-4 bg-muted/40 p-2 text-sm",
                      r.skip
                        ? "border-l-red-600"
                        : model
                          ? "border-l-violet-500"
                          : "border-l-slate-400",
                    )}
                  >
                    {r.source && (
                      <Badge
                        variant="outline"
                        className={cn(
                          "w-fit",
                          model
                            ? "border-violet-400 text-violet-800 dark:text-violet-300"
                            : "text-slate-700 dark:text-slate-300",
                        )}
                      >
                        {t(model ? "td.match.model" : "td.match.deterministic")}
                      </Badge>
                    )}
                    <span
                      className={cn(r.skip && "text-red-700 dark:text-red-400")}
                    >
                      {r.text}
                    </span>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}

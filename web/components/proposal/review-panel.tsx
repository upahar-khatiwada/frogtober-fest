"use client";

import { CheckCircle2, LoaderCircle, Play, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { components } from "@/lib/api/types";
import type { ProposalSection, ReviewReport } from "@/lib/api/tenderly";
import { usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/utils";

type Verdict = components["schemas"]["ReviewVerdict"];

const VERDICT_CLASS: Record<Verdict, string> = {
  pass: "bg-emerald-600 text-white dark:bg-emerald-500",
  needs_work: "bg-amber-400 text-amber-950 dark:bg-amber-500",
  fail: "bg-red-600 text-white dark:bg-red-500",
};

export function VerdictBadge({ verdict, className }: { verdict: Verdict; className?: string }) {
  const { label } = usePrefs();
  return (
    <Badge className={cn(VERDICT_CLASS[verdict], className)} data-verdict={verdict} data-testid="verdict">
      {label("verdict", verdict)}
    </Badge>
  );
}

function ScoreBar({
  name,
  value,
  pass,
  fail,
}: {
  name: string;
  value: number;
  pass: number;
  fail: number;
}) {
  const tone = value < fail ? "bg-red-600" : value < pass ? "bg-amber-500" : "bg-emerald-600";
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between text-sm">
        <span>{name}</span>
        <span className="font-semibold tabular-nums">{value}</span>
      </div>
      <div
        role="meter"
        aria-label={name}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        className="relative h-2 rounded-full bg-muted"
      >
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${value}%` }} />
        {/* threshold ticks: fail-below and pass-min */}
        <span aria-hidden="true" className="absolute -top-0.5 h-3 w-px bg-red-700/70" style={{ left: `${fail}%` }} />
        <span aria-hidden="true" className="absolute -top-0.5 h-3 w-px bg-emerald-800/70" style={{ left: `${pass}%` }} />
      </div>
    </div>
  );
}

/** The review report: verdict, the model's three scores, why, the code checks, and gaps linked to the proposal. */
export function ReviewPanel({
  review,
  sections,
  canRunReview,
  reviewing,
  onRunReview,
  onSection,
  onRequirement,
}: {
  review: ReviewReport | null | undefined;
  sections: ProposalSection[];
  canRunReview: boolean;
  reviewing: boolean;
  onRunReview: () => void;
  onSection: (key: string) => void;
  onRequirement: (index: number) => void;
}) {
  const { t, label } = usePrefs();
  const titles = Object.fromEntries(sections.map((s) => [s.key, s.title]));

  return (
    <Card size="sm" aria-labelledby="review-title" data-testid="review-panel">
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2">
          <h2 id="review-title" className="text-base font-semibold">
            {t("pp.rv.title")}
          </h2>
          {review && <VerdictBadge verdict={review.verdict} className="h-6 px-3 text-sm" />}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!review && (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-muted-foreground">{t("pp.rv.none")}</p>
            {canRunReview && (
              <Button onClick={onRunReview} disabled={reviewing} className="w-fit">
                {reviewing ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Play aria-hidden="true" />}
                {reviewing ? t("pp.rv.running") : t("pp.rv.run")}
              </Button>
            )}
          </div>
        )}
        {review && (
          <>
            <div className="flex flex-col gap-3">
              {(["completeness", "relevance", "compliance"] as const).map((k) => (
                <ScoreBar
                  key={k}
                  name={t(`pp.rv.score.${k}`)}
                  value={review.scores[k]}
                  pass={review.pass_min_score ?? 70}
                  fail={review.fail_below_score ?? 40}
                />
              ))}
              <p className="text-xs text-muted-foreground">
                {t("pp.rv.thresholds", {
                  pass: review.pass_min_score ?? 70,
                  fail: review.fail_below_score ?? 40,
                })}
              </p>
            </div>

            {(review.verdict_reasons ?? []).length > 0 && (
              <section className="flex flex-col gap-1">
                <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{t("pp.rv.reasons")}</h3>
                <ul className="flex list-disc flex-col gap-0.5 pl-4 text-xs">
                  {review.verdict_reasons!.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </section>
            )}

            <section className="flex flex-col gap-1">
              <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{t("pp.rv.checks")}</h3>
              <ul className="flex flex-col gap-1 text-xs">
                {(review.checks ?? []).map((c) => (
                  <li key={c.check} className="flex items-start gap-1.5" title={c.detail}>
                    {c.passed ? (
                      <CheckCircle2 className="mt-px size-3.5 shrink-0 text-emerald-600" aria-hidden="true" />
                    ) : (
                      <XCircle
                        className={cn("mt-px size-3.5 shrink-0", c.severity === "hard" ? "text-red-600" : "text-amber-600")}
                        aria-hidden="true"
                      />
                    )}
                    <span>
                      <span className="sr-only">{c.passed ? t("pp.ap.met") : t("pp.ap.notMet")}: </span>
                      {label("check", c.check)}
                      <span className="block text-muted-foreground">{c.detail}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </section>

            <section className="flex flex-col gap-1.5">
              <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                {t("pp.rv.gaps", { n: (review.gaps ?? []).length })}
              </h3>
              {(review.gaps ?? []).length === 0 ? (
                <p className="text-xs text-muted-foreground">{t("pp.rv.noGaps")}</p>
              ) : (
                <ul className="flex flex-col gap-2" data-testid="review-gaps">
                  {review.gaps!.map((g, i) => (
                    <li
                      key={i}
                      className={cn(
                        "flex flex-col gap-1 rounded-lg border-l-4 bg-muted/40 p-2 text-xs",
                        g.severity === "hard" ? "border-l-red-600" : "border-l-amber-500",
                      )}
                    >
                      <div className="flex flex-wrap items-center gap-1">
                        <Badge variant="outline">{label("severity", g.severity)}</Badge>
                        <Badge variant="outline">{label("gap_source", g.source)}</Badge>
                      </div>
                      <p>{g.issue}</p>
                      {g.suggestion && <p className="text-muted-foreground">{t("pp.rv.suggestion", { text: g.suggestion })}</p>}
                      <div className="flex flex-wrap gap-2">
                        {g.section_key && (
                          <button
                            type="button"
                            onClick={() => onSection(g.section_key!)}
                            className="rounded text-left font-medium text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                          >
                            → {titles[g.section_key] ?? g.section_key}
                          </button>
                        )}
                        {g.requirement_index != null && (
                          <button
                            type="button"
                            onClick={() => onRequirement(g.requirement_index!)}
                            className="rounded font-medium text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                          >
                            → {t("pp.r.label", { n: g.requirement_index + 1 })}
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </CardContent>
    </Card>
  );
}

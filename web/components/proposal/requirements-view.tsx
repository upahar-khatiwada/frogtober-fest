"use client";

import { AlertTriangle, ArrowRight } from "lucide-react";

import { EmptyState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import type {
  ProposalSection,
  Requirement,
  ReviewReport,
} from "@/lib/api/tenderly";
import { usePrefs } from "@/lib/prefs";
import { isStub, sectionsFor } from "@/lib/proposal";
import { cn } from "@/lib/utils";

import { SectionBody } from "./section-card";

const EXCERPT = 420;

/**
 * Side by side: each tender requirement (with the notice's own words) next to the proposal text that answers it
 * (ProposalSection.requirement_indices), so a person can check the response against what was asked.
 */
export function RequirementsView({
  requirements,
  sections,
  review,
  lang,
  onSection,
}: {
  requirements: Requirement[];
  sections: ProposalSection[];
  review: ReviewReport | null | undefined;
  lang?: string;
  onSection: (key: string) => void;
}) {
  const { t, label } = usePrefs();
  if (requirements.length === 0) return <EmptyState>{t("pp.r.none")}</EmptyState>;

  return (
    <div className="flex flex-col gap-3">
      <div
        aria-hidden="true"
        className="hidden grid-cols-2 gap-4 px-4 text-xs font-medium tracking-wide text-muted-foreground uppercase md:grid"
      >
        <span>{t("pp.r.requirement")}</span>
        <span>{t("pp.r.response")}</span>
      </div>
      <ol className="flex flex-col gap-3" aria-label={t("pp.tabs.requirements")}>
      {requirements.map((req, i) => {
        const answering = sectionsFor(sections, i);
        const drafted = answering.filter((s) => !isStub(s));
        const gaps = (review?.gaps ?? []).filter((g) => g.requirement_index === i);
        const problem = drafted.length === 0;
        return (
          <li
            key={i}
            id={`req-${i}`}
            tabIndex={-1}
            data-testid="requirement-row"
            className={cn(
              "grid scroll-mt-24 gap-4 rounded-xl border p-4 outline-none focus-visible:ring-2 focus-visible:ring-ring md:grid-cols-2",
              problem && req.mandatory && "border-red-300 dark:border-red-900",
              problem && !req.mandatory && "border-amber-300 dark:border-amber-900",
            )}
          >
            <div className="flex min-w-0 flex-col gap-2">
              <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase md:hidden">
                {t("pp.r.requirement")}
              </span>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs font-semibold">{t("pp.r.label", { n: i + 1 })}</span>
                <Badge variant={req.mandatory ? "default" : "outline"}>
                  {req.mandatory ? t("pp.r.mandatory") : t("pp.r.optional")}
                </Badge>
                <Badge variant="outline">{label("category", req.category)}</Badge>
              </div>
              <p className="text-sm font-medium" lang={lang}>
                {req.text}
              </p>
              <blockquote className="border-l-2 pl-3 text-xs text-muted-foreground">
                <span className="sr-only">{t("pp.r.quote")}: </span>
                {req.source_quote}
              </blockquote>
              {gaps.map((g, j) => (
                <p key={j} className="text-xs text-amber-800 dark:text-amber-300">
                  <AlertTriangle className="mr-1 inline size-3" aria-hidden="true" />
                  {g.issue}
                </p>
              ))}
            </div>
            <div className="flex min-w-0 flex-col gap-3">
              <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase md:hidden">
                {t("pp.r.response")}
              </span>
              {answering.length === 0 && (
                <p
                  className={cn(
                    "flex items-start gap-2 rounded-lg p-3 text-sm",
                    req.mandatory
                      ? "bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200"
                      : "bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200",
                  )}
                >
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                  {t("pp.r.unaddressed")}
                </p>
              )}
              {answering.map((s) => (
                <div key={s.key} className="flex flex-col gap-1.5 rounded-lg bg-muted/40 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-sm font-medium" lang={lang}>
                      {s.title}
                    </span>
                    <button
                      type="button"
                      onClick={() => onSection(s.key)}
                      className="inline-flex items-center gap-1 rounded text-xs font-medium text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                    >
                      {t("pp.r.goTo")}
                      <ArrowRight className="size-3" aria-hidden="true" />
                    </button>
                  </div>
                  {isStub(s) && (
                    <p className="text-xs text-amber-800 dark:text-amber-300">{t("pp.r.stub")}</p>
                  )}
                  <SectionBody
                    lang={lang}
                    body={s.body.length > EXCERPT ? `${s.body.slice(0, EXCERPT).trimEnd()}…` : s.body}
                  />
                </div>
              ))}
            </div>
          </li>
        );
      })}
      </ol>
    </div>
  );
}

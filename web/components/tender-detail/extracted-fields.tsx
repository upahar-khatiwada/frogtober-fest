"use client";

import { AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { TenderRecord } from "@/lib/api/tenderly";
import { formatNpr, formatNprShort } from "@/lib/format";
import { usePrefs } from "@/lib/prefs";
import { flagsFor, sourceNeedsReview, unmatchedFlags, type Source } from "@/lib/review-flags";
import { cn } from "@/lib/utils";

function ValueCell({ source }: { source: Source }) {
  const { t, lang } = usePrefs();
  const { field, value, raw } = source;
  if (value == null) {
    return raw != null ? (
      <div>
        <span className="font-medium italic text-amber-700 dark:text-amber-400">{t("td.fields.notParsed")}</span>
        <div className="font-mono text-xs text-muted-foreground">{t("td.fields.raw", { raw })}</div>
      </div>
    ) : (
      <span className="text-muted-foreground">—</span>
    );
  }
  const shown =
    typeof value === "boolean" ? (
      t(value ? "td.yes" : "td.no")
    ) : typeof value === "number" && field.endsWith("_npr") ? (
      <span title={formatNpr(value, lang)} className="tabular-nums">
        {formatNprShort(value, lang)}
      </span>
    ) : (
      <span className="break-words">{String(value)}</span>
    );
  return (
    <div>
      {shown}
      {raw != null && raw !== String(value) && <div className="font-mono text-xs text-muted-foreground">{t("td.fields.raw", { raw })}</div>}
    </div>
  );
}

/** Every extracted value next to the notice text it came from; values the parser could not confirm are badged. */
export function ExtractedFields({ record }: { record: TenderRecord | null | undefined }) {
  const { t } = usePrefs();
  const sources = record?.sources ?? [];
  const flags = record?.review_flags ?? [];
  const reviewCount = sources.filter((s) => sourceNeedsReview(s, flags)).length;
  const extra = unmatchedFlags(sources, flags);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {t("td.section.fields")}
          {reviewCount + extra.length > 0 && (
            <Badge className="bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              <AlertTriangle aria-hidden="true" />
              {t("td.fields.reviewCount", { n: reviewCount + extra.length })}
            </Badge>
          )}
        </CardTitle>
        <CardDescription>{t("td.fields.subtitle")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {sources.length === 0 ? (
          <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">{t("td.fields.empty")}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-56">{t("td.fields.colField")}</TableHead>
                <TableHead className="w-72">{t("td.fields.colValue")}</TableHead>
                <TableHead>{t("td.fields.colQuote")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.map((s, i) => {
                const review = sourceNeedsReview(s, flags);
                const reasons = flagsFor(s.field, flags).map((f) => f.reason);
                return (
                  <TableRow key={`${s.field}-${i}`} data-testid="field-row" data-review={review || undefined} className={cn(review && "bg-amber-50/70 dark:bg-amber-950/20")}>
                    <TableCell className="align-top whitespace-normal">
                      <code className="text-xs">{s.field}</code>
                      {review && (
                        <div className="mt-1">
                          <Badge className="bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                            <AlertTriangle aria-hidden="true" />
                            {t("tender.needsReview")}
                          </Badge>
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="align-top whitespace-normal">
                      <ValueCell source={s} />
                      {reasons.map((r, j) => (
                        <div key={j} className="mt-1 text-xs text-amber-800 dark:text-amber-300">
                          {t("td.fields.parser", { reason: r })}
                        </div>
                      ))}
                    </TableCell>
                    <TableCell className="align-top whitespace-normal">
                      {s.quote ? (
                        <blockquote className="border-l-2 pl-2 text-xs text-muted-foreground">{s.quote}</blockquote>
                      ) : (
                        <span className="text-xs text-muted-foreground">{t("td.fields.noQuote")}</span>
                      )}
                      {(s.quote != null || s.raw != null) && !s.quote_found && (
                        <div className="mt-1 text-xs text-amber-800 dark:text-amber-300">{t("td.fields.quoteMissing")}</div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
        {extra.length > 0 && (
          <div>
            <h3 className="mb-1 text-sm font-medium">{t("td.fields.otherFlags")}</h3>
            <ul className="flex flex-col gap-1 text-xs text-amber-800 dark:text-amber-300">
              {extra.map((f, i) => (
                <li key={i}>
                  <code>{f.field}</code>: {f.reason}
                  {f.raw ? ` (${f.raw})` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
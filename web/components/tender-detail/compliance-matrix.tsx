"use client";

import {
  ChevronDown,
  ChevronRight,
  CircleCheck,
  CircleHelp,
  CircleX,
  ExternalLink,
  ShieldAlert,
} from "lucide-react";
import { Fragment, useState } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  CompanyDocumentView,
  ComplianceItem,
  ComplianceView,
  KBChunkView,
  RuleView,
} from "@/lib/api/tenderly";
import { formatDate } from "@/lib/nepal/calendar";
import { EnumText, usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/utils";

type Status = ComplianceItem["status"];

const TONE: Record<
  Status,
  { row: string; bar: string; text: string; Icon: typeof CircleCheck }
> = {
  pass: {
    row: "bg-emerald-50/70 dark:bg-emerald-950/20",
    bar: "border-l-emerald-600",
    text: "text-emerald-800 dark:text-emerald-300",
    Icon: CircleCheck,
  },
  fail: {
    row: "bg-red-50/80 dark:bg-red-950/25",
    bar: "border-l-red-600",
    text: "text-red-800 dark:text-red-300",
    Icon: CircleX,
  },
  unclear: {
    row: "bg-amber-50/80 dark:bg-amber-950/25",
    bar: "border-l-amber-500",
    text: "text-amber-900 dark:text-amber-300",
    Icon: CircleHelp,
  },
};

export type MatrixProps = {
  compliance: ComplianceView | null | undefined;
  rules: Record<string, RuleView>;
  chunks: Record<number, KBChunkView>;
  documents: Record<number, CompanyDocumentView>;
};

function Expiry({
  expiresOn,
  isExpired,
}: {
  expiresOn?: string | null;
  isExpired?: boolean | null;
}) {
  const { t, calendar, lang } = usePrefs();
  if (!expiresOn)
    return <span className="text-muted-foreground">{t("kb.noExpiry")}</span>;
  return (
    <span>
      {t("td.cm.expires", { date: formatDate(expiresOn, calendar, lang) })}
      {isExpired && (
        <Badge variant="destructive" className="ml-1.5">
          {t("kb.expired")}
        </Badge>
      )}
    </span>
  );
}

function Highlighted({ text, quote }: { text: string; quote?: string | null }) {
  const i = quote ? text.indexOf(quote) : -1;
  if (!quote || i < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, i)}
      <mark className="rounded bg-yellow-200 px-0.5 dark:bg-yellow-700/60">
        {quote}
      </mark>
      {text.slice(i + quote.length)}
    </>
  );
}

function Evidence({
  item,
  chunks,
  documents,
}: {
  item: ComplianceItem;
  chunks: MatrixProps["chunks"];
  documents: MatrixProps["documents"];
}) {
  const { t, label } = usePrefs();
  const chunkIds = item.evidence_chunk_ids ?? [];
  const docIds = item.evidence_document_ids ?? [];
  const shownByChunks = new Set(chunkIds.map((id) => chunks[id]?.document_id));
  const docOnly = docIds.filter((id) => !shownByChunks.has(id));
  const empty =
    chunkIds.length === 0 &&
    docOnly.length === 0 &&
    !item.evidence_ref &&
    !item.evidence_quote;

  return (
    <div className="grid gap-3 text-sm">
      {item.explanation && (
        <p>
          <span className="font-medium">{t("td.cm.why")}: </span>
          {item.explanation}
        </p>
      )}
      {item.evidence_ref && (
        <p className="text-muted-foreground">
          {t("td.cm.ref", { ref: item.evidence_ref })}
        </p>
      )}
      {chunkIds.map((id) => {
        const c = chunks[id];
        return (
          <div
            key={`c${id}`}
            className="rounded-lg border bg-background p-3"
            data-testid="evidence-chunk"
          >
            <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">
                {t("td.cm.chunk", { id })}
              </span>
              {c && (
                <>
                  <span>
                    {c.filename} · {label("doc_type", c.doc_type)}
                    {c.fiscal_year_bs ? ` · FY ${c.fiscal_year_bs}` : ""}
                  </span>
                  <Expiry expiresOn={c.expires_on} isExpired={c.is_expired} />
                </>
              )}
            </div>
            {c ? (
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 text-xs">
                <Highlighted text={c.content} quote={item.evidence_quote} />
              </pre>
            ) : (
              <p className="text-xs text-muted-foreground">
                {t("td.cm.chunkMissing")}
              </p>
            )}
          </div>
        );
      })}
      {docOnly.map((id) => {
        const d = documents[id];
        return (
          <div
            key={`d${id}`}
            className="rounded-lg border bg-background p-3 text-xs"
            data-testid="evidence-document"
          >
            {d ? (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-medium text-foreground">
                  {d.filename}
                </span>
                <span className="text-muted-foreground">
                  {label("doc_type", d.doc_type)}
                  {d.fiscal_year_bs ? ` · FY ${d.fiscal_year_bs}` : ""}
                </span>
                <Expiry expiresOn={d.expires_on} isExpired={d.is_expired} />
              </div>
            ) : (
              <span className="text-muted-foreground">
                {t("td.cm.documentMissing", { id })}
              </span>
            )}
          </div>
        );
      })}
      {item.evidence_quote && chunkIds.length === 0 && (
        <blockquote className="border-l-2 pl-2 text-xs">
          <span className="font-medium">{t("td.cm.quote")}: </span>
          {item.evidence_quote}
        </blockquote>
      )}
      {empty && !item.explanation && (
        <p className="text-muted-foreground">{t("td.cm.noEvidence")}</p>
      )}
    </div>
  );
}

function RuleBadge({
  item,
  rules,
}: {
  item: ComplianceItem;
  rules: MatrixProps["rules"];
}) {
  const { t } = usePrefs();
  if (!item.rule_id) {
    return (
      <Badge
        variant="outline"
        title={t("td.cm.modelTitle")}
        className="border-violet-400 text-violet-800 dark:text-violet-300"
      >
        {t("td.cm.model")}
      </Badge>
    );
  }
  const rule = rules[item.rule_id];
  return (
    <div className="flex flex-col items-start gap-1">
      <a
        href={`#rule-${item.rule_id}`}
        title={rule?.description ?? t("td.cm.ruleUnknown")}
        className="rounded-4xl focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <Badge variant="outline" className="font-mono hover:bg-muted">
          {item.rule_id}
        </Badge>
      </a>
      {rule && (
        <span
          className={cn(
            "text-[11px] font-medium",
            rule.verified
              ? "text-emerald-700 dark:text-emerald-400"
              : "text-amber-700 dark:text-amber-400",
          )}
        >
          {t(rule.verified ? "td.cm.verified" : "td.cm.unverified")}
        </span>
      )}
    </div>
  );
}

/** The rules the matrix cites, each an anchor target for the badge links. */
export function RulesReference({
  items,
  rules,
}: {
  items: ComplianceItem[];
  rules: MatrixProps["rules"];
}) {
  const { t } = usePrefs();
  const used = [
    ...new Set(items.map((i) => i.rule_id).filter((x): x is string => !!x)),
  ].filter((id) => rules[id]);
  if (used.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("td.section.rules")}</CardTitle>
        <CardDescription>{t("td.rules.subtitle")}</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-3">
          {used.map((id) => {
            const r = rules[id];
            return (
              <li
                key={id}
                id={`rule-${id}`}
                className="scroll-mt-20 rounded-lg border p-3 text-sm target:ring-2 target:ring-ring"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono font-medium">{id}</span>
                  <Badge
                    className={
                      r.verified
                        ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
                        : "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
                    }
                  >
                    {t(r.verified ? "td.cm.verified" : "td.cm.unverified")}
                  </Badge>
                  <EnumText kind="severity" value={r.severity} />
                </div>
                <p className="mt-1">{r.description}</p>
                {r.notes && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t("td.rules.notes")}: {r.notes}
                  </p>
                )}
                <a
                  href={r.source}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-flex items-center gap-1 text-xs text-primary underline-offset-4 hover:underline"
                >
                  <ExternalLink className="size-3" aria-hidden="true" />
                  {t("td.rules.source")}
                </a>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

function SummaryBar({ compliance }: { compliance: ComplianceView }) {
  const { t, lang, calendar } = usePrefs();
  const o = compliance.override;
  const accepted = compliance.blocked && compliance.proposal_allowed;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="font-medium">
          {t("td.cm.counts", {
            ok: compliance.counts.pass ?? 0,
            fail: compliance.counts.fail ?? 0,
            unclear: compliance.counts.unclear ?? 0,
          })}
        </span>
      </div>
      {compliance.blocked && !accepted && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        >
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {t("td.cm.blocked", { n: compliance.hard_failures })}
        </div>
      )}
      {accepted && (
        <div
          role="status"
          className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
        >
          {t("td.cm.accepted", { n: compliance.hard_failures })}
        </div>
      )}
      {!compliance.blocked && (
        <p className="text-sm text-emerald-800 dark:text-emerald-300">
          {t("td.cm.clear")}
        </p>
      )}
      {o && (
        <p
          className="text-xs text-muted-foreground"
          data-testid="override-note"
        >
          {t("td.cm.override", { by: o.overridden_by, reason: o.reason })} ·{" "}
          {formatDate(o.overridden_at.slice(0, 10), calendar, lang)} ·{" "}
          {t(o.active ? "td.cm.overrideActive" : "td.cm.overrideStale")}
        </p>
      )}
    </div>
  );
}

/** Per-requirement checklist: green/red/amber rows, expandable evidence, action needed, linked rule badges. */
export function ComplianceMatrix({
  compliance,
  rules,
  chunks,
  documents,
}: MatrixProps) {
  const { t } = usePrefs();
  const [open, setOpen] = useState<Set<number>>(new Set());
  const items = compliance?.items ?? [];

  function toggle(i: number) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>{t("td.section.compliance")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {!compliance || items.length === 0 ? (
            <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
              {t("td.cm.empty")}
            </p>
          ) : (
            <>
              <SummaryBar compliance={compliance} />
              <Table aria-label={t("td.section.compliance")}>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-32">
                      {t("td.cm.colStatus")}
                    </TableHead>
                    <TableHead>{t("td.cm.colRequirement")}</TableHead>
                    <TableHead className="w-44">{t("td.cm.colRule")}</TableHead>
                    <TableHead className="w-80">
                      {t("td.cm.colAction")}
                    </TableHead>
                    <TableHead className="w-36">
                      {t("td.cm.colEvidence")}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item, i) => {
                    const tone = TONE[item.status];
                    const expanded = open.has(i);
                    return (
                      <Fragment key={i}>
                        <TableRow
                          data-testid="cm-row"
                          data-status={item.status}
                          data-severity={item.severity}
                          className={cn(tone.row)}
                        >
                          <TableCell
                            className={cn(
                              "border-l-4 align-top whitespace-normal",
                              tone.bar,
                            )}
                          >
                            <span
                              className={cn(
                                "inline-flex items-center gap-1.5 font-medium",
                                tone.text,
                              )}
                            >
                              <tone.Icon
                                className="size-4"
                                aria-hidden="true"
                              />
                              <EnumText
                                kind="compliance_status"
                                value={item.status}
                              />
                            </span>
                          </TableCell>
                          <TableCell className="align-top whitespace-normal">
                            <div>{item.requirement}</div>
                            <Badge
                              variant={
                                item.severity === "hard" ? "outline" : "ghost"
                              }
                              className="mt-1"
                            >
                              <EnumText kind="severity" value={item.severity} />
                            </Badge>
                          </TableCell>
                          <TableCell className="align-top whitespace-normal">
                            <RuleBadge item={item} rules={rules} />
                          </TableCell>
                          <TableCell className="align-top whitespace-normal">
                            {item.action_needed ? (
                              <span>{item.action_needed}</span>
                            ) : (
                              <span className="text-muted-foreground">
                                {t("td.cm.nothing")}
                              </span>
                            )}
                          </TableCell>
                          <TableCell className="align-top whitespace-normal">
                            <button
                              type="button"
                              aria-expanded={expanded}
                              aria-controls={`cm-evidence-${i}`}
                              onClick={() => toggle(i)}
                              className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs font-medium hover:bg-background/70 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                            >
                              {expanded ? (
                                <ChevronDown
                                  className="size-3.5"
                                  aria-hidden="true"
                                />
                              ) : (
                                <ChevronRight
                                  className="size-3.5"
                                  aria-hidden="true"
                                />
                              )}
                              {t(expanded ? "td.cm.hide" : "td.cm.show")}
                            </button>
                          </TableCell>
                        </TableRow>
                        {expanded && (
                          <TableRow className={cn(tone.row)}>
                            <TableCell
                              colSpan={5}
                              id={`cm-evidence-${i}`}
                              className="whitespace-normal"
                            >
                              <Evidence
                                item={item}
                                chunks={chunks}
                                documents={documents}
                              />
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
                    );
                  })}
                </TableBody>
              </Table>
            </>
          )}
        </CardContent>
      </Card>
      <RulesReference items={items} rules={rules} />
    </div>
  );
}

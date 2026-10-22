"use client";

import { Check, ChevronDown, ChevronRight, Copy } from "lucide-react";
import Link from "next/link";
import { Fragment, useState } from "react";

import { DateTime } from "@/components/date-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { AgentRunView } from "@/lib/api/tenderly";
import { formatDuration } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n/dict";
import { usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/utils";

const NAMED_MODELS: Record<string, MessageKey> = {
  human: "runs.model.human",
  deterministic: "runs.model.deterministic",
  orchestrator: "runs.model.orchestrator",
};

function ModelCell({ model }: { model: string }) {
  const { t } = usePrefs();
  const named = NAMED_MODELS[model];
  if (!named) return <code className="text-xs">{model}</code>;
  return (
    <Badge variant={model === "human" ? "default" : "secondary"} title={model}>
      {t(named)}
    </Badge>
  );
}

function CopyButton({ text }: { text: string }) {
  const { t } = usePrefs();
  const [done, setDone] = useState(false);
  return (
    <Button
      type="button"
      size="xs"
      variant="outline"
      onClick={() =>
        navigator.clipboard
          ?.writeText(text)
          .then(() => {
            setDone(true);
            setTimeout(() => setDone(false), 1500);
          })
          .catch(() => {})
      }
    >
      {done ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
      {done ? t("runs.copied") : t("runs.copy")}
    </Button>
  );
}

function Details({ row }: { row: AgentRunView }) {
  const { t } = usePrefs();
  return (
    <div className="flex flex-col gap-3 py-2" data-testid="run-details">
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">{t("runs.inputHash")}</span>
        <div className="flex flex-wrap items-center gap-2">
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs break-all" data-testid="input-hash">
            {row.input_hash}
          </code>
          <CopyButton text={row.input_hash} />
        </div>
      </div>
      {row.error && (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">{t("runs.error")}</span>
          <p className="text-sm text-destructive">{row.error}</p>
        </div>
      )}
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">{t("runs.output")}</span>
        {row.output_json ? (
          <pre className="max-h-96 overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs leading-relaxed" data-testid="output-json">
            {JSON.stringify(row.output_json, null, 2)}
          </pre>
        ) : (
          <p className="text-sm text-muted-foreground">{t("runs.noOutput")}</p>
        )}
      </div>
      {row.raw_output && (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">{t("runs.rawOutput")}</span>
          <pre className="max-h-64 overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs whitespace-pre-wrap">
            {row.raw_output}
          </pre>
        </div>
      )}
    </div>
  );
}

/** The audit log (agent_runs): one row per model call, code-only stage or human action; expand for hash + output. */
export function AgentRunsTable({ rows }: { rows: AgentRunView[] }) {
  const { t, label, lang } = usePrefs();
  const [open, setOpen] = useState<Set<number>>(new Set());
  const toggle = (id: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table data-testid="agent-runs">
        <TableHeader>
          <TableRow>
            <TableHead className="w-10" />
            <TableHead>{t("runs.col.time")}</TableHead>
            <TableHead>{t("runs.col.tender")}</TableHead>
            <TableHead>{t("runs.col.stage")}</TableHead>
            <TableHead>{t("runs.col.status")}</TableHead>
            <TableHead className="text-right">{t("runs.col.duration")}</TableHead>
            <TableHead>{t("runs.col.model")}</TableHead>
            <TableHead>{t("runs.col.run")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => {
            const expanded = open.has(row.id);
            const detailsId = `agent-run-${row.id}`;
            return (
              <Fragment key={row.id}>
                <TableRow
                  data-testid="agent-run-row"
                  data-stage={row.stage}
                  data-model={row.model}
                  className={cn(!row.ok && "bg-red-50/60 dark:bg-red-950/20")}
                >
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-expanded={expanded}
                      aria-controls={detailsId}
                      aria-label={t("runs.expand", { id: row.id })}
                      onClick={() => toggle(row.id)}
                    >
                      {expanded ? <ChevronDown aria-hidden="true" /> : <ChevronRight aria-hidden="true" />}
                    </Button>
                  </TableCell>
                  <TableCell className="text-xs whitespace-nowrap">
                    <DateTime iso={row.created_at} />
                  </TableCell>
                  <TableCell className="max-w-72 min-w-48 text-sm whitespace-normal">
                    {row.tender_id != null ? (
                      <Link
                        href={`/tenders/${row.tender_id}`}
                        className="line-clamp-2 hover:underline"
                        title={row.tender_title ?? undefined}
                      >
                        <span className="text-muted-foreground">#{row.tender_id}</span> {row.tender_title ?? ""}
                      </Link>
                    ) : (
                      t("runs.none")
                    )}
                  </TableCell>
                  <TableCell>{label("stage", row.stage)}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-1">
                      {row.ok ? (
                        <Badge className="bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
                          {t("runs.ok")}
                        </Badge>
                      ) : (
                        <Badge variant="destructive">{t("runs.failed")}</Badge>
                      )}
                      {row.cached && <Badge variant="outline">{t("runs.cached")}</Badge>}
                      {(row.attempts ?? 1) > 1 && (
                        <Badge variant="outline">{t("runs.attempts", { n: row.attempts ?? 1 })}</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{formatDuration(row.latency_ms, lang)}</TableCell>
                  <TableCell>
                    <ModelCell model={row.model} />
                  </TableCell>
                  <TableCell className="text-xs">
                    {row.pipeline_run_id != null ? (
                      <Link href={`/runs?run=${row.pipeline_run_id}`} className="text-primary hover:underline">
                        {t("runs.runLink", { id: row.pipeline_run_id })}
                      </Link>
                    ) : (
                      t("runs.none")
                    )}
                  </TableCell>
                </TableRow>
                {expanded && (
                  <TableRow id={detailsId} className="hover:bg-transparent">
                    <TableCell />
                    <TableCell colSpan={7} className="whitespace-normal">
                      <Details row={row} />
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

"use client";

import Link from "next/link";

import { DateTime } from "@/components/date-time";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { PipelineRunView } from "@/lib/api/tenderly";
import { formatDuration } from "@/lib/format";
import { usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/utils";

const RUN_CLASS: Record<PipelineRunView["status"], string> = {
  queued: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100",
  running: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  succeeded: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  stopped: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
};

/** Pipeline runs (one orchestrated pass over a tender): stages with their durations, linked to their audit rows. */
export function PipelineRunsTable({ runs }: { runs: PipelineRunView[] }) {
  const { t, label, lang } = usePrefs();
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table data-testid="pipeline-runs">
        <TableHeader>
          <TableRow>
            <TableHead>{t("runs.col.run")}</TableHead>
            <TableHead>{t("runs.col.time")}</TableHead>
            <TableHead>{t("runs.col.tender")}</TableHead>
            <TableHead>{t("runs.col.status")}</TableHead>
            <TableHead>{t("runs.col.stages")}</TableHead>
            <TableHead className="text-right">{t("runs.col.duration")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => (
            <TableRow key={run.id}>
              <TableCell className="text-xs">
                <Link href={`/runs?run=${run.id}`} className="text-primary hover:underline">
                  {t("runs.runLink", { id: run.id })}
                </Link>
              </TableCell>
              <TableCell className="text-xs whitespace-nowrap">
                <DateTime iso={run.created_at} />
              </TableCell>
              <TableCell className="max-w-64 min-w-40 text-sm whitespace-normal">
                <Link href={`/tenders/${run.tender_id}`} className="line-clamp-2 hover:underline" title={run.tender_title ?? undefined}>
                  <span className="text-muted-foreground">#{run.tender_id}</span> {run.tender_title ?? ""}
                </Link>
              </TableCell>
              <TableCell>
                <Badge className={RUN_CLASS[run.status]}>{label("run_status", run.status)}</Badge>
              </TableCell>
              <TableCell className="whitespace-normal">
                <ol className="flex flex-wrap gap-1">
                  {run.stages.map((s) => (
                    <li key={s.stage}>
                      <Badge
                        variant="outline"
                        title={s.error ?? undefined}
                        className={cn(s.status === "failed" && "border-red-400 text-red-700 dark:text-red-300")}
                      >
                        {label("stage", s.stage)}: {label("stage_status", s.status ?? "pending")}
                        {s.duration_ms != null && ` · ${formatDuration(s.duration_ms, lang)}`}
                      </Badge>
                    </li>
                  ))}
                </ol>
                {run.error && <p className="mt-1 text-xs text-destructive">{run.error}</p>}
              </TableCell>
              <TableCell className="text-right text-xs tabular-nums">{formatDuration(run.duration_ms, lang)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

"use client";

import { AlertTriangle, LoaderCircle, Play } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { DeadlineDisplay } from "@/components/deadline-display";
import { StatusBadge } from "@/components/tenders/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  analyzeTender,
  ApiError,
  generateProposal,
  getRun,
  loadTenderBundle,
  overrideCompliance,
  type PipelineRunView,
  type RuleView,
  type TenderBundle,
} from "@/lib/api/tenderly";
import type { MessageKey } from "@/lib/i18n/dict";
import { usePrefs } from "@/lib/prefs";

import { ComplianceMatrix } from "./compliance-matrix";
import { ExtractedFields } from "./extracted-fields";
import { MatchPanel } from "./match-panel";
import { NepalSummary } from "./nepal-summary";
import { OverrideDialog } from "./override-dialog";

/** Spec section 9.2: progress via polling every 2 seconds. */
export const RUN_POLL_MS = 2000;
const ACTIVE = ["queued", "running"];
const PROPOSAL_STATUSES = ["checked", "drafted", "reviewed"];

type Notice = {
  kind: "ok" | "error" | "info";
  key: MessageKey;
  vars?: Record<string, string | number>;
};
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** The tender page: header and actions, run progress, then the four panels. */
export function TenderWorkspace({
  initial,
  rules,
}: {
  initial: TenderBundle;
  rules: RuleView[];
}) {
  const { t, label } = usePrefs();
  const [bundle, setBundle] = useState(initial);
  const [run, setRun] = useState<PipelineRunView | null>(null);
  const [starting, setStarting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  const { detail } = bundle;
  const id = detail.id;
  const record = detail.record;
  const compliance = detail.compliance;
  const rulesById = useMemo(
    () => Object.fromEntries(rules.map((r) => [r.id, r])),
    [rules],
  );

  const runId = run?.id;
  const runStatus = run?.status;
  const running =
    starting || (runStatus !== undefined && ACTIVE.includes(runStatus));

  // Poll the run every 2 s while it is queued or running.
  useEffect(() => {
    if (
      runId === undefined ||
      runStatus === undefined ||
      !ACTIVE.includes(runStatus)
    )
      return;
    const timer = setInterval(() => {
      getRun(runId)
        .then(setRun)
        .catch((e) =>
          setNotice({
            kind: "error",
            key: "td.analyzeFailed",
            vars: { error: errText(e) },
          }),
        );
    }, RUN_POLL_MS);
    return () => clearInterval(timer);
  }, [runId, runStatus]);

  // When the run ends, re-read the tender (new status, match, compliance and evidence).
  useEffect(() => {
    if (
      runId === undefined ||
      runStatus === undefined ||
      ACTIVE.includes(runStatus)
    )
      return;
    let cancelled = false;
    loadTenderBundle(id)
      .then((next) => {
        if (!cancelled && next) setBundle(next);
      })
      .catch((e) => {
        if (!cancelled)
          setNotice({
            kind: "error",
            key: "td.refreshFailed",
            vars: { error: errText(e) },
          });
      });
    return () => {
      cancelled = true;
    };
  }, [runId, runStatus, id]);

  async function analyze() {
    setNotice(null);
    setStarting(true);
    try {
      setRun(await analyzeTender(id));
    } catch (e) {
      setNotice({
        kind: "error",
        key: "td.analyzeFailed",
        vars: { error: errText(e) },
      });
    } finally {
      setStarting(false);
    }
  }

  async function generate() {
    setNotice(null);
    setGenerating(true);
    try {
      setRun(await generateProposal(id)); // polled like an analyze run
      setNotice({ kind: "ok", key: "td.proposalDone" });
    } catch (e) {
      if (e instanceof ApiError && e.status === 501)
        setNotice({ kind: "info", key: "td.proposalNotBuilt" });
      else
        setNotice({
          kind: "error",
          key: "td.proposalFailed",
          vars: { error: errText(e) },
        });
    } finally {
      setGenerating(false);
    }
  }

  async function confirmOverride(by: string, reason: string) {
    await overrideCompliance(id, by, reason); // throws into the dialog, which shows the error
    setOverrideOpen(false);
    const next = await loadTenderBundle(id);
    if (next) setBundle(next);
    await generate();
  }

  const blocked =
    !!compliance && compliance.blocked && !compliance.proposal_allowed;
  const canGenerate =
    !!compliance &&
    compliance.proposal_allowed &&
    PROPOSAL_STATUSES.includes(detail.status) &&
    !running &&
    !generating;
  const whyDisabled: MessageKey | null = canGenerate
    ? null
    : running
      ? "td.whyRunning"
      : blocked
        ? "td.whyBlocked"
        : "td.whyNotChecked";
  const failures = (compliance?.items ?? []).filter(
    (i) => i.status === "fail" && i.severity === "hard",
  );
  const notExtracted = !record && !compliance && !detail.match;
  const lastError = run?.status === "failed" ? run.error : null;

  return (
    <div className="flex flex-col gap-5">
      <Link
        href="/"
        className="w-fit text-sm text-muted-foreground hover:text-foreground"
      >
        ← {t("td.back")}
      </Link>

      <header className="grid gap-4 md:grid-cols-[1fr_auto] md:items-start">
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex flex-wrap items-start gap-2">
            <h1
              className="min-w-0 flex-1 text-2xl font-semibold leading-snug tracking-tight"
              lang={record?.language === "ne" ? "ne" : undefined}
            >
              {record?.title ?? (
                <span className="text-muted-foreground">
                  {t("tender.untitled")}
                </span>
              )}
            </h1>
            <StatusBadge status={detail.status} />
          </div>
          {record && (
            <p className="text-sm text-muted-foreground">
              <span className="text-foreground">{record.buyer}</span>
              {record.reference_no ? ` · ${record.reference_no}` : ""}
            </p>
          )}
        </div>
        <div className="md:w-56">
          <DeadlineDisplay deadline={detail.deadline_view} />
        </div>
      </header>

      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={analyze} disabled={running}>
            {running ? (
              <LoaderCircle className="animate-spin" aria-hidden="true" />
            ) : (
              <Play aria-hidden="true" />
            )}
            {running ? t("td.analyzing") : t("td.analyze")}
          </Button>
          <Button
            variant="outline"
            onClick={generate}
            disabled={!canGenerate}
            aria-describedby={whyDisabled ? "generate-why" : undefined}
          >
            {generating && (
              <LoaderCircle className="animate-spin" aria-hidden="true" />
            )}
            {generating ? t("td.generating") : t("td.generate")}
          </Button>
          {blocked && failures.length > 0 && !running && (
            <Button variant="destructive" onClick={() => setOverrideOpen(true)}>
              {t("td.override")}
            </Button>
          )}
        </div>
        {whyDisabled && (
          <p id="generate-why" className="text-xs text-muted-foreground">
            {t(whyDisabled)}
          </p>
        )}
        <p role="status" aria-live="polite" className="min-h-5 text-sm">
          {notice && (
            <span
              className={
                notice.kind === "error"
                  ? "text-destructive"
                  : notice.kind === "ok"
                    ? "text-emerald-700 dark:text-emerald-400"
                    : "text-muted-foreground"
              }
            >
              {t(notice.key, notice.vars)}
            </span>
          )}
        </p>
      </div>

      {run && (
        <Card size="sm" aria-live="polite">
          <CardContent className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              {running && (
                <LoaderCircle
                  className="size-4 animate-spin"
                  aria-hidden="true"
                />
              )}
              <span className="font-medium">
                {t("td.run.title", { id: run.id })}
              </span>
              <Badge variant="outline">{label("run_status", run.status)}</Badge>
              {running && (
                <span className="text-xs text-muted-foreground">
                  {t("td.run.polling")}
                </span>
              )}
            </div>
            <ol className="flex flex-wrap gap-2">
              {run.stages.map((s) => (
                <li key={s.stage}>
                  <Badge variant="outline">
                    {label("stage", s.stage)}: {label("stage_status", s.status)}
                  </Badge>
                </li>
              ))}
            </ol>
            {run.error && (
              <p className="text-sm text-destructive">
                {t("td.run.error", { error: run.error })}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {detail.status === "failed" && !running && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
        >
          <AlertTriangle
            className="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          {lastError
            ? t("td.statusFailedWith", { error: lastError })
            : t("td.statusFailed")}
        </div>
      )}

      {notExtracted && detail.status !== "failed" && (
        <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
          {t("td.notExtracted")}
        </p>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <NepalSummary record={record} />
        <MatchPanel match={detail.match} />
      </div>

      <ComplianceMatrix
        compliance={compliance}
        rules={rulesById}
        chunks={bundle.chunks}
        documents={bundle.documents}
      />

      <ExtractedFields record={record} />

      <OverrideDialog
        open={overrideOpen}
        onOpenChange={setOverrideOpen}
        failures={failures}
        onConfirm={confirmOverride}
      />
    </div>
  );
}

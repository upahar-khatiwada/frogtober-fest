"use client";

import { CheckCircle2, Circle, LoaderCircle, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";

import { formatDateTime } from "@/components/date-time";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { Proposal } from "@/lib/api/tenderly";
import type { MessageKey } from "@/lib/i18n/dict";
import { usePrefs } from "@/lib/prefs";
import { rememberName, rememberedName, type ApprovalGates } from "@/lib/proposal";

function ApproveDialog({
  open,
  onOpenChange,
  version,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  version: number;
  onConfirm: (by: string, note: string | null) => Promise<void>;
}) {
  const { t } = usePrefs();
  const [by, setBy] = useState(rememberedName);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!by.trim()) return;
    setBusy(true);
    setError(null);
    try {
      rememberName(by.trim());
      await onConfirm(by.trim(), note.trim() || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("pp.ap.dialogTitle")}</DialogTitle>
          <DialogDescription>{t("pp.ap.dialogBody")}</DialogDescription>
        </DialogHeader>
        <form id="approve-form" onSubmit={submit} className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ap-by">{t("pp.ap.by")}</Label>
            <Input id="ap-by" value={by} maxLength={200} onChange={(e) => setBy(e.target.value)} required />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ap-note">{t("pp.ap.note")}</Label>
            <Textarea id="ap-note" rows={3} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {t("pp.ap.failed", { error })}
            </p>
          )}
        </form>
        <DialogFooter>
          <Button type="button" variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>
            {t("pp.ap.cancel")}
          </Button>
          <Button type="submit" form="approve-form" disabled={!by.trim() || busy}>
            {busy && <LoaderCircle className="animate-spin" aria-hidden="true" />}
            {busy ? t("pp.ap.saving") : t("pp.ap.confirm", { version })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * The human gate (spec section 9.2): Approve stays disabled until the verdict is not "fail" and the person has
 * opened this version since its review. Each condition is listed with its state, so the reason is never hidden.
 */
export function ApprovalPanel({
  proposal,
  gates,
  opening,
  onApprove,
}: {
  proposal: Proposal;
  gates: ApprovalGates;
  opening: boolean;
  onApprove: (by: string, note: string | null) => Promise<void>;
}) {
  const { t, calendar, lang } = usePrefs();
  const [open, setOpen] = useState(false);
  const conditions: [MessageKey, boolean][] = [
    ["pp.ap.gateReviewed", gates.reviewed],
    ["pp.ap.gateVerdict", gates.verdictOk],
    ["pp.ap.gateOpened", gates.opened],
    ["pp.ap.gateLatest", gates.latest],
  ];

  return (
    <Card size="sm" aria-labelledby="approval-title" data-testid="approval-panel">
      <CardHeader>
        <CardTitle>
          <h2 id="approval-title" className="text-base font-semibold">
            {t("pp.ap.title")}
          </h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {gates.approved ? (
          <p className="flex items-start gap-2 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200" data-testid="approved">
            <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>
              {t("pp.ap.approved", {
                name: proposal.approved_by ?? "?",
                date: proposal.approved_at ? formatDateTime(proposal.approved_at, calendar, lang) : "",
              })}
              {proposal.approval_note && <span className="mt-1 block text-xs">“{proposal.approval_note}”</span>}
            </span>
          </p>
        ) : (
          <>
            <ul className="flex flex-col gap-1.5 text-sm" aria-label={t("pp.ap.title")}>
              {conditions.map(([key, ok]) => (
                <li key={key} className="flex items-start gap-2" data-met={ok}>
                  {ok ? (
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />
                  ) : (
                    <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  )}
                  <span>
                    {t(key)}
                    <span className="sr-only"> ({ok ? t("pp.ap.met") : t("pp.ap.notMet")})</span>
                  </span>
                </li>
              ))}
            </ul>
            {opening && (
              <p role="status" className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <LoaderCircle className="size-3 animate-spin" aria-hidden="true" />
                {t("pp.ap.opening")}
              </p>
            )}
            <Button
              size="lg"
              onClick={() => setOpen(true)}
              disabled={!gates.canApprove}
              aria-describedby={gates.canApprove ? undefined : "approve-why"}
            >
              <ShieldCheck aria-hidden="true" />
              {t("pp.ap.approve")}
            </Button>
            {!gates.canApprove && (
              <p id="approve-why" className="text-xs text-muted-foreground">
                {t("pp.ap.disabled")}
              </p>
            )}
          </>
        )}
        <ApproveDialog
          open={open}
          onOpenChange={setOpen}
          version={proposal.version}
          onConfirm={async (by, note) => {
            await onApprove(by, note);
            setOpen(false);
          }}
        />
      </CardContent>
    </Card>
  );
}

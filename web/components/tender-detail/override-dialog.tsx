"use client";

import { LoaderCircle } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
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
import type { ComplianceItem } from "@/lib/api/tenderly";
import { usePrefs } from "@/lib/prefs";

/** Confirmation that records who accepts the hard failures, and why (POST .../compliance/override). */
export function OverrideDialog({
  open,
  onOpenChange,
  failures,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  failures: ComplianceItem[];
  onConfirm: (overriddenBy: string, reason: string) => Promise<void>;
}) {
  const { t } = usePrefs();
  const [by, setBy] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = by.trim().length > 0 && reason.trim().length > 0;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      await onConfirm(by.trim(), reason.trim());
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
          <DialogTitle>{t("td.ov.title")}</DialogTitle>
          <DialogDescription>{t("td.ov.body")}</DialogDescription>
        </DialogHeader>
        <form
          id="override-form"
          onSubmit={submit}
          className="flex flex-col gap-3"
        >
          <div>
            <h3 className="mb-1 text-sm font-medium">{t("td.ov.failures")}</h3>
            <ul className="flex flex-col gap-1 text-sm">
              {failures.map((f, i) => (
                <li
                  key={i}
                  className="rounded border-l-4 border-l-red-600 bg-red-50 px-2 py-1 dark:bg-red-950/30"
                >
                  {f.rule_id && (
                    <code className="mr-2 text-xs">{f.rule_id}</code>
                  )}
                  {f.requirement}
                </li>
              ))}
            </ul>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ov-by">{t("td.ov.by")}</Label>
            <Input
              id="ov-by"
              value={by}
              maxLength={200}
              onChange={(e) => setBy(e.target.value)}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ov-reason">{t("td.ov.reason")}</Label>
            <Textarea
              id="ov-reason"
              rows={3}
              value={reason}
              maxLength={2000}
              onChange={(e) => setReason(e.target.value)}
              required
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {t("td.ov.failed", { error })}
            </p>
          )}
        </form>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => onOpenChange(false)}
          >
            {t("td.ov.cancel")}
          </Button>
          <Button
            type="submit"
            form="override-form"
            variant="destructive"
            disabled={!valid || busy}
          >
            {busy && (
              <LoaderCircle className="animate-spin" aria-hidden="true" />
            )}
            {busy ? t("td.ov.saving") : t("td.ov.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

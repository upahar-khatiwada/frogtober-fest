"use client";

import { Download, LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { scrapeTenders, type ScrapeReport } from "@/lib/api/tenderly";
import { usePrefs } from "@/lib/prefs";

/** POST /tenders/scrape (seed source: offline, idempotent), then re-render the list. */
export function LoadTendersButton() {
  const router = useRouter();
  const { t } = usePrefs();
  const [busy, setBusy] = useState(false);
  const [refreshing, startTransition] = useTransition();
  const [report, setReport] = useState<ScrapeReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      const r = await scrapeTenders();
      setReport(r);
      startTransition(() => router.refresh());
    } catch (e) {
      setReport(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const loading = busy || refreshing;
  return (
    <div className="flex flex-col items-end gap-1">
      <Button onClick={load} disabled={loading}>
        {loading ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Download aria-hidden="true" />}
        {loading ? t("dashboard.loading") : t("dashboard.load")}
      </Button>
      <p role="status" className="min-h-4 text-xs text-muted-foreground">
        {report && t("dashboard.loaded", { created: report.created, updated: report.updated, unchanged: report.unchanged })}
        {error && <span className="text-destructive">{t("dashboard.loadFailed", { error })}</span>}
      </p>
    </div>
  );
}

"use client";

import { RefreshCw } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { usePrefs } from "@/lib/prefs";
import { RUN_POLL_MS } from "@/lib/use-polled-run";

const STAGES = ["scout", "matching", "compliance", "proposal", "review"];

/** Stage / status filters (the URL is the state), a refresh button, and 2 s auto-refresh while a run is active. */
export function RunsControls({ live }: { live: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [pending, startTransition] = useTransition();
  const { t, label } = usePrefs();

  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => router.refresh(), RUN_POLL_MS);
    return () => clearInterval(timer);
  }, [live, router]);

  function apply(param: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(param, value);
    else next.delete(param);
    startTransition(() => router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false }));
  }

  return (
    <div className="flex flex-wrap items-end gap-3" aria-busy={pending}>
      <div className="flex flex-col gap-1">
        <Label htmlFor="runs-stage">{t("runs.col.stage")}</Label>
        <NativeSelect id="runs-stage" size="sm" value={params.get("stage") ?? ""} onChange={(e) => apply("stage", e.target.value)}>
          <NativeSelectOption value="">{t("runs.filter.all")}</NativeSelectOption>
          {STAGES.map((s) => (
            <NativeSelectOption key={s} value={s}>
              {label("stage", s)}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="runs-ok">{t("runs.col.status")}</Label>
        <NativeSelect id="runs-ok" size="sm" value={params.get("ok") ?? ""} onChange={(e) => apply("ok", e.target.value)}>
          <NativeSelectOption value="">{t("runs.filter.all")}</NativeSelectOption>
          <NativeSelectOption value="true">{t("runs.ok")}</NativeSelectOption>
          <NativeSelectOption value="false">{t("runs.failed")}</NativeSelectOption>
        </NativeSelect>
      </div>
      <Button variant="outline" size="sm" onClick={() => startTransition(() => router.refresh())} disabled={pending}>
        <RefreshCw className={pending ? "animate-spin" : undefined} aria-hidden="true" />
        {t("runs.refresh")}
      </Button>
      {live && (
        <p role="status" className="text-xs text-muted-foreground">
          {t("runs.live")}
        </p>
      )}
    </div>
  );
}

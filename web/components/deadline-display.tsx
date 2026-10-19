"use client";

import { Clock } from "lucide-react";

import type { DeadlineView } from "@/lib/api/tenderly";
import { useNow } from "@/lib/clock";
import { countdown, countdownFromView, countdownText, nptTime, type Urgency } from "@/lib/deadline";
import { formatAd, toDevanagariDigits } from "@/lib/nepal/calendar";
import { usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/utils";

const URGENCY_CLASS: Record<Urgency, string> = {
  passed: "bg-muted text-muted-foreground line-through decoration-1",
  today: "bg-red-600 text-white dark:bg-red-500",
  urgent: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
  soon: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  ok: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
};

/**
 * A deadline in both calendars (the preferred one first) with a live countdown in NPT.
 * BS strings come from the API (DeadlineView, nepal.dates); nothing is re-derived here.
 */
export function DeadlineDisplay({ deadline }: { deadline: DeadlineView | null | undefined }) {
  const { lang, calendar, t } = usePrefs();
  const now = useNow();
  if (!deadline) {
    return <span className="text-sm text-muted-foreground">{t("tender.noDeadline")}</span>;
  }
  const c = now ? countdown(deadline.ad, now) : countdownFromView(deadline);
  const time = nptTime(deadline.ad);
  const bs = lang === "ne" ? deadline.bs_ne : deadline.bs_long;
  const ad = formatAd(deadline.ad_date, lang);
  const [primary, secondary] = calendar === "BS" ? [`${bs} BS`, `${ad} AD`] : [`${ad} AD`, `${bs} BS`];
  return (
    <div className="flex flex-col gap-1 text-sm" data-testid="deadline">
      <span
        className={cn("inline-flex w-fit items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium", URGENCY_CLASS[c.urgency])}
        data-urgency={c.urgency}
      >
        <Clock className="size-3" aria-hidden="true" />
        {countdownText(c, lang)}
      </span>
      <span className="font-medium">
        {primary}, {lang === "ne" ? toDevanagariDigits(time) : time} NPT
      </span>
      <span className="text-xs text-muted-foreground">{secondary}</span>
    </div>
  );
}

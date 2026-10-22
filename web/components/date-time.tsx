"use client";

import type { Lang } from "@/lib/format";
import { nptDate, nptTime } from "@/lib/deadline";
import { translate } from "@/lib/i18n/dict";
import { formatDate, toDevanagariDigits } from "@/lib/nepal/calendar";
import { usePrefs, type Calendar } from "@/lib/prefs";

/**
 * "22 Kartik 2083 BS, 10:00 NPT": an instant in Nepal Time, in the given calendar. The NPT date is taken
 * first, so 20:00 UTC is the next day, like the API's DeadlineView.
 */
export function formatDateTime(iso: string, calendar: Calendar, lang: Lang, time = true): string {
  const day = formatDate(nptDate(new Date(iso)), calendar, lang);
  if (!time) return `${day} ${calendar}`;
  const clock = nptTime(iso);
  return `${day} ${calendar}, ${lang === "ne" ? toDevanagariDigits(clock) : clock} ${translate(lang, "common.npt")}`;
}

/** A timestamp in the preferred calendar (BS/AD toggle), with the other calendar on hover. */
export function DateTime({
  iso,
  time = true,
  className,
}: {
  iso: string | null | undefined;
  time?: boolean;
  className?: string;
}) {
  const { calendar, lang, t } = usePrefs();
  if (!iso) return <span className={className}>{t("runs.none")}</span>;
  const other = calendar === "BS" ? "AD" : "BS";
  return (
    <time dateTime={iso} title={formatDateTime(iso, other, lang, time)} className={className}>
      {formatDateTime(iso, calendar, lang, time)}
    </time>
  );
}

/**
 * Deadline countdown in Nepal Time (UTC+05:45). Calendar-day counts match the API's
 * DeadlineView.days_left: days between the NPT dates of "now" and of the deadline.
 */
import type { Lang } from "@/lib/format";
import { translate } from "@/lib/i18n/dict";

export const NPT_OFFSET_MS = (5 * 60 + 45) * 60_000;
const DAY_MS = 86_400_000;

/** The NPT calendar date ("YYYY-MM-DD") of an instant. */
export function nptDate(instant: Date): string {
  return new Date(instant.getTime() + NPT_OFFSET_MS).toISOString().slice(0, 10);
}

/** Calendar days from today (NPT) to the deadline's NPT date; negative once passed. */
export function daysLeftNpt(deadline: Date, now: Date): number {
  return Math.round((Date.parse(nptDate(deadline)) - Date.parse(nptDate(now))) / DAY_MS);
}

export type Urgency = "passed" | "today" | "urgent" | "soon" | "ok";

export type Countdown = {
  passed: boolean;
  /** NPT calendar days (API semantics). */
  daysLeft: number;
  /** Whole hours and minutes until the deadline instant (0 once passed). */
  hours: number;
  minutes: number;
  urgency: Urgency;
};

/** Countdown to an ISO deadline instant. Deadlines within 3 days are urgent, within 7 soon. */
export function countdown(deadlineIso: string, now: Date): Countdown {
  const deadline = new Date(deadlineIso);
  if (Number.isNaN(deadline.getTime())) throw new Error(`invalid deadline: ${deadlineIso}`);
  const ms = deadline.getTime() - now.getTime();
  const passed = ms <= 0;
  const daysLeft = daysLeftNpt(deadline, now);
  const totalMinutes = passed ? 0 : Math.floor(ms / 60_000);
  let urgency: Urgency = "ok";
  if (passed) urgency = "passed";
  else if (daysLeft <= 0) urgency = "today";
  else if (daysLeft <= 3) urgency = "urgent";
  else if (daysLeft <= 7) urgency = "soon";
  return {
    passed,
    daysLeft,
    hours: Math.floor(totalMinutes / 60),
    minutes: totalMinutes % 60,
    urgency,
  };
}

/** Countdown from the API's DeadlineView alone (server render, before the live clock starts). */
export function countdownFromView(view: { days_left: number; passed: boolean }): Countdown {
  const { days_left: daysLeft, passed } = view;
  let urgency: Urgency = "ok";
  if (passed) urgency = "passed";
  else if (daysLeft <= 0) urgency = "today";
  else if (daysLeft <= 3) urgency = "urgent";
  else if (daysLeft <= 7) urgency = "soon";
  return { passed, daysLeft, hours: -1, minutes: -1, urgency };
}

/** Human countdown text. `hours < 0` means "not known yet" (no live clock). */
export function countdownText(c: Countdown, lang: Lang): string {
  if (c.passed) return c.daysLeft < 0 ? translate(lang, "countdown.passed", { n: -c.daysLeft }) : translate(lang, "countdown.passedToday");
  if (c.hours >= 0 && c.hours < 24) {
    return c.daysLeft <= 0
      ? translate(lang, "countdown.today", { h: c.hours, m: c.minutes })
      : translate(lang, "countdown.hours", { h: c.hours, m: c.minutes });
  }
  if (c.daysLeft <= 0) return translate(lang, "countdown.dueToday");
  if (c.daysLeft === 1) return translate(lang, "countdown.day");
  return translate(lang, "countdown.days", { n: c.daysLeft });
}

/** "HH:MM" of the deadline in NPT, for display next to the date. */
export function nptTime(deadlineIso: string): string {
  return new Date(new Date(deadlineIso).getTime() + NPT_OFFSET_MS).toISOString().slice(11, 16);
}

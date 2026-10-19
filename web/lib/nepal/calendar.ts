/**
 * Bikram Sambat (BS) <-> AD conversion and display.
 *
 * The month-length table is exported from the backend (`api/scripts/export_bs_calendar.py`,
 * nepali-datetime), so the UI shows exactly the BS dates the API computes. Never compute BS
 * arithmetically (NEPAL_CONTEXT section 7). Dates are plain calendar dates ("YYYY-MM-DD"), so no
 * timezone is involved here; see lib/deadline.ts for NPT instants.
 */
import table from "./bs-calendar.json";

export type BSDate = { year: number; month: number; day: number };

type YearRow = { start_ad: string; months: number[] };
const YEARS = table.years as Record<string, YearRow>;
export const BS_MIN_YEAR = table.min_year;
export const BS_MAX_YEAR = table.max_year;

/** Same spellings as api/nepal/dates.py MONTHS_EN / MONTHS_NE. */
export const MONTHS_EN = ["Baisakh", "Jestha", "Asar", "Shrawan", "Bhadra", "Asoj", "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"];
export const MONTHS_NE = ["बैशाख", "जेठ", "असार", "साउन", "भदौ", "असोज", "कात्तिक", "मंसिर", "पुस", "माघ", "फागुन", "चैत"];

const DEVANAGARI_DIGITS = "०१२३४५६७८९";
const DAY_MS = 86_400_000;

export function toDevanagariDigits(text: string | number): string {
  return String(text).replace(/[0-9]/g, (d) => DEVANAGARI_DIGITS[Number(d)]);
}

export function toAsciiDigits(text: string): string {
  return text.replace(/[०-९]/g, (d) => String(DEVANAGARI_DIGITS.indexOf(d)));
}

const ISO_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Days since 1970-01-01 for an AD ISO date. */
function adDayNumber(iso: string): number {
  const m = ISO_RE.exec(iso);
  if (!m) throw new Error(`not an ISO date: ${iso}`);
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const t = Date.UTC(y, mo - 1, d);
  const back = new Date(t);
  if (back.getUTCFullYear() !== y || back.getUTCMonth() !== mo - 1 || back.getUTCDate() !== d) {
    throw new Error(`invalid AD date: ${iso}`);
  }
  return t / DAY_MS;
}

function adFromDayNumber(n: number): string {
  return new Date(n * DAY_MS).toISOString().slice(0, 10);
}

/** Days in a BS month (from the table). Throws outside the table's range. */
export function daysInBsMonth(year: number, month: number): number {
  const row = YEARS[String(year)];
  if (!row || month < 1 || month > 12) throw new Error(`BS month outside the table: ${year}-${month}`);
  return row.months[month - 1];
}

export function isValidBs(bs: BSDate): boolean {
  const row = YEARS[String(bs.year)];
  return (
    !!row &&
    Number.isInteger(bs.month) &&
    bs.month >= 1 &&
    bs.month <= 12 &&
    Number.isInteger(bs.day) &&
    bs.day >= 1 &&
    bs.day <= row.months[bs.month - 1]
  );
}

/** "2083-08-05" or "२०८३-०८-०५" -> BSDate, or null if it is not a real BS date in the table. */
export function parseBsIso(text: string): BSDate | null {
  const m = ISO_RE.exec(toAsciiDigits(text.trim()));
  if (!m) return null;
  const bs = { year: Number(m[1]), month: Number(m[2]), day: Number(m[3]) };
  return isValidBs(bs) ? bs : null;
}

export function bsToIso(bs: BSDate): string {
  return `${bs.year}-${String(bs.month).padStart(2, "0")}-${String(bs.day).padStart(2, "0")}`;
}

/** BS -> AD ISO date. Throws outside the table's range or on an invalid date. */
export function bsToAd(bs: BSDate): string {
  if (!isValidBs(bs)) throw new Error(`invalid BS date: ${bsToIso(bs)}`);
  const row = YEARS[String(bs.year)];
  let offset = bs.day - 1;
  for (let i = 0; i < bs.month - 1; i++) offset += row.months[i];
  return adFromDayNumber(adDayNumber(row.start_ad) + offset);
}

/** AD ISO date -> BS. Throws outside the table's range. */
export function adToBs(adIso: string): BSDate {
  const n = adDayNumber(adIso);
  for (let year = BS_MIN_YEAR; year <= BS_MAX_YEAR; year++) {
    const row = YEARS[String(year)];
    let offset = n - adDayNumber(row.start_ad);
    const total = row.months.reduce((a, b) => a + b, 0);
    if (offset < 0) break;
    if (offset >= total) continue;
    for (let month = 1; month <= 12; month++) {
      const len = row.months[month - 1];
      if (offset < len) return { year, month, day: offset + 1 };
      offset -= len;
    }
  }
  throw new Error(`AD date outside the BS table (${BS_MIN_YEAR}-${BS_MAX_YEAR}): ${adIso}`);
}

/** "5 Mangsir 2083" (en) or "५ मंसिर २०८३" (ne), the same forms as the API's DeadlineView. */
export function formatBs(bs: BSDate, lang: "en" | "ne" = "en"): string {
  if (lang === "ne") return `${toDevanagariDigits(bs.day)} ${MONTHS_NE[bs.month - 1]} ${toDevanagariDigits(bs.year)}`;
  return `${bs.day} ${MONTHS_EN[bs.month - 1]} ${bs.year}`;
}

const MONTHS_AD_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_AD_NE = ["जनवरी", "फेब्रुअरी", "मार्च", "अप्रिल", "मे", "जुन", "जुलाई", "अगस्ट", "सेप्टेम्बर", "अक्टोबर", "नोभेम्बर", "डिसेम्बर"];

/** "21 Nov 2026" (en) or "२१ नोभेम्बर २०२६" (ne) for an AD ISO date. */
export function formatAd(adIso: string, lang: "en" | "ne" = "en"): string {
  const [y, m, d] = adIso.slice(0, 10).split("-").map(Number);
  if (lang === "ne") return `${toDevanagariDigits(d)} ${MONTHS_AD_NE[m - 1]} ${toDevanagariDigits(y)}`;
  return `${d} ${MONTHS_AD_EN[m - 1]} ${y}`;
}

/** Format an AD ISO date in the user's preferred calendar; falls back to AD outside the BS table. */
export function formatDate(adIso: string, calendar: "BS" | "AD", lang: "en" | "ne" = "en"): string {
  if (calendar === "BS") {
    try {
      return formatBs(adToBs(adIso.slice(0, 10)), lang);
    } catch {
      return formatAd(adIso, lang);
    }
  }
  return formatAd(adIso, lang);
}

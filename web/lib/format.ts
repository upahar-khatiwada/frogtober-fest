/**
 * NPR display in the South Asian system (NEPAL_CONTEXT section 9): 1 lakh = 1,00,000 and
 * 1 crore = 1,00,00,000. Amounts arrive from the API as integer NPR; this is display only.
 */
import { toDevanagariDigits } from "@/lib/nepal/calendar";

export type Lang = "en" | "ne";

const LAKH = 100_000;
const CRORE = 10_000_000;

/** 14875000 -> "1,48,75,000" (last three digits, then groups of two). */
export function groupLakh(amount: number): string {
  const negative = amount < 0;
  const digits = String(Math.trunc(Math.abs(amount)));
  const last3 = digits.slice(-3);
  const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return (negative ? "-" : "") + (rest ? `${rest},${last3}` : last3);
}

function digits(text: string, lang: Lang): string {
  return lang === "ne" ? toDevanagariDigits(text) : text;
}

/** Full amount: "Rs. 1,48,75,000" / "रु. १,४८,७५,०००". */
export function formatNpr(amount: number, lang: Lang = "en"): string {
  return `${lang === "ne" ? "रु." : "Rs."} ${digits(groupLakh(amount), lang)}`;
}

function trimDecimals(value: number, places: number): string {
  return value.toFixed(places).replace(/\.?0+$/, "");
}

/**
 * Short amount: 14875000 -> "Rs. 1.49 crore" / "रु. १.४९ करोड"; 7500000 -> "Rs. 75 lakh";
 * amounts below one lakh are shown in full.
 */
export function formatNprShort(amount: number, lang: Lang = "en"): string {
  const prefix = lang === "ne" ? "रु." : "Rs.";
  const abs = Math.abs(amount);
  const sign = amount < 0 ? "-" : "";
  if (abs >= CRORE) {
    return `${prefix} ${sign}${digits(trimDecimals(abs / CRORE, 2), lang)} ${lang === "ne" ? "करोड" : "crore"}`;
  }
  if (abs >= LAKH) {
    return `${prefix} ${sign}${digits(trimDecimals(abs / LAKH, 2), lang)} ${lang === "ne" ? "लाख" : "lakh"}`;
  }
  return formatNpr(amount, lang);
}

/** Run durations: 840 -> "840 ms", 6100 -> "6.1 s", 85500 -> "1 min 26 s" (Devanagari digits in Nepali). */
export function formatDuration(ms: number | null | undefined, lang: Lang = "en"): string {
  if (ms == null) return "–";
  let text: string;
  if (ms < 1000) text = `${Math.round(ms)} ms`;
  else if (ms < 60_000) text = `${trimDecimals(ms / 1000, ms < 10_000 ? 1 : 0)} s`;
  else {
    const s = Math.round(ms / 1000);
    text = `${Math.floor(s / 60)} min ${s % 60} s`;
  }
  return digits(text, lang);
}

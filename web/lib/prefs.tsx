"use client";

/**
 * UI preferences kept in localStorage: label language (en/ne) and date calendar (BS/AD).
 * Every consumer reads them through its own useSyncExternalStore, so each component's server render and
 * hydration use the defaults (English, BS) and the stored choice applies right after, with no hydration
 * mismatch. That includes Suspense boundaries that stream in and hydrate after the stored choice applied
 * (a shared context value would already be Nepali there while the server HTML is English).
 */
import { useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";

import type { Lang } from "@/lib/format";
import { enumLabel, translate, type EnumKind, type MessageKey } from "@/lib/i18n/dict";

export type Calendar = "BS" | "AD";

export const LANG_KEY = "tenderly.lang";
export const CALENDAR_KEY = "tenderly.calendar";
export const DEFAULT_LANG: Lang = "en";
export const DEFAULT_CALENDAR: Calendar = "BS";

const CHANGE_EVENT = "tenderly:prefs";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

function write(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage blocked (private mode): the choice still applies for this page view.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

type Prefs = {
  lang: Lang;
  calendar: Calendar;
  setLang: (lang: Lang) => void;
  setCalendar: (calendar: Calendar) => void;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
  label: (kind: EnumKind, value: string) => string;
};

const setLang = (value: Lang) => write(LANG_KEY, value);
const setCalendar = (value: Calendar) => write(CALENDAR_KEY, value);

/** Preferences (defaults during SSR and each component's hydration; the stored choice right after). */
export function usePrefs(): Prefs {
  const storedLang = useSyncExternalStore(subscribe, () => read(LANG_KEY), () => null);
  const storedCalendar = useSyncExternalStore(subscribe, () => read(CALENDAR_KEY), () => null);
  const lang: Lang = storedLang === "ne" || storedLang === "en" ? storedLang : DEFAULT_LANG;
  const calendar: Calendar = storedCalendar === "AD" || storedCalendar === "BS" ? storedCalendar : DEFAULT_CALENDAR;

  return useMemo<Prefs>(
    () => ({
      lang,
      calendar,
      setLang,
      setCalendar,
      t: (key, vars) => translate(lang, key, vars),
      label: (kind, v) => enumLabel(lang, kind, v),
    }),
    [lang, calendar],
  );
}

/** Keeps <html lang> in step with the language preference. */
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const { lang } = usePrefs();
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  return <>{children}</>;
}

/** A translated label, usable from server components. */
export function T({ k, vars }: { k: MessageKey; vars?: Record<string, string | number> }) {
  return <>{usePrefs().t(k, vars)}</>;
}

/** A translated API enum value, usable from server components. */
export function EnumText({ kind, value }: { kind: EnumKind; value: string }) {
  return <>{usePrefs().label(kind, value)}</>;
}

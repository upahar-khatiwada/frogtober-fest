"use client";

/**
 * UI preferences kept in localStorage: label language (en/ne) and date calendar (BS/AD).
 * Read through useSyncExternalStore, so the server render and hydration use the defaults
 * (English, BS) and the stored choice applies right after, with no hydration mismatch.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";

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

const PrefsContext = createContext<Prefs | null>(null);

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const storedLang = useSyncExternalStore(subscribe, () => read(LANG_KEY), () => null);
  const storedCalendar = useSyncExternalStore(subscribe, () => read(CALENDAR_KEY), () => null);
  const lang: Lang = storedLang === "ne" || storedLang === "en" ? storedLang : DEFAULT_LANG;
  const calendar: Calendar = storedCalendar === "AD" || storedCalendar === "BS" ? storedCalendar : DEFAULT_CALENDAR;

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((value: Lang) => write(LANG_KEY, value), []);
  const setCalendar = useCallback((value: Calendar) => write(CALENDAR_KEY, value), []);

  const value = useMemo<Prefs>(
    () => ({
      lang,
      calendar,
      setLang,
      setCalendar,
      t: (key, vars) => translate(lang, key, vars),
      label: (kind, v) => enumLabel(lang, kind, v),
    }),
    [lang, calendar, setLang, setCalendar],
  );
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}

/** Preferences; outside a provider (e.g. isolated tests) the defaults apply. */
export function usePrefs(): Prefs {
  const ctx = useContext(PrefsContext);
  if (ctx) return ctx;
  return {
    lang: DEFAULT_LANG,
    calendar: DEFAULT_CALENDAR,
    setLang: () => {},
    setCalendar: () => {},
    t: (key, vars) => translate(DEFAULT_LANG, key, vars),
    label: (kind, v) => enumLabel(DEFAULT_LANG, kind, v),
  };
}

/** A translated label, usable from server components. */
export function T({ k, vars }: { k: MessageKey; vars?: Record<string, string | number> }) {
  return <>{usePrefs().t(k, vars)}</>;
}

/** A translated API enum value, usable from server components. */
export function EnumText({ kind, value }: { kind: EnumKind; value: string }) {
  return <>{usePrefs().label(kind, value)}</>;
}

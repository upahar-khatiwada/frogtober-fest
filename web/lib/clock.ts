"use client";

import { useSyncExternalStore } from "react";

/**
 * The current time, ticking every 30 s, or null during the server render and hydration.
 * Callers fall back to server-computed values (e.g. DeadlineView.days_left) while it is null,
 * so the first client render matches the HTML and live countdowns take over right after.
 */
const TICK_MS = 30_000;
let now: number | null = null;
let timer: ReturnType<typeof setInterval> | undefined;
const listeners = new Set<() => void>();

function notify() {
  now = Date.now();
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!timer) {
    timer = setInterval(notify, TICK_MS);
    queueMicrotask(notify);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

export function useNow(): Date | null {
  const value = useSyncExternalStore(
    subscribe,
    () => now,
    () => null,
  );
  return value === null ? null : new Date(value);
}

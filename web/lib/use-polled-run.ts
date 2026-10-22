"use client";

import { useEffect, useRef, useState } from "react";

import { getRun, type PipelineRunView } from "@/lib/api/tenderly";

/** Spec section 9.2: progress via polling every 2 seconds on a run endpoint. */
export const RUN_POLL_MS = 2000;
export const ACTIVE_RUN = ["queued", "running"];

export const isActive = (run: PipelineRunView | null) =>
  !!run && ACTIVE_RUN.includes(run.status);

/**
 * A pipeline run polled every 2 s while queued/running; `onEnd` fires once when it settles.
 * Callbacks are read through refs, so passing inline functions does not restart the polling.
 */
export function usePolledRun(
  onEnd: (run: PipelineRunView) => void,
  onError: (error: unknown) => void,
) {
  const [run, setRun] = useState<PipelineRunView | null>(null);
  const handlers = useRef({ onEnd, onError });
  useEffect(() => {
    handlers.current = { onEnd, onError };
  });
  const runId = run?.id;
  const active = isActive(run);

  useEffect(() => {
    if (runId === undefined || !active) return;
    const timer = setInterval(() => {
      getRun(runId)
        .then(setRun)
        .catch((e) => handlers.current.onError(e));
    }, RUN_POLL_MS);
    return () => clearInterval(timer);
  }, [runId, active]);

  useEffect(() => {
    if (run && !active) handlers.current.onEnd(run);
    // Only when the run settles (id/active change), not on every poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, active]);

  return [run, setRun] as const;
}

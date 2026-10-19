/**
 * Match reasons arrive as "[deterministic] ..." / "[model] ..." strings (agents/matching.py),
 * with "SKIP: " after the prefix for a hard skip. The preview leads with what decided the row.
 */
export type ReasonSource = "deterministic" | "model";
export type Reason = { source: ReasonSource | null; skip: boolean; text: string };

const PREFIX = /^\[(deterministic|model)\]\s*/;

export function parseReason(raw: string): Reason {
  const m = PREFIX.exec(raw);
  let text = m ? raw.slice(m[0].length) : raw;
  const skip = text.startsWith("SKIP: ");
  if (skip) text = text.slice(6);
  return { source: (m?.[1] as ReasonSource | undefined) ?? null, skip, text };
}

/** Up to `n` reasons: hard-skip reasons first, then the model's, then the rules'. */
export function previewReasons(reasons: string[] | undefined, n = 2): { shown: Reason[]; more: number } {
  const parsed = (reasons ?? []).map(parseReason);
  const rank = (r: Reason) => (r.skip ? 0 : r.source === "model" ? 1 : 2);
  const ordered = parsed.map((r, i) => ({ r, i })).sort((a, b) => rank(a.r) - rank(b.r) || a.i - b.i).map(({ r }) => r);
  return { shown: ordered.slice(0, n), more: Math.max(0, ordered.length - n) };
}

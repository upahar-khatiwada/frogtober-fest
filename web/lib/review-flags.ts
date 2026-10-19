/**
 * Which extracted values the deterministic parser could not confirm. Scout flags use the field name
 * the parser was working on ("deadline", "estimated_cost_npr"), while sources are stored per output
 * field ("deadline_ad", "deadline_bs_iso"), so "deadline" covers both.
 */
import type { components } from "@/lib/api/types";

type S = components["schemas"];
export type Source = S["FieldSource"];
export type Flag = S["ReviewFlag"];

export function flagsFor(field: string, flags: Flag[]): Flag[] {
  return flags.filter(
    (f) =>
      f.field === field ||
      (f.field === "deadline" && field.startsWith("deadline")),
  );
}

/** Flagged, parsed to null from a raw string, or a quote/raw value that is not in the notice. */
export function sourceNeedsReview(source: Source, flags: Flag[]): boolean {
  if (flagsFor(source.field, flags).length > 0) return true;
  if (source.value == null && source.raw != null) return true;
  return (source.quote != null || source.raw != null) && !source.quote_found;
}

/** Flags that no source row explains (shown in their own list so none is dropped). */
export function unmatchedFlags(sources: Source[], flags: Flag[]): Flag[] {
  return flags.filter(
    (f) => !sources.some((s) => flagsFor(s.field, [f]).length > 0),
  );
}

import { describe, expect, it } from "vitest";

import {
  flagsFor,
  sourceNeedsReview,
  unmatchedFlags,
  type Flag,
  type Source,
} from "@/lib/review-flags";

const src = (over: Partial<Source> & { field: string }): Source => ({
  quote_found: true,
  value: "x",
  raw: null,
  quote: null,
  ...over,
});

const FLAGS: Flag[] = [
  { field: "deadline", reason: "several BS dates", raw: "a b" },
  {
    field: "estimated_cost_npr",
    reason: "invalid digit grouping",
    raw: "Rs. 1,50,000,00",
  },
  {
    field: "title",
    reason: "value and quote not found in the notice text",
    raw: "T",
  },
];

describe("review flags", () => {
  it("maps the deadline flag onto every deadline source", () => {
    expect(flagsFor("deadline_ad", FLAGS)).toHaveLength(1);
    expect(flagsFor("deadline_bs_iso", FLAGS)).toHaveLength(1);
    expect(flagsFor("estimated_cost_npr", FLAGS)).toHaveLength(1);
    expect(flagsFor("district", FLAGS)).toHaveLength(0);
  });

  it("needs review when flagged, parsed to null from a raw string, or the quote is missing", () => {
    expect(
      sourceNeedsReview(
        src({
          field: "estimated_cost_npr",
          value: null,
          raw: "Rs. 1,50,000,00",
        }),
        [],
      ),
    ).toBe(true);
    expect(
      sourceNeedsReview(
        src({ field: "title", quote: "q", quote_found: false }),
        [],
      ),
    ).toBe(true);
    expect(sourceNeedsReview(src({ field: "buyer" }), FLAGS)).toBe(false);
    expect(
      sourceNeedsReview(src({ field: "evaluation_method", value: null }), []),
    ).toBe(false); // null with no raw: simply absent
    expect(sourceNeedsReview(src({ field: "buyer", quote: "q" }), [])).toBe(
      false,
    );
  });

  it("returns flags that match no source", () => {
    const sources = [
      src({ field: "deadline_ad" }),
      src({ field: "estimated_cost_npr" }),
    ];
    expect(unmatchedFlags(sources, FLAGS).map((f) => f.field)).toEqual([
      "title",
    ]);
  });
});

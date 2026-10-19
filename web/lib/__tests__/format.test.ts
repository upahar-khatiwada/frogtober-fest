import { describe, expect, it } from "vitest";

import { formatNpr, formatNprShort, groupLakh } from "@/lib/format";

describe("groupLakh", () => {
  it.each([
    [0, "0"],
    [999, "999"],
    [1000, "1,000"],
    [100000, "1,00,000"],
    [102000, "1,02,000"], // NEPAL_CONTEXT section 9 example
    [14875000, "1,48,75,000"],
    [1000000000, "1,00,00,00,000"],
    [-250000, "-2,50,000"],
  ])("%d -> %s", (n, expected) => {
    expect(groupLakh(n)).toBe(expected);
  });
});

describe("formatNpr", () => {
  it("prefixes Rs. in English", () => {
    expect(formatNpr(14875000)).toBe("Rs. 1,48,75,000");
  });

  it("uses रु. and Devanagari digits in Nepali", () => {
    expect(formatNpr(14875000, "ne")).toBe("रु. १,४८,७५,०००");
  });
});

describe("formatNprShort", () => {
  it.each([
    [14875000, "Rs. 1.49 crore"],
    [10000000, "Rs. 1 crore"],
    [185500000, "Rs. 18.55 crore"],
    [7500000, "Rs. 75 lakh"],
    [3850000, "Rs. 38.5 lakh"],
    [100000, "Rs. 1 lakh"],
    [99999, "Rs. 99,999"],
  ])("%d -> %s", (n, expected) => {
    expect(formatNprShort(n)).toBe(expected);
  });

  it("writes करोड / लाख with Devanagari digits in Nepali", () => {
    expect(formatNprShort(14875000, "ne")).toBe("रु. १.४९ करोड");
    expect(formatNprShort(3850000, "ne")).toBe("रु. ३८.५ लाख");
  });
});

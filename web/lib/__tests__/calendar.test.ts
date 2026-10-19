import { describe, expect, it } from "vitest";

import {
  BS_MAX_YEAR,
  BS_MIN_YEAR,
  adToBs,
  bsToAd,
  daysInBsMonth,
  formatAd,
  formatBs,
  formatDate,
  parseBsIso,
  toAsciiDigits,
  toDevanagariDigits,
} from "@/lib/nepal/calendar";

describe("BS <-> AD (table exported from api/nepal/dates.py)", () => {
  // Same anchors as api/tests/test_nepal_dates.py and test_tenders_list_api.py.
  it.each([
    [{ year: 2064, month: 5, day: 3 }, "2007-08-20"], // NEPAL_CONTEXT section 7
    [{ year: 2080, month: 1, day: 1 }, "2023-04-14"],
    [{ year: 2081, month: 1, day: 1 }, "2024-04-13"],
    [{ year: 2082, month: 1, day: 1 }, "2025-04-14"],
    [{ year: 2083, month: 8, day: 5 }, "2026-11-21"],
  ])("%o <-> %s", (bs, ad) => {
    expect(bsToAd(bs)).toBe(ad);
    expect(adToBs(ad)).toEqual(bs);
  });

  it("round-trips every day of 2075-2090 BS", () => {
    for (let year = 2075; year <= 2090; year++) {
      for (let month = 1; month <= 12; month++) {
        for (let day = 1; day <= daysInBsMonth(year, month); day++) {
          expect(adToBs(bsToAd({ year, month, day }))).toEqual({ year, month, day });
        }
      }
    }
  });

  it("follows the backend where JS calendar packages disagree (nepali-date-converter gives Jestha 2084 32 days)", () => {
    // The demo licence is valid to 2084-03-32 (data/demo_company/06_construction_licence.txt).
    expect(daysInBsMonth(2084, 2)).toBe(31);
    expect(parseBsIso("2084-03-32")).toEqual({ year: 2084, month: 3, day: 32 });
  });

  it("rejects dates outside the table or the month", () => {
    expect(parseBsIso("2083-13-01")).toBeNull();
    expect(parseBsIso("2083-08-33")).toBeNull();
    expect(parseBsIso(`${BS_MAX_YEAR + 1}-01-01`)).toBeNull();
    expect(parseBsIso("5 Mangsir 2083")).toBeNull();
    expect(() => bsToAd({ year: 2083, month: 8, day: 40 })).toThrow();
    expect(() => adToBs("1900-01-01")).toThrow();
    expect(() => adToBs("2026-02-30")).toThrow();
    expect(BS_MIN_YEAR).toBeLessThanOrEqual(2064);
  });

  it("accepts Devanagari digits", () => {
    expect(parseBsIso("२०८३-०८-०५")).toEqual({ year: 2083, month: 8, day: 5 });
    expect(toAsciiDigits("२०८३")).toBe("2083");
    expect(toDevanagariDigits("2083-08-05")).toBe("२०८३-०८-०५");
  });
});

describe("display", () => {
  it("formats BS like the API's DeadlineView", () => {
    expect(formatBs({ year: 2083, month: 8, day: 5 })).toBe("5 Mangsir 2083");
    expect(formatBs({ year: 2083, month: 8, day: 5 }, "ne")).toBe("५ मंसिर २०८३");
  });

  it("formats AD", () => {
    expect(formatAd("2026-11-21")).toBe("21 Nov 2026");
    expect(formatAd("2026-11-21T12:00:00+05:45", "ne")).toBe("२१ नोभेम्बर २०२६");
  });

  it("formats in the preferred calendar", () => {
    expect(formatDate("2026-11-21", "BS")).toBe("5 Mangsir 2083");
    expect(formatDate("2026-11-21", "AD")).toBe("21 Nov 2026");
    expect(formatDate("1900-01-01", "BS")).toBe("1 Jan 1900"); // outside the BS table: falls back to AD
  });
});

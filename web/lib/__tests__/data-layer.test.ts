import { describe, expect, it } from "vitest";

import { errorMessage, parseTenderFilters } from "@/lib/api/tenderly";
import { EMPTY_TURNOVER, fromDraft, normalizeFiscalYear, parseAmount, toDraft } from "@/lib/company-form";
import { filterTenders } from "@/lib/mock/api";
import { MOCK_COMPANY, mockTenders } from "@/lib/mock/data";
import { parseReason, previewReasons } from "@/lib/reasons";

const NOW = new Date("2026-10-19T12:00:00+05:45");

describe("parseTenderFilters", () => {
  it("keeps valid values and drops unknown or invalid ones", () => {
    expect(
      parseTenderFilters({
        procurement_type: "works",
        method: "bogus",
        province: ["gandaki", "koshi"],
        district: "  कास्की ",
        min_score: "60",
        deadline_within_days: "-3",
        status: "blocked",
        extra: "x",
      }),
    ).toEqual({ procurement_type: "works", province: "gandaki", district: "कास्की", min_score: 60, status: "blocked" });
    expect(parseTenderFilters({ min_score: "101", district: " " })).toEqual({});
  });
});

describe("errorMessage", () => {
  it("reads FastAPI string and validation details", () => {
    expect(errorMessage({ detail: "No company profile yet" }, undefined)).toBe("No company profile yet");
    expect(errorMessage({ detail: [{ loc: ["body", "turnover", 0, "fiscal_year_bs"], msg: "bad FY" }] }, undefined)).toBe("turnover.0.fiscal_year_bs: bad FY");
    expect(errorMessage(undefined, new Response(null, { status: 503, statusText: "Service Unavailable" }))).toBe("HTTP 503 Service Unavailable");
  });
});

describe("reasons", () => {
  it("parses the matching agent's prefixes", () => {
    expect(parseReason("[deterministic] SKIP: deadline has passed")).toEqual({ source: "deterministic", skip: true, text: "deadline has passed" });
    expect(parseReason("[model] fits [chunk 3]")).toEqual({ source: "model", skip: false, text: "fits [chunk 3]" });
    expect(parseReason("plain")).toEqual({ source: null, skip: false, text: "plain" });
  });

  it("previews skip reasons first, then the model's", () => {
    const { shown, more } = previewReasons(["[deterministic] a", "[model] b", "[deterministic] SKIP: c", "[deterministic] d"], 2);
    expect(shown.map((r) => r.text)).toEqual(["c", "b"]);
    expect(more).toBe(2);
  });
});

describe("mock API", () => {
  const items = mockTenders(NOW);

  it("ranks like the API: score desc, unscored last", () => {
    const scores = items.map((t) => t.score);
    const scored = scores.filter((s): s is number => s != null);
    expect(scored).toEqual([...scored].sort((a, b) => b - a));
    expect(scores.slice(scored.length).every((s) => s == null)).toBe(true);
    expect(items.map((t) => t.rank)).toEqual(items.map((_, i) => i + 1));
  });

  it("emulates the GET /tenders filters", () => {
    expect(filterTenders(items, { procurement_type: "goods" }).every((t) => t.procurement_type === "goods")).toBe(true);
    expect(filterTenders(items, { district: "तनहुँ" }).map((t) => t.district)).toEqual(["Tanahun", "Tanahun"]);
    expect(filterTenders(items, { min_score: 80 }).every((t) => (t.score ?? 0) >= 80)).toBe(true);
    const soon = filterTenders(items, { deadline_within_days: 5 });
    expect(soon.length).toBeGreaterThan(0);
    expect(soon.every((t) => t.deadline && !t.deadline.passed && t.deadline.days_left <= 5)).toBe(true);
    expect(filterTenders(items, { status: "blocked", decision: "pursue" })[0].rank).toBe(1);
  });

  it("builds deadlines in both calendars relative to now", () => {
    const passed = items.find((t) => t.deadline?.passed);
    expect(passed?.deadline?.days_left).toBeLessThan(0);
    const d = items.find((t) => t.deadline)!.deadline!;
    expect(d.bs).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(d.bs_ne).toMatch(/^[०-९]+ \S+ [०-९]{4}$/);
  });
});

describe("company form", () => {
  it("validates fiscal years like schemas._base.FiscalYearBS", () => {
    expect(normalizeFiscalYear("2082/83")).toBe("2082/83");
    expect(normalizeFiscalYear("२०८२/८३")).toBe("2082/83");
    expect(normalizeFiscalYear("2099/00")).toBe("2099/00");
    expect(normalizeFiscalYear("2082/84")).toBeNull();
    expect(normalizeFiscalYear("2082-83")).toBeNull();
  });

  it("parses amounts in either grouping or Devanagari digits", () => {
    expect(parseAmount("1,48,75,000")).toBe(14875000);
    expect(parseAmount("१४,८७५,०००")).toBe(14875000);
    expect(parseAmount("12.5")).toBeNull();
    expect(parseAmount("")).toBeNull();
  });

  it("round-trips the demo profile", () => {
    const { profile, errors } = fromDraft(toDraft(MOCK_COMPANY));
    expect(errors).toEqual({});
    const expected: Partial<typeof MOCK_COMPANY> = { ...MOCK_COMPANY };
    delete expected.id;
    delete expected.updated_at;
    expect(profile).toEqual(expected);
  });

  it("reports field errors and returns no profile", () => {
    const draft = toDraft(null);
    draft.turnover = [
      { fiscal_year_bs: "2081/82", amount: "100" },
      { fiscal_year_bs: "2081/82", amount: "x" },
      { ...EMPTY_TURNOVER, fiscal_year_bs: "2081/83", amount: "5" },
    ];
    const { profile, errors } = fromDraft(draft);
    expect(profile).toBeNull();
    expect(errors).toEqual({
      name: "company.required",
      "turnover.1.fiscal_year_bs": "company.fyDuplicate",
      "turnover.1.amount": "company.required",
      "turnover.2.fiscal_year_bs": "company.fyInvalid",
    });
  });
});

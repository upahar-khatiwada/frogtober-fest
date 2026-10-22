import { describe, expect, it } from "vitest";

import type { Proposal, ProposalSection } from "@/lib/api/tenderly";
import { formatDuration } from "@/lib/format";
import { approvalGates, checklistCounts, needsOpen, openedSinceReview, sectionsFor, splitMarkers } from "@/lib/proposal";

const section = (key: string, over: Partial<ProposalSection> = {}): ProposalSection => ({
  key,
  title: key,
  body: "Text.",
  body_template: "Text.",
  cited_chunk_ids: [1],
  grounded: true,
  ...over,
});

const REVIEW = {
  scores: { completeness: 80, relevance: 80, compliance: 80 },
  verdict: "pass" as const,
  pass_min_score: 70,
  fail_below_score: 40,
};

function version(id: number, over: Partial<Proposal> = {}): Proposal {
  return {
    id,
    tender_id: 1,
    version: id,
    language: "en",
    sections: [section("cover_letter")],
    citation_rate: 1,
    status: "reviewed",
    review: REVIEW,
    reviewed_at: "2026-10-22T04:00:00Z",
    opened_at: "2026-10-22T10:00:00+05:45", // = 04:15 UTC, after the review
    ...over,
  };
}

describe("splitMarkers", () => {
  it("separates the markers code writes from plain text", () => {
    expect(splitMarkers("PAN 1, VAT [MISSING: company.vat] and ⟦unsourced: Rs 6,10,00,000⟧.")).toEqual([
      { text: "PAN 1, VAT ", marker: false },
      { text: "[MISSING: company.vat]", marker: true },
      { text: " and ", marker: false },
      { text: "⟦unsourced: Rs 6,10,00,000⟧", marker: true },
      { text: ".", marker: false },
    ]);
  });

  it("leaves ordinary brackets alone", () => {
    expect(splitMarkers("Class [C] (general)")).toEqual([{ text: "Class [C] (general)", marker: false }]);
  });
});

describe("approval gates (spec section 9.2)", () => {
  it("compares open and review instants, not strings", () => {
    expect(openedSinceReview(version(1))).toBe(true);
    expect(openedSinceReview(version(1, { opened_at: "2026-10-22T09:30:00+05:45" }))).toBe(false); // 03:45 UTC
    expect(openedSinceReview(version(1, { opened_at: null }))).toBe(false);
  });

  it("enables approval only for the latest, reviewed, opened version whose verdict is not fail", () => {
    const v2 = version(2);
    expect(approvalGates(v2, [v2, version(1)]).canApprove).toBe(true);
    expect(approvalGates(version(1), [v2, version(1)])).toMatchObject({ latest: false, canApprove: false });
    const failed = version(2, { review: { ...REVIEW, verdict: "fail" } });
    expect(approvalGates(failed, [failed])).toMatchObject({ verdictOk: false, canApprove: false });
    const unopened = version(2, { opened_at: null });
    expect(approvalGates(unopened, [unopened])).toMatchObject({ opened: false, canApprove: false });
    const draft = version(2, { review: null, status: "draft" });
    expect(approvalGates(draft, [draft])).toMatchObject({ reviewed: false, verdictOk: false, canApprove: false });
    const approved = version(2, { status: "approved" });
    expect(approvalGates(approved, [approved])).toMatchObject({ approved: true, canApprove: false });
  });

  it("needs_work is approvable", () => {
    const v = version(2, { review: { ...REVIEW, verdict: "needs_work" } });
    expect(approvalGates(v, [v]).canApprove).toBe(true);
  });

  it("records an open only for reviewed, unapproved versions not yet opened since the review", () => {
    expect(needsOpen(version(1, { opened_at: null }))).toBe(true);
    expect(needsOpen(version(1))).toBe(false);
    expect(needsOpen(version(1, { review: null, opened_at: null }))).toBe(false);
    expect(needsOpen(version(1, { status: "approved", opened_at: null }))).toBe(false);
  });
});

describe("requirements and checklist", () => {
  it("finds the sections that answer a requirement", () => {
    const sections = [section("a", { requirement_indices: [0, 2] }), section("b", { requirement_indices: [1] })];
    expect(sectionsFor(sections, 2).map((s) => s.key)).toEqual(["a"]);
    expect(sectionsFor(sections, 5)).toEqual([]);
  });

  it("counts checklist statuses", () => {
    const row = (status: "present" | "expiring" | "missing") => ({
      document: "d",
      doc_type: "other" as const,
      mandatory: true,
      status,
      note: "",
    });
    expect(checklistCounts([row("present"), row("missing"), row("missing")])).toEqual({
      present: 1,
      expiring: 0,
      missing: 2,
    });
  });
});

describe("formatDuration", () => {
  it("uses ms, seconds and minutes, with Devanagari digits in Nepali", () => {
    expect(formatDuration(840)).toBe("840 ms");
    expect(formatDuration(6100)).toBe("6.1 s");
    expect(formatDuration(41_200)).toBe("41 s");
    expect(formatDuration(85_500)).toBe("1 min 26 s");
    expect(formatDuration(6100, "ne")).toBe("६.१ s");
    expect(formatDuration(null)).toBe("–");
  });
});

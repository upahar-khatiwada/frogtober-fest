/**
 * Pure helpers for the proposal page: unresolved-value markers, the approval gates (mirrors
 * agents/review.py::approval_blockers), and which sections answer which tender requirement.
 */
import type {
  ChecklistItem,
  Proposal,
  ProposalSection,
} from "@/lib/api/tenderly";

/** Markers code writes into a section body (agents/proposal.py): a missing value or a masked figure. */
export const MARKER = /(\[(?:MISSING|UNKNOWN|UNVERIFIED): [^\]]*\]|⟦unsourced: [^⟧]*⟧)/g;

export type BodyPart = { text: string; marker: boolean };

/** Split a body into plain text and markers, so the UI can highlight what still needs a value. */
export function splitMarkers(body: string): BodyPart[] {
  return body
    .split(MARKER)
    .filter((part) => part !== "")
    .map((text) => ({ text, marker: /^(\[(MISSING|UNKNOWN|UNVERIFIED): |⟦unsourced: )/.test(text) }));
}

const time = (iso: string | null | undefined) => (iso ? Date.parse(iso) : NaN);

/** The person opened this version after its review (POST /proposals/{id}/open; approval needs it). */
export function openedSinceReview(p: Proposal): boolean {
  if (!p.opened_at) return false;
  if (!p.reviewed_at) return true;
  return time(p.opened_at) >= time(p.reviewed_at);
}

export type ApprovalGates = {
  reviewed: boolean;
  verdictOk: boolean;
  opened: boolean;
  latest: boolean;
  approved: boolean;
  canApprove: boolean;
};

/** Spec section 9.2: approve stays disabled until the verdict is not "fail" and the person opened the proposal. */
export function approvalGates(p: Proposal, versions: Proposal[]): ApprovalGates {
  const reviewed = !!p.review;
  const verdictOk = reviewed && p.review!.verdict !== "fail";
  const opened = reviewed && openedSinceReview(p);
  const latest = versions.length === 0 || versions[0].id === p.id;
  const approved = p.status === "approved";
  return {
    reviewed,
    verdictOk,
    opened,
    latest,
    approved,
    canApprove: reviewed && verdictOk && opened && latest && !approved,
  };
}

/** Whether the version still needs the open recorded (reviewed, not approved, not opened since its review). */
export function needsOpen(p: Proposal): boolean {
  return !!p.review && p.status !== "approved" && !openedSinceReview(p);
}

export const isStub = (s: ProposalSection) =>
  (s.flags ?? []).some((f) => f.kind === "no_kb_material");

/** Sections that answer tender requirement `index` (ProposalSection.requirement_indices). */
export function sectionsFor(
  sections: ProposalSection[],
  index: number,
): ProposalSection[] {
  return sections.filter((s) => (s.requirement_indices ?? []).includes(index));
}

export function checklistCounts(items: ChecklistItem[]) {
  return {
    present: items.filter((i) => i.status === "present").length,
    expiring: items.filter((i) => i.status === "expiring").length,
    missing: items.filter((i) => i.status === "missing").length,
  };
}

const NAME_KEY = "tenderly.name";

/** The person's name for edits and approvals, remembered in this browser (a convenience, not an identity). */
export function rememberedName(): string {
  try {
    return window.localStorage.getItem(NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

export function rememberName(name: string) {
  try {
    window.localStorage.setItem(NAME_KEY, name);
  } catch {
    // Storage blocked: the name is simply not prefilled next time.
  }
}

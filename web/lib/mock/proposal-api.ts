/**
 * Mock proposal versions (NEXT_PUBLIC_USE_MOCKS=1) for tender 1, modelled on what the Proposal and Review agents
 * store for the SYNTHETIC seed 001 and the FICTIONAL demo company: v1 reviewed `needs_work`, v2 its automatic
 * revision (still `needs_work`: a value is missing). Editing, re-review, open and approve are emulated in memory
 * (per tab in the browser, per process on the server), with the same gates as the API.
 */
import type {
  ChecklistItem,
  ExportKind,
  PipelineRunView,
  Proposal,
  ProposalSection,
  ReviewReport,
} from "@/lib/api/tenderly";

const delay = (ms = 120) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

const TENDER_ID = 1;
const REVIEW_MS = 2500;
const T0 = "2026-10-22T04:00:00Z";
const T1 = "2026-10-22T04:03:00Z";

function sec(
  key: string,
  title: string,
  body: string,
  cited: number[],
  extra: Partial<ProposalSection> = {},
): ProposalSection {
  return {
    key,
    title,
    body,
    body_template: body,
    cited_chunk_ids: cited,
    grounded: cited.length > 0,
    flags: [],
    requirement_indices: [],
    placeholders: [],
    ...extra,
  };
}

const V1_SECTIONS: ProposalSection[] = [
  sec(
    "cover_letter",
    "Cover letter",
    "Annapurna Demo Nirman Sewa Pvt. Ltd. is pleased to submit its bid for the Upgrading and Gravelling of Bhanu-Satiswara Road (3.2 km), reference BM/NCB/W-07/2083-84.\n\nWe have examined the bidding document and offer to carry out the works in accordance with it. A bid security of Rs 4,46,000 is enclosed.",
    [21],
  ),
  sec(
    "bidder_info",
    "Bidder information and eligibility",
    'The bidder is a registered private limited company (PAN 609876543, VAT [MISSING: company.vat]) holding a construction licence of "C" class (DEMO-C-0421), renewed for FY 2083/84.\n\nThe tax clearance on file is for FY 2081/82; the clearance for FY 2082/83 will be attached before submission.',
    [12, 5],
    {
      requirement_indices: [0, 1],
      flags: [
        {
          kind: "missing_value",
          detail: "VAT number (company.vat) is not on record",
        },
      ],
    },
  ),
  sec(
    "work_plan",
    "Work plan and schedule",
    "- Mobilisation and setting out: weeks 1–2\n- Earthwork in formation and side drains: weeks 3–8\n- Slab culverts (4 nos.): weeks 6–12\n- Gravelling and compaction: weeks 9–16\n- Clean-up and handover: week 17",
    [21],
    { requirement_indices: [4] },
  ),
  sec(
    "relevant_experience",
    "Relevant experience",
    "The company completed the gravelling and side-drain works of the Vyas-Damauli link road for Vyas Municipality, a contract of Rs 1,85,40,000, certified complete.",
    [7],
    { requirement_indices: [2] },
  ),
  sec(
    "key_equipment",
    "Key equipment",
    "_No supporting material was found in the company knowledge base for this section. Upload documents that cover it (equipment list) and regenerate, or write it by hand._",
    [],
    {
      requirement_indices: [5],
      flags: [
        {
          kind: "no_kb_material",
          detail: "no knowledge-base chunk was retrieved",
        },
      ],
    },
  ),
  sec(
    "financial_capacity",
    "Financial capacity",
    "The company's average annual construction turnover over the last three fiscal years is Rs 5.03 crore, above the notice's minimum. Audited statements will be enclosed. A turnover of ⟦unsourced: Rs 6,10,00,000⟧ was recorded in FY 2082/83.",
    [21],
    {
      requirement_indices: [3],
      flags: [
        {
          kind: "unsourced_figure",
          detail: "masked figure(s) the model wrote itself: Rs 6,10,00,000",
        },
      ],
    },
  ),
  sec(
    "declarations",
    "Declarations",
    "We declare that we are not disqualified, have no conflict of interest and have not been punished for a professional or business offence (PPR Rule 40(2)(e)).",
    [],
    {
      flags: [
        {
          kind: "ungrounded",
          detail: "the draft cited no knowledge-base chunk that was shown",
        },
      ],
    },
  ),
];

function revised(sections: ProposalSection[]): ProposalSection[] {
  return sections.map((s) =>
    s.key === "financial_capacity"
      ? {
          ...s,
          body: "The company's average annual construction turnover over the last three fiscal years is Rs 5.03 crore (company profile), above the notice's minimum of Rs 1,50,00,000. Audited statements will be enclosed.",
          body_template:
            "The company's average annual construction turnover over the last three fiscal years is {{company.turnover_average}} (company profile), above the notice's minimum of {{tender.min_turnover}}. Audited statements will be enclosed.",
          flags: [],
        }
      : s,
  );
}

function review(over: Partial<ReviewReport>): ReviewReport {
  return {
    scores: { completeness: 74, relevance: 81, compliance: 78 },
    checks: [
      {
        check: "mandatory_addressed",
        passed: true,
        severity: "hard",
        detail: "4 of 4 mandatory requirements answered",
      },
      {
        check: "no_placeholders",
        passed: false,
        severity: "soft",
        detail: "unresolved text in 1 section(s): bidder_info",
      },
      {
        check: "bid_security_stated",
        passed: true,
        severity: "soft",
        detail: "the proposal states the bid security",
      },
      {
        check: "deadline_not_passed",
        passed: true,
        severity: "hard",
        detail: "17 day(s) left",
      },
      {
        check: "sections_cited",
        passed: false,
        severity: "soft",
        detail: "5 of 7 sections cite the knowledge base",
      },
    ],
    gaps: [
      {
        source: "check",
        check: "no_placeholders",
        section_key: "bidder_info",
        issue: "Unresolved in the text: [MISSING: company.vat]",
        severity: "soft",
        suggestion:
          "Add the missing values to the company profile or the knowledge base and regenerate; never type a figure without a source.",
      },
      {
        source: "check",
        check: "sections_cited",
        section_key: "declarations",
        issue:
          "The section cites no knowledge-base chunk; its claims are unsupported.",
        severity: "soft",
      },
      {
        source: "model",
        requirement_index: 5,
        section_key: "key_equipment",
        issue:
          "The notice asks for a list of owned or leased equipment; the section has no material.",
        severity: "soft",
        suggestion:
          "Upload the equipment list (roller, excavator, tipper) to the knowledge base.",
      },
    ],
    uncited_sections: ["key_equipment", "declarations"],
    verdict: "needs_work",
    verdict_reasons: [
      "[check] no_placeholders failed: unresolved text in 1 section(s): bidder_info",
      "[check] sections_cited failed: 5 of 7 sections cite the knowledge base",
    ],
    pass_min_score: 70,
    fail_below_score: 40,
    revised_sections: [],
    ...over,
  };
}

function initialVersions(): Proposal[] {
  const v1Review = review({
    scores: { completeness: 68, relevance: 80, compliance: 72 },
    gaps: [
      ...(review({}).gaps ?? []),
      {
        source: "check",
        check: "no_placeholders",
        section_key: "financial_capacity",
        issue: "Unresolved in the text: ⟦unsourced: Rs 6,10,00,000⟧",
        severity: "soft",
      },
    ],
    verdict_reasons: [
      "[check] no_placeholders failed: unresolved text in 2 section(s): bidder_info, financial_capacity",
      "[model] lowest score 68 is below 70",
    ],
  });
  const v1: Proposal = {
    id: 101,
    tender_id: TENDER_ID,
    version: 1,
    language: "en",
    sections: V1_SECTIONS,
    review: v1Review,
    status: "reviewed",
    reviewed_at: T0,
    created_at: T0,
    citation_rate: 5 / 7,
  };
  const v2: Proposal = {
    ...v1,
    id: 102,
    version: 2,
    sections: revised(V1_SECTIONS),
    review: review({
      revision_of: 1,
      revised_sections: ["financial_capacity"],
      previous_verdict: "needs_work",
    }),
    reviewed_at: T1,
    created_at: T1,
  };
  return [v2, v1];
}

let versions = initialVersions();
let generated = false;
const reviewRuns = new Map<number, { startedAt: number; proposalId: number }>();

const find = (id: number) => {
  const p = versions.find((v) => v.id === id);
  if (!p) throw new Error(`No proposal ${id}`);
  return p;
};

function settleReviews(now = Date.now()) {
  for (const [, run] of reviewRuns) {
    const p = versions.find((v) => v.id === run.proposalId);
    if (p && !p.review && now - run.startedAt >= REVIEW_MS) {
      p.review = review({});
      p.status = "reviewed";
      p.reviewed_at = new Date(run.startedAt + REVIEW_MS).toISOString();
    }
  }
}

/** Latest version summary for the mock tender detail (after the mock proposal run, or always on the server). */
export function latestSummary(tenderId: number) {
  if (tenderId !== TENDER_ID) return null;
  settleReviews();
  const p = versions[0];
  return {
    id: p.id,
    version: p.version,
    language: p.language,
    status: p.status ?? "draft",
    created_at: p.created_at,
    sections_total: p.sections.length,
    sections_grounded: p.sections.filter((s) => s.grounded).length,
    sections_flagged: p.sections.filter((s) => (s.flags ?? []).length > 0)
      .length,
    verdict: p.review?.verdict ?? null,
  };
}

/** Tender status implied by the mock proposal state (null: leave the detail mock's own). */
export function proposalStatus(tenderId: number) {
  if (tenderId !== TENDER_ID || !generated) return null;
  settleReviews();
  if (versions.some((v) => v.status === "approved")) return "approved" as const;
  return versions[0].review ? ("reviewed" as const) : ("drafted" as const);
}

export function markGenerated() {
  generated = true;
}

export async function listProposals(tenderId: number): Promise<Proposal[]> {
  await delay();
  settleReviews();
  return tenderId === TENDER_ID ? structuredClone(versions) : [];
}

export async function openProposal(id: number): Promise<Proposal> {
  await delay(80);
  const p = find(id);
  p.opened_at = new Date().toISOString();
  return structuredClone(p);
}

export async function approveProposal(
  id: number,
  approvedBy: string,
  note: string | null,
): Promise<Proposal> {
  await delay(300);
  settleReviews();
  const p = find(id);
  const blockers: string[] = [];
  if (p.status === "approved") blockers.push(`version ${p.version} is already approved`);
  else if (!p.review) blockers.push(`version ${p.version} has not been reviewed`);
  else {
    if (p.review.verdict === "fail") blockers.push("the review verdict is fail");
    if (!p.opened_at || (p.reviewed_at && p.opened_at < p.reviewed_at))
      blockers.push(`version ${p.version} has not been opened since its review`);
    if (versions[0].id !== p.id)
      blockers.push(`version ${versions[0].version} is newer; approve the latest version`);
  }
  if (blockers.length) throw new Error(blockers.join("; "));
  Object.assign(p, {
    status: "approved",
    approved_by: approvedBy,
    approval_note: note,
    approved_at: new Date().toISOString(),
  });
  generated = true;
  return structuredClone(p);
}

export async function editSection(
  id: number,
  key: string,
  body: string,
  editedBy: string,
): Promise<Proposal> {
  await delay(250);
  const p = find(id);
  if (versions[0].id !== id) throw new Error(`version ${p.version} is not the latest; edit the latest version`);
  if (versions.some((v) => v.status === "approved")) throw new Error("the tender is approved");
  const now = new Date().toISOString();
  const next: Proposal = {
    ...structuredClone(p),
    id: Math.max(...versions.map((v) => v.id)) + 1,
    version: versions[0].version + 1,
    review: null,
    status: "draft",
    reviewed_at: null,
    opened_at: null,
    created_at: now,
    sections: p.sections.map((s) =>
      s.key === key
        ? {
            ...s,
            body,
            body_template: body,
            edited_by: editedBy,
            edited_at: now,
            flags: (s.flags ?? []).filter(
              (f) =>
                !(f.kind === "missing_value" && !body.includes("[MISSING:")) &&
                !(f.kind === "unsourced_figure" && !body.includes("⟦unsourced:")),
            ),
          }
        : s,
    ),
  };
  versions = [next, ...versions];
  return structuredClone(next);
}

export async function reviewProposal(id: number): Promise<PipelineRunView> {
  await delay(150);
  const runId = 900 + reviewRuns.size + 1;
  reviewRuns.set(runId, { startedAt: Date.now(), proposalId: id });
  return reviewRunView(runId)!;
}

/** A mock review run (polled through the detail mock's getRun). */
export function reviewRunView(runId: number): PipelineRunView | null {
  const run = reviewRuns.get(runId);
  if (!run) return null;
  settleReviews();
  const done = Date.now() - run.startedAt >= REVIEW_MS;
  const iso = new Date(run.startedAt).toISOString();
  return {
    id: runId,
    tender_id: TENDER_ID,
    target: "reviewed",
    status: done ? "succeeded" : "running",
    start_status: "reviewed",
    end_status: done ? "reviewed" : null,
    stages: [
      {
        stage: "review",
        status: done ? "ok" : "running",
        from_status: "drafted",
        to_status: done ? "reviewed" : null,
      },
    ],
    created_at: iso,
    started_at: iso,
    finished_at: done ? new Date(run.startedAt + REVIEW_MS).toISOString() : null,
  };
}

const CHECKLIST: ChecklistItem[] = [
  {
    document: "Firm registration certificate",
    doc_type: "company_registration",
    mandatory: true,
    status: "present",
    files: ["01_company_registration.pdf"],
    document_ids: [1],
    rule_id: "NP-REG-DOCS",
    compliance_status: "pass",
    note: "On file: 01_company_registration.pdf.",
  },
  {
    document: "Construction business licence",
    doc_type: "business_licence",
    mandatory: true,
    status: "present",
    files: ["06_construction_licence.txt"],
    document_ids: [3],
    expires_on: "2027-07-16",
    expires_on_bs: "2084-03-32",
    rule_id: "NP-REG-DOCS",
    compliance_status: "pass",
    note: "On file: 06_construction_licence.txt.",
  },
  {
    document: "Tax clearance certificate for F/Y 2082/83",
    doc_type: "tax_clearance",
    mandatory: true,
    fiscal_year_bs: "2082/83",
    status: "missing",
    files: [],
    document_ids: [],
    rule_id: "NP-TAX-CLEARANCE",
    compliance_status: "fail",
    note: "On file only for other fiscal years: 2081/82 (expired 2083-03-32 BS / 2026-07-16 AD); F/Y 2082/83 needed. Action: Renew tax clearance for F/Y 2082/83 and upload it before submission.",
  },
  {
    document: "Bid security (bank guarantee)",
    doc_type: "bid_security",
    mandatory: true,
    status: "missing",
    files: [],
    document_ids: [],
    rule_id: "NP-BID-SECURITY",
    compliance_status: "unclear",
    note: "Arrange Rs 4,46,000, valid until 2083-12-15 BS / 2027-03-29 AD.",
  },
  {
    document: "Self-declaration (statutory)",
    doc_type: "self_declaration",
    mandatory: true,
    status: "missing",
    files: [],
    document_ids: [],
    rule_id: "NP-BID-FORMS",
    compliance_status: "unclear",
    note: "Sign the declaration in section 3 of this package.",
  },
];

export async function getChecklist(id: number): Promise<ChecklistItem[]> {
  await delay(60);
  find(id);
  return structuredClone(CHECKLIST);
}

/** Downloads in mock mode: a small text file standing in for the real document. */
export function exportUrl(id: number, kind: ExportKind): string {
  const text = `Mock ${kind.toUpperCase()} for proposal ${id}. Run the backend for the real file.`;
  return `data:text/plain;charset=utf-8,${encodeURIComponent(text)}`;
}

/** Test helper: restore the initial mock state. */
export function resetMockProposalState() {
  versions = initialVersions();
  generated = false;
  reviewRuns.clear();
}

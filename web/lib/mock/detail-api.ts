/**
 * Mock tender detail (NEXT_PUBLIC_USE_MOCKS=1): tender 1 is blocked by an expired tax clearance
 * (the demo beat), tender 27 is clean. Modelled on the SYNTHETIC seed notices. Not real tenders.
 */
import type {
  CompanyDocumentView,
  KBChunkView,
  PipelineRunDetail,
  PipelineRunView,
  RuleView,
  TenderDetail,
} from "@/lib/api/tenderly";
import type { components } from "@/lib/api/types";

import { MOCK_DOCUMENTS, mockDeadline } from "./data";
import {
  latestSummary,
  markGenerated,
  proposalStatus,
  reviewRunView,
} from "./proposal-api";

type S = components["schemas"];

const MOCK_IDS = [1, 27];
let overridden = false;
type MockRun = {
  startedAt: number;
  tenderId: number;
  kind: "analyze" | "proposal";
};
const runs = new Map<number, MockRun>();
const RUN_MS = 3000;

const delay = (ms = 150) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

const TAX_DOC: CompanyDocumentView = MOCK_DOCUMENTS[1];
const LICENCE_DOC: CompanyDocumentView = MOCK_DOCUMENTS[2];

const CHUNKS: KBChunkView[] = [
  {
    chunk_id: 5,
    document_id: TAX_DOC.id,
    filename: TAX_DOC.filename,
    doc_type: "tax_clearance",
    chunk_index: 0,
    content:
      "Tax Clearance Certificate\nFiscal year: 2081/82\nTaxpayer: Annapurna Demo Nirman Sewa Pvt. Ltd.\nValidity: may be used for public procurement until 2083-03-32 BS.",
    expires_on: TAX_DOC.expires_on,
    is_expired: true,
    fiscal_year_bs: "2081/82",
  },
  {
    chunk_id: 12,
    document_id: LICENCE_DOC.id,
    filename: LICENCE_DOC.filename,
    doc_type: "business_licence",
    chunk_index: 0,
    content:
      'Construction Business Licence\nLicence No.: DEMO-C-0421\nClass: "C" class (general civil construction)\nRenewed for FY 2083/84.',
    expires_on: LICENCE_DOC.expires_on,
    is_expired: false,
    fiscal_year_bs: "2083/84",
  },
  {
    chunk_id: 7,
    document_id: 5,
    filename: "04_experience_certificate.docx",
    doc_type: "experience_certificate",
    chunk_index: 0,
    content:
      "Work Completion Certificate\nVyas Municipality certifies that Annapurna Demo Nirman Sewa Pvt. Ltd. completed the gravelling and side-drain works of the Vyas-Damauli link road. Contract amount: Rs 1,85,40,000. Completed: 2081-11-20 BS.",
    expires_on: null,
    is_expired: null,
    fiscal_year_bs: null,
  },
  {
    chunk_id: 21,
    document_id: 6,
    filename: "05_company_profile.pdf",
    doc_type: "company_profile",
    chunk_index: 0,
    content:
      "Company Profile: Annapurna Demo Nirman Sewa Pvt. Ltd., Pokhara. Rural roads, gravelling, drainage and small bridges in Gandaki Province. Average annual construction turnover over the last three fiscal years: Rs 5.03 crore. Typical road works are planned in mobilisation, earthwork, structures and surfacing phases.",
    expires_on: null,
    is_expired: null,
    fiscal_year_bs: null,
  },
];

const SRC =
  "https://www.fsmtoolbox.com/assets/pdf/32._Public-procurement-rule-2064.pdf";
const RULES: RuleView[] = [
  {
    id: "NP-DEADLINE",
    description: "Submission deadline has not passed (Nepal time).",
    severity: "hard",
    source:
      "https://nepallaws.com/Laws/public-procurement-act-2063/chapter-3-provisions-relating-to-bid/section-14-invitation-to-bids/",
    verified: true,
    notes: "Date-only deadlines are treated as end of day NPT.",
  },
  {
    id: "NP-REG-DOCS",
    description:
      "Registration documents required for eligibility are on file and unexpired at the deadline.",
    severity: "hard",
    source: SRC,
    verified: true,
    notes: "PPR-EN Rule 40(2)(a),(b) from the 2008 text.",
  },
  {
    id: "NP-TAX-CLEARANCE",
    description:
      "Tax clearance (or tax-return proof) on file for each fiscal year the notice requires.",
    severity: "hard",
    source: SRC,
    verified: true,
    notes: "PPR-EN Rule 40(2)(d); the fiscal year comes from the notice.",
  },
  {
    id: "NP-TURNOVER",
    description:
      "Average annual turnover over the notice's look-back window meets the notice's minimum.",
    severity: "hard",
    source: SRC,
    verified: false,
    notes: "Rule 28(3) lists the criteria; exact wording [VERIFY].",
  },
  {
    id: "NP-BID-SECURITY",
    description:
      "Bid security guarantee covers the notice's amount until the notice's validity date.",
    severity: "soft",
    source: SRC,
    verified: true,
    notes: "Amount and validity from the notice only.",
  },
];

const ITEMS: S["ComplianceItem"][] = [
  {
    requirement: "Submission deadline not passed",
    status: "pass",
    severity: "hard",
    source: "rule",
    rule_id: "NP-DEADLINE",
    evidence_ref: "tender.deadline",
    explanation: "17 day(s) left (deadline 2026-11-21 12:00 NPT).",
  },
  {
    requirement: "Tax clearance for F/Y 2082/83",
    status: "fail",
    severity: "hard",
    source: "rule",
    rule_id: "NP-TAX-CLEARANCE",
    evidence_document_ids: [TAX_DOC.id],
    explanation:
      "No clearance or tax-return proof for 2082/83; on file: F/Y 2081/82 (expired 2026-07-16).",
    action_needed:
      "Renew tax clearance for F/Y 2082/83 (or get proof of tax-return filing for F/Y 2082/83) from the Inland Revenue Office and upload it before submission.",
  },
  {
    requirement: "Registration documents",
    status: "pass",
    severity: "hard",
    source: "rule",
    rule_id: "NP-REG-DOCS",
    evidence_chunk_ids: [12],
    evidence_document_ids: [LICENCE_DOC.id],
    explanation: "All required registration documents on file and unexpired.",
  },
  {
    requirement: "Bid security",
    status: "unclear",
    severity: "soft",
    source: "rule",
    rule_id: "NP-BID-SECURITY",
    explanation:
      "Required: Rs 4,46,000 (fixed amount in notice), valid until 2027-03-29 AD / 2083-12-15 BS. No guarantee on file yet.",
    action_needed:
      "Arrange a bank guarantee of Rs 4,46,000 valid until at least 2027-03-29 AD (2083-12-15 BS) (or the cash deposit the notice allows) before submission.",
  },
  {
    requirement: "Minimum average annual turnover",
    status: "unclear",
    severity: "hard",
    source: "rule",
    rule_id: "NP-TURNOVER",
    explanation:
      "Minimum Rs 1,50,00,000, but the look-back years were not extracted from the notice. [rule unverified: see NEPAL_CONTEXT.md]",
    action_needed:
      "Check the notice's turnover period (e.g. 'best 3 of the last 5 years') against the Rs 1,50,00,000 minimum.",
  },
  {
    requirement: 'Construction licence of class "D" or above',
    status: "pass",
    severity: "hard",
    source: "model",
    evidence_chunk_ids: [12],
    evidence_document_ids: [LICENCE_DOC.id],
    evidence_quote: 'Class: "C" class (general civil construction)',
    explanation: "The licence is class C, above D.",
    requirement_index: 0,
  },
];

const REQUIREMENTS_001: S["Requirement"][] = [
  {
    text: "Valid firm registration and construction licence of class D or above",
    mandatory: true,
    category: "eligibility",
    source_quote:
      'Bidders must hold a valid construction licence of class "D" or above.',
  },
  {
    text: "Tax clearance certificate for F/Y 2082/83",
    mandatory: true,
    category: "eligibility",
    source_quote:
      "Copy of tax clearance certificate of F/Y 2082/83 or proof of tax return submission.",
  },
  {
    text: "At least one similar road contract of Rs 60 lakh or more in the last 7 years",
    mandatory: true,
    category: "experience",
    source_quote:
      "Successful completion of at least one similar road work of value not less than Rs. 60,00,000 within the last seven years.",
  },
  {
    text: "Average annual turnover of at least Rs 1,50,00,000",
    mandatory: true,
    category: "financial",
    source_quote:
      "Average annual construction turnover of the best three years within the last five fiscal years of at least Rs. 1,50,00,000.",
  },
  {
    text: "Work programme showing completion within the contract period",
    mandatory: false,
    category: "technical",
    source_quote:
      "Bidders shall submit a work programme for completion within 150 days.",
  },
  {
    text: "List of key equipment (roller, excavator, tipper) owned or leased",
    mandatory: false,
    category: "equipment",
    source_quote:
      "Availability of key equipment: one vibratory roller, one excavator and two tippers.",
  },
  {
    text: "ISO 9001 quality certificate",
    mandatory: false,
    category: "other",
    source_quote: "ISO 9001 certification will be an advantage.",
  },
];

function buildDetail(id: number): TenderDetail | null {
  if (!MOCK_IDS.includes(id)) return null;
  const clean = id === 27;
  const items = ITEMS.filter(
    (i) => !(clean && i.rule_id === "NP-TAX-CLEARANCE"),
  );
  const hard = items.filter(
    (i) => i.status === "fail" && i.severity === "hard",
  );
  const blocked = hard.length > 0;
  const accepted = blocked && overridden;
  const now = new Date();
  const deadline = mockDeadline(17, now);
  const compliance: S["ComplianceView"] = {
    items,
    override: accepted
      ? {
          id: 1,
          overridden_by: "Sita Demo Thapa",
          reason: "FY 2082/83 clearance issued; upload pending.",
          overridden_at: now.toISOString(),
          hard_failures: hard.map((i) => `${i.rule_id}:${i.requirement}`),
          active: true,
        }
      : null,
    blocked,
    hard_failures: hard.length,
    counts: {
      pass: items.filter((i) => i.status === "pass").length,
      fail: items.filter((i) => i.status === "fail").length,
      unclear: items.filter((i) => i.status === "unclear").length,
    },
    proposal_allowed: !blocked || accepted,
  };
  const record: S["TenderRecord"] = {
    title: clean
      ? "Gabion river training works, Paundi Khola (180 m)"
      : "Upgrading and Gravelling of Bhanu-Satiswara Road (3.2 km) including Side Drains and Slab Culverts, Bhanu-6, Tanahun",
    reference_no: "BM/NCB/W-07/2083-84",
    buyer: clean
      ? "Madhya Nepal Municipality"
      : "Bhanu Municipality, Office of the Municipal Executive",
    buyer_level: "local",
    province: "gandaki",
    district: clean ? "Lamjung" : "Tanahun",
    scope:
      "Gravelling of a 3.2 km road with side drains and four slab culverts.",
    procurement_type: "works",
    method: "ncb",
    evaluation_method: "lowest_evaluated",
    language: "mixed",
    deadline_ad: deadline.ad,
    deadline_bs_iso: deadline.bs,
    currency: "NPR",
    estimated_cost_npr: 14_875_000,
    bid_security: { amount_npr: 446_000, percent: null, validity_days: 128 },
    bid_validity_days: 90,
    bid_doc_fee_npr: null,
    performance_security_percent: 5,
    domestic_preference: false,
    jv_allowed: true,
    required_docs: [],
    requirements: clean ? [] : REQUIREMENTS_001,
    bid_security_due: {
      amount_npr: 446_000,
      valid_until: "2027-03-29",
      valid_until_bs: "2083-12-15",
      basis: "fixed amount in notice",
    },
    sources: [
      {
        field: "title",
        value: record_title(clean),
        raw: record_title(clean),
        quote: "Name of Work: " + record_title(clean),
        quote_found: true,
      },
      {
        field: "buyer",
        value: "Bhanu Municipality, Office of the Municipal Executive",
        raw: "Bhanu Municipality, Office of the Municipal Executive",
        quote:
          "Bhanu Municipality, Office of the Municipal Executive, invites electronic bids",
        quote_found: true,
      },
      {
        field: "deadline_ad",
        value: deadline.ad,
        raw: "12:00 hours on 2083-08-05 B.S. (2026-11-21 A.D.)",
        quote:
          "Bids must be submitted electronically through the PPMO e-GP system on or before 12:00 hours on 2083-08-05 B.S. (2026-11-21 A.D.).",
        quote_found: true,
      },
      {
        field: "estimated_cost_npr",
        value: 14_875_000,
        raw: "Rs. 1,48,75,000/-",
        quote: "Estimated cost (excluding VAT): Rs. 1,48,75,000/-",
        quote_found: true,
      },
      {
        field: "bid_security.amount_npr",
        value: 446_000,
        raw: "Rs. 4,46,000/-",
        quote:
          "Bidders must submit a bid security of Rs. 4,46,000/- in the form of a bank guarantee",
        quote_found: true,
      },
      {
        field: "bid_doc_fee_npr",
        value: null,
        raw: "Rs. 3,0000/-",
        quote:
          "after paying a non-refundable fee of Rs. 3,0000/- to the municipality's revenue account",
        quote_found: true,
      },
      {
        field: "criteria.min_avg_turnover_npr",
        value: 15_000_000,
        raw: "Rs. 1,50,00,000",
        quote:
          "Average annual construction turnover of the best three years within the last five fiscal years of at least Rs. 1,50,00,000.",
        quote_found: true,
      },
      {
        field: "jv_allowed",
        value: true,
        raw: null,
        quote:
          "Bidders may form a joint venture of not more than three partners.",
        quote_found: true,
      },
    ],
    review_flags: [
      {
        field: "bid_doc_fee_npr",
        reason: "cannot read: invalid digit grouping 'Rs. 3,0000/-'",
        raw: "Rs. 3,0000/-",
      },
    ],
    needs_review: true,
  };
  const match: S["MatchResult"] = {
    score: 82,
    decision: "pursue",
    threshold: 60,
    deterministic_score: 100,
    semantic_score: 70,
    llm_weight: 0.6,
    reasons: [
      "[deterministic] procurement type works is one the company bids on",
      "[deterministic] Tanahun district is served by the company",
      "[deterministic] estimated cost 1.4875 crore is 0.30x average annual turnover 5.03 crore (within capacity)",
      "[deterministic] deadline 2026-11-21 12:00 NPT: 17 days left",
      "[model] Rural road gravelling is the company's core service [chunk 3]",
    ],
  };
  const status =
    proposalStatus(id) ?? (blocked && !accepted ? "blocked" : "checked");
  return {
    id,
    latest_proposal: proposalStatus(id) ? latestSummary(id) : null,
    source_url: `seed://seed_tenders/${id}`,
    status,
    deadline: deadline.ad,
    deadline_view: deadline,
    record,
    match,
    compliance,
  };
}

function record_title(clean: boolean): string {
  return clean
    ? "Gabion River Training Works on Paundi Khola (180 m) at Madhya Nepal-6, Lamjung"
    : "Upgrading and Gravelling of Bhanu-Satiswara Road (3.2 km) including Side Drains and Slab Culverts, Bhanu-6, Tanahun";
}

export async function getTender(id: number): Promise<TenderDetail | null> {
  await delay();
  return buildDetail(id);
}

export async function overrideCompliance(id: number): Promise<TenderDetail> {
  await delay(300);
  overridden = true;
  const detail = buildDetail(id);
  if (!detail) throw new Error(`No tender ${id}`);
  return detail;
}

export async function analyzeTender(id: number): Promise<PipelineRunView> {
  await delay(200);
  const runId = Math.max(0, ...runs.keys()) + 1;
  runs.set(runId, { startedAt: Date.now(), tenderId: id, kind: "analyze" });
  return runView(runId, Date.now());
}

/** POST /tenders/{id}/proposal: a mock Proposal + Review run with section-by-section progress. */
export async function generateProposal(id: number): Promise<PipelineRunView> {
  await delay(200);
  const detail = buildDetail(id);
  if (!detail?.compliance?.proposal_allowed)
    throw new Error(`tender ${id} is blocked by hard compliance failures`);
  const runId = Math.max(0, ...runs.keys()) + 1;
  runs.set(runId, { startedAt: Date.now(), tenderId: id, kind: "proposal" });
  return runView(runId, Date.now());
}

const SECTION_TITLES = [
  "Cover letter",
  "Bidder information and eligibility",
  "Work plan and schedule",
  "Relevant experience",
  "Key equipment",
  "Financial capacity",
  "Declarations",
];
const DRAFT_MS = 2000;

function proposalRunView(
  runId: number,
  entry: MockRun,
  now: number,
): PipelineRunView {
  const elapsed = now - entry.startedAt;
  const done = elapsed >= RUN_MS;
  if (done) markGenerated();
  const total = SECTION_TITLES.length;
  const drafted = Math.min(total, Math.floor((elapsed / DRAFT_MS) * total));
  const draftingDone = elapsed >= DRAFT_MS;
  const iso = new Date(entry.startedAt).toISOString();
  return {
    id: runId,
    tender_id: entry.tenderId,
    target: "reviewed",
    status: done ? "succeeded" : "running",
    start_status: "checked",
    end_status: done ? "reviewed" : null,
    stages: [
      {
        stage: "proposal",
        status: draftingDone ? "ok" : "running",
        from_status: "checked",
        to_status: draftingDone ? "drafted" : null,
        progress: {
          done: drafted,
          total,
          current: draftingDone ? null : (SECTION_TITLES[drafted] ?? null),
          items: SECTION_TITLES.map((title, i) => ({
            key: String(i),
            title,
            status: i < drafted ? "ok" : i === drafted ? "running" : "pending",
          })),
        },
      },
      {
        stage: "review",
        status: done ? "ok" : draftingDone ? "running" : "pending",
        from_status: "drafted",
        to_status: done ? "reviewed" : null,
      },
    ],
    created_at: iso,
    started_at: iso,
    finished_at: done ? new Date(entry.startedAt + RUN_MS).toISOString() : null,
  };
}

function runView(runId: number, now: number): PipelineRunView {
  const entry = runs.get(runId);
  if (!entry) throw new Error(`No run ${runId}`);
  if (entry.kind === "proposal") return proposalRunView(runId, entry, now);
  const elapsed = now - entry.startedAt;
  const done = elapsed >= RUN_MS;
  const blocked = entry.tenderId === 1 && !overridden;
  const iso = new Date(entry.startedAt).toISOString();
  return {
    id: runId,
    tender_id: entry.tenderId,
    target: "checked",
    status: done
      ? blocked
        ? "stopped"
        : "succeeded"
      : elapsed < 200
        ? "queued"
        : "running",
    start_status: "extracted",
    end_status: done ? (blocked ? "blocked" : "checked") : null,
    stages: [
      {
        stage: "matching",
        status: elapsed >= 1500 ? "ok" : "running",
        from_status: "extracted",
        to_status: elapsed >= 1500 ? "matched" : null,
      },
      {
        stage: "compliance",
        status: done
          ? blocked
            ? "branched"
            : "ok"
          : elapsed >= 1500
            ? "running"
            : "pending",
        from_status: "matched",
        to_status: done ? (blocked ? "blocked" : "checked") : null,
      },
    ],
    created_at: iso,
    started_at: iso,
    finished_at: done ? new Date(entry.startedAt + 3000).toISOString() : null,
  };
}

export async function getRun(runId: number): Promise<PipelineRunDetail> {
  await delay(100);
  const review = reviewRunView(runId);
  if (review) return { ...review, agent_runs: [] };
  return { ...runView(runId, Date.now()), agent_runs: [] };
}

export async function listRules(): Promise<RuleView[]> {
  await delay(50);
  return structuredClone(RULES);
}

export async function listChunks(ids: number[]): Promise<KBChunkView[]> {
  await delay(50);
  return structuredClone(CHUNKS.filter((c) => ids.includes(c.chunk_id)));
}

/** Test helper: restore the initial mock state. */
export function resetMockDetailState() {
  overridden = false;
  runs.clear();
}

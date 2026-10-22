/**
 * The app's API calls, typed from the generated OpenAPI schema. With NEXT_PUBLIC_USE_MOCKS=1
 * each call is served by lib/mock/ instead, so the UI works without the backend.
 */
import { PUBLIC_API_URL, USE_MOCKS, apiBaseUrl } from "@/lib/config";
import * as mock from "@/lib/mock/api";
import * as mockDetail from "@/lib/mock/detail-api";
import * as mockProposal from "@/lib/mock/proposal-api";
import * as mockRuns from "@/lib/mock/runs-api";

import { getApiClient } from "./client";
import {
  BUYER_LEVELS,
  DECISIONS,
  LANGUAGES,
  METHODS,
  PROCUREMENT_TYPES,
  PROVINCES,
  STATUSES,
} from "./enums";
import type { components, operations } from "./types";

type S = components["schemas"];
export type TenderListItem = S["TenderListItem"];
export type DeadlineView = S["DeadlineView"];
export type ScrapeReport = S["ScrapeReport"];
export type CompanyProfile = S["CompanyProfile"];
export type CompanyView = S["CompanyView"];
export type CompanyDocumentView = S["CompanyDocumentView"];
export type DocType = S["DocType"];
export type TenderDetail = S["TenderDetail"];
export type TenderRecord = S["TenderRecord"];
export type MatchResult = S["MatchResult"];
export type ComplianceItem = S["ComplianceItem"];
export type ComplianceView = S["ComplianceView"];
export type PipelineRunView = S["PipelineRunView"];
export type PipelineRunDetail = S["PipelineRunDetail"];
export type Proposal = S["Proposal"];
export type ProposalSection = S["ProposalSection"];
export type ReviewReport = S["ReviewReport"];
export type ChecklistItem = S["ChecklistItem"];
export type AgentRunView = S["AgentRunView"];
export type Requirement = S["Requirement"];
export type TenderFilters = NonNullable<
  operations["list_tenders_tenders_get"]["parameters"]["query"]
>;

/** GET /rules (api/routers/reference.py): the fields the UI reads (a subset of the generated `Rule`). */
export type RuleView = {
  id: string;
  description: string;
  severity: "hard" | "soft";
  /** URL of the source the rule is seeded from. */
  source: string;
  verified: boolean;
  notes?: string | null;
};

/** GET /chunks: one knowledge-base chunk with its document. */
export type KBChunkView = S["KBChunkView"];

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI errors: {"detail": "text"} or {"detail": [{loc, msg}, ...]} (422). */
export function errorMessage(
  error: unknown,
  response: Response | undefined,
): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map(
        (d: { loc?: (string | number)[]; msg?: string }) =>
          `${(d.loc ?? []).filter((p) => p !== "body").join(".")}: ${d.msg ?? ""}`,
      )
      .join("; ");
  }
  return response
    ? `HTTP ${response.status} ${response.statusText}`
    : "network error";
}

function fail(error: unknown, response: Response | undefined): never {
  throw new ApiError(errorMessage(error, response), response?.status ?? 0);
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, { cache: "no-store" });
  if (!response.ok)
    throw new ApiError(
      `HTTP ${response.status} ${response.statusText}`,
      response.status,
    );
  return (await response.json()) as T;
}

export async function listTenders(
  filters: TenderFilters = {},
): Promise<TenderListItem[]> {
  if (USE_MOCKS) return mock.listTenders(filters);
  const { data, error, response } = await getApiClient().GET("/tenders", {
    params: { query: filters },
    cache: "no-store",
  });
  if (!data) fail(error, response);
  return data;
}

export async function scrapeTenders(): Promise<ScrapeReport> {
  if (USE_MOCKS) return mock.scrapeTenders();
  const { data, error, response } = await getApiClient().POST(
    "/tenders/scrape",
    { body: { source: "seed", max_pages: 1, max_notices: 3 } },
  );
  if (!data) fail(error, response);
  return data;
}

/** The stored profile, or null if none has been saved yet (404). */
export async function getCompany(): Promise<CompanyView | null> {
  if (USE_MOCKS) return mock.getCompany();
  const { data, error, response } = await getApiClient().GET("/company", {
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!data) fail(error, response);
  return data;
}

export async function saveCompany(
  profile: CompanyProfile,
): Promise<CompanyView> {
  if (USE_MOCKS) return mock.saveCompany(profile);
  const { data, error, response } = await getApiClient().POST("/company", {
    body: profile,
  });
  if (!data) fail(error, response);
  return data;
}

export async function listDocuments(): Promise<CompanyDocumentView[]> {
  if (USE_MOCKS) return mock.listDocuments();
  const { data, error, response } = await getApiClient().GET(
    "/company/documents",
    { cache: "no-store" },
  );
  if (!data) fail(error, response);
  return data;
}

export type UploadInput = {
  file: File;
  doc_type: DocType;
  /** AD ISO date. */
  expires_on?: string | null;
  fiscal_year_bs?: string | null;
  value_npr?: number | null;
};

export async function uploadDocument(
  input: UploadInput,
): Promise<CompanyDocumentView> {
  if (USE_MOCKS) return mock.uploadDocument(input);
  const form = new FormData();
  form.append("file", input.file);
  form.append("doc_type", input.doc_type);
  if (input.expires_on) form.append("expires_on", input.expires_on);
  if (input.fiscal_year_bs) form.append("fiscal_year_bs", input.fiscal_year_bs);
  if (input.value_npr != null)
    form.append("value_npr", String(input.value_npr));
  const { data, error, response } = await getApiClient().POST(
    "/company/documents",
    {
      // The generated body type models the file as a string; the real payload is this FormData.
      body: {} as S["Body_upload_company_document_company_documents_post"],
      bodySerializer: () => form,
    },
  );
  if (!data) fail(error, response);
  return data;
}

// --- tender detail ------------------------------------------------------------------------------------

/** "12" -> 12; anything else (including "12abc", "-1", "") -> null. */
export function parseTenderId(raw: string): number | null {
  return /^\d{1,9}$/.test(raw) ? Number(raw) : null;
}

/** GET /tenders/{id}, or null on 404. */
export async function getTender(id: number): Promise<TenderDetail | null> {
  if (USE_MOCKS) return mockDetail.getTender(id);
  const { data, error, response } = await getApiClient().GET(
    "/tenders/{tender_id}",
    {
      params: { path: { tender_id: id } },
      cache: "no-store",
    },
  );
  if (response.status === 404) return null;
  if (!data) fail(error, response);
  return asTenderDetail(data);
}

/**
 * openapi-fetch's Readable<T> maps arrays element-wise, which widens the FieldSource.span
 * tuple ([start, end)) to number[]. The generated schema type is the accurate one.
 */
function asTenderDetail(data: unknown): TenderDetail {
  return data as TenderDetail;
}

/** POST /tenders/{id}/analyze: 202 + a queued run. Poll it with getRun. */
export async function analyzeTender(id: number): Promise<PipelineRunView> {
  if (USE_MOCKS) return mockDetail.analyzeTender(id);
  const { data, error, response } = await getApiClient().POST(
    "/tenders/{tender_id}/analyze",
    { params: { path: { tender_id: id } } },
  );
  if (!data) fail(error, response);
  return data;
}

export async function getRun(runId: number): Promise<PipelineRunDetail> {
  if (USE_MOCKS) return mockDetail.getRun(runId);
  const { data, error, response } = await getApiClient().GET("/runs/{run_id}", {
    params: { path: { run_id: runId } },
    cache: "no-store",
  });
  if (!data) fail(error, response);
  return data;
}

/** POST /tenders/{id}/compliance/override: a named person accepts the current hard failures. */
export async function overrideCompliance(
  id: number,
  overriddenBy: string,
  reason: string,
): Promise<TenderDetail> {
  if (USE_MOCKS) return mockDetail.overrideCompliance(id);
  const { data, error, response } = await getApiClient().POST(
    "/tenders/{tender_id}/compliance/override",
    {
      params: { path: { tender_id: id } },
      body: { overridden_by: overriddenBy, reason },
    },
  );
  if (!data) fail(error, response);
  return asTenderDetail(data);
}

/**
 * POST /tenders/{id}/proposal: 202 + a queued run that drafts a new proposal version (409 while blocked).
 * Poll it with getRun; the proposal stage carries section-by-section `progress`.
 */
export async function generateProposal(
  id: number,
  forceEnglish?: boolean,
): Promise<PipelineRunView> {
  if (USE_MOCKS) return mockDetail.generateProposal(id);
  const { data, error, response } = await getApiClient().POST(
    "/tenders/{tender_id}/proposal",
    {
      params: { path: { tender_id: id } },
      body:
        forceEnglish === undefined ? undefined : { force_english: forceEnglish },
    },
  );
  if (!data) fail(error, response);
  return data;
}

export async function listRules(): Promise<RuleView[]> {
  if (USE_MOCKS) return mockDetail.listRules();
  return getJson<RuleView[]>("/rules");
}

export async function listChunks(ids: number[]): Promise<KBChunkView[]> {
  if (ids.length === 0) return [];
  if (USE_MOCKS) return mockDetail.listChunks(ids);
  return getJson<KBChunkView[]>(
    `/chunks?${ids.map((i) => `ids=${i}`).join("&")}`,
  );
}

/** A tender with the evidence its compliance items cite, ready for the matrix. */
export type TenderBundle = {
  detail: TenderDetail;
  chunks: Record<number, KBChunkView>;
  documents: Record<number, CompanyDocumentView>;
};

const uniq = (xs: number[]) => [...new Set(xs)];

/**
 * The tender plus the chunk text and document records its compliance items cite. Evidence lookups
 * are best effort: if they fail the matrix still renders, with ids instead of text.
 */
export async function loadTenderBundle(
  id: number,
): Promise<TenderBundle | null> {
  const detail = await getTender(id);
  if (!detail) return null;
  const items = detail.compliance?.items ?? [];
  const chunkIds = uniq(items.flatMap((i) => i.evidence_chunk_ids ?? []));
  const needDocs = items.some(
    (i) => (i.evidence_document_ids ?? []).length > 0,
  );
  const [chunkList, docList] = await Promise.all([
    chunkIds.length
      ? listChunks(chunkIds).catch((): KBChunkView[] => [])
      : Promise.resolve([] as KBChunkView[]),
    needDocs
      ? listDocuments().catch((): CompanyDocumentView[] => [])
      : Promise.resolve([] as CompanyDocumentView[]),
  ]);
  return {
    detail,
    chunks: Object.fromEntries(chunkList.map((c) => [c.chunk_id, c])),
    documents: Object.fromEntries(docList.map((d) => [d.id, d])),
  };
}

// --- proposal page -------------------------------------------------------------------------------------

/** GET /tenders/{id}/proposals: every stored version, newest first. */
export async function listProposals(tenderId: number): Promise<Proposal[]> {
  if (USE_MOCKS) return mockProposal.listProposals(tenderId);
  const { data, error, response } = await getApiClient().GET(
    "/tenders/{tender_id}/proposals",
    { params: { path: { tender_id: tenderId } }, cache: "no-store" },
  );
  if (!data) fail(error, response);
  return data;
}

/** POST /proposals/{id}/open: a person is looking at this version (approval needs an open after its review). */
export async function openProposal(id: number): Promise<Proposal> {
  if (USE_MOCKS) return mockProposal.openProposal(id);
  const { data, error, response } = await getApiClient().POST(
    "/proposals/{proposal_id}/open",
    { params: { path: { proposal_id: id } } },
  );
  if (!data) fail(error, response);
  return data;
}

/** POST /proposals/{id}/approve: the human gate (409 lists every blocker). */
export async function approveProposal(
  id: number,
  approvedBy: string,
  note: string | null,
): Promise<Proposal> {
  if (USE_MOCKS) return mockProposal.approveProposal(id, approvedBy, note);
  const { data, error, response } = await getApiClient().POST(
    "/proposals/{proposal_id}/approve",
    {
      params: { path: { proposal_id: id } },
      body: { approved_by: approvedBy, note },
    },
  );
  if (!data) fail(error, response);
  return data;
}

/** POST /proposals/{id}/sections/{key}/edit: a person's text, saved as a new (unreviewed) version. */
export async function editSection(
  id: number,
  key: string,
  body: string,
  editedBy: string,
  note: string | null,
): Promise<Proposal> {
  if (USE_MOCKS) return mockProposal.editSection(id, key, body, editedBy);
  const { data, error, response } = await getApiClient().POST(
    "/proposals/{proposal_id}/sections/{section_key}/edit",
    {
      params: { path: { proposal_id: id, section_key: key } },
      body: { body, edited_by: editedBy, note },
    },
  );
  if (!data) fail(error, response);
  return data;
}

/** POST /proposals/{id}/review: 202 + a run that reviews the latest version (no automatic revision). */
export async function reviewProposal(id: number): Promise<PipelineRunView> {
  if (USE_MOCKS) return mockProposal.reviewProposal(id);
  const { data, error, response } = await getApiClient().POST(
    "/proposals/{proposal_id}/review",
    { params: { path: { proposal_id: id } } },
  );
  if (!data) fail(error, response);
  return data;
}

/** GET /proposals/{id}/checklist: the attachment checklist (present / expiring / missing). */
export async function getChecklist(id: number): Promise<ChecklistItem[]> {
  if (USE_MOCKS) return mockProposal.getChecklist(id);
  const { data, error, response } = await getApiClient().GET(
    "/proposals/{proposal_id}/checklist",
    { params: { path: { proposal_id: id } }, cache: "no-store" },
  );
  if (!data) fail(error, response);
  return data;
}

export type ExportKind = "docx" | "pdf" | "zip";

/** Download link of an approved version: the bid document (DOCX/PDF) or the whole package (ZIP). */
export function exportUrl(id: number, kind: ExportKind): string {
  if (USE_MOCKS) return mockProposal.exportUrl(id, kind);
  const path =
    kind === "zip" ? `/proposals/${id}/package` : `/proposals/${id}/export/${kind}`;
  return `${PUBLIC_API_URL}${path}`;
}

/** The proposal page's data: tender, versions, the shown version and the KB chunks it cites. */
export type ProposalBundle = {
  tender: TenderDetail;
  versions: Proposal[];
  proposal: Proposal | null;
  chunks: Record<number, KBChunkView>;
  checklist: ChecklistItem[] | null;
};

/**
 * Tender + versions + the chosen version (default: the latest) + its cited chunk text. The chunk text and
 * the checklist are best effort: on failure the page still renders, with chunk ids and no checklist.
 */
export async function loadProposalBundle(
  tenderId: number,
  proposalId?: number | null,
): Promise<ProposalBundle | null> {
  const [tender, versions] = await Promise.all([
    getTender(tenderId),
    listProposals(tenderId).catch((e) => {
      if (e instanceof ApiError && e.status === 404) return [] as Proposal[];
      throw e;
    }),
  ]);
  if (!tender) return null;
  const proposal =
    versions.find((v) => v.id === proposalId) ?? versions[0] ?? null;
  const chunkIds = uniq(
    (proposal?.sections ?? []).flatMap((s) => s.cited_chunk_ids ?? []),
  );
  const [chunkList, checklist] = await Promise.all([
    listChunks(chunkIds).catch((): KBChunkView[] => []),
    proposal
      ? getChecklist(proposal.id).catch((): ChecklistItem[] | null => null)
      : Promise.resolve(null),
  ]);
  return {
    tender,
    versions,
    proposal,
    chunks: Object.fromEntries(chunkList.map((c) => [c.chunk_id, c])),
    checklist,
  };
}

// --- runs page -----------------------------------------------------------------------------------------

export type AgentRunFilters = NonNullable<
  operations["list_agent_runs_agent_runs_get"]["parameters"]["query"]
>;

/** GET /agent-runs: the audit log, newest first. */
export async function listAgentRuns(
  filters: AgentRunFilters = {},
): Promise<AgentRunView[]> {
  if (USE_MOCKS) return mockRuns.listAgentRuns(filters);
  const { data, error, response } = await getApiClient().GET("/agent-runs", {
    params: { query: filters },
    cache: "no-store",
  });
  if (!data) fail(error, response);
  return data;
}

/** GET /runs: pipeline runs, newest first. */
export async function listRuns(limit = 20): Promise<PipelineRunView[]> {
  if (USE_MOCKS) return mockRuns.listRuns(limit);
  const { data, error, response } = await getApiClient().GET("/runs", {
    params: { query: { limit } },
    cache: "no-store",
  });
  if (!data) fail(error, response);
  return data;
}

const STAGES = ["scout", "matching", "compliance", "proposal", "review"] as const;

/** URL search params -> GET /agent-runs filters (invalid values dropped). */
export function parseAgentRunFilters(sp: SearchParams): AgentRunFilters {
  const ok = Array.isArray(sp.ok) ? sp.ok[0] : sp.ok;
  const filters: AgentRunFilters = {
    stage: pick(sp.stage, STAGES),
    ok: ok === "true" ? true : ok === "false" ? false : undefined,
    tender_id: int(sp.tender_id, 1, 999_999_999),
    pipeline_run_id: int(sp.run, 1, 999_999_999),
    limit: 100,
  };
  return Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined),
  ) as AgentRunFilters;
}

type SearchParams = Record<string, string | string[] | undefined>;

function pick<T extends string>(
  value: string | string[] | undefined,
  allowed: readonly T[],
): T | undefined {
  const v = Array.isArray(value) ? value[0] : value;
  return allowed.includes(v as T) ? (v as T) : undefined;
}

function int(
  value: string | string[] | undefined,
  min: number,
  max: number,
): number | undefined {
  const v = Array.isArray(value) ? value[0] : value;
  if (!v || !/^\d+$/.test(v)) return undefined;
  const n = Number(v);
  return n >= min && n <= max ? n : undefined;
}

/** URL search params -> GET /tenders filters. Unknown or invalid values are dropped, never sent. */
export function parseTenderFilters(sp: SearchParams): TenderFilters {
  const district = (
    Array.isArray(sp.district) ? sp.district[0] : sp.district
  )?.trim();
  const filters: TenderFilters = {
    procurement_type: pick(sp.procurement_type, PROCUREMENT_TYPES),
    method: pick(sp.method, METHODS),
    province: pick(sp.province, PROVINCES),
    district: district || undefined,
    buyer_level: pick(sp.buyer_level, BUYER_LEVELS),
    min_score: int(sp.min_score, 0, 100),
    deadline_within_days: int(sp.deadline_within_days, 0, 3650),
    language: pick(sp.language, LANGUAGES),
    decision: pick(sp.decision, DECISIONS),
    status: pick(sp.status, STATUSES),
  };
  return Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined),
  ) as TenderFilters;
}

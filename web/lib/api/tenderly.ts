/**
 * The app's API calls, typed from the generated OpenAPI schema. With NEXT_PUBLIC_USE_MOCKS=1
 * each call is served by lib/mock/ instead, so the UI works without the backend.
 */
import { USE_MOCKS, apiBaseUrl } from "@/lib/config";
import * as mock from "@/lib/mock/api";
import * as mockDetail from "@/lib/mock/detail-api";

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
export type TenderFilters = NonNullable<
  operations["list_tenders_tenders_get"]["parameters"]["query"]
>;

/** GET /rules (api/routers/reference.py). Hand-typed until `bun run gen:api` is re-run. */
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
export type KBChunkView = {
  chunk_id: number;
  document_id: number;
  filename: string;
  doc_type: DocType;
  chunk_index: number;
  content: string;
  expires_on?: string | null;
  is_expired?: boolean | null;
  fiscal_year_bs?: string | null;
};

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
  return data;
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
  return data;
}

/** POST /tenders/{id}/proposal. 409 while blocked; 501 until the Proposal agent exists. */
export async function generateProposal(id: number): Promise<Proposal> {
  if (USE_MOCKS)
    throw new ApiError(
      "Not implemented yet - see PROGRESS.md Next prompt.",
      501,
    );
  const { data, error, response } = await getApiClient().POST(
    "/tenders/{tender_id}/proposal",
    { params: { path: { tender_id: id } } },
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

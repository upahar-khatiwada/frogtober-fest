/**
 * The app's API calls, typed from the generated OpenAPI schema. With NEXT_PUBLIC_USE_MOCKS=1
 * each call is served by lib/mock/api.ts instead, so the UI works without the backend.
 */
import { USE_MOCKS } from "@/lib/config";
import * as mock from "@/lib/mock/api";

import { getApiClient } from "./client";
import { BUYER_LEVELS, DECISIONS, LANGUAGES, METHODS, PROCUREMENT_TYPES, PROVINCES, STATUSES } from "./enums";
import type { components, operations } from "./types";

type S = components["schemas"];
export type TenderListItem = S["TenderListItem"];
export type DeadlineView = S["DeadlineView"];
export type ScrapeReport = S["ScrapeReport"];
export type CompanyProfile = S["CompanyProfile"];
export type CompanyView = S["CompanyView"];
export type CompanyDocumentView = S["CompanyDocumentView"];
export type DocType = S["DocType"];
export type TenderFilters = NonNullable<operations["list_tenders_tenders_get"]["parameters"]["query"]>;

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
export function errorMessage(error: unknown, response: Response | undefined): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: (string | number)[]; msg?: string }) => `${(d.loc ?? []).filter((p) => p !== "body").join(".")}: ${d.msg ?? ""}`)
      .join("; ");
  }
  return response ? `HTTP ${response.status} ${response.statusText}` : "network error";
}

function fail(error: unknown, response: Response | undefined): never {
  throw new ApiError(errorMessage(error, response), response?.status ?? 0);
}

export async function listTenders(filters: TenderFilters = {}): Promise<TenderListItem[]> {
  if (USE_MOCKS) return mock.listTenders(filters);
  const { data, error, response } = await getApiClient().GET("/tenders", { params: { query: filters }, cache: "no-store" });
  if (!data) fail(error, response);
  return data;
}

export async function scrapeTenders(): Promise<ScrapeReport> {
  if (USE_MOCKS) return mock.scrapeTenders();
  const { data, error, response } = await getApiClient().POST("/tenders/scrape", { body: { source: "seed", max_pages: 1, max_notices: 3 } });
  if (!data) fail(error, response);
  return data;
}

/** The stored profile, or null if none has been saved yet (404). */
export async function getCompany(): Promise<CompanyView | null> {
  if (USE_MOCKS) return mock.getCompany();
  const { data, error, response } = await getApiClient().GET("/company", { cache: "no-store" });
  if (response.status === 404) return null;
  if (!data) fail(error, response);
  return data;
}

export async function saveCompany(profile: CompanyProfile): Promise<CompanyView> {
  if (USE_MOCKS) return mock.saveCompany(profile);
  const { data, error, response } = await getApiClient().POST("/company", { body: profile });
  if (!data) fail(error, response);
  return data;
}

export async function listDocuments(): Promise<CompanyDocumentView[]> {
  if (USE_MOCKS) return mock.listDocuments();
  const { data, error, response } = await getApiClient().GET("/company/documents", { cache: "no-store" });
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

export async function uploadDocument(input: UploadInput): Promise<CompanyDocumentView> {
  if (USE_MOCKS) return mock.uploadDocument(input);
  const form = new FormData();
  form.append("file", input.file);
  form.append("doc_type", input.doc_type);
  if (input.expires_on) form.append("expires_on", input.expires_on);
  if (input.fiscal_year_bs) form.append("fiscal_year_bs", input.fiscal_year_bs);
  if (input.value_npr != null) form.append("value_npr", String(input.value_npr));
  const { data, error, response } = await getApiClient().POST("/company/documents", {
    // The generated body type models the file as a string; the real payload is this FormData.
    body: {} as S["Body_upload_company_document_company_documents_post"],
    bodySerializer: () => form,
  });
  if (!data) fail(error, response);
  return data;
}

type SearchParams = Record<string, string | string[] | undefined>;

function pick<T extends string>(value: string | string[] | undefined, allowed: readonly T[]): T | undefined {
  const v = Array.isArray(value) ? value[0] : value;
  return allowed.includes(v as T) ? (v as T) : undefined;
}

function int(value: string | string[] | undefined, min: number, max: number): number | undefined {
  const v = Array.isArray(value) ? value[0] : value;
  if (!v || !/^\d+$/.test(v)) return undefined;
  const n = Number(v);
  return n >= min && n <= max ? n : undefined;
}

/** URL search params -> GET /tenders filters. Unknown or invalid values are dropped, never sent. */
export function parseTenderFilters(sp: SearchParams): TenderFilters {
  const district = (Array.isArray(sp.district) ? sp.district[0] : sp.district)?.trim();
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
  return Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== undefined)) as TenderFilters;
}

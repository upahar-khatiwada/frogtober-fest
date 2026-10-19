/**
 * In-memory stand-in for the API (NEXT_PUBLIC_USE_MOCKS=1). It emulates GET /tenders filters
 * and the upload -> ingest status flow, so every screen can be built and demoed offline.
 * State lives in this module: per browser tab on the client, per process on the server.
 */
import type { CompanyDocumentView, CompanyProfile, CompanyView, ScrapeReport, TenderFilters, TenderListItem, UploadInput } from "@/lib/api/tenderly";

import { MOCK_COMPANY, MOCK_DOCUMENTS, mockTenders } from "./data";

/** Mock ingestion: a new upload is "processing" for this long, then "ready". */
export const MOCK_INGEST_MS = 3000;

let company: CompanyView | null = structuredClone(MOCK_COMPANY);
let documents: CompanyDocumentView[] = structuredClone(MOCK_DOCUMENTS);

const DISTRICT_ALIASES: Record<string, string> = {
  कास्की: "kaski",
  तनहुँ: "tanahun",
  तनहुं: "tanahun",
  स्याङ्जा: "syangja",
  स्याङजा: "syangja",
  लमजुङ: "lamjung",
  पर्वत: "parbat",
  काठमाडौं: "kathmandu",
};

function normDistrict(name: string): string {
  const n = name.trim().normalize("NFC");
  return DISTRICT_ALIASES[n] ?? n.toLowerCase();
}

function delay(ms = 250): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function filterTenders(items: TenderListItem[], f: TenderFilters): TenderListItem[] {
  const filtered = items.filter((t) => {
    if (f.procurement_type && t.procurement_type !== f.procurement_type) return false;
    if (f.method && t.method !== f.method) return false;
    if (f.province && t.province !== f.province) return false;
    if (f.district && (!t.district || normDistrict(t.district) !== normDistrict(f.district))) return false;
    if (f.buyer_level && t.buyer_level !== f.buyer_level) return false;
    if (f.min_score != null && (t.score == null || t.score < f.min_score)) return false;
    if (f.deadline_within_days != null && (!t.deadline || t.deadline.passed || t.deadline.days_left > f.deadline_within_days)) return false;
    if (f.language && t.language !== f.language) return false;
    if (f.decision && t.decision !== f.decision) return false;
    if (f.status && t.status !== f.status) return false;
    return true;
  });
  return filtered.map((t, i) => ({ ...t, rank: i + 1 }));
}

export async function listTenders(filters: TenderFilters): Promise<TenderListItem[]> {
  await delay(100);
  return filterTenders(mockTenders(new Date()), filters);
}

export async function scrapeTenders(): Promise<ScrapeReport> {
  await delay(600);
  const ids = mockTenders(new Date()).map((t) => t.id);
  return { source: "seed", created: 0, updated: 0, unchanged: ids.length, tender_ids: ids, skipped: [], blocked: null };
}

export async function getCompany(): Promise<CompanyView | null> {
  await delay();
  return company ? structuredClone(company) : null;
}

export async function saveCompany(profile: CompanyProfile): Promise<CompanyView> {
  await delay();
  company = { ...structuredClone(profile), id: 1, updated_at: new Date().toISOString() };
  return structuredClone(company);
}

export async function listDocuments(): Promise<CompanyDocumentView[]> {
  await delay(100);
  const now = Date.now();
  documents = documents.map((d) =>
    d.ingest_status === "processing" && now - Date.parse(d.uploaded_at) >= MOCK_INGEST_MS ? { ...d, ingest_status: "ready", chunk_count: 1 } : d,
  );
  return structuredClone(documents).sort((a, b) => b.id - a.id);
}

export async function uploadDocument(input: UploadInput): Promise<CompanyDocumentView> {
  await delay(400);
  if (!company) throw new Error("No company profile yet; POST /company first.");
  const today = new Date().toISOString().slice(0, 10);
  const doc: CompanyDocumentView = {
    id: Math.max(0, ...documents.map((d) => d.id)) + 1,
    filename: input.file.name,
    doc_type: input.doc_type,
    expires_on: input.expires_on ?? null,
    is_expired: input.expires_on ? input.expires_on < today : null,
    fiscal_year_bs: input.fiscal_year_bs ?? null,
    value_npr: input.value_npr ?? null,
    ingest_status: "processing",
    warnings: [],
    page_count: null,
    chunk_count: 0,
    uploaded_at: new Date().toISOString(),
  };
  documents = [...documents, doc];
  return structuredClone(doc);
}

/** Test helper: restore the initial mock state. */
export function resetMockState() {
  company = structuredClone(MOCK_COMPANY);
  documents = structuredClone(MOCK_DOCUMENTS);
}

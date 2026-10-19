/**
 * Mock data for NEXT_PUBLIC_USE_MOCKS=1. Modelled on the SYNTHETIC seed notices and the
 * FICTIONAL demo company (data/seed_tenders, data/demo_company). Not real tenders.
 * Deadlines are relative to "now" so countdowns stay meaningful whenever the UI is opened.
 */
import type { components } from "@/lib/api/types";
import { daysLeftNpt, nptDate } from "@/lib/deadline";
import { adToBs, bsToAd, bsToIso, daysInBsMonth, formatBs } from "@/lib/nepal/calendar";

type S = components["schemas"];

/** A DeadlineView like the API's: `daysFromNow` NPT calendar days away, at `time` NPT. */
export function mockDeadline(daysFromNow: number, now: Date, time = "12:00"): S["DeadlineView"] {
  const today = nptDate(now);
  const adDate = new Date(Date.parse(today) + daysFromNow * 86_400_000).toISOString().slice(0, 10);
  const ad = `${adDate}T${time}:00+05:45`;
  const bs = adToBs(adDate);
  return {
    ad,
    ad_date: adDate,
    bs: bsToIso(bs),
    bs_long: formatBs(bs, "en"),
    bs_ne: formatBs(bs, "ne"),
    days_left: daysLeftNpt(new Date(ad), now),
    passed: new Date(ad).getTime() <= now.getTime(),
  };
}

type MockTender = Omit<S["TenderListItem"], "rank" | "deadline"> & { deadlineInDays: number | null };

const TENDERS: MockTender[] = [
  {
    id: 27,
    status: "checked",
    title: "River training works with gabion walls, Marsyangdi left bank",
    buyer: "Madhyanepal Municipality",
    buyer_level: "local",
    procurement_type: "works",
    method: "quotation",
    province: "gandaki",
    district: "Lamjung",
    language: "mixed",
    estimated_cost_npr: 3_850_000,
    deadlineInDays: 4,
    score: 86,
    decision: "pursue",
    reasons: [
      "[deterministic] procurement type works is one the company bids on",
      "[deterministic] Lamjung district is served by the company",
      "[deterministic] estimated cost NPR 38.5 lakh is 0.07x average annual turnover NPR 5.04 crore (within capacity)",
      "[model] Gabion river training matches the company's retaining-wall experience [chunk 12]",
    ],
    hard_failures: 0,
    needs_review: false,
    source_url: "seed://seed_tenders/027_madhyanepal_gabion_river_training_sq.txt",
  },
  {
    id: 1,
    status: "blocked",
    title: "Gravelling and side drains, Bhanu–Bandipur road section",
    buyer: "Bhanu Municipality",
    buyer_level: "local",
    procurement_type: "works",
    method: "ncb",
    province: "gandaki",
    district: "Tanahun",
    language: "mixed",
    estimated_cost_npr: 14_875_000,
    deadlineInDays: 17,
    score: 82,
    decision: "pursue",
    reasons: [
      "[deterministic] procurement type works is one the company bids on",
      "[deterministic] Tanahun district is served by the company",
      "[deterministic] estimated cost NPR 1.49 crore is 0.3x average annual turnover NPR 5.04 crore (within capacity)",
      "[model] Rural road gravelling is the company's core service [chunk 3]",
    ],
    hard_failures: 1,
    needs_review: false,
    source_url: "seed://seed_tenders/001_bhanu_road_gravelling.txt",
  },
  {
    id: 19,
    status: "matched",
    title: "Gabion retaining wall and covered drain, Bhimad ward 4",
    buyer: "Bhimad Municipality",
    buyer_level: "local",
    procurement_type: "works",
    method: "ncb",
    province: "gandaki",
    district: "Tanahun",
    language: "en",
    estimated_cost_npr: 6_240_000,
    deadlineInDays: 11,
    score: 78,
    decision: "pursue",
    reasons: [
      "[deterministic] Tanahun district is served by the company",
      "[model] Retaining walls and drains are listed services [chunk 3]",
    ],
    hard_failures: null,
    needs_review: false,
    source_url: "seed://seed_tenders/019_bhimad_gabion_wall_drain.txt",
  },
  {
    id: 29,
    status: "checked",
    title: "माछापुच्छ्रे गाउँपालिका ग्रामीण सडक मर्मत सम्भार",
    buyer: "माछापुच्छ्रे गाउँपालिका",
    buyer_level: "local",
    procurement_type: "works",
    method: "ncb",
    province: "gandaki",
    district: "Kaski",
    language: "ne",
    estimated_cost_npr: 9_200_000,
    deadlineInDays: 22,
    score: 74,
    decision: "pursue",
    reasons: [
      "[deterministic] Kaski district is served by the company",
      "[model] Road maintenance in Kaski fits the company's rural road work [chunk 5]",
    ],
    hard_failures: 0,
    needs_review: false,
    source_url: "seed://seed_tenders/029_machhapuchchhre_road_maintenance.txt",
  },
  {
    id: 15,
    status: "matched",
    title: "फेदीखोला गाउँपालिका वडा नं. ३ वडा कार्यालय भवन निर्माण",
    buyer: "फेदीखोला गाउँपालिका",
    buyer_level: "local",
    procurement_type: "works",
    method: "ncb",
    province: "gandaki",
    district: "Syangja",
    language: "ne",
    estimated_cost_npr: 11_500_000,
    deadlineInDays: 2,
    score: 71,
    decision: "pursue",
    reasons: [
      "[model] Small public buildings such as ward offices are a listed service [chunk 3]",
    ],
    hard_failures: null,
    needs_review: false,
    source_url: "seed://seed_tenders/015_phedikhola_ward_office_building.txt",
  },
  {
    id: 34,
    status: "extracted",
    title: "Footpath and kerb stone works, Pokhara ward 14",
    buyer: "Pokhara Metropolitan City, Ward 14",
    buyer_level: "local",
    procurement_type: "works",
    method: "quotation",
    province: "gandaki",
    district: "Kaski",
    language: "en",
    estimated_cost_npr: null,
    deadlineInDays: 9,
    score: null,
    decision: null,
    reasons: [],
    hard_failures: null,
    needs_review: true,
    source_url: "seed://seed_tenders/034_pokhara_ward14_footpath_garbled_cost.txt",
  },
  {
    id: 2,
    status: "skipped",
    title: "Seti river training and embankment protection works",
    buyer: "Ministry of Physical Infrastructure Development, Gandaki Province",
    buyer_level: "province",
    procurement_type: "works",
    method: "ncb",
    province: "gandaki",
    district: "Kaski",
    language: "en",
    estimated_cost_npr: 185_500_000,
    deadlineInDays: 25,
    score: 59,
    decision: "skip",
    reasons: [
      "[deterministic] SKIP: estimated cost NPR 18.55 crore is 3.68x average annual turnover NPR 5.04 crore (above the 2x capacity limit)",
      "[deterministic] Kaski district is served by the company",
    ],
    hard_failures: null,
    needs_review: false,
    source_url: "seed://seed_tenders/002_gandaki_seti_river_training.txt",
  },
  {
    id: 8,
    status: "skipped",
    title: "Blacktopping of Besisahar–Bhulbhule road",
    buyer: "Besisahar Municipality",
    buyer_level: "local",
    procurement_type: "works",
    method: "ncb",
    province: "gandaki",
    district: "Lamjung",
    language: "mixed",
    estimated_cost_npr: 24_000_000,
    deadlineInDays: -5,
    score: 40,
    decision: "skip",
    reasons: ["[deterministic] SKIP: deadline has passed"],
    hard_failures: null,
    needs_review: false,
    source_url: "seed://seed_tenders/008_besisahar_blacktop_expired.txt",
  },
  {
    id: 3,
    status: "skipped",
    title: "Supply and delivery of ICU ventilators (ICB)",
    buyer: "Department of Health Services",
    buyer_level: "federal",
    procurement_type: "goods",
    method: "icb",
    province: "bagmati",
    district: "Kathmandu",
    language: "en",
    estimated_cost_npr: 450_000_000,
    deadlineInDays: 30,
    score: 20,
    decision: "skip",
    reasons: [
      "[deterministic] SKIP: procurement type goods is not one the company bids on (works)",
      "[deterministic] SKIP: Kathmandu is outside the company's province",
    ],
    hard_failures: null,
    needs_review: false,
    source_url: "seed://seed_tenders/003_dohs_icu_ventilators_icb.txt",
  },
  {
    id: 33,
    status: "new",
    title: null,
    buyer: null,
    buyer_level: null,
    procurement_type: null,
    method: null,
    province: null,
    district: null,
    language: null,
    estimated_cost_npr: null,
    deadlineInDays: null,
    score: null,
    decision: null,
    reasons: [],
    hard_failures: null,
    needs_review: false,
    source_url: "seed://seed_tenders/033_rhishing_culvert_two_deadlines.txt",
  },
];

/** Mock list items in the API's ranking order (score desc, deadline asc, unscored last). */
export function mockTenders(now: Date): S["TenderListItem"][] {
  const items = TENDERS.map(({ deadlineInDays, ...t }) => ({
    ...t,
    rank: 0,
    deadline: deadlineInDays === null ? null : mockDeadline(deadlineInDays, now),
  }));
  items.sort((a, b) => {
    if (a.score == null !== (b.score == null)) return a.score == null ? 1 : -1;
    if (a.score !== b.score) return (b.score ?? 0) - (a.score ?? 0);
    const da = a.deadline ? Date.parse(a.deadline.ad) : Infinity;
    const db = b.deadline ? Date.parse(b.deadline.ad) : Infinity;
    return da - db || a.id - b.id;
  });
  return items.map((t, i) => ({ ...t, rank: i + 1 }));
}

export const MOCK_COMPANY: S["CompanyView"] = {
  id: 1,
  updated_at: "2026-10-17T10:00:00+05:45",
  name: "Annapurna Demo Nirman Sewa Pvt. Ltd.",
  sectors: ["civil works", "rural roads", "drainage and culverts", "small public buildings"],
  procurement_types: ["works"],
  services:
    "Gravel and blacktop rural roads, side drains and culverts, gabion and stone-masonry retaining walls, and small public buildings (ward offices, school blocks, health posts) for local governments in Gandaki Province.",
  location: "Pokhara Metropolitan City-8, Kaski",
  province: "gandaki",
  districts_served: ["Kaski", "Tanahun", "Syangja", "Parbat", "Lamjung"],
  pan_number: "999123456",
  vat_number: "999123456",
  registration_date: "2015-03-12",
  licences: [
    {
      licence_type: "construction",
      licence_class: "C",
      licence_number: "DEMO-C-0421",
      issuing_body: "Federal construction licensing authority (fictional demo record)",
      last_renewed_fy_bs: "2083/84",
    },
  ],
  turnover: [
    { fiscal_year_bs: "2079/80", amount_npr: 42_000_000 },
    { fiscal_year_bs: "2080/81", amount_npr: 51_000_000 },
    { fiscal_year_bs: "2081/82", amount_npr: 58_000_000 },
  ],
  certifications: [],
  jv_partners: [{ name: "Machhapuchchhre Demo Builders Pvt. Ltd.", pan_number: null, notes: "Fictional JV partner for works above the company's own capacity." }],
};

export const MOCK_DOCUMENTS: S["CompanyDocumentView"][] = [
  {
    id: 1,
    filename: "01_company_registration.pdf",
    doc_type: "company_registration",
    expires_on: null,
    is_expired: null,
    ingest_status: "ready",
    warnings: [],
    page_count: 1,
    chunk_count: 2,
    uploaded_at: "2026-10-17T10:05:00+05:45",
  },
  {
    id: 2,
    filename: "03_tax_clearance_2081_82.pdf",
    doc_type: "tax_clearance",
    // FY 2081/82 ends on the last day of Asar 2082 (NEPAL_CONTEXT section 7).
    expires_on: bsToAd({ year: 2082, month: 3, day: daysInBsMonth(2082, 3) }),
    is_expired: true,
    fiscal_year_bs: "2081/82",
    ingest_status: "ready",
    warnings: [],
    page_count: 1,
    chunk_count: 1,
    uploaded_at: "2026-10-17T10:05:30+05:45",
  },
  {
    id: 3,
    filename: "06_construction_licence.txt",
    doc_type: "business_licence",
    // Valid to 2084-03-32 BS, like data/demo_company/06_construction_licence.txt.
    expires_on: bsToAd({ year: 2084, month: 3, day: 32 }),
    is_expired: false,
    fiscal_year_bs: "2083/84",
    ingest_status: "ready",
    warnings: [],
    page_count: null,
    chunk_count: 1,
    uploaded_at: "2026-10-17T10:06:00+05:45",
  },
  {
    id: 4,
    filename: "scanned_experience_letter.pdf",
    doc_type: "experience_certificate",
    expires_on: null,
    is_expired: null,
    value_npr: 8_600_000,
    ingest_status: "needs_ocr",
    warnings: ["no text layer: scanned PDF (OCR is out of scope)"],
    page_count: 2,
    chunk_count: 0,
    uploaded_at: "2026-10-18T09:12:00+05:45",
  },
];

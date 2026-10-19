/**
 * Runtime lists of the API's enum values (for selects and query parsing). The `satisfies` +
 * `Exhaustive` checks make `bunx tsc` fail if the generated types gain or lose a value.
 */
import type { components } from "./types";

type S = components["schemas"];
type Exhaustive<Union, List extends readonly unknown[]> = [Union] extends [List[number]] ? List : never;

export const PROCUREMENT_TYPES = ["works", "goods", "consulting", "non_consulting", "unknown"] as const satisfies readonly S["ProcurementType"][];
export const METHODS = ["ncb", "icb", "quotation", "eoi", "rfp", "other"] as const satisfies readonly S["ProcurementMethod"][];
export const BUYER_LEVELS = ["federal", "province", "local", "other"] as const satisfies readonly S["BuyerLevel"][];
export const PROVINCES = ["koshi", "madhesh", "bagmati", "gandaki", "lumbini", "karnali", "sudurpashchim"] as const satisfies readonly S["Province"][];
export const LANGUAGES = ["en", "ne", "mixed"] as const satisfies readonly S["NoticeLanguage"][];
export const DECISIONS = ["pursue", "skip"] as const satisfies readonly S["MatchDecision"][];
export const STATUSES = ["new", "extracted", "matched", "checked", "drafted", "reviewed", "approved", "skipped", "blocked", "failed"] as const satisfies readonly S["TenderStatus"][];
export const DOC_TYPES = [
  "company_registration",
  "business_licence",
  "licence_renewal",
  "pan_vat",
  "tax_clearance",
  "tax_return",
  "audit_report",
  "experience_certificate",
  "company_profile",
  "jv_agreement",
  "self_declaration",
  "power_of_attorney",
  "bid_security",
  "other",
] as const satisfies readonly S["DocType"][];
export const CONTRACTOR_CLASSES = ["A", "B", "C", "D"] as const satisfies readonly S["ContractorClass"][];

// Compile-time exhaustiveness: each line errors if the API enum has a value missing above.
export const _exhaustive: [
  Exhaustive<S["ProcurementType"], typeof PROCUREMENT_TYPES>,
  Exhaustive<S["ProcurementMethod"], typeof METHODS>,
  Exhaustive<S["BuyerLevel"], typeof BUYER_LEVELS>,
  Exhaustive<S["Province"], typeof PROVINCES>,
  Exhaustive<S["NoticeLanguage"], typeof LANGUAGES>,
  Exhaustive<S["MatchDecision"], typeof DECISIONS>,
  Exhaustive<S["TenderStatus"], typeof STATUSES>,
  Exhaustive<S["DocType"], typeof DOC_TYPES>,
  Exhaustive<S["ContractorClass"], typeof CONTRACTOR_CLASSES>,
] = [PROCUREMENT_TYPES, METHODS, BUYER_LEVELS, PROVINCES, LANGUAGES, DECISIONS, STATUSES, DOC_TYPES, CONTRACTOR_CLASSES];

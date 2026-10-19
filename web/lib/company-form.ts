/**
 * Company profile form <-> CompanyProfile (POST /company). Pure functions, so the
 * conversion and validation are unit-tested apart from the React form.
 */
import type { CompanyProfile, CompanyView } from "@/lib/api/tenderly";
import type { components } from "@/lib/api/types";
import type { MessageKey } from "@/lib/i18n/dict";
import { toAsciiDigits } from "@/lib/nepal/calendar";

type S = components["schemas"];

export type LicenceDraft = {
  licence_type: string;
  licence_class: S["ContractorClass"] | "";
  licence_number: string;
  issuing_body: string;
  last_renewed_fy_bs: string;
};
export type TurnoverDraft = { fiscal_year_bs: string; amount: string };
export type PartnerDraft = { name: string; pan_number: string; notes: string };

export type ProfileDraft = {
  name: string;
  sectors: string;
  procurement_types: S["ProcurementType"][];
  services: string;
  location: string;
  province: S["Province"] | "";
  districts_served: string;
  pan_number: string;
  vat_number: string;
  registration_date: string;
  licences: LicenceDraft[];
  turnover: TurnoverDraft[];
  certifications: string;
  jv_partners: PartnerDraft[];
};

/** Field path (e.g. "turnover.1.fiscal_year_bs") -> message key. */
export type FormErrors = Record<string, MessageKey>;

export const EMPTY_LICENCE: LicenceDraft = { licence_type: "", licence_class: "", licence_number: "", issuing_body: "", last_renewed_fy_bs: "" };
export const EMPTY_TURNOVER: TurnoverDraft = { fiscal_year_bs: "", amount: "" };
export const EMPTY_PARTNER: PartnerDraft = { name: "", pan_number: "", notes: "" };

const list = (items: string[] | undefined) => (items ?? []).join(", ");
const split = (text: string) =>
  text
    .split(/[,،\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
const orNull = (text: string) => (text.trim() ? text.trim() : null);

export function toDraft(view: CompanyView | CompanyProfile | null): ProfileDraft {
  return {
    name: view?.name ?? "",
    sectors: list(view?.sectors),
    procurement_types: [...(view?.procurement_types ?? [])],
    services: view?.services ?? "",
    location: view?.location ?? "",
    province: view?.province ?? "",
    districts_served: list(view?.districts_served),
    pan_number: view?.pan_number ?? "",
    vat_number: view?.vat_number ?? "",
    registration_date: view?.registration_date ?? "",
    licences: (view?.licences ?? []).map((l) => ({
      licence_type: l.licence_type,
      licence_class: l.licence_class ?? "",
      licence_number: l.licence_number ?? "",
      issuing_body: l.issuing_body ?? "",
      last_renewed_fy_bs: l.last_renewed_fy_bs ?? "",
    })),
    turnover: (view?.turnover ?? []).map((t) => ({ fiscal_year_bs: t.fiscal_year_bs, amount: String(t.amount_npr) })),
    certifications: list(view?.certifications),
    jv_partners: (view?.jv_partners ?? []).map((p) => ({ name: p.name, pan_number: p.pan_number ?? "", notes: p.notes ?? "" })),
  };
}

/** "2082/83" with consecutive years (same rule as schemas._base.FiscalYearBS). Devanagari digits accepted. */
export function normalizeFiscalYear(text: string): string | null {
  const m = /^(\d{4})\/(\d{2})$/.exec(toAsciiDigits(text.trim()));
  if (!m) return null;
  return (Number(m[1]) + 1) % 100 === Number(m[2]) ? `${m[1]}/${m[2]}` : null;
}

/** "1,48,75,000" / "१४८७५०००" -> 14875000; null if not a whole non-negative number. */
export function parseAmount(text: string): number | null {
  const cleaned = toAsciiDigits(text).replace(/[,\s]/g, "");
  if (!/^\d+$/.test(cleaned)) return null;
  const n = Number(cleaned);
  return Number.isSafeInteger(n) ? n : null;
}

export function fromDraft(d: ProfileDraft): { profile: CompanyProfile | null; errors: FormErrors } {
  const errors: FormErrors = {};
  if (!d.name.trim()) errors.name = "company.required";

  const licences: S["ContractorLicence"][] = [];
  d.licences.forEach((l, i) => {
    if (!l.licence_type.trim()) errors[`licences.${i}.licence_type`] = "company.required";
    let fy: string | null = null;
    if (l.last_renewed_fy_bs.trim()) {
      fy = normalizeFiscalYear(l.last_renewed_fy_bs);
      if (!fy) errors[`licences.${i}.last_renewed_fy_bs`] = "company.fyInvalid";
    }
    licences.push({
      licence_type: l.licence_type.trim(),
      licence_class: l.licence_class || null,
      licence_number: orNull(l.licence_number),
      issuing_body: orNull(l.issuing_body),
      last_renewed_fy_bs: fy,
    });
  });

  const turnover: S["AnnualTurnover"][] = [];
  const seen = new Set<string>();
  d.turnover.forEach((t, i) => {
    const fy = normalizeFiscalYear(t.fiscal_year_bs);
    const amount = parseAmount(t.amount);
    if (!fy) errors[`turnover.${i}.fiscal_year_bs`] = "company.fyInvalid";
    else if (seen.has(fy)) errors[`turnover.${i}.fiscal_year_bs`] = "company.fyDuplicate";
    if (amount === null) errors[`turnover.${i}.amount`] = "company.required";
    if (fy) seen.add(fy);
    if (fy && amount !== null) turnover.push({ fiscal_year_bs: fy, amount_npr: amount });
  });
  turnover.sort((a, b) => a.fiscal_year_bs.localeCompare(b.fiscal_year_bs));

  const jv_partners: S["JVPartner"][] = [];
  d.jv_partners.forEach((p, i) => {
    if (!p.name.trim()) errors[`jv_partners.${i}.name`] = "company.required";
    jv_partners.push({ name: p.name.trim(), pan_number: orNull(p.pan_number), notes: orNull(p.notes) });
  });

  if (Object.keys(errors).length > 0) return { profile: null, errors };
  return {
    profile: {
      name: d.name.trim(),
      sectors: split(d.sectors),
      procurement_types: d.procurement_types,
      services: d.services.trim(),
      location: orNull(d.location),
      province: d.province || null,
      districts_served: split(d.districts_served),
      // PAN/VAT are free strings: no format is confirmed (NEPAL_CONTEXT section 10, item 11).
      pan_number: orNull(d.pan_number),
      vat_number: orNull(d.vat_number),
      registration_date: orNull(d.registration_date),
      licences,
      turnover,
      certifications: split(d.certifications),
      jv_partners,
    },
    errors,
  };
}

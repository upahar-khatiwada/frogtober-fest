"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";

import { BsAdDateField } from "@/components/date-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { CONTRACTOR_CLASSES, PROCUREMENT_TYPES, PROVINCES } from "@/lib/api/enums";
import { saveCompany, type CompanyView } from "@/lib/api/tenderly";
import {
  EMPTY_LICENCE,
  EMPTY_PARTNER,
  EMPTY_TURNOVER,
  fromDraft,
  parseAmount,
  toDraft,
  type FormErrors,
  type ProfileDraft,
} from "@/lib/company-form";
import { formatNprShort } from "@/lib/format";
import type { MessageKey } from "@/lib/i18n/dict";
import { usePrefs } from "@/lib/prefs";

function Field({ id, label, error, children, className }: { id: string; label: string; error?: string; children: ReactNode; className?: string }) {
  return (
    <div className={`flex flex-col gap-1.5 ${className ?? ""}`}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error && (
        <p id={`${id}-error`} className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

/** Profile form (POST /company): identity, PAN/VAT, licence classes, turnover per FY, districts. */
export function ProfileForm({ initial, onSaved }: { initial: CompanyView | null; onSaved?: (c: CompanyView) => void }) {
  const { t, label, lang } = usePrefs();
  const [draft, setDraft] = useState<ProfileDraft>(() => toDraft(initial));
  const [errors, setErrors] = useState<FormErrors>({});
  const [state, setState] = useState<{ kind: "idle" | "saving" | "saved" } | { kind: "error"; message: string }>({ kind: "idle" });

  const err = (path: string) => (errors[path] ? t(errors[path] as MessageKey) : undefined);
  const set = <K extends keyof ProfileDraft>(key: K, value: ProfileDraft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  function setRow<K extends "licences" | "turnover" | "jv_partners">(key: K, i: number, patch: Partial<ProfileDraft[K][number]>) {
    setDraft((d) => ({ ...d, [key]: d[key].map((row, j) => (j === i ? { ...row, ...patch } : row)) }));
  }
  function removeRow(key: "licences" | "turnover" | "jv_partners", i: number) {
    setDraft((d) => ({ ...d, [key]: d[key].filter((_, j) => j !== i) }));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const { profile, errors: found } = fromDraft(draft);
    setErrors(found);
    if (!profile) return;
    setState({ kind: "saving" });
    try {
      const saved = await saveCompany(profile);
      setDraft(toDraft(saved));
      setState({ kind: "saved" });
      onSaved?.(saved);
    } catch (e) {
      setState({ kind: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <form onSubmit={submit} noValidate aria-label={t("company.title")} className="flex flex-col gap-4">
      {!initial && <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">{t("company.noProfile")}</p>}

      <Card>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field id="name" label={t("company.name")} error={err("name")} className="sm:col-span-2">
            <Input id="name" value={draft.name} onChange={(e) => set("name", e.target.value)} aria-invalid={!!errors.name || undefined} required />
          </Field>
          <Field id="pan" label={t("company.pan")}>
            <Input id="pan" value={draft.pan_number} onChange={(e) => set("pan_number", e.target.value)} />
          </Field>
          <Field id="vat" label={t("company.vat")}>
            <Input id="vat" value={draft.vat_number} onChange={(e) => set("vat_number", e.target.value)} />
          </Field>
          <Field id="location" label={t("company.location")}>
            <Input id="location" value={draft.location} onChange={(e) => set("location", e.target.value)} />
          </Field>
          <Field id="province" label={t("company.province")}>
            <NativeSelect id="province" className="w-full" value={draft.province} onChange={(e) => set("province", e.target.value as ProfileDraft["province"])}>
              <NativeSelectOption value="">—</NativeSelectOption>
              {PROVINCES.map((p) => (
                <NativeSelectOption key={p} value={p}>
                  {label("province", p)}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Field>
          <Field id="districts" label={t("company.districts")} className="sm:col-span-2">
            <Input id="districts" value={draft.districts_served} onChange={(e) => set("districts_served", e.target.value)} placeholder="Kaski, Tanahun, Syangja" />
          </Field>
          <BsAdDateField
            id="registration_date"
            value={draft.registration_date}
            onChange={(v) => set("registration_date", v)}
            labelAd={t("company.registrationDate")}
            labelBs={t("company.registrationDateBs")}
          />
          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1.5 text-sm font-medium">{t("company.procurementTypes")}</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {PROCUREMENT_TYPES.filter((p) => p !== "unknown").map((p) => (
                <label key={p} className="flex items-center gap-1.5 text-sm">
                  <input
                    type="checkbox"
                    className="size-4 accent-primary"
                    checked={draft.procurement_types.includes(p)}
                    onChange={(e) =>
                      set("procurement_types", e.target.checked ? [...draft.procurement_types, p] : draft.procurement_types.filter((x) => x !== p))
                    }
                  />
                  {label("procurement_type", p)}
                </label>
              ))}
            </div>
          </fieldset>
          <Field id="sectors" label={t("company.sectors")} className="sm:col-span-2">
            <Input id="sectors" value={draft.sectors} onChange={(e) => set("sectors", e.target.value)} />
          </Field>
          <Field id="services" label={t("company.services")} className="sm:col-span-2">
            <Textarea id="services" rows={3} value={draft.services} onChange={(e) => set("services", e.target.value)} />
          </Field>
          <Field id="certifications" label={t("company.certifications")} className="sm:col-span-2">
            <Input id="certifications" value={draft.certifications} onChange={(e) => set("certifications", e.target.value)} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("company.licences")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {draft.licences.length === 0 && <p className="text-sm text-muted-foreground">{t("company.none")}</p>}
          {draft.licences.map((l, i) => (
            <div key={i} className="grid gap-3 rounded-lg border p-3 sm:grid-cols-[1fr_6rem_1fr_1fr_8rem_auto] sm:items-end">
              <Field id={`lic-${i}-type`} label={t("company.licenceType")} error={err(`licences.${i}.licence_type`)}>
                <Input id={`lic-${i}-type`} value={l.licence_type} placeholder="construction" onChange={(e) => setRow("licences", i, { licence_type: e.target.value })} />
              </Field>
              <Field id={`lic-${i}-class`} label={t("company.licenceClass")}>
                <NativeSelect
                  id={`lic-${i}-class`}
                  className="w-full"
                  value={l.licence_class}
                  onChange={(e) => setRow("licences", i, { licence_class: e.target.value as typeof l.licence_class })}
                >
                  <NativeSelectOption value="">—</NativeSelectOption>
                  {CONTRACTOR_CLASSES.map((c) => (
                    <NativeSelectOption key={c} value={c}>
                      {c}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Field>
              <Field id={`lic-${i}-number`} label={t("company.licenceNumber")}>
                <Input id={`lic-${i}-number`} value={l.licence_number} onChange={(e) => setRow("licences", i, { licence_number: e.target.value })} />
              </Field>
              <Field id={`lic-${i}-body`} label={t("company.issuingBody")}>
                <Input id={`lic-${i}-body`} value={l.issuing_body} onChange={(e) => setRow("licences", i, { issuing_body: e.target.value })} />
              </Field>
              <Field id={`lic-${i}-fy`} label={t("company.lastRenewed")} error={err(`licences.${i}.last_renewed_fy_bs`)}>
                <Input id={`lic-${i}-fy`} value={l.last_renewed_fy_bs} placeholder="2083/84" onChange={(e) => setRow("licences", i, { last_renewed_fy_bs: e.target.value })} />
              </Field>
              <Button type="button" variant="ghost" size="icon" aria-label={t("company.remove")} onClick={() => removeRow("licences", i)}>
                <Trash2 />
              </Button>
            </div>
          ))}
          <Button type="button" variant="outline" className="w-fit" onClick={() => set("licences", [...draft.licences, { ...EMPTY_LICENCE }])}>
            <Plus /> {t("company.addLicence")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("company.turnover")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {draft.turnover.length === 0 && <p className="text-sm text-muted-foreground">{t("company.none")}</p>}
          {draft.turnover.map((row, i) => {
            const amount = parseAmount(row.amount);
            return (
              <div key={i} className="grid gap-3 sm:grid-cols-[10rem_1fr_auto] sm:items-start">
                <Field id={`to-${i}-fy`} label={t("company.fiscalYear")} error={err(`turnover.${i}.fiscal_year_bs`)}>
                  <Input id={`to-${i}-fy`} value={row.fiscal_year_bs} placeholder="2082/83" onChange={(e) => setRow("turnover", i, { fiscal_year_bs: e.target.value })} />
                </Field>
                <Field id={`to-${i}-amount`} label={t("company.amount")} error={err(`turnover.${i}.amount`)}>
                  <Input id={`to-${i}-amount`} inputMode="numeric" value={row.amount} onChange={(e) => setRow("turnover", i, { amount: e.target.value })} />
                  <span className="min-h-4 text-xs text-muted-foreground">{amount !== null ? formatNprShort(amount, lang) : ""}</span>
                </Field>
                <Button type="button" variant="ghost" size="icon" className="sm:mt-6" aria-label={t("company.remove")} onClick={() => removeRow("turnover", i)}>
                  <Trash2 />
                </Button>
              </div>
            );
          })}
          <Button type="button" variant="outline" className="w-fit" onClick={() => set("turnover", [...draft.turnover, { ...EMPTY_TURNOVER }])}>
            <Plus /> {t("company.addYear")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("company.jvPartners")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {draft.jv_partners.length === 0 && <p className="text-sm text-muted-foreground">{t("company.none")}</p>}
          {draft.jv_partners.map((p, i) => (
            <div key={i} className="grid gap-3 sm:grid-cols-[1fr_10rem_1fr_auto] sm:items-end">
              <Field id={`jv-${i}-name`} label={t("company.jvName")} error={err(`jv_partners.${i}.name`)}>
                <Input id={`jv-${i}-name`} value={p.name} onChange={(e) => setRow("jv_partners", i, { name: e.target.value })} />
              </Field>
              <Field id={`jv-${i}-pan`} label={t("company.pan")}>
                <Input id={`jv-${i}-pan`} value={p.pan_number} onChange={(e) => setRow("jv_partners", i, { pan_number: e.target.value })} />
              </Field>
              <Field id={`jv-${i}-notes`} label={t("company.jvNotes")}>
                <Input id={`jv-${i}-notes`} value={p.notes} onChange={(e) => setRow("jv_partners", i, { notes: e.target.value })} />
              </Field>
              <Button type="button" variant="ghost" size="icon" aria-label={t("company.remove")} onClick={() => removeRow("jv_partners", i)}>
                <Trash2 />
              </Button>
            </div>
          ))}
          <Button type="button" variant="outline" className="w-fit" onClick={() => set("jv_partners", [...draft.jv_partners, { ...EMPTY_PARTNER }])}>
            <Plus /> {t("company.addPartner")}
          </Button>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={state.kind === "saving"}>
          {state.kind === "saving" ? t("company.saving") : t("company.save")}
        </Button>
        <p role="status" className="text-sm">
          {state.kind === "saved" && <span className="text-emerald-700 dark:text-emerald-400">{t("company.saved")}</span>}
          {state.kind === "error" && <span className="text-destructive">{t("company.saveFailed", { error: state.message })}</span>}
        </p>
      </div>
    </form>
  );
}

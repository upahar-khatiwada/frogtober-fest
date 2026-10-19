"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTransition, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { BUYER_LEVELS, DECISIONS, LANGUAGES, METHODS, PROCUREMENT_TYPES, PROVINCES, STATUSES } from "@/lib/api/enums";
import type { EnumKind, MessageKey } from "@/lib/i18n/dict";
import { usePrefs } from "@/lib/prefs";

/** Enum filters of GET /tenders: query param, label, enum kind (for option labels), values. */
const SELECTS: { param: string; label: MessageKey; kind: EnumKind; values: readonly string[] }[] = [
  { param: "procurement_type", label: "filters.procurementType", kind: "procurement_type", values: PROCUREMENT_TYPES },
  { param: "method", label: "filters.method", kind: "method", values: METHODS },
  { param: "buyer_level", label: "filters.buyerLevel", kind: "buyer_level", values: BUYER_LEVELS },
  { param: "province", label: "filters.province", kind: "province", values: PROVINCES },
  { param: "language", label: "filters.language", kind: "language", values: LANGUAGES },
  { param: "decision", label: "filters.decision", kind: "decision", values: DECISIONS },
  { param: "status", label: "filters.status", kind: "status", values: STATUSES },
];

const TEXT_PARAMS = ["district", "min_score", "deadline_within_days"] as const;

/**
 * Filter bar for the ranked list. The URL is the state: selects apply on change, text and
 * number fields on Enter or blur, and the server component re-fetches GET /tenders.
 */
export function TenderFilters() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [pending, startTransition] = useTransition();
  const { t, label } = usePrefs();

  function apply(updates: Record<string, string>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (next.toString() === params.toString()) return;
    startTransition(() => router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false }));
  }

  function submitText(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    apply(Object.fromEntries(TEXT_PARAMS.map((p) => [p, String(data.get(p) ?? "").trim()])));
  }

  const hasFilters = [...SELECTS.map((s) => s.param), ...TEXT_PARAMS].some((p) => params.has(p));

  return (
    <form
      onSubmit={submitText}
      aria-label={t("filters.title")}
      aria-busy={pending}
      className="grid grid-cols-2 gap-3 rounded-xl border bg-card p-4 sm:grid-cols-3 lg:grid-cols-5"
    >
      {SELECTS.map((s) => (
        <div key={s.param} className="flex flex-col gap-1.5">
          <Label htmlFor={`f-${s.param}`}>{t(s.label)}</Label>
          <NativeSelect
            id={`f-${s.param}`}
            className="w-full"
            value={params.get(s.param) ?? ""}
            onChange={(e) => apply({ [s.param]: e.target.value })}
          >
            <NativeSelectOption value="">{t("filters.any")}</NativeSelectOption>
            {s.values.map((v) => (
              <NativeSelectOption key={v} value={v}>
                {label(s.kind, v)}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
      ))}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="f-district">{t("filters.district")}</Label>
        <Input
          id="f-district"
          name="district"
          key={`district-${params.get("district") ?? ""}`}
          defaultValue={params.get("district") ?? ""}
          placeholder={t("filters.districtPlaceholder")}
          onBlur={(e) => apply({ district: e.target.value.trim() })}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="f-min_score">{t("filters.minScore")}</Label>
        <Input
          id="f-min_score"
          name="min_score"
          type="number"
          min={0}
          max={100}
          key={`min-${params.get("min_score") ?? ""}`}
          defaultValue={params.get("min_score") ?? ""}
          onBlur={(e) => apply({ min_score: e.target.value })}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="f-deadline_within_days">{t("filters.deadlineWithin")}</Label>
        <Input
          id="f-deadline_within_days"
          name="deadline_within_days"
          type="number"
          min={0}
          key={`dl-${params.get("deadline_within_days") ?? ""}`}
          defaultValue={params.get("deadline_within_days") ?? ""}
          onBlur={(e) => apply({ deadline_within_days: e.target.value })}
        />
      </div>
      <div className="flex items-end">
        <Button
          type="button"
          variant="ghost"
          disabled={!hasFilters}
          onClick={() => startTransition(() => router.push(pathname, { scroll: false }))}
        >
          {t("filters.clear")}
        </Button>
      </div>
      <button type="submit" hidden />
    </form>
  );
}

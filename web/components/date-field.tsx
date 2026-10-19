"use client";

import { useState } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { adToBs, bsToAd, bsToIso, formatAd, formatBs, parseBsIso } from "@/lib/nepal/calendar";
import { usePrefs } from "@/lib/prefs";

function bsOf(adIso: string): string | null {
  try {
    return bsToIso(adToBs(adIso));
  } catch {
    return null;
  }
}

/**
 * A date picker that follows the BS/AD preference. The value is always an AD ISO date (what the
 * API stores); in BS mode the user types a BS date ("2084-03-32", Devanagari digits accepted)
 * and the converted AD date is shown, in AD mode a native date picker shows the BS date.
 * Conversion uses the backend's own table (lib/nepal/calendar.ts).
 */
export function BsAdDateField({
  id,
  value,
  onChange,
  labelAd,
  labelBs,
}: {
  id: string;
  value: string;
  onChange: (adIso: string) => void;
  labelAd: string;
  labelBs: string;
}) {
  const { calendar, lang, t } = usePrefs();
  // Raw BS text while typing; it may be incomplete or invalid, so it is not derived from `value`.
  const [bsText, setBsText] = useState(() => (value ? (bsOf(value) ?? "") : ""));
  const [bsInvalid, setBsInvalid] = useState(false);

  if (calendar === "BS") {
    const shownBs = bsText || (value ? (bsOf(value) ?? "") : "");
    return (
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={id}>{labelBs}</Label>
        <Input
          id={id}
          inputMode="numeric"
          placeholder="2084-03-31"
          value={shownBs}
          aria-invalid={bsInvalid || undefined}
          onChange={(e) => {
            const text = e.target.value;
            setBsText(text);
            if (!text.trim()) {
              setBsInvalid(false);
              onChange("");
              return;
            }
            const bs = parseBsIso(text);
            setBsInvalid(!bs && text.trim().length >= 10);
            onChange(bs ? bsToAd(bs) : "");
          }}
        />
        <p className="min-h-4 text-xs text-muted-foreground" aria-live="polite">
          {bsInvalid ? <span className="text-destructive">{t("kb.invalidBs")}</span> : value ? t("kb.inAd", { date: formatAd(value, lang) }) : null}
        </p>
      </div>
    );
  }

  const bs = value ? bsOf(value) : null;
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{labelAd}</Label>
      <Input
        id={id}
        type="date"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setBsText(e.target.value ? (bsOf(e.target.value) ?? "") : "");
          setBsInvalid(false);
        }}
      />
      <p className="min-h-4 text-xs text-muted-foreground" aria-live="polite">
        {bs ? t("kb.inBs", { date: formatBs(parseBsIso(bs)!, lang) }) : null}
      </p>
    </div>
  );
}

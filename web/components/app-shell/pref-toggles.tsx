"use client";

import { usePrefs, type Calendar } from "@/lib/prefs";
import type { Lang } from "@/lib/format";
import { cn } from "@/lib/utils";

function Segmented<V extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: V;
  options: { value: V; text: string; lang?: string }[];
  onChange: (v: V) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          lang={o.lang}
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-md px-2 py-0.5 text-xs font-medium transition-colors",
            value === o.value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
          )}
        >
          {o.text}
        </button>
      ))}
    </div>
  );
}

/** Language (EN / नेपाली) and calendar (BS / AD) toggles; both persist in localStorage. */
export function PrefToggles() {
  const { lang, setLang, calendar, setCalendar, t } = usePrefs();
  return (
    <div className="flex items-center gap-2">
      <Segmented<Lang>
        label={t("prefs.language")}
        value={lang}
        onChange={setLang}
        options={[
          { value: "en", text: "EN", lang: "en" },
          { value: "ne", text: "नेपाली", lang: "ne" },
        ]}
      />
      <Segmented<Calendar>
        label={t("prefs.calendar")}
        value={calendar}
        onChange={setCalendar}
        options={[
          { value: "BS", text: "BS" },
          { value: "AD", text: "AD" },
        ]}
      />
    </div>
  );
}

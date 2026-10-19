"use client";

import { formatNpr, formatNprShort } from "@/lib/format";
import { usePrefs } from "@/lib/prefs";

/** NPR in lakh/crore (short), with the full South Asian grouping as a tooltip. */
export function Money({ amount }: { amount: number }) {
  const { lang } = usePrefs();
  return (
    <span title={formatNpr(amount, lang)} className="tabular-nums">
      {formatNprShort(amount, lang)}
    </span>
  );
}

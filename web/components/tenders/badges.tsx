"use client";

import { Badge } from "@/components/ui/badge";
import type { components } from "@/lib/api/types";
import type { EnumKind } from "@/lib/i18n/dict";
import { usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/utils";

type TenderStatus = components["schemas"]["TenderStatus"];

const STATUS_CLASS: Record<TenderStatus, string> = {
  new: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100",
  extracted: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  matched: "bg-indigo-100 text-indigo-900 dark:bg-indigo-950 dark:text-indigo-200",
  checked: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  drafted: "bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-200",
  reviewed: "bg-violet-200 text-violet-950 dark:bg-violet-900 dark:text-violet-100",
  approved: "bg-emerald-600 text-white dark:bg-emerald-500",
  skipped: "border-border bg-transparent text-muted-foreground",
  blocked: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
  failed: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
};

export function StatusBadge({ status }: { status: TenderStatus }) {
  const { label } = usePrefs();
  return (
    <Badge className={cn(STATUS_CLASS[status])} data-status={status}>
      {label("status", status)}
    </Badge>
  );
}

/** A neutral badge showing a translated enum value (type, method, buyer level, ...). */
export function EnumBadge({ kind, value, className }: { kind: EnumKind; value: string; className?: string }) {
  const { label } = usePrefs();
  return (
    <Badge variant="outline" className={className}>
      {label(kind, value)}
    </Badge>
  );
}

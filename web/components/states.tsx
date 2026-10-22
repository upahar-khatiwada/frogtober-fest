import { AlertTriangle, Inbox } from "lucide-react";
import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { T } from "@/lib/prefs";
import { cn } from "@/lib/utils";

/**
 * The app's three non-data states, one look everywhere (dashboard, tender, proposal, runs, company):
 * a dashed box for "nothing here yet", a red alert for errors, skeleton blocks while loading.
 * Plain markup: usable from server and client components.
 */
export function EmptyState({
  children,
  action,
  className,
}: {
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      data-state="empty"
      className={cn(
        "flex flex-col items-center gap-3 rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground",
        className,
      )}
    >
      <Inbox className="size-5" aria-hidden="true" />
      <p className="max-w-prose">{children}</p>
      {action}
    </div>
  );
}

export function ErrorState({
  children,
  action,
  className,
}: {
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="alert"
      data-state="error"
      className={cn(
        "flex items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive",
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="flex flex-col gap-2">
        <p>{children}</p>
        {action}
      </div>
    </div>
  );
}

/** Skeleton blocks (heights in Tailwind units) with a screen-reader "Loading…". */
export function LoadingState({
  blocks = ["h-10 w-2/3", "h-32 w-full", "h-64 w-full"],
}: {
  blocks?: string[];
}) {
  return (
    <div className="flex flex-col gap-4" role="status" aria-live="polite" data-state="loading">
      <span className="sr-only">
        <T k="state.loading" />
      </span>
      {blocks.map((b, i) => (
        <Skeleton key={i} className={cn("rounded-xl", b)} aria-hidden="true" />
      ))}
    </div>
  );
}

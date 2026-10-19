import { T } from "@/lib/prefs";

/** Placeholder so the nav link resolves; the run log (spec section 9.1) is a later prompt. */
export default function RunsPage() {
  return (
    <div className="flex flex-col gap-3">
      <h1 className="text-2xl font-semibold tracking-tight">
        <T k="runs.title" />
      </h1>
      <p className="rounded-xl border border-dashed p-8 text-sm text-muted-foreground">
        <T k="runs.placeholder" />
      </p>
    </div>
  );
}

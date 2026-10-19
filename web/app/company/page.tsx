import { connection } from "next/server";
import { Suspense } from "react";

import { CompanyWorkspace } from "@/components/company/company-workspace";
import { Skeleton } from "@/components/ui/skeleton";
import { getCompany, listDocuments } from "@/lib/api/tenderly";
import { T } from "@/lib/prefs";

/** Loads the profile and documents on the server; the form and upload are client components. */
async function CompanyData() {
  await connection();
  let data: [Awaited<ReturnType<typeof getCompany>>, Awaited<ReturnType<typeof listDocuments>>];
  try {
    data = await Promise.all([getCompany(), listDocuments()]);
  } catch (e) {
    return (
      <div role="alert" className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
        <T k="company.loadFailed" vars={{ error: e instanceof Error ? e.message : String(e) }} />
      </div>
    );
  }
  return <CompanyWorkspace company={data[0]} documents={data[1]} />;
}

export default function CompanyPage() {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          <T k="company.title" />
        </h1>
        <p className="text-sm text-muted-foreground">
          <T k="company.subtitle" />
        </p>
      </div>
      <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
        <CompanyData />
      </Suspense>
    </div>
  );
}

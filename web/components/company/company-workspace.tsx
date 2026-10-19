"use client";

import { useState } from "react";

import type { CompanyDocumentView, CompanyView } from "@/lib/api/tenderly";

import { KnowledgeBase } from "./knowledge-base";
import { ProfileForm } from "./profile-form";

/** Profile + KB; uploading needs a saved profile (the API returns 404 otherwise). */
export function CompanyWorkspace({ company, documents }: { company: CompanyView | null; documents: CompanyDocumentView[] }) {
  const [hasProfile, setHasProfile] = useState(company !== null);
  return (
    <div className="flex flex-col gap-6">
      <ProfileForm initial={company} onSaved={() => setHasProfile(true)} />
      <KnowledgeBase initial={documents} hasProfile={hasProfile} />
    </div>
  );
}

"use client";

import { Info, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { formatDateTime } from "@/components/date-time";
import { StatusBadge } from "@/components/tenders/badges";
import { Badge } from "@/components/ui/badge";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  approveProposal,
  editSection,
  loadProposalBundle,
  openProposal,
  reviewProposal,
  type ProposalBundle,
} from "@/lib/api/tenderly";
import type { MessageKey } from "@/lib/i18n/dict";
import { usePrefs } from "@/lib/prefs";
import { approvalGates, needsOpen } from "@/lib/proposal";
import { isActive, usePolledRun } from "@/lib/use-polled-run";

import { ApprovalPanel } from "./approval-panel";
import { PackagePanel } from "./package-panel";
import { RequirementsView } from "./requirements-view";
import { ReviewPanel, VerdictBadge } from "./review-panel";
import { SectionCard } from "./section-card";

type Notice = { kind: "ok" | "error"; key: MessageKey; vars?: Record<string, string | number> };
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Focus an element once the tab holding it has rendered. */
function focusLater(id: string) {
  requestAnimationFrame(() => {
    const el = document.getElementById(id);
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
    el?.focus({ preventScroll: true });
  });
}

/**
 * /tenders/[id]/proposal: one proposal version at a time. Showing a reviewed version records that the person opened
 * it (POST /proposals/{id}/open), which the approval gate needs. Edits are saved as a new version, which needs a new
 * review before it can be approved.
 */
export function ProposalWorkspace({ initial }: { initial: ProposalBundle }) {
  const { t, label, calendar, lang: prefLang } = usePrefs();
  const [bundle, setBundle] = useState(initial);
  const [tab, setTab] = useState<"sections" | "requirements">("sections");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [openFailed, setOpenFailed] = useState<number | null>(null);
  const { tender, versions, proposal, chunks, checklist } = bundle;
  const tenderId = tender.id;
  const record = tender.record;
  const lang = proposal?.language === "ne" ? "ne" : undefined;

  const reload = useCallback(
    async (proposalId?: number | null) => {
      const next = await loadProposalBundle(tenderId, proposalId);
      if (!next) return;
      setBundle(next);
      if (next.proposal) {
        const url = new URL(window.location.href);
        url.searchParams.set("v", String(next.proposal.id));
        window.history.replaceState(null, "", url);
      }
    },
    [tenderId],
  );

  const [run, setRun] = usePolledRun(
    () => {
      reload(proposal?.id).catch((e) => setNotice({ kind: "error", key: "pp.loadFailed", vars: { error: errText(e) } }));
    },
    (e) => setNotice({ kind: "error", key: "pp.rv.failed", vars: { error: errText(e) } }),
  );
  const reviewing = isActive(run);

  // Showing a reviewed version = the person opened it (approval needs an open after the review).
  const proposalId = proposal?.id;
  const mustOpen = proposal ? needsOpen(proposal) : false;
  useEffect(() => {
    if (proposalId === undefined || !mustOpen) return;
    let cancelled = false;
    openProposal(proposalId)
      .then((opened) => {
        if (cancelled) return;
        setBundle((b) => ({
          ...b,
          proposal: opened,
          versions: b.versions.map((v) => (v.id === opened.id ? opened : v)),
        }));
      })
      .catch((e) => {
        if (cancelled) return;
        setOpenFailed(proposalId);
        setNotice({ kind: "error", key: "pp.ap.openFailed", vars: { error: errText(e) } });
      });
    return () => {
      cancelled = true;
    };
  }, [proposalId, mustOpen]);

  if (!proposal) return null; // the page shows the empty state before mounting this

  const opening = mustOpen && openFailed !== proposal.id;
  const gates = approvalGates(proposal, versions);
  const editable = gates.latest && !versions.some((v) => v.status === "approved") && !reviewing;
  const review = proposal.review;
  const grounded = proposal.sections.filter((s) => s.grounded).length;

  const goToSection = (key: string) => {
    setTab("sections");
    focusLater(`section-${key}`);
  };
  const goToRequirement = (index: number) => {
    setTab("requirements");
    focusLater(`req-${index}`);
  };

  async function save(key: string, body: string, by: string, note: string | null) {
    setNotice(null);
    const next = await editSection(proposal!.id, key, body, by, note); // errors stay in the editor
    await reload(next.id);
    setNotice({ kind: "ok", key: "pp.s.saved", vars: { version: next.version } });
  }

  async function runReview() {
    setNotice(null);
    try {
      setRun(await reviewProposal(proposal!.id));
    } catch (e) {
      setNotice({ kind: "error", key: "pp.rv.failed", vars: { error: errText(e) } });
    }
  }

  async function approve(by: string, note: string | null) {
    await approveProposal(proposal!.id, by, note); // errors stay in the dialog
    await reload(proposal!.id);
  }

  return (
    <div className="flex flex-col gap-5">
      <Link href={`/tenders/${tenderId}`} className="w-fit text-sm text-muted-foreground hover:text-foreground">
        ← {t("pp.back")}
      </Link>

      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-muted-foreground">{t("pp.title")}</p>
            <h1 className="text-2xl leading-snug font-semibold tracking-tight" lang={record?.language === "ne" ? "ne" : undefined}>
              {record?.title ?? t("tender.untitled")}
            </h1>
          </div>
          <StatusBadge status={tender.status} />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-muted-foreground">{t("pp.version")}</span>
            <NativeSelect
              size="sm"
              value={String(proposal.id)}
              data-testid="version-select"
              onChange={(e) =>
                reload(Number(e.target.value)).catch((err) =>
                  setNotice({ kind: "error", key: "pp.loadFailed", vars: { error: errText(err) } }),
                )
              }
            >
              {versions.map((v, i) => (
                <NativeSelectOption key={v.id} value={String(v.id)}>
                  {t("pp.versionLabel", { version: v.version })}
                  {i === 0 ? ` (${t("pp.latest")})` : ""} · {label("proposal_status", v.status ?? "draft")}
                  {v.review ? ` · ${label("verdict", v.review.verdict)}` : ""}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </label>
          {review && <VerdictBadge verdict={review.verdict} />}
          <Badge variant="outline">{label("proposal_status", proposal.status ?? "draft")}</Badge>
          <span className="text-muted-foreground">
            {t("pp.drafted", {
              date: proposal.created_at ? formatDateTime(proposal.created_at, calendar, prefLang) : t("runs.none"),
            })}
          </span>
          <span className="text-muted-foreground">
            {t("pp.citationRate", { grounded, total: proposal.sections.length })}
          </span>
        </div>
      </header>

      <div role="status" aria-live="polite" className="min-h-5 text-sm empty:hidden">
        {notice && (
          <span className={notice.kind === "error" ? "text-destructive" : "text-emerald-700 dark:text-emerald-400"}>
            {t(notice.key, notice.vars)}
          </span>
        )}
      </div>

      {!gates.latest && <Banner>{t("pp.olderVersion")}</Banner>}
      {gates.latest && !review && !reviewing && <Banner>{t("pp.unreviewed")}</Banner>}
      {review?.revision_of != null && (
        <Banner>
          {t("pp.revisionOf", {
            version: review.revision_of,
            verdict: review.previous_verdict ? label("verdict", review.previous_verdict) : "?",
            sections: (review.revised_sections ?? [])
              .map((k) => proposal.sections.find((s) => s.key === k)?.title ?? k)
              .join(", "),
          })}
        </Banner>
      )}
      {reviewing && (
        <p role="status" className="flex items-center gap-2 text-sm">
          <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
          {t("pp.rv.running")} · {run && label("run_status", run.status)}
        </p>
      )}

      {gates.approved && <PackagePanel proposalId={proposal.id} checklist={checklist} />}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_19rem] xl:grid-cols-[minmax(0,1fr)_21rem]">
        <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)} className="min-w-0">
          <TabsList>
            <TabsTrigger value="sections">
              {t("pp.tabs.sections")} ({proposal.sections.length})
            </TabsTrigger>
            <TabsTrigger value="requirements">
              {t("pp.tabs.requirements")} ({record?.requirements?.length ?? 0})
            </TabsTrigger>
          </TabsList>
          <TabsContent value="sections" className="flex flex-col gap-4 pt-2">
            {proposal.sections.map((s) => (
              <SectionCard
                key={s.key}
                section={s}
                chunks={chunks}
                lang={lang}
                editable={editable}
                onSave={(body, by, note) => save(s.key, body, by, note)}
                onRequirement={goToRequirement}
              />
            ))}
          </TabsContent>
          <TabsContent value="requirements" className="pt-2">
            <RequirementsView
              requirements={record?.requirements ?? []}
              sections={proposal.sections}
              review={review}
              lang={lang}
              onSection={goToSection}
            />
          </TabsContent>
        </Tabs>

        <aside className="flex flex-col gap-4 lg:sticky lg:top-20">
          <ApprovalPanel proposal={proposal} gates={gates} opening={opening} onApprove={approve} />
          <ReviewPanel
            review={review}
            sections={proposal.sections}
            canRunReview={gates.latest && !gates.approved}
            reviewing={reviewing}
            onRunReview={runReview}
            onSection={goToSection}
            onRequirement={goToRequirement}
          />
        </aside>
      </div>
    </div>
  );
}

function Banner({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-950 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-100">
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      {children}
    </p>
  );
}

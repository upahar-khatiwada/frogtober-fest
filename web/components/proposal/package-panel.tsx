"use client";

import { Download, FileArchive, FileText } from "lucide-react";

import { ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { exportUrl, type ChecklistItem, type ExportKind } from "@/lib/api/tenderly";
import { formatDate } from "@/lib/nepal/calendar";
import { usePrefs } from "@/lib/prefs";
import { checklistCounts } from "@/lib/proposal";
import { cn } from "@/lib/utils";

const STATUS_CLASS: Record<ChecklistItem["status"], string> = {
  present: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  expiring: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  missing: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
};

const DOWNLOADS: { kind: ExportKind; key: "pp.dl.docx" | "pp.dl.pdf" | "pp.dl.zip"; icon: typeof FileText }[] = [
  { kind: "docx", key: "pp.dl.docx", icon: FileText },
  { kind: "pdf", key: "pp.dl.pdf", icon: FileText },
  { kind: "zip", key: "pp.dl.zip", icon: FileArchive },
];

/** After approval: the three downloads and the attachment checklist, inline. Nothing is submitted (hard rule 6). */
export function PackagePanel({
  proposalId,
  checklist,
}: {
  proposalId: number;
  checklist: ChecklistItem[] | null;
}) {
  const { t, label, calendar, lang } = usePrefs();
  const counts = checklist ? checklistCounts(checklist) : null;

  return (
    <Card aria-labelledby="package-title" data-testid="package-panel" className="ring-emerald-500/50">
      <CardHeader>
        <CardTitle>
          <h2 id="package-title" className="text-lg font-semibold">
            {t("pp.dl.title")}
          </h2>
        </CardTitle>
        <CardDescription>{t("pp.dl.body")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <div className="flex flex-wrap gap-2">
          {DOWNLOADS.map(({ kind, key, icon: Icon }) => (
            <a
              key={kind}
              href={exportUrl(proposalId, kind)}
              download
              data-testid={`download-${kind}`}
              className={cn(buttonVariants({ variant: kind === "zip" ? "default" : "outline", size: "lg" }))}
            >
              <Icon aria-hidden="true" />
              {t(key)}
              <Download className="opacity-60" aria-hidden="true" />
            </a>
          ))}
        </div>

        <section className="flex flex-col gap-2" aria-labelledby="checklist-title">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 id="checklist-title" className="text-base font-semibold">
              {t("pp.cl.title")}
            </h3>
            {counts && <span className="text-xs text-muted-foreground">{t("pp.cl.summary", counts)}</span>}
          </div>
          {!checklist ? (
            <ErrorState>{t("pp.cl.unavailable")}</ErrorState>
          ) : (
            <div className="overflow-x-auto rounded-lg border">
              <Table data-testid="checklist">
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("pp.cl.document")}</TableHead>
                    <TableHead>{t("pp.cl.status")}</TableHead>
                    <TableHead>{t("pp.cl.files")}</TableHead>
                    <TableHead>{t("pp.cl.validUntil")}</TableHead>
                    <TableHead className="min-w-64">{t("pp.cl.note")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {checklist.map((item, i) => (
                    <TableRow key={i} data-status={item.status}>
                      <TableCell className="align-top font-medium whitespace-normal">{item.document}</TableCell>
                      <TableCell className="align-top">
                        <Badge className={STATUS_CLASS[item.status]}>{label("checklist_status", item.status)}</Badge>
                      </TableCell>
                      <TableCell className="align-top text-xs whitespace-normal">
                        {(item.files ?? []).join(", ") || t("runs.none")}
                      </TableCell>
                      <TableCell className="align-top text-xs">
                        {item.expires_on ? (
                          <span title={formatDate(item.expires_on, calendar === "BS" ? "AD" : "BS", lang)}>
                            {formatDate(item.expires_on, calendar, lang)} {calendar}
                          </span>
                        ) : (
                          t("runs.none")
                        )}
                      </TableCell>
                      <TableCell className="align-top text-xs whitespace-normal text-muted-foreground">{item.note}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </section>
      </CardContent>
    </Card>
  );
}

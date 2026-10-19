"use client";

import { LoaderCircle, Upload } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { BsAdDateField } from "@/components/date-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DOC_TYPES } from "@/lib/api/enums";
import { listDocuments, uploadDocument, type CompanyDocumentView, type DocType } from "@/lib/api/tenderly";
import type { components } from "@/lib/api/types";
import { normalizeFiscalYear, parseAmount } from "@/lib/company-form";
import { formatDate, toDevanagariDigits } from "@/lib/nepal/calendar";
import { usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/utils";

/** Spec section 9.2: progress via polling every 2 seconds. */
export const POLL_MS = 2000;

type IngestStatus = components["schemas"]["IngestStatus"];
const IN_PROGRESS: IngestStatus[] = ["pending", "processing"];

const INGEST_CLASS: Record<IngestStatus, string> = {
  pending: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100",
  processing: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  ready: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  needs_ocr: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
};

function IngestBadge({ status }: { status: IngestStatus }) {
  const { label } = usePrefs();
  return (
    <Badge className={INGEST_CLASS[status]} data-ingest={status}>
      {IN_PROGRESS.includes(status) && <LoaderCircle className="animate-spin" aria-hidden="true" />}
      {label("ingest_status", status)}
    </Badge>
  );
}

function UploadForm({ disabled, onUploaded }: { disabled: boolean; onUploaded: (doc: CompanyDocumentView) => void }) {
  const { t, label } = usePrefs();
  const fileRef = useRef<HTMLInputElement>(null);
  const [docType, setDocType] = useState<DocType>("tax_clearance");
  const [expiresOn, setExpiresOn] = useState("");
  const [fiscalYear, setFiscalYear] = useState("");
  const [value, setValue] = useState("");
  const [resetKey, setResetKey] = useState(0);
  const [state, setState] = useState<{ kind: "idle" | "uploading" | "done" } | { kind: "error"; message: string }>({ kind: "idle" });

  const fyError = fiscalYear.trim() && !normalizeFiscalYear(fiscalYear) ? t("company.fyInvalid") : null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file || fyError) return;
    setState({ kind: "uploading" });
    try {
      const doc = await uploadDocument({
        file,
        doc_type: docType,
        expires_on: expiresOn || null,
        fiscal_year_bs: normalizeFiscalYear(fiscalYear),
        value_npr: value.trim() ? parseAmount(value) : null,
      });
      onUploaded(doc);
      setState({ kind: "done" });
      setExpiresOn("");
      setFiscalYear("");
      setValue("");
      setResetKey((k) => k + 1);
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      setState({ kind: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <form onSubmit={submit} aria-label={t("kb.upload")} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <div className="flex flex-col gap-1.5 lg:col-span-2">
        <Label htmlFor="kb-file">{t("kb.file")}</Label>
        <Input id="kb-file" ref={fileRef} type="file" accept=".pdf,.docx,.txt,application/pdf,text/plain" required disabled={disabled} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="kb-type">{t("kb.docType")}</Label>
        <NativeSelect id="kb-type" className="w-full" value={docType} onChange={(e) => setDocType(e.target.value as DocType)} disabled={disabled}>
          {DOC_TYPES.map((d) => (
            <NativeSelectOption key={d} value={d}>
              {label("doc_type", d)}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      <BsAdDateField key={resetKey} id="kb-expiry" value={expiresOn} onChange={setExpiresOn} labelAd={t("kb.expiryAd")} labelBs={t("kb.expiryBs")} />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="kb-fy">{t("kb.fiscalYear")}</Label>
        <Input id="kb-fy" value={fiscalYear} placeholder="2082/83" onChange={(e) => setFiscalYear(e.target.value)} aria-invalid={!!fyError || undefined} disabled={disabled} />
        <p className="min-h-4 text-xs text-destructive">{fyError}</p>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="kb-value">{t("kb.value")}</Label>
        <Input id="kb-value" inputMode="numeric" value={value} onChange={(e) => setValue(e.target.value)} disabled={disabled} />
      </div>
      <div className="flex items-center gap-3 sm:col-span-2 lg:col-span-3">
        <Button type="submit" disabled={disabled || state.kind === "uploading"}>
          {state.kind === "uploading" ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
          {state.kind === "uploading" ? t("kb.uploading") : t("kb.upload")}
        </Button>
        <p role="status" className="text-sm">
          {disabled && <span className="text-muted-foreground">{t("kb.needProfile")}</span>}
          {state.kind === "done" && <span className="text-emerald-700 dark:text-emerald-400">{t("kb.uploaded")}</span>}
          {state.kind === "error" && <span className="text-destructive">{t("kb.uploadFailed", { error: state.message })}</span>}
        </p>
      </div>
    </form>
  );
}

function DocumentTable({ documents }: { documents: CompanyDocumentView[] }) {
  const { t, label, lang, calendar } = usePrefs();
  if (documents.length === 0) return <p className="text-sm text-muted-foreground">{t("kb.empty")}</p>;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("kb.colFile")}</TableHead>
          <TableHead>{t("kb.colType")}</TableHead>
          <TableHead>{t("kb.colExpiry")}</TableHead>
          <TableHead>{t("kb.colStatus")}</TableHead>
          <TableHead className="text-right">{t("kb.colChunks")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {documents.map((d) => (
          <TableRow key={d.id} data-testid="kb-row">
            <TableCell className="max-w-64">
              <div className="truncate font-medium" title={d.filename}>
                {d.filename}
              </div>
              {d.fiscal_year_bs && <div className="text-xs text-muted-foreground">FY {d.fiscal_year_bs}</div>}
              {(d.warnings ?? []).map((w, i) => (
                <div key={i} className="text-xs text-amber-700 dark:text-amber-400">
                  {w}
                </div>
              ))}
              {d.ingest_error && <div className="text-xs text-destructive">{d.ingest_error}</div>}
            </TableCell>
            <TableCell>{label("doc_type", d.doc_type)}</TableCell>
            <TableCell>
              {d.expires_on ? (
                <div className="flex flex-col gap-0.5">
                  <span className={cn(d.is_expired && "text-destructive")}>{formatDate(d.expires_on, calendar, lang)}</span>
                  <span className="text-xs text-muted-foreground">{formatDate(d.expires_on, calendar === "BS" ? "AD" : "BS", lang)}</span>
                  {d.is_expired && (
                    <Badge variant="destructive" className="w-fit">
                      {t("kb.expired")}
                    </Badge>
                  )}
                </div>
              ) : (
                <span className="text-muted-foreground">{t("kb.noExpiry")}</span>
              )}
            </TableCell>
            <TableCell>
              <IngestBadge status={d.ingest_status} />
            </TableCell>
            <TableCell className="text-right tabular-nums">{lang === "ne" ? toDevanagariDigits(d.chunk_count) : d.chunk_count}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/** Upload + document list. Polls GET /company/documents every 2 s while any ingest is in progress. */
export function KnowledgeBase({ initial, hasProfile }: { initial: CompanyDocumentView[]; hasProfile: boolean }) {
  const { t } = usePrefs();
  const [documents, setDocuments] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const busy = documents.some((d) => IN_PROGRESS.includes(d.ingest_status));

  useEffect(() => {
    if (!busy) return;
    const id = setInterval(async () => {
      try {
        setDocuments(await listDocuments());
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }, POLL_MS);
    return () => clearInterval(id);
  }, [busy]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("kb.title")}</CardTitle>
        <CardDescription>{t("kb.subtitle")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <UploadForm disabled={!hasProfile} onUploaded={(doc) => setDocuments((ds) => [doc, ...ds.filter((d) => d.id !== doc.id)])} />
        {error && <p className="text-sm text-destructive">{t("kb.loadFailed", { error })}</p>}
        <DocumentTable documents={documents} />
      </CardContent>
    </Card>
  );
}

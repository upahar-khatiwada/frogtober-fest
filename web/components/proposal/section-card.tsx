"use client";

import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  FileText,
  LoaderCircle,
  Pencil,
} from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { KBChunkView, ProposalSection } from "@/lib/api/tenderly";
import { usePrefs } from "@/lib/prefs";
import { rememberName, rememberedName, splitMarkers } from "@/lib/proposal";
import { cn } from "@/lib/utils";

/** Section text with the unresolved markers ([MISSING: …], ⟦unsourced: …⟧) highlighted. */
export function SectionBody({ body, lang }: { body: string; lang?: string }) {
  return (
    <div className="text-sm leading-relaxed whitespace-pre-wrap" lang={lang}>
      {splitMarkers(body).map((part, i) =>
        part.marker ? (
          <mark
            key={i}
            className="rounded bg-amber-200 px-0.5 text-amber-950 dark:bg-amber-800 dark:text-amber-50"
          >
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </div>
  );
}

function Citation({ id, chunk }: { id: number; chunk: KBChunkView | undefined }) {
  const { t, label } = usePrefs();
  const [open, setOpen] = useState(false);
  const panel = `chunk-${id}-${useId()}`;
  return (
    <li className="flex flex-col gap-1">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panel}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex w-fit items-center gap-1 rounded-md px-1 py-0.5 text-left text-xs font-medium text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        {open ? (
          <ChevronDown className="size-3.5" aria-hidden="true" />
        ) : (
          <ChevronRight className="size-3.5" aria-hidden="true" />
        )}
        <FileText className="size-3.5" aria-hidden="true" />
        {t("pp.s.chunk", { id })}
        {chunk && (
          <span className="font-normal text-muted-foreground">
            · {chunk.filename} · {label("doc_type", chunk.doc_type)}
          </span>
        )}
      </button>
      {open && (
        <div
          id={panel}
          className="ml-5 rounded-lg border bg-muted/40 p-3 text-xs leading-relaxed whitespace-pre-wrap"
        >
          {chunk ? chunk.content : t("pp.s.chunkMissing", { id })}
        </div>
      )}
    </li>
  );
}

function Editor({
  section,
  onSave,
  onCancel,
}: {
  section: ProposalSection;
  onSave: (body: string, by: string, note: string | null) => Promise<void>;
  onCancel: () => void;
}) {
  const { t } = usePrefs();
  const [body, setBody] = useState(section.body);
  const [by, setBy] = useState(rememberedName);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = body.trim() !== "" && by.trim() !== "" && body !== section.body;
  const ids = {
    body: `edit-${section.key}`,
    by: `edit-${section.key}-by`,
    note: `edit-${section.key}-note`,
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      rememberName(by.trim());
      await onSave(body, by.trim(), note.trim() || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={ids.body}>{t("pp.s.editLabel")}</Label>
        <Textarea
          id={ids.body}
          rows={Math.min(18, Math.max(6, body.split("\n").length + 2))}
          value={body}
          maxLength={20000}
          onChange={(e) => setBody(e.target.value)}
          className="font-mono text-sm"
          autoFocus
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={ids.by}>{t("pp.s.editName")}</Label>
          <Input id={ids.by} value={by} maxLength={200} onChange={(e) => setBy(e.target.value)} required />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={ids.note}>{t("pp.s.editNote")}</Label>
          <Input id={ids.note} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
        </div>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {t("pp.s.saveFailed", { error })}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={!valid || busy}>
          {busy && <LoaderCircle className="animate-spin" aria-hidden="true" />}
          {busy ? t("pp.s.saving") : t("pp.s.save")}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel} disabled={busy}>
          {t("pp.s.cancel")}
        </Button>
      </div>
    </form>
  );
}

/** One proposal section: badges, ungrounded warning, flags, text, expandable KB citations and the editor. */
export function SectionCard({
  section,
  chunks,
  lang,
  editable,
  onSave,
  onRequirement,
}: {
  section: ProposalSection;
  chunks: Record<number, KBChunkView>;
  lang?: string;
  editable: boolean;
  onSave: (body: string, by: string, note: string | null) => Promise<void>;
  onRequirement: (index: number) => void;
}) {
  const { t, label } = usePrefs();
  const [editing, setEditing] = useState(false);
  const cited = section.cited_chunk_ids ?? [];
  const flags = section.flags ?? [];
  const reqs = section.requirement_indices ?? [];
  const headingId = `section-${section.key}`;

  return (
    <Card
      id={`card-${section.key}`}
      data-testid="proposal-section"
      data-grounded={section.grounded}
      className={cn(!section.grounded && "ring-amber-400/70 dark:ring-amber-700")}
    >
      <CardHeader className="gap-2">
        <CardTitle>
          <h3 id={headingId} tabIndex={-1} className="scroll-mt-24 text-base font-semibold outline-none" lang={lang}>
            {section.title}
          </h3>
        </CardTitle>
        <div className="flex flex-wrap items-center gap-1.5">
          {section.grounded ? (
            <Badge className="bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
              {t("pp.s.grounded")}
            </Badge>
          ) : (
            <Badge className="bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              <AlertTriangle aria-hidden="true" />
              {t("pp.s.ungrounded")}
            </Badge>
          )}
          {flags.map((f, i) => (
            <Badge key={i} variant="outline" title={f.detail}>
              {label("flag", f.kind)}
            </Badge>
          ))}
          {section.edited_by && (
            <Badge variant="secondary">
              <Pencil aria-hidden="true" />
              {t("pp.s.editedBy", { name: section.edited_by })}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!section.grounded && (
          <p
            role="note"
            className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
          >
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {t("pp.s.ungroundedWarning")}
          </p>
        )}
        {flags.length > 0 && (
          <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
            {flags.map((f, i) => (
              <li key={i}>
                <span className="font-medium text-foreground">{label("flag", f.kind)}:</span> {f.detail}
              </li>
            ))}
          </ul>
        )}

        {editing ? (
          <Editor
            section={section}
            onCancel={() => setEditing(false)}
            onSave={async (body, by, note) => {
              await onSave(body, by, note);
              setEditing(false);
            }}
          />
        ) : (
          <SectionBody body={section.body} lang={lang} />
        )}

        {reqs.length > 0 && (
          <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            {t("pp.s.answers")}:
            {reqs.map((i) => (
              <button
                key={i}
                type="button"
                onClick={() => onRequirement(i)}
                className="rounded border px-1.5 py-0.5 font-medium text-foreground hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                {t("pp.r.label", { n: i + 1 })}
              </button>
            ))}
          </p>
        )}

        <div className="flex flex-col gap-1.5 border-t pt-3">
          <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {t("pp.s.sources", { n: cited.length })}
          </h4>
          {cited.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t("pp.s.noSources")}</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {cited.map((id) => (
                <Citation key={id} id={id} chunk={chunks[id]} />
              ))}
            </ul>
          )}
        </div>

        {!editing && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEditing(true)}
              disabled={!editable}
              aria-describedby={editable ? undefined : `${headingId}-why`}
            >
              <Pencil aria-hidden="true" />
              {t("pp.s.edit")}
            </Button>
            {!editable && (
              <span id={`${headingId}-why`} className="text-xs text-muted-foreground">
                {t("pp.s.editDisabled")}
              </span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

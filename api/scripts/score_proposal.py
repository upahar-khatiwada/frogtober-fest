"""Proposal metric: share of sections with at least one valid KB citation (CLAUDE.md hard rule 8, spec section 8.2).

A citation is valid when the cited chunk was among the excerpts retrieved for that section (or a fact quoted
verbatim from one). An ungrounded section is kept and flagged, so the rate measures how much of a draft is backed by
the company's knowledge base, not whether drafting ran.

Tenders: the 7 pursued seeds labelled in data/golden/compliance_requirements.json (oracle records with their
requirements), plus 009 (consulting EOI) and 010 (consulting RFP) from the manifest, so every template runs.

Modes:
- default (offline): the section plan per tender only. No citation rate: that needs a model.
- `--llm`: drafts every section through Ollama with top-k retrieval over the demo KB (parsed and chunked like ingest,
  embedded by the real embedding model, in memory; no DB).
- `--db`: scores the latest stored proposal of every tender in DATABASE_URL (what the API produced).

From api/:
  uv run python -m api.scripts.score_proposal                  # plan only, offline
  uv run python -m api.scripts.score_proposal --llm --out ../data/golden/proposal_report.json
  uv run python -m api.scripts.score_proposal --db
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.score_compliance import DEMO_DIR, LABELS_PATH, demo_kb, make_retriever

EXTRA_SEEDS = ("009", "010")  # consulting EOI, consulting RFP


def score(proposals: dict[str, list[Any]]) -> dict[str, Any]:
    """Citation rate over all sections, per section key, and flag counts. `proposals`: id -> [ProposalSection]."""
    sections = [s for secs in proposals.values() for s in secs]
    by_key: dict[str, list[bool]] = {}
    for s in sections:
        by_key.setdefault(s.key, []).append(s.grounded)
    flags = Counter(f.kind.value for s in sections for f in s.flags)
    return {
        "tenders": len(proposals),
        "sections": len(sections),
        "grounded": sum(s.grounded for s in sections),
        "citation_rate": round(sum(s.grounded for s in sections) / len(sections), 3) if sections else None,
        "by_section": {k: round(sum(v) / len(v), 3) for k, v in sorted(by_key.items())},
        "per_tender": {nid: round(sum(s.grounded for s in secs) / len(secs), 3) if secs else None
                       for nid, secs in proposals.items()},
        "flags": dict(sorted(flags.items())),
    }


def format_report(m: dict[str, Any], mode: str) -> str:
    lines = [f"Proposal citation metric ({mode})",
             f"  sections with >= 1 valid KB citation: {m['grounded']}/{m['sections']} = {m['citation_rate']}"]
    lines += [f"    {k:<22} {v}" for k, v in m["by_section"].items()]
    lines.append("  per tender: " + ", ".join(f"{k}={v}" for k, v in m["per_tender"].items()))
    lines.append("  flags: " + (", ".join(f"{k}={v}" for k, v in m["flags"].items()) or "none"))
    return "\n".join(lines)


def records(settings, labels_doc: dict[str, Any]) -> dict[str, Any]:
    from ingest.seed_tenders import load_manifest
    from scripts.score_compliance import oracle_record
    from scripts.score_matching import oracle_record as base_record

    notices = {n["id"]: n for n in load_manifest(settings.seed_tenders_dir)["notices"]}
    out = {}
    for nid in [*labels_doc["tenders"], *EXTRA_SEEDS]:
        text = (settings.seed_tenders_dir / notices[nid]["file"]).read_text(encoding="utf-8")
        rec = (oracle_record(notices[nid], text, labels_doc["tenders"][nid]) if nid in labels_doc["tenders"]
               else base_record(notices[nid], text))
        out[nid] = (rec, text)
    return out


def from_db(settings) -> dict[str, list[Any]]:
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from agents.proposal import latest_proposal, proposal_from_row
    from db.models import Tender

    engine = create_engine(settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    out = {}
    with Session(engine) as session:
        for tender in session.scalars(select(Tender).order_by(Tender.id)):
            if (row := latest_proposal(session, tender.id)) is not None:
                out[str(tender.id)] = proposal_from_row(row).sections
    return out


def main(argv: list[str] | None = None) -> int:
    from agents.proposal import ProposalContext, draft_proposal, plan_sections, proposal_language, uses_bs
    from config import get_settings
    from pipeline.llm import LLMClient, LLMError
    from schemas import CompanyProfile

    ap = argparse.ArgumentParser(prog="python -m api.scripts.score_proposal")
    ap.add_argument("--labels", type=Path, default=LABELS_PATH)
    ap.add_argument("--demo", type=Path, default=DEMO_DIR)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--llm", action="store_true", help="draft through Ollama (needs LLM_MODEL + EMBED_MODEL)")
    mode.add_argument("--db", action="store_true", help="score the latest stored proposal per tender (DATABASE_URL)")
    ap.add_argument("--force-english", action="store_true", help="draft every proposal in English")
    ap.add_argument("--out", type=Path, help="write the report as JSON")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    if args.db:
        proposals = from_db(settings)
        if not proposals:
            print("no stored proposals in DATABASE_URL")
            return 1
        m = score(proposals)
        print(format_report(m, "stored proposals"))
        if args.out:
            args.out.write_text(json.dumps({"mode": "db", "metrics": m}, ensure_ascii=False, indent=1), encoding="utf-8")
        return 0

    labels_doc = json.loads(args.labels.read_text(encoding="utf-8"))
    now = datetime.fromisoformat(labels_doc["now"])
    company = CompanyProfile.model_validate_json((args.demo / "profile.json").read_text(encoding="utf-8"))
    recs = records(settings, labels_doc)
    if not args.llm:
        print("Section plans (offline; the citation rate needs --llm or --db):")
        for nid, (rec, text) in recs.items():
            lang = proposal_language(rec, force_english=args.force_english).value
            plan = ", ".join(s.key + (f"[{len(s.requirement_indices)}]" if s.requirement_indices else "")
                             for s in plan_sections(rec))
            print(f"  {nid} {rec.procurement_type.value}/{rec.method.value} {lang} bs={uses_bs(rec, text)}: {plan}")
        return 0

    client = LLMClient(lambda _run: None, settings)
    proposals: dict[str, list[Any]] = {}
    try:
        retrieve_fn = make_retriever(demo_kb(args.demo), client, settings.proposal_top_k)
        for nid, (rec, text) in recs.items():
            ctx = ProposalContext(record=rec, company=company, now=now, with_bs=uses_bs(rec, text),
                                  language=proposal_language(rec, force_english=args.force_english))
            proposals[nid] = draft_proposal(ctx, client=client, retrieve_fn=retrieve_fn)
            print(f"  {nid}: {sum(s.grounded for s in proposals[nid])}/{len(proposals[nid])} grounded", flush=True)
    except LLMError as exc:
        print(f"model call failed: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()

    m = score(proposals)
    label = f"llm={settings.llm_model}, oracle records, demo KB, top_k={settings.proposal_top_k}"
    print(format_report(m, label))
    if args.out:
        out = {"mode": label, "now": labels_doc["now"], "metrics": m,
               "sections": {nid: [s.model_dump(mode="json") for s in secs] for nid, secs in proposals.items()}}
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Compliance metric: recall on hand-labelled mandatory requirements of 7 seed tenders, for the demo company.

Labels: data/golden/compliance_requirements.json (one label per mandatory requirement, with the verdict a careful
reviewer would reach from the demo KB). The worst error is a requirement the company does NOT meet that does not come
out as a hard fail (the bid would go ahead and be disqualified), so `hard_fail_recall` is the headline number.

Metrics:
- recall:           labelled requirements that some compliance item covers (rule_id match, or a model item whose
                    requirement text contains one of the label's keywords).
- hard_fail_recall: labels with expected=fail that come out as status fail + severity hard.
- status_accuracy:  labels whose (most severe) matched item status equals the label; uncovered labels count as wrong.
- false_hard_fails: hard-fail items that match no expected-fail label (a wrong block).
- blocked_accuracy: tenders whose blocked yes/no matches the label.

Records: by default "oracle" TenderRecords built from the labels (requirements, required docs, criteria, bid security)
plus the seed manifest (deadline, cost), which isolates Compliance from Scout errors. `--records PATH` uses saved
Scout output instead (`python -m api.agents.scout --seed --json PATH`), which measures Scout + Compliance together.

Documents: data/demo_company/manifest.json, parsed and chunked like ingest into an in-memory KB (no DB). Default:
rules only, and model-layer requirements are listed as unclear. `--llm` adds the real model through Ollama, with
top-k retrieval over that KB embedded by the real embedding model.

From api/:
  uv run python -m api.scripts.score_compliance                      # rules only, oracle records
  uv run python -m api.scripts.score_compliance --llm --out ../data/golden/compliance_report.json
  uv run python -m api.scripts.score_compliance --records scout.json --llm
"""

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LABELS_PATH = ROOT / "data" / "golden" / "compliance_requirements.json"
DEMO_DIR = ROOT / "data" / "demo_company"
SEVERITY_ORDER = {"fail": 0, "unclear": 1, "pass": 2}


@dataclass
class KB:
    """The demo company's documents as DocumentMeta + chunks, built without a database."""

    documents: list[Any]  # DocumentMeta
    chunks: list[Any]  # ChunkHit (similarity 0)
    vectors: list[list[float]] = field(default_factory=list)


def demo_kb(demo_dir: Path = DEMO_DIR) -> KB:
    from db.search import ChunkHit
    from ingest.chunking import chunk_text
    from ingest.parse_docs import parse_document
    from nepal.dates import bs_to_ad, parse_bs_date
    from nepal.rules import DocumentMeta
    from schemas import DocType

    manifest = json.loads((demo_dir / "manifest.json").read_text(encoding="utf-8"))
    documents, chunks = [], []
    for doc_id, entry in enumerate(manifest["documents"], start=1):
        path = demo_dir / entry["file"]
        parsed = parse_document(path.read_bytes(), path.name)
        expiry = bs_to_ad(parse_bs_date(entry["expires_on_bs"])) if entry.get("expires_on_bs") else None
        first = len(chunks) + 1
        for index, chunk in enumerate(chunk_text(parsed.text)):
            chunks.append(ChunkHit(chunk_id=len(chunks) + 1, document_id=doc_id, filename=path.name,
                                   doc_type=DocType(entry["doc_type"]), expires_on=expiry, chunk_index=index,
                                   content=chunk.text, similarity=0.0))
        documents.append(DocumentMeta(
            doc_type=entry["doc_type"], document_id=doc_id, filename=path.name, expiry=expiry,
            fiscal_year_bs=entry.get("fiscal_year_bs"), value_npr=entry.get("value_npr"),
            chunk_id=first if len(chunks) >= first else None,
        ))
    return KB(documents, chunks)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / ((math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))) or 1.0)


def make_retriever(kb: KB, client, k: int):
    from dataclasses import replace

    if not kb.vectors:
        kb.vectors = client.embed([c.content for c in kb.chunks])

    def retrieve_fn(query: str):
        [q] = client.embed([query])
        scored = sorted(((_cosine(q, v), c) for v, c in zip(kb.vectors, kb.chunks)), key=lambda t: (-t[0], t[1].chunk_id))
        return [replace(c, similarity=s) for s, c in scored[:k]]

    return retrieve_fn


def oracle_record(notice: dict[str, Any], text: str, labelled: dict[str, Any]):
    """The matching metric's oracle record (manifest facts) + this file's compliance fields and requirements."""
    from schemas import TenderRecord
    from scripts.score_matching import oracle_record as base_record

    base = base_record(notice, text).model_dump(mode="json")
    rec = labelled["record"]
    base.update({
        "required_docs": rec["required_docs"],
        "criteria": rec.get("criteria") or {},
        "bid_security": rec.get("bid_security"),
        "bid_validity_days": rec.get("bid_validity_days"),
        "performance_security_percent": rec.get("performance_security_percent"),
        "domestic_preference": rec.get("domestic_preference", False),
        "requirements": [{"text": r["text"], "mandatory": True, "category": r["category"], "source_quote": r["quote"]}
                         for r in labelled["requirements"]],
    })
    return TenderRecord.model_validate(base)


def matches(label: dict[str, Any], item) -> bool:
    if label.get("rule_id"):
        return item.rule_id == label["rule_id"]
    text = item.requirement.casefold()
    return item.source.value == "model" and any(k.casefold() in text for k in label.get("keywords", []))


def score(labels_doc: dict[str, Any], reports: dict[str, Any]) -> dict[str, Any]:
    """reports: {tender id: ComplianceReport | None (stage failed)}. Pure; tested offline."""
    rows, false_hard, blocked_ok = [], [], 0
    for nid, labelled in labels_doc["tenders"].items():
        report = reports.get(nid)
        items = report.items if report else []
        expected_fail_keys = set()
        for label in labelled["requirements"]:
            hits = [i for i in items if matches(label, i)]
            status = min((i.status.value for i in hits), key=SEVERITY_ORDER.get) if hits else None
            hard_fail = any(i.status.value == "fail" and i.severity.value == "hard" for i in hits)
            if label["expected"] == "fail":
                expected_fail_keys |= {i.key for i in hits}
            rows.append({"tender": nid, "key": label["key"], "expected": label["expected"], "hard": label["hard"],
                         "covered": bool(hits), "status": status, "hard_fail": hard_fail,
                         "items": [f"{i.rule_id or 'model'}: {i.requirement}" for i in hits]})
        for item in (report.hard_failures if report else []):
            if item.key not in expected_fail_keys:
                false_hard.append({"tender": nid, "item": f"{item.rule_id or 'model'}: {item.requirement}"})
        blocked_ok += (report is not None and report.is_blocked) == labelled["expected_blocked"]

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 3) if b else None

    must_fail = [r for r in rows if r["expected"] == "fail" and r["hard"]]
    return {
        "labels": len(rows),
        "recall": ratio(sum(r["covered"] for r in rows), len(rows)),
        "hard_fail_recall": ratio(sum(r["hard_fail"] for r in must_fail), len(must_fail)),
        "hard_fail_labels": len(must_fail),
        "missed_hard_fails": [f"{r['tender']}:{r['key']}" for r in must_fail if not r["hard_fail"]],
        "uncovered": [f"{r['tender']}:{r['key']}" for r in rows if not r["covered"]],
        "status_accuracy": ratio(sum(r["status"] == r["expected"] for r in rows), len(rows)),
        "false_hard_fails": false_hard,
        "blocked_accuracy": ratio(blocked_ok, len(labels_doc["tenders"])),
        "rows": rows,
    }


def format_report(m: dict[str, Any], mode: str) -> str:
    lines = [f"Compliance metric ({mode})", ""]
    lines.append(f"{'tender':<7} {'requirement':<17} {'expected':<9} {'got':<9} hard-fail")
    for r in m["rows"]:
        got = r["status"] or "MISSING"
        flag = "yes" if r["hard_fail"] else ("MISSED" if r["expected"] == "fail" else "")
        lines.append(f"{r['tender']:<7} {r['key']:<17} {r['expected']:<9} {got:<9} {flag}")
    lines += [
        "",
        f"recall (requirements covered)      {m['recall']}  ({m['labels']} labels)",
        f"hard-fail recall (worst error)     {m['hard_fail_recall']}  ({m['hard_fail_labels']} must-fail labels)",
        f"  missed hard fails                {', '.join(m['missed_hard_fails']) or '-'}",
        f"status accuracy                    {m['status_accuracy']}",
        f"false hard fails (wrong blocks)    {len(m['false_hard_fails'])}"
        + "".join(f"\n  {f['tender']}: {f['item']}" for f in m["false_hard_fails"]),
        f"blocked accuracy                   {m['blocked_accuracy']}",
        f"uncovered                          {', '.join(m['uncovered']) or '-'}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from agents.compliance import check_requirements
    from config import get_settings
    from ingest.seed_tenders import load_manifest
    from pipeline.llm import LLMClient, LLMError
    from schemas import CompanyProfile, TenderRecord

    ap = argparse.ArgumentParser(prog="python -m api.scripts.score_compliance")
    ap.add_argument("--labels", type=Path, default=LABELS_PATH)
    ap.add_argument("--demo", type=Path, default=DEMO_DIR)
    ap.add_argument("--records", type=Path, help="Scout output JSON ({id: TenderRecord | null}) instead of oracle records")
    ap.add_argument("--llm", action="store_true", help="add the model layer through Ollama (needs LLM_MODEL + EMBED_MODEL)")
    ap.add_argument("--out", type=Path, help="write the report as JSON")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    labels_doc = json.loads(args.labels.read_text(encoding="utf-8"))
    now = datetime.fromisoformat(labels_doc["now"])
    company = CompanyProfile.model_validate_json((args.demo / "profile.json").read_text(encoding="utf-8"))
    notices = {n["id"]: n for n in load_manifest(settings.seed_tenders_dir)["notices"]}
    saved = json.loads(args.records.read_text(encoding="utf-8")) if args.records else None
    kb = demo_kb(args.demo)

    client = LLMClient(lambda _run: None, settings) if args.llm else None
    reports: dict[str, Any] = {}
    try:
        retrieve_fn = make_retriever(kb, client, settings.compliance_top_k) if client else None
        for nid, labelled in labels_doc["tenders"].items():
            notice = notices[nid]
            if saved is not None:
                if not saved.get(nid):
                    reports[nid] = None
                    continue
                record = TenderRecord.model_validate(saved[nid])
            else:
                record = oracle_record(notice, (settings.seed_tenders_dir / notice["file"]).read_text(encoding="utf-8"), labelled)
            reports[nid] = check_requirements(record, company, kb.documents, client=client, retrieve_fn=retrieve_fn, now=now)
    except LLMError as exc:
        print(f"model call failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if client:
            client.close()

    m = score(labels_doc, reports)
    mode = f"{'oracle' if saved is None else 'scout'} records, {'llm=' + settings.llm_model if args.llm else 'rules only'}"
    print(format_report(m, mode))
    if args.out:
        out = {"mode": mode, "now": labels_doc["now"], "metrics": m,
               "items": {nid: [i.model_dump(mode="json") for i in r.items] if r else None for nid, r in reports.items()}}
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

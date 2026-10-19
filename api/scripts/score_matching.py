"""Matching metric: do the hand-labelled relevant seed tenders rank in the top 3 for the demo company?

Labels: data/golden/match_relevance.json (`core` = the manifest's strong/good matches; `relevant` = core
plus in-scope works with messy notices). Tenders are ranked exactly like GET /tenders (score high first,
then soonest deadline, then id) at the labels' fixed clock, so passed deadlines are reproducible.

Records: by default each tender's TenderRecord is built from the seed manifest's hand labels ("oracle"
records: type, method, buyer level, district, cost, deadline), which isolates Matching from Scout errors.
`--records PATH` uses saved Scout output instead (`python -m api.agents.scout --seed --json PATH`).

Scoring: by default deterministic signals only (no model). `--llm` adds the real model's semantic score
through Ollama. KB chunks are not retrieved here (no DB); the model sees the company profile only.

From api/:
  uv run python -m api.scripts.score_matching                  # deterministic only, oracle records
  uv run python -m api.scripts.score_matching --llm            # + semantic score from the real model
  uv run python -m api.scripts.score_matching --records scout.json --llm --out ../data/golden/match_report.json
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LABELS_PATH = ROOT / "data" / "golden" / "match_relevance.json"
COMPANY_PATH = ROOT / "data" / "demo_company" / "profile.json"
TOP_N = 3


@dataclass
class Row:
    nid: str
    score: int
    decision: str
    deadline: datetime | None
    core: bool
    relevant: bool
    reasons: list[str]


def _slug_title(filename: str) -> str:
    return filename.split("_", 1)[1].rsplit(".", 1)[0].replace("_", " ")


def _buyer(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("[SYNTHETIC")]
    return lines[0] if lines else "unknown"


def oracle_record(notice: dict[str, Any], text: str):
    """A TenderRecord from the manifest's hand labels (title = the file slug, which carries the work type)."""
    from nepal.dates import END_OF_DAY, NPT, bs_to_ad, parse_bs_date
    from schemas import TenderRecord

    exp = notice.get("expected", {})
    day = date.fromisoformat(exp["deadline_ad"]) if exp.get("deadline_ad") else None
    if day is None and exp.get("deadline_bs"):  # BS-only notice: lookup-table conversion, like Scout
        day = bs_to_ad(parse_bs_date(exp["deadline_bs"]))
    deadline = datetime.combine(day, END_OF_DAY, tzinfo=NPT) if day else None
    title = _slug_title(notice["file"])
    return TenderRecord(
        title=title, buyer=_buyer(text), buyer_level=notice["buyer_level"], province=notice.get("province"),
        district=notice.get("district"), scope=title, procurement_type=notice["procurement_type"],
        method=notice["method"], language=notice["language"], deadline_ad=deadline,
        deadline_bs_iso=exp.get("deadline_bs"), estimated_cost_npr=exp.get("estimated_cost_npr"),
        jv_allowed=exp.get("jv_allowed"),
    )


def rank(rows: list[Row]) -> list[Row]:
    far = datetime.max.replace(tzinfo=None)
    return sorted(rows, key=lambda r: (-r.score, r.deadline.replace(tzinfo=None) if r.deadline else far, r.nid))


def metrics(ranked: list[Row]) -> dict[str, Any]:
    top = ranked[:TOP_N]
    core = [r for r in ranked if r.core]
    relevant = [r for r in ranked if r.relevant]
    irrelevant = [r for r in ranked if not r.relevant]
    pursued = [r for r in ranked if r.decision == "pursue"]

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 3) if b else None

    return {
        "n": len(ranked),
        "top3": [r.nid for r in top],
        f"core_precision_at_{TOP_N}": ratio(sum(r.core for r in top), len(top)),
        f"relevant_precision_at_{TOP_N}": ratio(sum(r.relevant for r in top), len(top)),
        "core_ranks": {r.nid: ranked.index(r) + 1 for r in core},
        "relevant_pursued": ratio(sum(r.decision == "pursue" for r in relevant), len(relevant)),
        "irrelevant_skipped": ratio(sum(r.decision == "skip" for r in irrelevant), len(irrelevant)),
        "pursue_precision": ratio(sum(r.relevant for r in pursued), len(pursued)),
        "false_pursue": [r.nid for r in pursued if not r.relevant],
        "missed_relevant": [r.nid for r in relevant if r.decision == "skip"],
    }


def format_report(ranked: list[Row], m: dict[str, Any], mode: str) -> str:
    lines = [f"Matching metric ({mode}); labels: {LABELS_PATH.name}", "",
             f"{'rank':>4}  {'id':<4} {'score':>5}  {'decision':<8} {'label':<8} first reason"]
    for i, r in enumerate(ranked, 1):
        label = "core" if r.core else "relevant" if r.relevant else "-"
        first = next((x for x in r.reasons if "SKIP" in x), r.reasons[0] if r.reasons else "")
        lines.append(f"{i:>4}  {r.nid:<4} {r.score:>5}  {r.decision:<8} {label:<8} {first[:90]}")
    lines += ["", f"top {TOP_N}: {', '.join(m['top3'])}",
              f"core precision@{TOP_N}: {m[f'core_precision_at_{TOP_N}']}   "
              f"relevant precision@{TOP_N}: {m[f'relevant_precision_at_{TOP_N}']}",
              f"core ranks: {m['core_ranks']}",
              f"relevant pursued: {m['relevant_pursued']} (missed {m['missed_relevant']})",
              f"irrelevant skipped: {m['irrelevant_skipped']} (false pursue {m['false_pursue']})",
              f"pursue precision: {m['pursue_precision']}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from agents.matching import score_tender
    from config import get_settings
    from ingest.seed_tenders import load_manifest
    from pipeline.llm import LLMClient, LLMError
    from schemas import CompanyProfile, TenderRecord

    ap = argparse.ArgumentParser(prog="python -m api.scripts.score_matching")
    ap.add_argument("--labels", type=Path, default=LABELS_PATH)
    ap.add_argument("--company", type=Path, default=COMPANY_PATH)
    ap.add_argument("--records", type=Path, help="Scout output JSON ({id: TenderRecord | null}) instead of oracle records")
    ap.add_argument("--llm", action="store_true", help="add the real model's semantic score (needs Ollama)")
    ap.add_argument("--out", type=Path, help="write the report as JSON")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    labels_doc = json.loads(args.labels.read_text(encoding="utf-8"))
    labels, now = labels_doc["labels"], datetime.fromisoformat(labels_doc["now"])
    company = CompanyProfile.model_validate_json(args.company.read_text(encoding="utf-8"))
    manifest = load_manifest(settings.seed_tenders_dir)
    saved = json.loads(args.records.read_text(encoding="utf-8")) if args.records else None

    client = LLMClient(lambda _run: None, settings) if args.llm else None
    rows: list[Row] = []
    try:
        for notice in manifest["notices"]:
            nid = notice["id"]
            text = (settings.seed_tenders_dir / notice["file"]).read_text(encoding="utf-8")
            if saved is not None:
                if not saved.get(nid):  # Scout failed or skipped: unscored, ranks last
                    rows.append(Row(nid, 0, "skip", None, labels[nid]["core"], labels[nid]["relevant"], ["no Scout record"]))
                    continue
                record = TenderRecord.model_validate(saved[nid])
            else:
                record = oracle_record(notice, text)
            try:
                result = score_tender(record, company, [], client=client, settings=settings, now=now)
            except LLMError as exc:
                print(f"{nid}: model call failed: {exc}", file=sys.stderr)
                return 1
            rows.append(Row(nid, result.score, result.decision.value, record.deadline_ad, labels[nid]["core"],
                            labels[nid]["relevant"], result.reasons))
    finally:
        if client:
            client.close()

    ranked = rank(rows)
    m = metrics(ranked)
    mode = f"{'oracle' if saved is None else 'scout'} records, {'llm=' + settings.llm_model if args.llm else 'deterministic only'}"
    print(format_report(ranked, m, mode))
    if args.out:
        out = {"mode": mode, "now": labels_doc["now"], "threshold": settings.match_threshold, "metrics": m,
               "ranking": [{"id": r.nid, "score": r.score, "decision": r.decision, "reasons": r.reasons} for r in ranked]}
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

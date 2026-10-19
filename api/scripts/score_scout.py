"""Field-level accuracy of Scout against the golden set (data/golden/scout_expected.json).

Scores deadline (BS date, and AD datetime to the minute), estimated cost, and required
document types (micro precision / recall / F1 and exact-set accuracy). A null label is
correct only if Scout also gives null (no guessing). A failed extraction is wrong on
every field. With --manifest, deadline and cost are also scored on all seed notices
against the `expected` blocks in data/seed_tenders/manifest.json.

From api/:
  uv run python -m scripts.score_scout                         # runs Scout on the real model (Ollama)
  uv run python -m scripts.score_scout --manifest              # + deadline/cost on all 37 seeds
  uv run python -m scripts.score_scout --predictions out.json  # score saved `agents.scout --json` output
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

GOLDEN_PATH = Path(__file__).resolve().parents[2] / "data" / "golden" / "scout_expected.json"


@dataclass
class FieldScore:
    correct: int = 0
    total: int = 0
    misses: list[str] = field(default_factory=list)

    def add(self, nid: str, ok: bool, got: Any, want: Any) -> None:
        self.total += 1
        self.correct += ok
        if not ok:
            self.misses.append(f"{nid}: got {got!r}, want {want!r}")

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.total if self.total else None


@dataclass
class DocScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    exact: FieldScore = field(default_factory=FieldScore)

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)


@dataclass
class Report:
    deadline_bs: FieldScore = field(default_factory=FieldScore)
    deadline_ad: FieldScore = field(default_factory=FieldScore)
    budget: FieldScore = field(default_factory=FieldScore)
    docs: DocScore = field(default_factory=DocScore)
    failed: list[str] = field(default_factory=list)
    scored: int = 0
    skipped_todo: int = 0

    def as_dict(self) -> dict[str, Any]:
        def fs(s: FieldScore) -> dict[str, Any]:
            return {"accuracy": s.accuracy, "correct": s.correct, "total": s.total, "misses": s.misses}

        d = self.docs
        return {
            "scored": self.scored, "skipped_todo": self.skipped_todo, "failed": self.failed,
            "deadline_bs": fs(self.deadline_bs), "deadline_ad": fs(self.deadline_ad), "budget": fs(self.budget),
            "required_docs": {"precision": d.precision, "recall": d.recall, "f1": d.f1, "tp": d.tp, "fp": d.fp, "fn": d.fn,
                              "exact_set": fs(d.exact)},
        }


def _same_instant(got: str | None, want: str | None) -> bool:
    if got is None or want is None:
        return got is want
    return datetime.fromisoformat(got).replace(second=0, microsecond=0) == datetime.fromisoformat(want).replace(second=0, microsecond=0)


def score(golden: list[dict[str, Any]], predictions: dict[str, dict[str, Any] | None]) -> Report:
    """`predictions`: seed id -> TenderRecord as JSON (or None if Scout failed)."""
    report = Report()
    for entry in golden:
        if entry.get("status") != "filled":
            report.skipped_todo += 1
            continue
        nid = entry["id"]
        if nid not in predictions:
            continue
        report.scored += 1
        rec = predictions[nid]
        if rec is None:
            report.failed.append(nid)
            rec = {}
        if "deadline_bs" in entry:
            got = rec.get("deadline_bs_iso")
            report.deadline_bs.add(nid, got == entry["deadline_bs"], got, entry["deadline_bs"])
        if "deadline_ad" in entry:
            got = rec.get("deadline_ad")
            report.deadline_ad.add(nid, _same_instant(got, entry["deadline_ad"]), got, entry["deadline_ad"])
        if "estimated_cost_npr" in entry:
            got = rec.get("estimated_cost_npr")
            report.budget.add(nid, got == entry["estimated_cost_npr"], got, entry["estimated_cost_npr"])
        if entry.get("required_doc_types") is not None:
            want = set(entry["required_doc_types"])
            got_docs = {d["doc_type"] for d in rec.get("required_docs", [])}
            report.docs.tp += len(want & got_docs)
            report.docs.fp += len(got_docs - want)
            report.docs.fn += len(want - got_docs)
            report.docs.exact.add(nid, got_docs == want, sorted(got_docs), sorted(want))
    return report


def manifest_golden(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Deadline (BS date only; the manifest has no times) and cost labels for every seed notice."""
    return [{"id": n["id"], "status": "filled", "deadline_bs": n["expected"]["deadline_bs"],
             "estimated_cost_npr": n["expected"]["estimated_cost_npr"]} for n in manifest["notices"]]


def _pct(x: float | None) -> str:
    return "  n/a" if x is None else f"{100 * x:5.1f}%"


def format_report(title: str, r: Report) -> str:
    lines = [f"== {title}: {r.scored} scored, {r.skipped_todo} todo, {len(r.failed)} failed {r.failed or ''}"]
    for name, s in (("deadline_bs", r.deadline_bs), ("deadline_ad", r.deadline_ad), ("budget", r.budget)):
        if s.total:
            lines.append(f"  {name:<12} {_pct(s.accuracy)}  ({s.correct}/{s.total})")
            lines += [f"      x {m}" for m in s.misses]
    d = r.docs
    if d.exact.total:
        lines.append(f"  docs         P {_pct(d.precision)}  R {_pct(d.recall)}  F1 {_pct(d.f1)}  "
                     f"exact {_pct(d.exact.accuracy)} ({d.exact.correct}/{d.exact.total})")
        lines += [f"      x {m}" for m in d.exact.misses]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from config import get_settings
    from ingest.seed_tenders import load_manifest

    ap = argparse.ArgumentParser(prog="python -m scripts.score_scout")
    ap.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    ap.add_argument("--predictions", type=Path, help="JSON from `python -m agents.scout --seed --json PATH`")
    ap.add_argument("--manifest", action="store_true", help="also score deadline/cost on every seed notice")
    ap.add_argument("--out", type=Path, help="write the report as JSON")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    golden = json.loads(args.golden.read_text(encoding="utf-8"))["tenders"]
    manifest = load_manifest(settings.seed_tenders_dir)
    if args.predictions:
        predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    else:
        from agents.scout import run_seed_offline
        from pipeline.llm import LLMClient

        wanted = {e["id"] for e in golden if e.get("status") == "filled"}
        if args.manifest:
            wanted |= {n["id"] for n in manifest["notices"]}
        with LLMClient(lambda _run: None, settings) as client:
            rows = run_seed_offline(client, settings.seed_tenders_dir, wanted)
        predictions = {nid: rec.model_dump(mode="json") if rec else None for nid, rec, _ in rows}

    out = {"model": settings.llm_model, "golden": score(golden, predictions).as_dict()}
    print(f"model: {settings.llm_model}")
    print(format_report("golden set", score(golden, predictions)))
    if args.manifest:
        report = score(manifest_golden(manifest), predictions)
        out["manifest"] = report.as_dict()
        print(format_report("manifest (deadline_bs + budget, all seeds)", report))
    if args.out:
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

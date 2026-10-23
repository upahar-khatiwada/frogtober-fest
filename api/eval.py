"""One command that runs every metric and writes docs/EVAL.md.

    cd api && uv run python -m api.eval                       # real model from LLM_MODEL (needs Ollama)
    cd api && uv run python -m api.eval --model llama3.1:8b   # fallback model
    cd api && uv run python -m api.eval --offline             # no model: rules/deterministic parts only
    cd api && uv run python -m api.eval --render-only         # rebuild docs/EVAL.md from saved runs

Metrics (spec section 13):
- Scout: field accuracy on data/golden/scout_expected.json (deadline BS, deadline AD, budget, document types),
  overall and per notice language (en / ne / mixed).
- Matching: top-3 precision against data/golden/match_relevance.json.
- Compliance: recall and hard-fail recall on data/golden/compliance_requirements.json.
- Proposal: share of sections with >= 1 valid KB citation.

Matching and Compliance use oracle records (hand-labelled facts) so they are measured apart from Scout errors.
Each run is saved to data/golden/eval/<model>.json; EVAL.md has one column per saved run. The replay cache is
disabled here so latencies and answers are the live model's.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "data" / "golden" / "scout_expected.json"
RESULTS_DIR = ROOT / "data" / "golden" / "eval"
DOC = ROOT / "docs" / "EVAL.md"
LANGS = ("en", "ne", "mixed")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", name.lower()).strip("-")


def _scout_numbers(r) -> dict:
    return {"n": r.scored, "failed": r.failed, "deadline_bs": r.deadline_bs.accuracy,
            "deadline_ad": r.deadline_ad.accuracy, "budget": r.budget.accuracy,
            "docs_f1": r.docs.f1, "docs_exact": r.docs.exact.accuracy,
            "misses": r.deadline_bs.misses + r.deadline_ad.misses + r.budget.misses + r.docs.exact.misses}


def run_scout(settings, all_seeds: bool) -> dict:
    from agents.scout import run_seed_offline
    from ingest.seed_tenders import load_manifest
    from pipeline.llm import LLMClient
    from scripts.score_scout import score

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["tenders"]
    manifest = {n["id"]: n for n in load_manifest(settings.seed_tenders_dir)["notices"]}
    wanted = set(manifest) if all_seeds else {e["id"] for e in golden if e["status"] == "filled"}
    with LLMClient(lambda _r: None, settings) as client:
        rows = run_seed_offline(client, settings.seed_tenders_dir, wanted)
    preds = {nid: rec.model_dump(mode="json") if rec else None for nid, rec, _ in rows}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"scout_predictions_{slug(settings.llm_model)}.json").write_text(
        json.dumps(preds, ensure_ascii=False, indent=1), encoding="utf-8")
    out = {"overall": _scout_numbers(score(golden, preds)),
           "needs_review": sum(1 for p in preds.values() if p and p.get("needs_review")),
           "extracted": sum(1 for p in preds.values() if p), "attempted": len(preds), "by_language": {}}
    for lang in LANGS:
        subset = [e for e in golden if e.get("language") == lang]
        if subset:
            out["by_language"][lang] = _scout_numbers(score(subset, preds))
    return out


def _call(main, argv: list[str]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.json"
        rc = main([*argv, "--out", str(path)])
        if rc != 0 or not path.is_file():
            raise RuntimeError(f"{main.__module__} exited {rc} (see output above)")
        return json.loads(path.read_text(encoding="utf-8"))["metrics"]


def run_matching(llm: bool) -> dict:
    from scripts.score_matching import main
    m = _call(main, ["--llm"] if llm else [])
    return {k: m[k] for k in ("core_precision_at_3", "relevant_precision_at_3", "relevant_pursued",
                              "irrelevant_skipped", "top3", "false_pursue", "missed_relevant")}


def run_compliance(llm: bool) -> dict:
    from scripts.score_compliance import main
    m = _call(main, ["--llm"] if llm else [])
    return {"recall": m["recall"], "hard_fail_recall": m["hard_fail_recall"], "status_accuracy": m["status_accuracy"],
            "false_hard_fails": len(m["false_hard_fails"]), "blocked_accuracy": m["blocked_accuracy"],
            "labels": m["labels"], "missed_hard_fails": m["missed_hard_fails"]}


def run_proposal() -> dict:
    from scripts.score_proposal import main
    m = _call(main, ["--llm"])
    return {"citation_rate": m["citation_rate"], "sections": m["sections"], "grounded": m["grounded"],
            "flags": m["flags"]}


def guarded(res: dict, name: str, fn) -> None:
    started = time.perf_counter()
    try:
        res[name] = fn()
    except Exception as exc:  # a dead model must give a row of errors, not a stack trace and no report
        res[name] = None
        res["errors"][name] = f"{type(exc).__name__}: {exc}"
    res["seconds"][name] = round(time.perf_counter() - started, 1)


def pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def render(runs: list[dict]) -> str:
    cols = [f"{r['model']}{' (offline)' if r['offline'] else ''}" for r in runs]

    def row(label, getter, fmt=pct):
        cells = []
        for r in runs:
            try:
                v = getter(r)
            except (KeyError, TypeError):
                v = None
            cells.append(fmt(v) if v is not None else "n/a")
        return f"| {label} | " + " | ".join(cells) + " |"

    def sc(path):
        return lambda r: path(r["scout"])

    lines = ["# Evaluation", "",
             "Generated by `cd api && uv run python -m api.eval`. Do not edit by hand; rerun to refresh.", "",
             "| Metric | " + " | ".join(cols) + " |", "|---|" + "---|" * len(runs)]
    lines += [
        row("**Scout** deadline (BS date)", sc(lambda s: s["overall"]["deadline_bs"])),
        row("Scout deadline (AD datetime)", sc(lambda s: s["overall"]["deadline_ad"])),
        row("Scout budget", sc(lambda s: s["overall"]["budget"])),
        row("Scout required-doc types, F1", sc(lambda s: s["overall"]["docs_f1"])),
        row("Scout required-doc types, exact set", sc(lambda s: s["overall"]["docs_exact"])),
        row("Scout notices extracted", sc(lambda s: s["extracted"] / s["attempted"])),
        row("Scout notices flagged needs_review", sc(lambda s: s["needs_review"] / s["attempted"])),
    ]
    for lang in LANGS:
        n = next((r["scout"]["by_language"][lang]["n"] for r in runs if r.get("scout") and lang in r["scout"]["by_language"]), 0)
        if not n:
            continue
        for key, label in (("deadline_bs", "deadline BS"), ("budget", "budget"), ("docs_f1", "docs F1")):
            lines.append(row(f"Scout {label} [{lang}, n={n}]", sc(lambda s, l=lang, k=key: s["by_language"][l][k])))
    lines += [
        row("**Matching** core precision@3", lambda r: r["matching"]["core_precision_at_3"]),
        row("Matching relevant precision@3", lambda r: r["matching"]["relevant_precision_at_3"]),
        row("Matching relevant tenders pursued", lambda r: r["matching"]["relevant_pursued"]),
        row("Matching irrelevant tenders skipped", lambda r: r["matching"]["irrelevant_skipped"]),
        row("**Compliance** recall (mandatory requirements covered)", lambda r: r["compliance"]["recall"]),
        row("Compliance hard-fail recall (worst error)", lambda r: r["compliance"]["hard_fail_recall"]),
        row("Compliance status accuracy", lambda r: r["compliance"]["status_accuracy"]),
        row("Compliance false hard fails (count)", lambda r: r["compliance"]["false_hard_fails"], str),
        row("Compliance blocked/not-blocked accuracy", lambda r: r["compliance"]["blocked_accuracy"]),
        row("**Proposal** sections with a valid KB citation", lambda r: r["proposal"]["citation_rate"]),
        row("Wall time, Scout (s)", lambda r: r["seconds"]["scout"], lambda v: f"{v:.0f}"),
    ]
    lines += ["", "## How to read this", "",
              "- Scout: 15 hand-labelled synthetic notices (`data/golden/scout_expected.json`). One notice is 6.7 points, "
              "so small gaps between models are noise. A `null` label counts as correct only if Scout also returns null.",
              "- Matching and Compliance run on **oracle records** (hand-labelled facts), so they do not include Scout errors. "
              "Compliance's Layer 1 is deterministic code and identical across models; only the model layer "
              "(licence class, personnel, equipment, ...) changes with the model.",
              "- Compliance hard-fail recall is the number to watch: a missed hard fail means a bid that will be disqualified goes ahead.",
              "- The notices and the demo company are synthetic and the labels were written by the project team from the same text. "
              "These numbers show the plumbing and relative model behaviour; they are not an estimate of accuracy on real notices.",
              "- `n/a` means the stage was not run (offline mode, or the model call failed; see Errors)."]
    for r, c in zip(runs, cols):
        lines += ["", f"## {c}", "", f"Run at {r['date']} on `{r['model']}`; "
                  f"stage wall time (s): {json.dumps(r['seconds'])}."]
        if r["errors"]:
            lines += ["", "**Errors**", *[f"- {k}: {v}" for k, v in r["errors"].items()]]
        if r.get("scout"):
            o = r["scout"]["overall"]
            lines += ["", f"Scout: {o['n']} scored, failed {o['failed'] or 'none'}."]
            lines += [f"- miss: {m}" for m in o["misses"][:40]]
        if r.get("matching"):
            m = r["matching"]
            lines += ["", f"Matching top-3: {m['top3']}; false pursues: {m['false_pursue'] or 'none'}; "
                          f"missed relevant: {m['missed_relevant'] or 'none'}."]
        if r.get("compliance"):
            lines += [f"Compliance missed hard fails: {r['compliance']['missed_hard_fails'] or 'none'}."]
        if r.get("proposal"):
            lines += [f"Proposal flags: {json.dumps(r['proposal']['flags'])}."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m api.eval", description=__doc__.splitlines()[0])
    ap.add_argument("--model", help="override LLM_MODEL (e.g. llama3.1:8b)")
    ap.add_argument("--offline", action="store_true", help="no model calls: deterministic Matching/Compliance only")
    ap.add_argument("--all-seeds", action="store_true", help="run Scout on all 37 seeds, not just the 15 golden ones")
    ap.add_argument("--skip", default="", help="comma list of: scout,matching,compliance,proposal")
    ap.add_argument("--render-only", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    os.environ["LLM_REPLAY_CACHE"] = ""  # live answers only

    errors = {}
    if not args.render_only:
        from config import get_settings
        settings = get_settings()
        skip = {s.strip() for s in args.skip.split(",") if s.strip()}
        res = {"model": "deterministic" if args.offline else settings.llm_model, "offline": args.offline,
               "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "errors": {}, "seconds": {}, "scout": None, "matching": None, "compliance": None, "proposal": None}
        llm = not args.offline
        if llm and "scout" not in skip:
            guarded(res, "scout", lambda: run_scout(settings, args.all_seeds))
        if "matching" not in skip:
            guarded(res, "matching", lambda: run_matching(llm))
        if "compliance" not in skip:
            guarded(res, "compliance", lambda: run_compliance(llm))
        if llm and "proposal" not in skip:
            guarded(res, "proposal", run_proposal)
        res["seconds"].setdefault("scout", None)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        name = "offline" if args.offline else slug(settings.llm_model)
        (RESULTS_DIR / f"{name}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        errors = res["errors"]

    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS_DIR.glob("*.json"))
            if not p.name.startswith("scout_predictions_")]
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(render(runs), encoding="utf-8")
    print(f"wrote {DOC} ({len(runs)} run(s))")
    for k, v in errors.items():
        print(f"ERROR {k}: {v}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
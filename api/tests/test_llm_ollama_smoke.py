"""Real-Ollama smoke test. Skipped by default; run with `uv run pytest -m ollama`.

Needs Ollama at LLM_BASE_URL with LLM_MODEL and EMBED_MODEL pulled.
On low-RAM machines, point LLM_MODEL at a smaller open-weight model
(e.g. LLM_MODEL=qwen2.5:1.5b-instruct) - this only checks the plumbing.
"""

import pytest

from pipeline.llm import EMBED_DIM, LLMClient
from schemas import MatchAssessment, Stage

pytestmark = pytest.mark.ollama


def test_real_ollama_chat_and_embed():
    runs = []
    with LLMClient(runs.append) as client:
        result = client.chat(
            stage=Stage.MATCHING,
            messages=[
                {
                    "role": "system",
                    "content": "Score how well a tender fits a company from 0 to 100 and give short reasons.",
                },
                {
                    "role": "user",
                    "content": "Company: road construction contractor in Jhapa. "
                    "Tender: gravelling of a 2 km rural road in Jhapa.",
                },
            ],
            schema=MatchAssessment,
        )
        vectors = client.embed(["Class C construction licence, renewed for FY 2083/84."])

    assert 0 <= result.score <= 100
    assert runs[0].ok
    assert len(vectors[0]) == EMBED_DIM


def test_real_ollama_scout_on_seed_001():
    """Plumbing: Ollama's grammar accepts the TenderExtraction schema and post-processing runs on real output."""
    from pathlib import Path

    from agents.scout import extract_tender

    text = (Path(__file__).resolve().parents[2] / "data" / "seed_tenders" / "001_bhanu_road_gravelling.txt").read_text(encoding="utf-8")
    runs = []
    with LLMClient(runs.append) as client:
        record = extract_tender(client, text)
    assert runs[0].ok and runs[0].stage is Stage.SCOUT
    assert record.title and record.sources


def test_real_ollama_matching_on_seed_001_and_003():
    """Plumbing + sanity: the real model rates road works above ICU ventilators for the demo company."""
    import json
    from pathlib import Path

    from agents.matching import assess
    from schemas import CompanyProfile
    from scripts.score_matching import oracle_record

    root = Path(__file__).resolve().parents[2]
    company = CompanyProfile.model_validate_json((root / "data" / "demo_company" / "profile.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "data" / "seed_tenders" / "manifest.json").read_text(encoding="utf-8"))
    notices = {n["id"]: n for n in manifest["notices"]}
    runs = []
    with LLMClient(runs.append) as client:
        scores = {nid: assess(client, oracle_record(notices[nid], (root / "data" / "seed_tenders" / notices[nid]["file"])
                                                    .read_text(encoding="utf-8")), company, []).score
                  for nid in ("001", "003")}
    assert all(r.ok and r.stage is Stage.MATCHING for r in runs)
    assert scores["001"] > scores["003"]


def test_real_ollama_compliance_on_seed_001():
    """Compliance on the demo KB: the grammar accepts ComplianceAssessment, the expired clearance still blocks
    (a rule, not the model), and every model pass is backed by a chunk the code verified."""
    from scripts.score_compliance import demo_kb, make_retriever
    from tests.test_compliance import COMPANY, NOW, golden_record

    from agents.compliance import check_requirements

    kb = demo_kb()
    with LLMClient(lambda _run: None) as client:
        report = check_requirements(golden_record("001"), COMPANY, kb.documents, client=client,
                                    retrieve_fn=make_retriever(kb, client, 4), now=NOW)
    assert report.is_blocked and any(i.rule_id == "NP-TAX-CLEARANCE" for i in report.hard_failures)
    for item in report.items:
        if item.source.value == "model" and item.status.value != "unclear":
            assert item.evidence_chunk_ids and item.evidence_quote

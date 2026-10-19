"""scripts/precache_demo.py: record the demo analyses with a (fake) model, then replay them with no HTTP at all."""

import json

import httpx
from sqlalchemy import select

from db.models import AgentRunRow, Tender
from tests.test_orchestrator import GOOD, SchemaFake


def test_record_then_check_offline(pg_url, session_factory, tmp_path, capsys):
    from scripts.precache_demo import main

    cache = tmp_path / "llm_cache.json"
    fake = SchemaFake(GOOD)
    argv = ["--only", "001", "--cache", str(cache), "--database-url", pg_url]
    assert main([*argv, "--seed-company"], transport=httpx.MockTransport(fake.handler)) == 0
    out = capsys.readouterr().out
    assert "001  blocked" in out and "scout:ok" in out and "compliance:branched" in out
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert {e["stage"] for e in data["chat"].values()} == {"scout", "matching", "compliance"} and data["embed"]

    # Replay: --check refuses every HTTP request, so this passes only if every call is a cache hit.
    assert main([*argv, "--check"]) == 0
    out = capsys.readouterr().out
    assert "001  blocked" in out and " 0 misses" in out
    with session_factory() as s:
        tender = s.scalar(select(Tender).where(Tender.source_url.like("%/001_%")))
        assert tender.status == "blocked"
        last_run = max(r.pipeline_run_id for r in s.scalars(select(AgentRunRow)) if r.pipeline_run_id)
        replayed = s.scalars(select(AgentRunRow).where(AgentRunRow.pipeline_run_id == last_run,
                                                       AgentRunRow.model != "deterministic")).all()
        assert replayed and all(r.cached for r in replayed)


def test_check_fails_on_a_cache_miss(pg_url, tmp_path, capsys):
    from scripts.precache_demo import main

    cache = tmp_path / "llm_cache.json"
    argv = ["--only", "001", "--cache", str(cache), "--database-url", pg_url]
    assert main([*argv, "--check"]) == 1  # no cache file yet
    assert main([*argv, "--seed-company"], transport=httpx.MockTransport(SchemaFake(GOOD).handler)) == 0
    data = json.loads(cache.read_text(encoding="utf-8"))
    data["chat"] = {k: v for k, v in data["chat"].items() if v["stage"] != "matching"}
    cache.write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()
    assert main([*argv, "--check"]) == 1
    out = capsys.readouterr().out
    assert "001  failed" in out and "Cache misses" in out

"""Failure drills: Ollama dies / times out / resets, at Scout and mid-run at Matching. A run must end `failed`
with a readable error (never stay queued/running), and the tender must resume from its last good state."""

import json

import httpx
import pytest

from db.runs import make_run_recorder
from ingest.notices import RawNotice, upsert_notices
from pipeline.llm import LLMClient
from pipeline.orchestrator import resume_status, run_pipeline
from schemas import TenderStatus
from tests.conftest import bag_of_words_vector
from tests.test_matching import NOW, seed_company, settings_
from tests.test_scout import fixture_001, seed_text

ERRORS = [
    lambda r: httpx.ConnectError("connection refused", request=r),      # container killed
    lambda r: httpx.ReadTimeout("model stuck loading", request=r),      # Ollama alive but hung
    lambda r: httpx.RemoteProtocolError("server disconnected", request=r),  # killed mid-response
]


class DyingOllama:
    def __init__(self, error, alive_chats: int = 0, embed_dies: bool = False):
        self.error, self.alive_chats, self.embed_dies, self.chats = error, alive_chats, embed_dies, 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/embed":
            if self.embed_dies:
                raise self.error(request)
            body = json.loads(request.content)
            return httpx.Response(200, json={"embeddings": [bag_of_words_vector(t) for t in body["input"]]})
        self.chats += 1
        if self.chats > self.alive_chats:
            raise self.error(request)
        content = json.dumps(fixture_001(), ensure_ascii=False)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


def client(session_factory, fake) -> LLMClient:
    return LLMClient(make_run_recorder(session_factory), settings_(), transport=httpx.MockTransport(fake.handler),
                     timeout_s=0.5)


def new_tender(session_factory) -> int:
    with session_factory() as s:
        _, [tid] = upsert_notices(s, [RawNotice("seed://seed_tenders/001", seed_text("001"))])
    return tid


@pytest.mark.parametrize("error", ERRORS)
def test_ollama_dead_at_scout_fails_the_run_cleanly(session_factory, db_session, error):
    tid = new_tender(session_factory)
    run = run_pipeline(session_factory, client(session_factory, DyingOllama(error)), tid,
                       target=TenderStatus.EXTRACTED, settings=settings_(), now=NOW)
    assert run.status == "failed" and run.finished_at is not None and run.end_status == "failed"
    assert run.error.startswith("scout:") and "/api/chat" in run.error
    from db.models import Tender
    tender = db_session.get(Tender, tid)
    db_session.refresh(tender)
    assert tender.status == "failed" and resume_status(db_session, tender) is TenderStatus.NEW


@pytest.mark.parametrize("error", ERRORS)
def test_ollama_killed_mid_run_keeps_scout_result_and_resumes_at_matching(session_factory, db_session, error):
    seed_company(db_session)
    tid = new_tender(session_factory)
    fake = DyingOllama(error, alive_chats=1, embed_dies=True)  # Scout answers, then embeddings (Matching) die
    run = run_pipeline(session_factory, client(session_factory, fake), tid, target=TenderStatus.CHECKED,
                       settings=settings_(), now=NOW)
    assert run.status == "failed" and run.finished_at is not None
    assert [(s["stage"], s["status"]) for s in run.stages] == [
        ("scout", "ok"), ("matching", "failed"), ("compliance", "not_run")]
    assert run.error.startswith("matching:") and "KB retrieval failed" in run.error
    from db.models import Tender
    tender = db_session.get(Tender, tid)
    db_session.refresh(tender)
    assert tender.status == "failed" and tender.record_json is not None  # Scout's work is kept
    assert resume_status(db_session, tender) is TenderStatus.EXTRACTED
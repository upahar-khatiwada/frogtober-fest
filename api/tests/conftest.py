import hashlib
import json
import math
import os
import re
from collections.abc import Callable

import httpx
import pytest

from config import Settings
from pipeline.llm import LLMClient


@pytest.fixture
def tender_payload() -> dict:
    """A realistic municipal works notice, as the Scout LLM would return it."""
    return {
        "title": "Construction of Ward No. 4 Road Gravelling",
        "reference_no": "KMun/NCB/W/12/2083-84",
        "buyer": "Kankai Municipality",
        "buyer_address": "Surunga, Jhapa",
        "buyer_level": "local",
        "province": "koshi",
        "district": "Jhapa",
        "location": "Ward No. 4, Kankai",
        "scope": "Gravelling and drainage of 2.3 km rural road.",
        "procurement_type": "works",
        "method": "ncb",
        "evaluation_method": "lowest_evaluated",
        "language": "mixed",
        "deadline_ad": "2026-11-20T12:00:00+05:45",
        "deadline_bs_raw": "२०८३।०८।०४ १२:०० बजे",
        "deadline_bs_iso": "2083-08-04",
        "currency": "NPR",
        "estimated_cost_npr": 3430000,
        "bid_security": {"amount_npr": 102000, "percent": None, "validity_days": 120},
        "bid_validity_days": 90,
        "bid_doc_fee_npr": 3000,
        "performance_security_percent": 5,
        "domestic_preference": False,
        "jv_allowed": True,
        "required_docs": [
            {"doc_type": "company_registration", "description": "Firm registration certificate"},
            {"doc_type": "pan_vat", "description": "VAT and PAN registration certificate"},
            {
                "doc_type": "tax_clearance",
                "description": "Tax clearance of F/Y 2082/83",
                "fiscal_year_bs": "2082/83",
                "source_quote": "आ.व. २०८२/८३ को कर चुक्ता प्रमाणपत्र",
            },
        ],
        "requirements": [
            {
                "text": "Class D or above construction licence",
                "mandatory": True,
                "category": "eligibility",
                "source_quote": "Bidders must hold a valid construction licence of class D or above.",
            }
        ],
    }


@pytest.fixture
def settings() -> Settings:
    return Settings(llm_base_url="http://ollama.test", llm_model="test-model", embed_model="test-embed")


def bag_of_words_vector(text: str, dim: int = 1024) -> list[float]:
    """Deterministic stand-in for bge-m3: hashed bag of words, L2-normalised.

    Texts sharing words get a high cosine similarity, so retrieval order is testable offline.
    """
    vector = [0.0] * dim
    for word in re.findall(r"[\wऀ-ॿ]+", text.lower()):
        vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector] if any(vector) else [1.0] + [0.0] * (dim - 1)


class FakeOllama:
    """Scripted Ollama: each /api/chat call pops the next reply content.

    /api/embed returns zero vectors, or `embed_fn(text)` when given.
    """

    def __init__(
        self,
        replies: list[str] | None = None,
        embed_dim: int = 1024,
        embed_fn: Callable[[str], list[float]] | None = None,
        embed_status: int = 200,
    ) -> None:
        self.replies = list(replies or [])
        self.embed_dim = embed_dim
        self.embed_fn = embed_fn
        self.embed_status = embed_status
        self.requests: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"path": request.url.path, "body": body})
        if request.url.path == "/api/chat":
            return httpx.Response(200, json={"message": {"role": "assistant", "content": self.replies.pop(0)}})
        if request.url.path == "/api/embed":
            if self.embed_status != 200:
                return httpx.Response(self.embed_status, json={"error": "embed failed"})
            embed = self.embed_fn or (lambda _text: [0.0] * self.embed_dim)
            return httpx.Response(200, json={"embeddings": [embed(text) for text in body["input"]]})
        return httpx.Response(404)


@pytest.fixture
def make_client(settings):
    created: list[LLMClient] = []

    def _make(fake: FakeOllama, runs: list) -> LLMClient:
        client = LLMClient(runs.append, settings, transport=httpx.MockTransport(fake.handler))
        created.append(client)
        return client

    yield _make
    for client in created:
        client.close()


# --- Postgres + pgvector -----------------------------------------------------
# TEST_DATABASE_URL (a disposable DB with pgvector available) wins; otherwise an
# embedded Postgres from the `pgserver` dev dependency (bundles pgvector) is
# started for the session. DB tests skip only if neither is possible.


@pytest.fixture(scope="session")
def pg_url(tmp_path_factory) -> str:
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return
    try:
        import pgserver
    except ImportError:
        pytest.skip("no TEST_DATABASE_URL and pgserver is not installed")
    server = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="stop")
    server.psql("CREATE DATABASE tenderly_test;")
    yield server.get_uri("tenderly_test")
    server.cleanup()


def alembic_config(url: str):
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def migrated_engine(pg_url):
    from alembic import command

    from db.session import make_engine

    command.upgrade(alembic_config(pg_url), "head")
    engine = make_engine(pg_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(migrated_engine):
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from db.models import Base

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return sessionmaker(migrated_engine, expire_on_commit=False)


@pytest.fixture
def db_session(session_factory):
    with session_factory() as session:
        yield session

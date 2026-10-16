import json

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


class FakeOllama:
    """Scripted Ollama: each /api/chat call pops the next reply content."""

    def __init__(self, replies: list[str] | None = None, embed_dim: int = 1024) -> None:
        self.replies = list(replies or [])
        self.embed_dim = embed_dim
        self.requests: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"path": request.url.path, "body": body})
        if request.url.path == "/api/chat":
            return httpx.Response(200, json={"message": {"role": "assistant", "content": self.replies.pop(0)}})
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.0] * self.embed_dim for _ in body["input"]]})
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

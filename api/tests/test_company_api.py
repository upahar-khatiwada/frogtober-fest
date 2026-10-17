"""POST/GET /company and the document upload -> ingest -> retrieve flow (needs Postgres)."""

from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from db import retrieve
from deps import get_llm_client, get_session, get_sessionmaker
from main import app
from pipeline.llm import LLMClient
from tests.conftest import FakeOllama, bag_of_words_vector
from tests.test_parse_docs import make_pdf

PROFILE = {
    "name": "Demo Nirman Sewa Pvt. Ltd.",
    "sectors": ["civil works"],
    "services": "Road and drainage construction",
    "province": "gandaki",
    "pan_number": "999000111",
    "licences": [{"licence_type": "construction", "licence_class": "C", "last_renewed_fy_bs": "2083/84"}],
    "turnover": [
        {"fiscal_year_bs": "2080/81", "amount_npr": 51000000},
        {"fiscal_year_bs": "2081/82", "amount_npr": 58000000},
    ],
}


@pytest.fixture
def fake() -> FakeOllama:
    return FakeOllama(embed_fn=bag_of_words_vector)


@pytest.fixture
def api(session_factory, fake, settings):
    llm = LLMClient(lambda _run: None, settings, transport=httpx.MockTransport(fake.handler))

    def session():
        with session_factory() as s:
            yield s

    app.dependency_overrides.update(
        {get_session: session, get_sessionmaker: lambda: session_factory, get_llm_client: lambda: llm}
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
    llm.close()


def upload(api, name: str, data: bytes, doc_type: str, **form):
    return api.post("/company/documents", files={"file": (name, data)}, data={"doc_type": doc_type, **form})


def test_company_create_get_update(api, db_session):
    assert api.get("/company").status_code == 404

    created = api.post("/company", json=PROFILE)
    assert created.status_code == 200
    body = created.json()
    assert body["name"] == PROFILE["name"] and body["id"] == 1

    updated = api.post("/company", json={**PROFILE, "name": "Renamed Demo Pvt. Ltd."}).json()
    assert updated["id"] == 1
    assert api.get("/company").json()["name"] == "Renamed Demo Pvt. Ltd."

    from db import Company

    [row] = db_session.query(Company).all()
    assert row.licence_classes == ["C"]
    assert row.turnover_npr == 58000000  # latest fiscal year
    assert row.province == "gandaki" and row.pan_number == "999000111"


def test_company_rejects_unknown_fields(api):
    assert api.post("/company", json={**PROFILE, "rating": 5}).status_code == 422


def test_upload_requires_company(api):
    assert upload(api, "a.txt", b"hello", "other").status_code == 404


def test_upload_ingests_devanagari_text(api, fake):
    api.post("/company", json=PROFILE)
    text = "कर चुक्ता प्रमाणपत्र। आर्थिक वर्ष २०८१/८२। Tax clearance certificate for FY 2081/82."

    response = upload(api, "tax.txt", text.encode("utf-8"), "tax_clearance", expires_on="2026-07-16", fiscal_year_bs="2081/82")

    assert response.status_code == 202
    assert response.json()["ingest_status"] == "pending"  # ingest runs after the response
    [doc] = api.get("/company/documents").json()
    assert doc["ingest_status"] == "ready", doc["ingest_error"]
    assert doc["chunk_count"] == 1
    assert doc["doc_type"] == "tax_clearance" and doc["fiscal_year_bs"] == "2081/82"
    assert doc["expires_on"] == "2026-07-16"
    assert doc["is_expired"] is (date(2026, 7, 16) < date.today())
    [embed_call] = [r for r in fake.requests if r["path"] == "/api/embed"]
    assert embed_call["body"]["input"] == [text]  # Devanagari reached the embedder intact


def test_expiry_can_be_given_in_bs(api):
    api.post("/company", json=PROFILE)
    response = upload(api, "reg.txt", b"Registration renewed", "company_registration", expires_on_bs="2083-03-32")
    assert response.status_code == 202
    assert response.json()["expires_on"] == "2026-07-16"  # 2083 Asar 32 BS
    bad = upload(api, "reg.txt", b"x", "company_registration", expires_on="2026-07-01", expires_on_bs="2083-03-32")
    assert bad.status_code == 422


def test_scanned_pdf_is_flagged(api):
    api.post("/company", json=PROFILE)
    upload(api, "scan.pdf", make_pdf([None]), "pan_vat")
    [doc] = api.get("/company/documents").json()
    assert doc["ingest_status"] == "needs_ocr"
    assert doc["chunk_count"] == 0
    assert "OCR" in doc["ingest_error"]


def test_embedding_failure_marks_document_failed(api, fake):
    api.post("/company", json=PROFILE)
    fake.embed_status = 500
    upload(api, "a.txt", b"Some company text", "other")
    [doc] = api.get("/company/documents").json()
    assert doc["ingest_status"] == "failed"
    assert "embedding failed" in doc["ingest_error"]


def test_upload_validation(api):
    api.post("/company", json=PROFILE)
    assert upload(api, "photo.jpg", b"x", "other").status_code == 415
    assert upload(api, "a.txt", b"x", "passport").status_code == 422
    assert upload(api, "a.txt", b"x", "tax_clearance", fiscal_year_bs="2081-82").status_code == 422
    assert upload(api, "a.txt", b"", "other").status_code == 400
    assert api.get("/company/documents").json() == []


def test_uploaded_documents_are_retrievable(api, db_session, make_client):
    api.post("/company", json=PROFILE)
    upload(api, "experience.txt", b"Completed gravel road and drainage works for Demo Rural Municipality.", "experience_certificate")
    upload(api, "equipment.txt", b"We own two excavators, one vibratory roller and three tipper trucks.", "company_profile")

    client = make_client(FakeOllama(embed_fn=bag_of_words_vector), [])
    hits = retrieve(db_session, client, "excavators and roller", k=2)

    assert [h.filename for h in hits] == ["equipment.txt", "experience.txt"]
    assert hits[0].doc_type == "company_profile"

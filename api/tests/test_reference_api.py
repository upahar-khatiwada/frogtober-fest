"""GET /rules and GET /chunks (the latter needs Postgres)."""

import pytest
from fastapi.testclient import TestClient

from deps import get_session
from main import app
from schemas import DocType
from tests.test_db import add_company, add_doc, unit


@pytest.fixture
def api(session_factory):
    def session():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_rules_expose_description_and_verified_flag():
    rules = {r["id"]: r for r in TestClient(app).get("/rules").json()}
    assert rules["NP-TAX-CLEARANCE"]["verified"] is True and rules["NP-TAX-CLEARANCE"]["severity"] == "hard"
    assert rules["NP-TURNOVER"]["verified"] is False
    assert rules["NP-DEADLINE"]["description"] and rules["NP-DEADLINE"]["source"].startswith("http")


def test_chunks_return_text_document_and_expiry(api, db_session):
    company = add_company(db_session)
    doc = add_doc(db_session, company, DocType.TAX_CLEARANCE, chunks=[("Tax clearance FY 2081/82", unit(0)), ("second", unit(1))])
    first, second = (c.id for c in doc.chunks)

    rows = api.get("/chunks", params={"ids": [second, first, 99999]}).json()

    assert [r["chunk_id"] for r in rows] == [first, second]  # ordered by id, unknown id omitted
    assert rows[0]["content"] == "Tax clearance FY 2081/82"
    assert rows[0]["filename"] == "tax_clearance.txt" and rows[0]["doc_type"] == "tax_clearance"
    assert rows[0]["expires_on"] is None and rows[0]["is_expired"] is None


def test_chunks_require_ids(api):
    assert api.get("/chunks").status_code == 422
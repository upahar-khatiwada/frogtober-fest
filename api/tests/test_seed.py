"""The demo seed loads every document and gives the compliance demo one expired + one valid doc."""

from datetime import date

from sqlalchemy import select

from db import Company, Document, retrieve
from scripts.seed_demo import DEFAULT_DATA_DIR, seed
from tests.conftest import FakeOllama, bag_of_words_vector


def test_seed_demo_company(pg_url, session_factory, db_session, make_client):
    client = make_client(FakeOllama(embed_fn=bag_of_words_vector), [])

    results = seed(DEFAULT_DATA_DIR, pg_url, client)
    assert set(results.values()) == {"ready"}, results
    assert seed(DEFAULT_DATA_DIR, pg_url, client) == results  # idempotent

    [company] = db_session.scalars(select(Company)).all()
    assert "Demo" in company.name
    assert company.licence_classes == ["C"] and company.province == "gandaki"

    docs = {d.filename: d for d in db_session.scalars(select(Document))}
    assert len(docs) == 6
    today = date(2026, 10, 17)
    tax = docs["03_tax_clearance_2081-82.pdf"]
    assert tax.doc_type == "tax_clearance" and tax.fiscal_year_bs == "2081/82"
    assert tax.expires_on == date(2026, 7, 16) and tax.expires_on < today  # expired
    reg = docs["01_company_registration.txt"]
    assert reg.expires_on == date(2027, 7, 16) and reg.expires_on > today  # valid
    assert "अन्नपूर्ण" in reg.raw_text
    assert docs["04_experience_certificate.docx"].value_npr == 18540000

    [hit] = retrieve(db_session, client, "hydraulic excavators vibratory roller tipper trucks equipment", k=1)
    assert hit.filename == "05_company_profile.pdf"

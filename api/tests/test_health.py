from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_openapi_exposes_stage_contracts():
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("TenderRecord", "TenderDetail", "CompanyProfile", "MatchResult", "ComplianceView", "ComplianceItem",
                 "ComplianceOverrideRequest",
                 "Proposal", "ProposalSection", "ReviewReport", "AgentRun"):
        assert name in schemas

# The proposal route (still 501 behind the compliance gate) is tested with a DB in tests/test_compliance_api.py.

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_openapi_exposes_stage_contracts():
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("TenderRecord", "TenderDetail", "CompanyProfile", "MatchResult", "ComplianceReport",
                 "Proposal", "ProposalSection", "ReviewReport", "AgentRun"):
        assert name in schemas


def test_stub_routes_still_return_501():
    assert client.post("/tenders/1/proposal").status_code == 501

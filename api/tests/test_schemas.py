import json

import pytest
from pydantic import ValidationError

from schemas import (
    CompanyProfile,
    ComplianceAssessment,
    ComplianceItem,
    ComplianceReport,
    MatchAssessment,
    MatchDecision,
    MatchResult,
    ProposalSection,
    ReviewReport,
    TenderRecord,
)


# --- valid outputs parse ---


def test_tender_record_parses_from_llm_json(tender_payload):
    record = TenderRecord.model_validate_json(json.dumps(tender_payload), strict=True)
    assert record.province == "koshi"
    assert record.bid_security.amount_npr == 102000
    assert record.required_docs[2].fiscal_year_bs == "2082/83"
    assert record.currency == "NPR"


def test_tender_record_minimal_defaults():
    record = TenderRecord.model_validate(
        {
            "title": "Supply of laptops",
            "buyer": "Nepal Electricity Authority",
            "buyer_level": "federal",
            "scope": "20 laptops",
            "procurement_type": "goods",
            "method": "quotation",
            "language": "en",
        }
    )
    assert record.currency == "NPR"
    assert record.jv_allowed is None
    assert record.required_docs == []


def test_company_profile_parses():
    profile = CompanyProfile.model_validate(
        {
            "name": "Himal Builders Pvt. Ltd.",
            "pan_number": "601234567",
            "vat_number": None,
            "registration_date": "2015-03-10",
            "licences": [{"licence_type": "construction", "licence_class": "C", "last_renewed_fy_bs": "2083/84"}],
            "turnover": [
                {"fiscal_year_bs": "2081/82", "amount_npr": 45000000},
                {"fiscal_year_bs": "2082/83", "amount_npr": 52000000},
            ],
            "jv_partners": [{"name": "Sagarmatha Engineering"}],
            "districts_served": ["Jhapa", "Morang"],
        }
    )
    assert profile.licences[0].licence_class == "C"
    assert profile.turnover[1].amount_npr == 52_000_000


def test_match_decision_is_deterministic():
    assessment = MatchAssessment.model_validate_json('{"score": 59, "reasons": ["Sector fits"]}', strict=True)
    assert MatchResult.from_assessment(assessment, threshold=60).decision is MatchDecision.SKIP
    assert MatchResult.from_assessment(assessment, threshold=59).decision is MatchDecision.PURSUE


def test_compliance_report_blocks_on_hard_failure():
    assessment = ComplianceAssessment.model_validate_json(
        json.dumps({"status": "pass", "evidence_chunk_ids": [12], "evidence_quote": "Class C construction licence no. 1234",
                    "explanation": "The licence is class C, above D."}),
        strict=True,
    )
    model_item = ComplianceItem(requirement="Class D licence", severity="hard", source="model",
                                **assessment.model_dump(exclude={"explanation"}))
    deadline_rule = ComplianceItem(
        requirement="Submission deadline not passed",
        status="fail",
        severity="hard",
        source="rule",
        rule_id="NP-DEADLINE",
    )
    soft = ComplianceItem(requirement="Performance security", status="fail", severity="soft", source="rule", rule_id="NP-X")
    report = ComplianceReport(items=[model_item, deadline_rule, soft])
    assert report.is_blocked
    assert report.hard_failures == [deadline_rule]
    assert not ComplianceReport(items=[model_item, soft]).is_blocked


def test_proposal_section_and_review_parse():
    section = ProposalSection.model_validate_json(
        '{"title": "Relevant experience", "body": "We built ...", "cited_chunk_ids": [3, 7]}', strict=True
    )
    assert section.cited_chunk_ids == [3, 7]
    review = ReviewReport.model_validate_json(
        json.dumps(
            {
                "scores": {"completeness": 80, "relevance": 75, "compliance": 90},
                "gaps": [{"section_title": None, "issue": "No work schedule", "severity": "soft"}],
                "verdict": "pass",
            }
        ),
        strict=True,
    )
    assert review.verdict == "pass"


# --- Nepal enum and contract fields reject bad values ---


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("procurement_type", "construction"),
        ("method", "open_tender"),
        ("buyer_level", "municipal"),
        ("province", "Province No. 1"),
        ("language", "nepali"),
        ("evaluation_method", "cheapest"),
        ("currency", "Rs"),
        ("deadline_bs_iso", "2083-13-01"),
        ("deadline_bs_iso", "२०८३-०८-०४"),
        ("estimated_cost_npr", -5),
        ("estimated_cost_npr", "34 lakh"),
    ],
)
def test_tender_record_rejects_bad_values(tender_payload, field, bad):
    tender_payload[field] = bad
    with pytest.raises(ValidationError):
        TenderRecord.model_validate_json(json.dumps(tender_payload), strict=True)


def test_required_doc_rejects_unknown_doc_type(tender_payload):
    tender_payload["required_docs"][0]["doc_type"] = "citizenship"
    with pytest.raises(ValidationError):
        TenderRecord.model_validate(tender_payload)


@pytest.mark.parametrize("fy", ["2082-83", "2082/84", "82/83", "2082/2083"])
def test_fiscal_year_must_be_consecutive_bs_years(tender_payload, fy):
    tender_payload["required_docs"][2]["fiscal_year_bs"] = fy
    with pytest.raises(ValidationError):
        TenderRecord.model_validate(tender_payload)


def test_unknown_fields_are_rejected(tender_payload):
    tender_payload["confidence"] = 0.9
    with pytest.raises(ValidationError):
        TenderRecord.model_validate(tender_payload)


def test_bid_security_needs_amount_or_percent(tender_payload):
    tender_payload["bid_security"] = {"amount_npr": None, "percent": None, "validity_days": 120}
    with pytest.raises(ValidationError):
        TenderRecord.model_validate(tender_payload)


def test_contractor_class_rejects_bad_value():
    with pytest.raises(ValidationError):
        CompanyProfile.model_validate({"name": "X", "licences": [{"licence_type": "construction", "licence_class": "E"}]})


def test_llm_pass_without_chunk_id_is_rejected():
    """Hard rule 8: evidence without a chunk id must be 'unclear', never 'pass'."""
    for status in ("pass", "fail"):  # a decision either way needs a cited chunk
        with pytest.raises(ValidationError):
            ComplianceAssessment.model_validate({"status": status, "explanation": "PAN certificate seen"})
    assert ComplianceAssessment.model_validate({"status": "unclear", "explanation": "nothing in the KB"})
    with pytest.raises(ValidationError):  # code-built items: a pass needs a chunk or a document record
        ComplianceItem(requirement="PAN", status="pass", severity="hard", source="model")
    with pytest.raises(ValidationError):  # a rule may cite the notice, but not a profile field, on its own
        ComplianceItem(requirement="JV", status="pass", severity="soft", source="rule", rule_id="NP-JV",
                       evidence_ref="company.jv_partners")
    assert ComplianceItem(requirement="Deadline", status="pass", severity="hard", source="rule", rule_id="NP-DEADLINE",
                          evidence_ref="tender.deadline")
    assert ComplianceItem(requirement="PAN", status="pass", severity="hard", source="rule", rule_id="NP-PAN-VAT",
                          evidence_document_ids=[2])


def test_llm_cannot_claim_a_rule_id_or_choose_severity():
    base = {"status": "pass", "evidence_chunk_ids": [1], "evidence_quote": "PAN 999", "explanation": "PAN seen"}
    assert ComplianceAssessment.model_validate(base)
    for extra in ({"rule_id": "NP-PAN"}, {"severity": "soft"}, {"requirement": "PAN"}):
        with pytest.raises(ValidationError):
            ComplianceAssessment.model_validate(base | extra)
    with pytest.raises(ValidationError):  # and a model item cannot carry one either
        ComplianceItem(requirement="PAN", status="unclear", severity="hard", source="model", rule_id="NP-PAN")


def test_proposal_section_must_cite_chunks():
    with pytest.raises(ValidationError):
        ProposalSection.model_validate({"title": "Approach", "body": "We will...", "cited_chunk_ids": []})

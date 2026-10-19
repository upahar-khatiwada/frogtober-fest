from datetime import date, datetime

import pytest

from nepal.dates import NPT
from nepal.rules import CHECKS, DocumentMeta, TenderCriteria, calc_bid_security, calc_performance_security, evaluate_rules, load_rules
from schemas import (AnnualTurnover, BidSecurity, CompanyProfile, ContractorLicence, DocType, JVPartner, ProcurementType,
                     RequiredDoc, TenderRecord)

NOW = datetime(2026, 10, 17, 22, 35, tzinfo=NPT)  # tender deadline in the fixture: 2026-11-20 12:00 NPT (F/Y 2083/84)
T = DocType
CRITERIA = TenderCriteria(min_avg_turnover_npr=30_000_000, turnover_years=3, min_similar_projects=2, min_similar_value_npr=1_500_000)


def D(t, chunk=1, **kw):
    return DocumentMeta(doc_type=t, chunk_id=chunk, **kw)


@pytest.fixture
def tender(tender_payload):
    return TenderRecord.model_validate(tender_payload)


@pytest.fixture
def company():
    return CompanyProfile(
        name="Himal Builders", pan_number="601234567",
        licences=[ContractorLicence(licence_type="construction", licence_class="C", last_renewed_fy_bs="2083/84")],
        turnover=[AnnualTurnover(fiscal_year_bs=fy, amount_npr=a) for fy, a in
                  (("2080/81", 30_000_000), ("2081/82", 40_000_000), ("2082/83", 50_000_000))],
        jv_partners=[JVPartner(name="Sagarmatha Engineering")],
    )


@pytest.fixture
def docs():
    return [
        D(T.COMPANY_REGISTRATION, 1), D(T.BUSINESS_LICENCE, 2), D(T.SELF_DECLARATION, 3), D(T.PAN_VAT, 4),
        D(T.TAX_CLEARANCE, 5, fiscal_year_bs="2082/83"), D(T.LICENCE_RENEWAL, 6),
        *[D(T.AUDIT_REPORT, 7 + i, fiscal_year_bs=fy) for i, fy in enumerate(("2080/81", "2081/82", "2082/83"))],
        D(T.EXPERIENCE_CERTIFICATE, 10, similar=True, value_npr=2_000_000),
        D(T.EXPERIENCE_CERTIFICATE, 11, similar=True, value_npr=3_000_000),
        D(T.BID_SECURITY, 12, value_npr=102_000, expiry=date(2027, 3, 25)),
    ]


def run(tender, company, docs, criteria=CRITERIA, **kw):
    kw.setdefault("now", NOW)
    return {i.rule_id: i for i in evaluate_rules(tender, company, docs, criteria=criteria, **kw)}


def without(docs, *types):
    return [d for d in docs if d.doc_type not in types]


def st(res, rule_id):
    return res[rule_id].status.value if rule_id in res else None


# --- rules file ---------------------------------------------------------------

def test_rules_file_is_well_formed():
    rules = load_rules()
    assert len({r.id for r in rules}) == len(rules)
    assert all(r.check in CHECKS and r.source.startswith("http") for r in rules)
    unverified = {r.id for r in rules if not r.verified}
    assert {"NP-LICENCE-RENEWAL", "NP-TURNOVER", "NP-EXPERIENCE", "NP-DOMESTIC-PREF"} <= unverified
    assert next(r for r in rules if r.id == "NP-LICENCE-RENEWAL").severity.value == "soft"


def test_baseline_all_pass(tender, company, docs):
    res = run(tender, company, docs)
    assert {k: v.status.value for k, v in res.items()} == {
        "NP-DEADLINE": "pass", "NP-REG-DOCS": "pass", "NP-BID-FORMS": "pass", "NP-PAN-VAT": "pass", "NP-TAX-CLEARANCE": "pass",
        "NP-LICENCE-RENEWAL": "pass", "NP-TURNOVER": "pass", "NP-EXPERIENCE": "pass", "NP-BID-SECURITY": "pass",
        "NP-PERF-SECURITY": "unclear",
    }
    assert "[rule unverified" in res["NP-TURNOVER"].explanation and "[rule unverified" not in res["NP-DEADLINE"].explanation


def test_never_pass_without_evidence(tender, company, docs):
    stripped = [d.model_copy(update={"chunk_id": None}) for d in docs]
    for res in (run(tender, company, docs), run(tender, company, stripped)):
        for item in res.values():
            if item.status.value == "pass":
                assert item.evidence_chunk_ids or "Evidence:" in item.explanation, item.rule_id
    res = run(tender, company, stripped)
    for rid in ("NP-REG-DOCS", "NP-PAN-VAT", "NP-TAX-CLEARANCE", "NP-TURNOVER", "NP-EXPERIENCE", "NP-BID-SECURITY"):
        assert st(res, rid) == "unclear", rid


# --- deadline -------------------------------------------------------------------

def test_deadline(tender, company, docs):
    assert st(run(tender, company, docs, now=datetime(2026, 11, 21, tzinfo=NPT)), "NP-DEADLINE") == "fail"
    assert st(run(tender, company, docs, now=datetime(2026, 11, 20, 11, 59, tzinfo=NPT)), "NP-DEADLINE") == "pass"
    assert st(run(tender, company, docs, now=datetime(2026, 11, 20, 12, 1, tzinfo=NPT)), "NP-DEADLINE") == "fail"
    tender.deadline_ad = tender.deadline_bs_raw = tender.deadline_bs_iso = None
    assert st(run(tender, company, docs), "NP-DEADLINE") == "unclear"


def test_deadline_falls_back_to_bs(tender, company, docs):
    tender.deadline_ad = None  # raw BS "२०८३।०८।०४ १२:०० बजे"
    assert st(run(tender, company, docs), "NP-DEADLINE") == "pass"


# --- registration docs / PAN / tax -----------------------------------------------

def test_reg_docs(tender, company, docs):
    assert st(run(tender, company, without(docs, T.BUSINESS_LICENCE)), "NP-REG-DOCS") == "fail"
    expired = [d.model_copy(update={"expiry": date(2026, 11, 1)}) if d.doc_type is T.COMPANY_REGISTRATION else d for d in docs]
    assert st(run(tender, company, expired), "NP-REG-DOCS") == "fail"
    res = run(tender, company, without(docs, T.BUSINESS_LICENCE))
    assert "business/construction licence" in res["NP-REG-DOCS"].action_needed


def test_bid_forms_are_never_a_fail(tender, company, docs):
    """Self-declaration / power of attorney are signed per bid: missing from the KB is unclear + an action, not a block."""
    res = run(tender, company, without(docs, T.SELF_DECLARATION))
    assert st(res, "NP-BID-FORMS") == "unclear" and "Prepare and sign the self-declaration" in res["NP-BID-FORMS"].action_needed
    assert st(res, "NP-REG-DOCS") == "pass"
    tender.required_docs.append(RequiredDoc(doc_type=T.POWER_OF_ATTORNEY, description="Power of attorney"))
    items = [i for i in evaluate_rules(tender, company, docs, criteria=CRITERIA, now=NOW) if i.rule_id == "NP-BID-FORMS"]
    assert [(i.requirement.split(" (")[0], i.status.value) for i in items] == [("Self-declaration", "pass"), ("Power of attorney", "unclear")]


def test_pan_vat(tender, company, docs):
    assert st(run(tender, company, without(docs, T.PAN_VAT)), "NP-PAN-VAT") == "fail"
    company.pan_number = "  "
    assert st(run(tender, company, docs), "NP-PAN-VAT") == "fail"


def test_tax_clearance(tender, company, docs):
    assert st(run(tender, company, without(docs, T.TAX_CLEARANCE)), "NP-TAX-CLEARANCE") == "fail"
    wrong = [d.model_copy(update={"fiscal_year_bs": "2081/82"}) if d.doc_type is T.TAX_CLEARANCE else d for d in docs]
    res = run(tender, company, wrong)
    assert st(res, "NP-TAX-CLEARANCE") == "fail" and "2081/82" in res["NP-TAX-CLEARANCE"].explanation
    ret = [d.model_copy(update={"doc_type": T.TAX_RETURN}) if d.doc_type is T.TAX_CLEARANCE else d for d in docs]
    assert st(run(tender, company, ret), "NP-TAX-CLEARANCE") == "pass"
    tender.required_docs[2].fiscal_year_bs = None
    assert st(run(tender, company, docs), "NP-TAX-CLEARANCE") == "unclear"


# --- licence ---------------------------------------------------------------------

def test_licence_renewal(tender, company, docs):
    company.licences[0].last_renewed_fy_bs = "2082/83"
    assert st(run(tender, company, docs), "NP-LICENCE-RENEWAL") == "fail"
    company.licences[0].last_renewed_fy_bs = None
    assert st(run(tender, company, docs), "NP-LICENCE-RENEWAL") == "unclear"
    company.licences = []
    assert st(run(tender, company, docs), "NP-LICENCE-RENEWAL") == "fail"


def test_licence_rule_only_for_works(tender, company, docs):
    tender.procurement_type = ProcurementType.GOODS
    assert "NP-LICENCE-RENEWAL" not in run(tender, company, docs)


def test_licence_renewal_doc_expired(tender, company, docs):
    old = [d.model_copy(update={"expiry": date(2026, 7, 1)}) if d.doc_type is T.LICENCE_RENEWAL else d for d in docs]
    assert st(run(tender, company, old), "NP-LICENCE-RENEWAL") == "fail"


# --- turnover / experience -----------------------------------------------------------

def test_turnover(tender, company, docs):
    low = TenderCriteria(min_avg_turnover_npr=41_000_000, turnover_years=3)
    assert st(run(tender, company, docs, criteria=low), "NP-TURNOVER") == "fail"  # avg is 40M
    assert st(run(tender, company, docs, criteria=TenderCriteria(min_avg_turnover_npr=40_000_000, turnover_years=3)), "NP-TURNOVER") == "pass"
    assert st(run(tender, company, docs, criteria=TenderCriteria(min_avg_turnover_npr=1, turnover_years=5)), "NP-TURNOVER") == "unclear"
    assert st(run(tender, company, docs, criteria=TenderCriteria(min_avg_turnover_npr=1)), "NP-TURNOVER") == "unclear"
    assert st(run(tender, company, without(docs, T.AUDIT_REPORT)), "NP-TURNOVER") == "unclear"


def test_turnover_ignores_current_fiscal_year(tender, company, docs):
    company.turnover.append(AnnualTurnover(fiscal_year_bs="2083/84", amount_npr=1))  # in-progress year
    assert st(run(tender, company, docs), "NP-TURNOVER") == "pass"


def test_criteria_missing(tender, company, docs):
    assert "NP-TURNOVER" not in run(tender, company, docs, criteria=TenderCriteria())
    from schemas import Requirement
    tender.requirements.append(Requirement(text="Turnover", mandatory=True, category="financial", source_quote="avg turnover"))
    assert st(run(tender, company, docs, criteria=TenderCriteria()), "NP-TURNOVER") == "unclear"


def test_experience(tender, company, docs):
    one = [d for d in docs if not (d.doc_type is T.EXPERIENCE_CERTIFICATE and d.chunk_id == 11)]
    assert st(run(tender, company, one), "NP-EXPERIENCE") == "fail"
    small = [d.model_copy(update={"value_npr": 1_000_000}) if d.chunk_id == 11 else d for d in docs]
    assert st(run(tender, company, small), "NP-EXPERIENCE") == "fail"  # below the notice's minimum value
    unclassified = [d.model_copy(update={"similar": None}) if d.chunk_id == 11 else d for d in docs]
    assert st(run(tender, company, unclassified), "NP-EXPERIENCE") == "unclear"


# --- bid / performance security ------------------------------------------------------

def test_bid_security_calc(tender):
    calc = calc_bid_security(tender)
    assert calc.amount_npr == 102_000 and calc.valid_until == date(2027, 3, 20) and calc.valid_until_bs
    tender.bid_security = BidSecurity(percent=2.5, validity_days=120)
    assert calc_bid_security(tender).amount_npr == 85_750  # 2.5% of the 34.3 lakh estimate
    assert calc_bid_security(tender, bid_price_npr=1_000_001).amount_npr == 25_001  # rounded up
    tender.estimated_cost_npr = None
    assert calc_bid_security(tender).amount_npr is None
    tender.bid_security = None
    assert calc_bid_security(tender).amount_npr is None


def test_bid_security_validity_needs_deadline(tender):
    tender.deadline_ad = tender.deadline_bs_raw = tender.deadline_bs_iso = None
    assert calc_bid_security(tender).valid_until is None


def test_performance_security_calc(tender):
    assert calc_performance_security(tender).amount_npr == 171_500  # 5% of 34.3 lakh
    assert calc_performance_security(tender, contract_price_npr=1_000_000).amount_npr == 50_000
    tender.performance_security_percent = None
    assert calc_performance_security(tender).amount_npr is None


def test_bid_security_check(tender, company, docs):
    assert st(run(tender, company, without(docs, T.BID_SECURITY)), "NP-BID-SECURITY") == "unclear"
    short = [d.model_copy(update={"expiry": date(2027, 3, 19)}) if d.doc_type is T.BID_SECURITY else d for d in docs]
    assert st(run(tender, company, short), "NP-BID-SECURITY") == "fail"
    small = [d.model_copy(update={"value_npr": 101_999}) if d.doc_type is T.BID_SECURITY else d for d in docs]
    assert st(run(tender, company, small), "NP-BID-SECURITY") == "fail"
    tender.bid_security = None
    assert "NP-BID-SECURITY" not in run(tender, company, docs)


def test_performance_security_item_is_never_pass(tender, company, docs):
    assert st(run(tender, company, docs), "NP-PERF-SECURITY") == "unclear"
    tender.performance_security_percent = None
    assert "NP-PERF-SECURITY" not in run(tender, company, docs)


# --- JV / domestic ---------------------------------------------------------------------

def test_jv(tender, company, docs):
    assert "NP-JV" not in run(tender, company, docs)  # nothing failed
    company.turnover = [AnnualTurnover(fiscal_year_bs=fy, amount_npr=10_000_000) for fy in ("2080/81", "2081/82", "2082/83")]
    res = run(tender, company, docs)
    assert st(res, "NP-TURNOVER") == "fail" and st(res, "NP-JV") == "unclear"  # partner on profile only: no evidence
    assert "Sign a JV agreement with Sagarmatha Engineering" in res["NP-JV"].action_needed
    res = run(tender, company, [*docs, D(T.JV_AGREEMENT, 30, document_id=30)])
    assert st(res, "NP-JV") == "pass" and res["NP-JV"].evidence_document_ids == [30] and res["NP-JV"].action_needed is None
    company.jv_partners = []
    assert st(run(tender, company, docs), "NP-JV") == "fail"
    company.jv_partners = [JVPartner(name="X")]
    tender.jv_allowed = False
    assert st(run(tender, company, docs), "NP-JV") == "fail"
    tender.jv_allowed = None
    assert st(run(tender, company, docs), "NP-JV") == "unclear"


def test_domestic_preference(tender, company, docs):
    assert "NP-DOMESTIC-PREF" not in run(tender, company, docs)
    tender.domestic_preference = True
    assert st(run(tender, company, docs), "NP-DOMESTIC-PREF") == "unclear"


def test_naive_now_rejected(tender, company, docs):
    with pytest.raises(ValueError):
        evaluate_rules(tender, company, docs, now=datetime(2026, 10, 17))

# --- expiry vs deadline and bid validity / actions / evidence (Prompt 7) ------------------

def test_tax_clearance_expired_document_is_hard_fail_with_action(tender, company, docs):
    """The demo case: only an FY 2081/82 clearance on file, expired before the deadline; the notice asks for 2082/83."""
    old = [d.model_copy(update={"fiscal_year_bs": "2081/82", "expiry": date(2026, 7, 16), "document_id": 3})
           if d.doc_type is T.TAX_CLEARANCE else d for d in docs]
    item = run(tender, company, old)["NP-TAX-CLEARANCE"]
    assert (item.status.value, item.severity.value) == ("fail", "hard")
    assert "F/Y 2081/82 (expired 2026-07-16)" in item.explanation and item.evidence_document_ids == [3]
    assert item.action_needed.startswith("Renew tax clearance for F/Y 2082/83")
    # Right FY, but expired before the deadline: still a hard fail.
    tender.required_docs[2].fiscal_year_bs = "2081/82"
    item = run(tender, company, old)["NP-TAX-CLEARANCE"]
    assert item.status.value == "fail" and "expired on 2026-07-16" in item.explanation


def test_document_lapsing_during_bid_validity(tender, company, docs):
    """Deadline 2026-11-20 + 90 days bid validity = 2027-02-18."""
    lapsing = [d.model_copy(update={"expiry": date(2027, 1, 10), "document_id": 1}) if d.doc_type is T.COMPANY_REGISTRATION
               else d for d in docs]
    res = run(tender, company, lapsing)
    item = res["NP-DOC-VALIDITY"]
    assert (item.status.value, item.severity.value) == ("unclear", "soft") and item.evidence_document_ids == [1]
    assert "Renew the company registration certificate before 2027-01-10" in item.action_needed
    assert st(res, "NP-REG-DOCS") == "pass"  # valid at the deadline
    ok = [d.model_copy(update={"expiry": date(2027, 7, 16)}) if d.doc_type is T.COMPANY_REGISTRATION else d for d in docs]
    assert st(run(tender, company, ok), "NP-DOC-VALIDITY") == "pass"
    tender.bid_validity_days = None
    assert "NP-DOC-VALIDITY" not in run(tender, company, lapsing)
    assert "NP-DOC-VALIDITY" not in run(tender, company, docs)  # no dated eligibility documents


def test_other_notice_documents_are_listed_not_judged(tender, company, docs):
    tender.required_docs.append(RequiredDoc(doc_type=T.OTHER, description="Bid document fee payment voucher"))
    item = run(tender, company, docs)["NP-OTHER-DOCS"]
    assert item.status.value == "unclear" and "payment voucher" in item.action_needed


def test_every_non_pass_rule_item_has_an_action(tender, company, docs):
    stripped = [d.model_copy(update={"chunk_id": None}) for d in docs]
    company.turnover = [AnnualTurnover(fiscal_year_bs="2082/83", amount_npr=1)]
    tender.domestic_preference = True
    for item in evaluate_rules(tender, company, stripped, criteria=CRITERIA, now=NOW):
        assert item.source.value == "rule"
        assert (item.action_needed is None) == (item.status.value == "pass"), item.rule_id


def test_profile_alone_is_not_evidence_for_licence(tender, company, docs):
    res = run(tender, company, without(docs, T.LICENCE_RENEWAL, T.BUSINESS_LICENCE))
    assert st(res, "NP-LICENCE-RENEWAL") == "unclear" and "Upload the construction licence" in res["NP-LICENCE-RENEWAL"].action_needed
    licence = D(T.BUSINESS_LICENCE, 40, fiscal_year_bs="2083/84")
    assert st(run(tender, company, [*without(docs, T.LICENCE_RENEWAL), licence]), "NP-LICENCE-RENEWAL") == "pass"

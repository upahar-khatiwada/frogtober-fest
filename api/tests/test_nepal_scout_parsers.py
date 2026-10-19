"""Deterministic parsers added for Scout: deadlines, compound/mis-grouped amounts, percent, days, documents."""

import json
from datetime import date, datetime, time
from pathlib import Path

import pytest

from nepal.dates import NPT, BSDate, bs_to_ad, parse_bs_date, parse_deadline
from nepal.documents import classify_document, find_fiscal_years
from nepal.numbers import has_thousands_marker, parse_days, parse_npr, parse_percent
from schemas import DocType

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed_tenders"


# --- parse_deadline ------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "bs", "ad", "hm"),
    [
        # Prompt 5a open issue 30: these failed in deadline_from_raw
        ("12:00 hours on 2083-08-05 B.S. (2026-11-21 A.D.)", "2083-08-05", date(2026, 11, 21), (12, 0)),
        ("२०८३।०८।०३ गते दिनको १२ बजेसम्म", "2083-08-03", date(2026, 11, 19), (12, 0)),
        ("15/08/2083 by 12 noon", "2083-08-15", date(2026, 12, 1), (12, 0)),
        # AD-only notices: BS comes from the lookup table
        ("December 14, 2026, 12:00 hours Nepal Standard Time", "2083-08-28", date(2026, 12, 14), (12, 0)),
        ("30 November 2026", "2083-08-14", date(2026, 11, 30), None),
        ("2 December 2026 at 13:00", "2083-08-16", date(2026, 12, 2), (13, 0)),
        # Nepali day-part words: "दिनको २:०० बजे" is 2 pm
        ("२०८३।०७।२८ गते दिनको २:०० बजे", "2083-07-28", None, (14, 0)),
        ("२०८३/०८/१० गते दिनको १२:०० बजेसम्म", "2083-08-10", None, (12, 0)),
        ("१५ असोज २०८३", "2083-06-15", None, None),
        ("Kartik 28, 2083 2 PM", "2083-07-28", None, (14, 0)),
        ("12 noon on 2083-08-15 B.S.", "2083-08-15", None, (12, 0)),
    ],
)
def test_parse_deadline_reads(raw, bs, ad, hm):
    p = parse_deadline(raw)
    assert p.issues == ()
    assert p.bs.iso() == bs
    want_ad = ad or bs_to_ad(parse_bs_date(bs))
    assert p.ad == want_ad
    assert p.deadline == datetime.combine(want_ad, time(*hm) if hm else time(23, 59, 59), tzinfo=NPT)


@pytest.mark.parametrize(
    ("raw", "issue"),
    [
        ("2083-08-05 B.S. (2026-11-22 A.D.)", "but the text says AD"),  # BS and AD disagree
        ("२०८३/०७/१० को सट्टा २०८३/०७/२५ दिनको १२:०० बजेसम्म", "several BS dates"),  # corrigendum: old + new
        ("within 15 days of publication", "no date found"),
        ("2083-02-33", "invalid BS date"),
        ("05/06/2026", "day/month or month/day"),
        ("2083-08-05 12:00 and opening 14:00", "several times of day"),
    ],
)
def test_parse_deadline_never_guesses(raw, issue):
    p = parse_deadline(raw)
    assert p.deadline is None
    assert any(issue in i for i in p.issues), p.issues


def test_parse_deadline_matches_every_seed_label():
    """Every labelled deadline quote in the seed manifest parses to its labelled BS (and AD) date."""
    manifest = json.loads((SEED_DIR / "manifest.json").read_text(encoding="utf-8"))
    checked = 0
    for n in manifest["notices"]:
        e = n["expected"]
        if not e["deadline_quote"]:
            continue
        p = parse_deadline(e["deadline_quote"])
        assert p.issues == (), (n["id"], p.issues)
        assert p.bs.iso() == e["deadline_bs"], n["id"]
        if e["deadline_ad"]:
            assert p.ad == date.fromisoformat(e["deadline_ad"]), n["id"]
        checked += 1
    assert checked >= 30


# --- amounts ----------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "npr"),
    [
        ("रु. ३२ लाख ५० हजार", 3_250_000),  # compound (issue 30)
        ("Rs 1 crore 25 lakh", 12_500_000),
        ("NPR 2,400 million", 2_400_000_000),  # western grouping
        ("NPR 48,000,000", 48_000_000),
        ("Rs. 1,48,75,000/-", 14_875_000),  # lakh grouping
        ("4850", 4850),
    ],
)
def test_parse_npr_compound_and_grouping(text, npr):
    assert parse_npr(text) == npr


@pytest.mark.parametrize("text", ["Rs. 1,50,000,00 (Rupees Fifteen Lakh only)", "Rs 1,2,3", "5 thousand 3 lakh", "32 lakh 50"])
def test_parse_npr_rejects_misgrouped_and_odd_compounds(text):
    with pytest.raises(ValueError):
        parse_npr(text)


def test_percent_days_thousands():
    assert parse_percent("कबोल अङ्कको २.५ प्रतिशत नगद") == 2.5
    assert parse_percent("5% of the contract price") == 5.0
    assert parse_days("valid for at least 150 days from the bid submission deadline") == 150
    assert parse_days("कम्तीमा १२० दिन मान्य") == 120
    assert parse_days("90 (ninety) days") == 90
    assert has_thousands_marker("लागत अनुमान (रु. हजारमा)")
    assert not has_thousands_marker("Rs. 3,000 thousand-fold")  # only the stated-in-thousands phrasings
    for bad, fn in (("2.5% or 3%", parse_percent), ("120%", parse_percent), ("30 days or 60 days", parse_days), ("soon", parse_days)):
        with pytest.raises(ValueError):
            fn(bad)


# --- documents ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "types"),
    [
        ("VAT and PAN registration certificate", [DocType.PAN_VAT]),
        ("Valid firm/company registration certificate", [DocType.COMPANY_REGISTRATION]),
        ("construction licence of Class \"D\" or above, renewed for F/Y 2083/84", [DocType.BUSINESS_LICENCE, DocType.LICENCE_RENEWAL]),
        ("Tax clearance certificate of F/Y 2082/83, or evidence of tax return", [DocType.TAX_CLEARANCE, DocType.TAX_RETURN]),
        ("फर्म दर्ता, मू.अ.कर/स्थायी लेखा नम्बर दर्ता, आ.व. २०८२/८३ को कर चुक्ता प्रमाणपत्र",
         [DocType.COMPANY_REGISTRATION, DocType.PAN_VAT, DocType.TAX_CLEARANCE]),
        ("इजाजतपत्र", [DocType.BUSINESS_LICENCE]),
        ("स्वघोषणा पत्र", [DocType.SELF_DECLARATION]),
        ("Power of attorney of the signatory", [DocType.POWER_OF_ATTORNEY]),
        ("A registered JV agreement", [DocType.JV_AGREEMENT]),
        ("Audited financial statements", [DocType.AUDIT_REPORT]),
        ("Company PAN", [DocType.PAN_VAT]),  # "company" contains "pan": not matched twice
        ("vehicle bluebook", []),
    ],
)
def test_classify_document(text, types):
    assert classify_document(text) == types


def test_find_fiscal_years():
    assert find_fiscal_years("कर चुक्ता प्रमाणपत्र (आ.व. २०८२/८३)") == ["2082/83"]
    assert find_fiscal_years("F/Y 2077-78") == ["2077/78"]
    assert find_fiscal_years("FY 2082/2083 and 082/83") == ["2082/83"]
    assert find_fiscal_years("deadline 2083/08/10") == []  # a date, not a fiscal year
    assert find_fiscal_years("2080/82") == []  # not consecutive
    assert find_fiscal_years("2081/82 or 2082/83") == ["2081/82", "2082/83"]


def test_bsdate_type_reexport():
    assert parse_deadline("2083-08-05").bs == BSDate(2083, 8, 5)

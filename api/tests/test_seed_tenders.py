"""The synthetic seed tender set: complete, labelled, internally consistent (no DB, no network).

The manifest's `expected` values are ground truth for later Scout golden-set checks, so they are
verified here with the deterministic Nepal parsers: every *_quote is verbatim in the notice and
parses to the labelled value, and BS/AD date pairs agree.
"""

from collections import Counter
from datetime import date

import pytest

from config import get_settings
from ingest.seed_tenders import SEED_URL_PREFIX, SeedDataError, load_manifest, load_seed_notices
from nepal import bs_to_ad, parse_bs_date, parse_npr
from schemas import BuyerLevel, CompanyProfile, NoticeLanguage, ProcurementMethod, ProcurementType, Province

SEED_DIR = get_settings().seed_tenders_dir
BANNER = "[SYNTHETIC SEED NOTICE"
MANIFEST = load_manifest(SEED_DIR)
NOTICES = MANIFEST["notices"]


def text_of(entry: dict) -> str:
    return (SEED_DIR / entry["file"]).read_text(encoding="utf-8")


def test_size_and_labelling():
    assert MANIFEST["synthetic"] is True
    assert "FICTIONAL" in MANIFEST["_comment"]
    assert 30 <= len(NOTICES) <= 40
    assert len({n["id"] for n in NOTICES}) == len({n["file"] for n in NOTICES}) == len(NOTICES)


def test_every_file_listed_readable_and_bannered():
    on_disk = {p.name for p in SEED_DIR.glob("*.txt")}
    assert on_disk == {n["file"] for n in NOTICES}
    for entry in NOTICES:
        raw = (SEED_DIR / entry["file"]).read_bytes()
        text = raw.decode("utf-8")  # strict: no mojibake in the seed set
        assert text.startswith(BANNER), entry["file"]
        assert entry["file"].startswith(entry["id"] + "_")


def test_enum_labels_are_valid():
    for n in NOTICES:
        ProcurementType(n["procurement_type"])
        ProcurementMethod(n["method"])
        BuyerLevel(n["buyer_level"])
        Province(n["province"])
        NoticeLanguage(n["language"])
        assert n["date_style"] in {"bs", "ad", "both", "none"}


def test_variety_covers_nepal_notice_space():
    def values(key):
        return {n[key] for n in NOTICES}

    assert values("procurement_type") >= {"goods", "works", "consulting", "non_consulting"}
    assert values("method") >= {"ncb", "icb", "eoi", "rfp", "quotation"}
    assert values("buyer_level") >= {"federal", "province", "local"}
    assert values("language") == {"en", "ne", "mixed"}
    assert values("date_style") == {"bs", "ad", "both", "none"}
    assert len(values("province")) >= 6
    features = Counter(f for n in NOTICES for f in n["features"])
    for f in ("bid_security", "jv_allowed", "jv_not_allowed", "devanagari_numerals", "lakh_amount",
              "crore_amount", "missing_deadline", "ambiguous_budget", "domestic_preference"):
        assert features[f] >= 1, f
    texts = "\n".join(text_of(n) for n in NOTICES)
    for marker in ("Rs.", "NPR", "रु.", "लाख", "lakh", "crore", "०", "B.S.", "A.D."):
        assert marker in texts, marker


def test_demo_roles():
    roles = Counter(n["demo_role"] for n in NOTICES)
    assert roles["strong_match"] == roles["hard_fail"] == roles["irrelevant"] == 1
    assert roles["messy"] >= 4
    assert roles["deadline_passed"] >= 1


@pytest.mark.parametrize("entry", NOTICES, ids=lambda e: e["id"])
def test_expected_values_match_the_text(entry):
    text, exp = text_of(entry), entry["expected"]
    for key in ("deadline_quote", "cost_quote", "bid_security_quote"):
        if exp[key] is not None:
            assert exp[key] in text, f"{key} {exp[key]!r} not verbatim in {entry['file']}"
    if exp["cost_quote"]:
        assert parse_npr(exp["cost_quote"]) == exp["estimated_cost_npr"]
    if exp["bid_security_quote"]:
        assert parse_npr(exp["bid_security_quote"]) == exp["bid_security_npr"]
    if entry["date_style"] in ("bs", "both"):
        assert parse_bs_date(exp["deadline_quote"]).iso() == exp["deadline_bs"]
    if entry["date_style"] == "none":
        assert exp["deadline_bs"] is None and exp["deadline_ad"] is None
    if exp["deadline_bs"] and exp["deadline_ad"]:
        assert bs_to_ad(parse_bs_date(exp["deadline_bs"])) == date.fromisoformat(exp["deadline_ad"])


def test_demo_roles_line_up_with_demo_company():
    """Deterministic sanity check of the demo story (the real verdicts come from Compliance)."""
    profile = CompanyProfile.model_validate_json((SEED_DIR.parent / "demo_company" / "profile.json").read_text("utf-8"))
    avg = sum(t.amount_npr for t in profile.turnover) / len(profile.turnover)
    by_role = {n["demo_role"]: n for n in NOTICES}
    strong, hard = by_role["strong_match"], by_role["hard_fail"]
    assert strong["district"] in profile.districts_served and strong["procurement_type"] == "works"
    assert strong["expected"]["min_avg_turnover_npr"] <= avg
    assert hard["expected"]["min_avg_turnover_npr"] > avg and hard["expected"]["jv_allowed"] is False
    assert by_role["irrelevant"]["procurement_type"] != "works"


def test_loader_returns_raw_text_with_stable_urls():
    notices = load_seed_notices(SEED_DIR)
    assert len(notices) == len(NOTICES)
    assert all(n.source_url.startswith(SEED_URL_PREFIX) for n in notices)
    assert notices[0].raw_text == text_of(NOTICES[0])


def test_loader_refuses_unlabelled_or_missing_data(tmp_path):
    with pytest.raises(SeedDataError):
        load_seed_notices(tmp_path)
    (tmp_path / "manifest.json").write_text('{"notices": []}', encoding="utf-8")
    with pytest.raises(SeedDataError, match="synthetic"):
        load_seed_notices(tmp_path)
    (tmp_path / "manifest.json").write_text('{"synthetic": true, "notices": [{"file": "x.txt"}]}', encoding="utf-8")
    with pytest.raises(SeedDataError, match="x.txt"):
        load_seed_notices(tmp_path)

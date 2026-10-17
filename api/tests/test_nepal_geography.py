import pytest

from nepal.geography import DISTRICTS, PROVINCES_NE, normalize_location
from schemas import Province


def test_counts():
    assert len(PROVINCES_NE) == 7 and len(DISTRICTS) == 77
    per = {p: sum(1 for _, pr in DISTRICTS.values() if pr is p) for p in Province}
    assert per == {Province.KOSHI: 14, Province.MADHESH: 8, Province.BAGMATI: 13, Province.GANDAKI: 11,
                   Province.LUMBINI: 12, Province.KARNALI: 10, Province.SUDURPASHCHIM: 9}


@pytest.mark.parametrize("en", list(DISTRICTS))
def test_every_district_resolves_in_both_scripts(en):
    ne, prov = DISTRICTS[en]
    for text in (en, ne, en.upper(), f"{en} District", f"{ne} जिल्ला"):
        loc = normalize_location(text)
        assert (loc.district, loc.province) == (en, prov), text


@pytest.mark.parametrize(
    ("text", "province", "district"),
    [
        ("Ward No. 4, Kankai Municipality, Jhapa", Province.KOSHI, "Jhapa"),
        ("काठमाडौं", Province.BAGMATI, "Kathmandu"),
        ("Kavre", Province.BAGMATI, "Kavrepalanchok"),
        ("Chitawan district", Province.BAGMATI, "Chitwan"),
        ("Nawalparasi East", Province.GANDAKI, "Nawalpur"),
        ("Nawalparasi West", Province.LUMBINI, "Parasi"),
        ("Rukum West", Province.KARNALI, "Rukum West"),
        ("Eastern Rukum", Province.LUMBINI, "Rukum East"),
        ("झापा जिल्ला", Province.KOSHI, "Jhapa"),
        ("Sudurpaschim Province, Kailali", Province.SUDURPASHCHIM, "Kailali"),
        ("Koshi Province, Kathmandu", Province.BAGMATI, "Kathmandu"),  # district wins over a conflicting province
        ("Koshi Pradesh", Province.KOSHI, None),
        ("Province No. 3", Province.BAGMATI, None),
        ("प्रदेश नं ५", Province.LUMBINI, None),
        ("Far Western", Province.SUDURPASHCHIM, None),
        ("Nowhere Municipality", None, None),
        ("", None, None),
    ],
)
def test_normalize(text, province, district):
    loc = normalize_location(text)
    assert (loc.province, loc.district) == (province, district)


def test_ambiguous_and_multiple():
    loc = normalize_location("Rukum")
    assert (loc.province, loc.district, loc.candidates) == (None, None, ("Rukum East", "Rukum West"))
    loc = normalize_location("Jhapa and Morang")
    assert (loc.province, loc.district, loc.candidates) == (Province.KOSHI, None, ("Jhapa", "Morang"))
    assert normalize_location("Rukum, Karnali").province is Province.KARNALI
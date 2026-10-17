import pytest

from nepal.numbers import format_npr, humanize_npr, parse_npr, to_ascii_digits, to_devanagari_digits


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Rs. 1,25,00,000", 12_500_000),
        ("NPR 12.5 million", 12_500_000),
        ("१२५०००००", 12_500_000),
        ("1.25 crore", 12_500_000),
        ("10 lakh", 1_000_000),
        ("रु. १० लाख", 1_000_000),
        ("Rs. १,२५,००,०००", 12_500_000),
        ("Rs 1,02,000.00", 102_000),
        ("NRs. 2.00 Million", 2_000_000),
        ("३.४३ करोड", 34_300_000),
        ("34.3 lakh", 3_430_000),
        ("२ अर्ब", 2_000_000_000),
        ("0.5 lakh", 50_000),
        ("Rs 5 cr", 50_000_000),
        ("1,000", 1000),
    ],
)
def test_parse_npr(text, expected):
    assert parse_npr(text) == expected


@pytest.mark.parametrize("text", ["", "Rs", "Rs 10 and 20", "USD 100", "$5 lakh", "Rs 1.5", "Rs 1.234 crore1"])
def test_parse_npr_rejects(text):
    with pytest.raises(ValueError):
        parse_npr(text)


@pytest.mark.parametrize(
    ("n", "expected"),
    [(0, "Rs 0"), (999, "Rs 999"), (1000, "Rs 1,000"), (100_000, "Rs 1,00,000"), (102_000, "Rs 1,02,000"),
     (12_500_000, "Rs 1,25,00,000"), (-150_000, "-Rs 1,50,000")],
)
def test_format_npr(n, expected):
    assert format_npr(n) == expected


@pytest.mark.parametrize("n", [0, 7, 1000, 102_000, 12_500_000, 2_000_000_000])
def test_format_parse_round_trip(n):
    assert parse_npr(format_npr(n)) == n


@pytest.mark.parametrize(
    ("n", "expected"),
    [(12_500_000, "1.25 crore"), (1_000_000, "10 lakh"), (99_999, "99999"), (2_000_000_000, "2 arab"), (150_000, "1.5 lakh")],
)
def test_humanize(n, expected):
    assert humanize_npr(n) == expected


def test_numerals_round_trip():
    assert to_ascii_digits("२०८३-०६-१५") == "2083-06-15"
    assert to_devanagari_digits("2083") == "२०८३"
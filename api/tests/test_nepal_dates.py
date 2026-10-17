from datetime import date, datetime, time, timedelta, timezone

import pytest
from pydantic import TypeAdapter

from nepal.dates import (MONTHS_EN, MONTHS_NE, NPT, BSDate, ad_to_bs, bs_to_ad, current_fiscal_year, days_in_bs_month,
                         days_left, deadline_from_raw, fiscal_year_bounds, fiscal_year_of, format_bs, parse_bs_date,
                         parse_bs_datetime)
from schemas._base import FiscalYearBS

NOW = datetime(2026, 10, 17, 22, 35, tzinfo=NPT)


@pytest.mark.parametrize(
    ("bs", "ad"),
    [
        (BSDate(2064, 5, 3), date(2007, 8, 20)),  # NEPAL_CONTEXT.md section 7 anchor
        (BSDate(2080, 1, 1), date(2023, 4, 14)),
        (BSDate(2081, 1, 1), date(2024, 4, 13)),
        (BSDate(2082, 1, 1), date(2025, 4, 14)),
    ],
)
def test_known_pairs(bs, ad):
    assert bs_to_ad(bs) == ad
    assert ad_to_bs(ad) == bs


@pytest.mark.parametrize(
    "text",
    ["2083-06-15", "2083/06/15", "2083.06.15", "२०८३।०६।१५", "२०८३-०६-१५", "15/06/2083", "Ashwin 15, 2083", "15 Asoj 2083",
     "15th Ashwin 2083", "१५ असोज २०८३", "असोज १५, २०८३", "2083 Asoj 15", "Deadline: 2083-06-15 12:00"],
)
def test_parse_formats(text):
    assert parse_bs_date(text) == BSDate(2083, 6, 15)


def test_every_month_name_parses():
    for i, (en, ne) in enumerate(zip(MONTHS_EN, MONTHS_NE), 1):
        assert parse_bs_date(f"15 {en} 2083") == BSDate(2083, i, 15)
        assert parse_bs_date(f"१५ {ne} २०८३") == BSDate(2083, i, 15)


@pytest.mark.parametrize("text", ["2083-13-01", "2083-06-33", "2083-00-10", "hello", "2083-06", "15 Asoj Kartik 2083", "15 Asoj 83", "1500-01-01"])
def test_parse_rejects(text):
    with pytest.raises(ValueError):
        parse_bs_date(text)


def test_datetime_with_time_and_default():
    dt = parse_bs_datetime("२०८३।०८।०४ १२:०० बजे")
    assert (dt.hour, dt.minute) == (12, 0) and dt.utcoffset() == timedelta(hours=5, minutes=45)
    assert dt.date() == bs_to_ad(BSDate(2083, 8, 4))
    assert parse_bs_datetime("2083-08-04").time() == time(23, 59, 59)
    assert parse_bs_datetime("2083-08-04 2:30 PM").hour == 14
    assert parse_bs_datetime("2083-08-04 12:05 am").hour == 0


def test_deadline_from_raw():
    iso, dt = deadline_from_raw("२०८३।०८।०४ १२:०० बजे")
    assert iso == "2083-08-04" and dt.hour == 12


def test_month_lengths_and_year_lengths():
    sizes = {(y, m): days_in_bs_month(y, m) for y in range(2070, 2096) for m in range(1, 13)}
    assert all(29 <= n <= 32 for n in sizes.values())
    assert 32 in sizes.values()  # day <= 32 in BSDateISO is not hypothetical
    for y in range(2070, 2095):
        assert sum(sizes[(y, m)] for m in range(1, 13)) == (bs_to_ad(BSDate(y + 1, 1, 1)) - bs_to_ad(BSDate(y, 1, 1))).days


def test_last_day_valid_and_next_invalid():
    n = days_in_bs_month(2082, 6)
    assert parse_bs_date(f"2082-06-{n}") == BSDate(2082, 6, n)
    with pytest.raises(ValueError):
        parse_bs_date(f"2082-06-{n + 1:02d}") if n < 32 else (_ for _ in ()).throw(ValueError)


def test_round_trip_over_many_days():
    d = date(2020, 1, 1)
    for _ in range(0, 3000, 7):
        assert bs_to_ad(ad_to_bs(d)) == d
        d += timedelta(days=7)


def test_fiscal_year_boundaries():
    assert fiscal_year_of(BSDate(2082, 4, 1)) == "2082/83"  # Shrawan 1
    assert fiscal_year_of(BSDate(2082, 3, days_in_bs_month(2082, 3))) == "2081/82"  # last day of Asar
    assert fiscal_year_of(BSDate(2082, 1, 1)) == "2081/82"
    assert fiscal_year_of(BSDate(2082, 12, 5)) == "2082/83"  # Chaitra 2082 is after Shrawan 2082
    assert fiscal_year_of(BSDate(2099, 4, 1)) == "2099/00"
    for fy in ("2082/83", "2081/82", "2099/00"):
        TypeAdapter(FiscalYearBS).validate_python(fy)


def test_fiscal_year_bounds_are_contiguous():
    s, e = fiscal_year_bounds("2082/83")
    assert s == BSDate(2082, 4, 1) and e.month == 3
    assert bs_to_ad(e) + timedelta(days=1) == bs_to_ad(fiscal_year_bounds("2083/84")[0])


@pytest.mark.parametrize(
    ("ad", "fy"),
    [(date(2025, 4, 20), "2081/82"), (date(2025, 7, 1), "2081/82"), (date(2025, 7, 30), "2082/83"), (date(2025, 9, 1), "2082/83")],
)
def test_current_fiscal_year(ad, fy):
    assert current_fiscal_year(datetime.combine(ad, time(12), tzinfo=NPT)) == fy


def test_current_fiscal_year_uses_nepal_time_not_utc():
    # 2025-07-16 20:00 UTC is already 2025-07-17 01:45 NPT (Shrawan 1, 2082 begins 2025-07-17)
    assert current_fiscal_year(datetime(2025, 7, 16, 20, 0, tzinfo=timezone.utc)) == "2082/83"
    assert current_fiscal_year(datetime(2025, 7, 16, 12, 0, tzinfo=timezone.utc)) == "2081/82"


def test_days_left():
    assert days_left(date(2026, 10, 20), NOW) == 3
    assert days_left(datetime(2026, 10, 17, 12, 0, tzinfo=NPT), NOW) == 0
    assert days_left(date(2026, 10, 16), NOW) == -1
    assert days_left(ad_to_bs(date(2026, 10, 20)), NOW) == 3
    # 18:30 UTC on Oct 17 is 00:15 NPT on Oct 18
    assert days_left(date(2026, 10, 18), datetime(2026, 10, 17, 18, 30, tzinfo=timezone.utc)) == 0


def test_naive_now_rejected():
    with pytest.raises(ValueError):
        days_left(date(2026, 10, 20), datetime(2026, 10, 17))


def test_format_bs():
    bs = BSDate(2083, 6, 15)
    assert format_bs(bs) == "2083-06-15"
    assert format_bs(bs, long=True) == "15 Asoj 2083"
    assert format_bs(bs, ne=True) == "२०८३-०६-१५"
    assert format_bs(bs, long=True, ne=True) == "१५ असोज २०८३"
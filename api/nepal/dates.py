"""Bikram Sambat dates, Nepal time, fiscal year (NEPAL_CONTEXT.md section 7).

BS<->AD uses the `nepali-datetime` lookup tables, never arithmetic.
"""

import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from typing import NamedTuple

import nepali_datetime as nd

from nepal.numbers import to_ascii_digits, to_devanagari_digits

NPT = timezone(timedelta(hours=5, minutes=45))
END_OF_DAY = time(23, 59, 59)

MONTHS_EN = ["Baisakh", "Jestha", "Asar", "Shrawan", "Bhadra", "Asoj", "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"]
MONTHS_NE = ["बैशाख", "जेठ", "असार", "साउन", "भदौ", "असोज", "कात्तिक", "मंसिर", "पुस", "माघ", "फागुन", "चैत"]

_ALIASES = (
    "baisakh,baishakh,baishak,vaisakh,vaishakh,बैशाख,वैशाख",
    "jestha,jeth,jyestha,jyeshtha,जेठ,जेष्ठ,ज्येष्ठ",
    "asar,ashar,ashadh,asadh,असार,आषाढ",
    "shrawan,srawan,shravan,sawan,saun,साउन,श्रावण,सावन",
    "bhadra,bhadau,bhado,भदौ,भाद्र",
    "asoj,ashoj,ashwin,aswin,asvin,असोज,आश्विन",
    "kartik,kattik,karthik,कात्तिक,कार्तिक",
    "mangsir,mangshir,manshir,margashirsha,मंसिर,मङ्सिर,मार्गशीर्ष",
    "poush,push,paush,pus,पुस,पुष,पौष",
    "magh,माघ",
    "falgun,phalgun,fagun,फागुन,फाल्गुन",
    "chaitra,chait,चैत,चैत्र",
)
_MONTHS = {unicodedata.normalize("NFC", a).casefold(): i for i, row in enumerate(_ALIASES, 1) for a in row.split(",")}

_SEP = re.compile(r"[\s,\-/.।|]+")
_TIME = re.compile(r"(\d{1,2}):(\d{2})\s*([ap]m)?", re.I)


class BSDate(NamedTuple):
    year: int
    month: int
    day: int

    def iso(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"


def _validate(y: int, m: int, d: int) -> BSDate:
    try:
        nd.date(y, m, d)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"invalid BS date {y:04d}-{m:02d}-{d:02d}: {exc}") from exc
    return BSDate(y, m, d)


def parse_bs_date(text: str) -> BSDate:
    """'2083-06-15', '2083/06/15', '२०८३।०६।१५', '15/06/2083', 'Ashwin 15, 2083', '१५ असोज २०८३'.

    Any time of day in the text is ignored here (see parse_bs_datetime).
    """
    t = _TIME.sub(" ", to_ascii_digits(unicodedata.normalize("NFC", text)))
    nums, months = [], []
    for tok in filter(None, _SEP.split(t)):
        if m := re.fullmatch(r"(\d+)(?:st|nd|rd|th)?", tok, re.I):
            nums.append(m[1])
        elif tok.casefold() in _MONTHS:
            months.append(_MONTHS[tok.casefold()])
    if len(months) > 1:
        raise ValueError(f"more than one month name in {text!r}")
    if months:
        years = [n for n in nums if len(n) == 4]
        if len(nums) != 2 or len(years) != 1:
            raise ValueError(f"cannot read a BS date from {text!r}")
        rest = list(nums)
        rest.remove(years[0])
        y, mo, d = int(years[0]), months[0], int(rest[0])
    elif len(nums) == 3:
        a, b, c = nums
        if len(a) == 4:
            y, mo, d = int(a), int(b), int(c)
        elif len(c) == 4:
            y, mo, d = int(c), int(b), int(a)
        else:
            raise ValueError(f"cannot find a 4-digit BS year in {text!r}")
    else:
        raise ValueError(f"cannot read a BS date from {text!r}")
    return _validate(y, mo, d)


def bs_to_ad(bs: BSDate) -> date:
    return nd.date(*bs).to_datetime_date()


def ad_to_bs(d: date) -> BSDate:
    if isinstance(d, datetime):
        if d.tzinfo is None:
            raise ValueError("naive datetime: attach a timezone first")
        d = d.astimezone(NPT).date()
    x = nd.date.from_datetime_date(d)
    return BSDate(x.year, x.month, x.day)


def parse_bs_datetime(text: str, default_time: time = END_OF_DAY) -> datetime:
    """BS date plus optional 'HH:MM [am|pm]' -> aware datetime in NPT.

    No time in the text -> default_time (end of day: the lenient reading of a deadline).
    """
    bs = parse_bs_date(text)
    if m := _TIME.search(to_ascii_digits(text)):
        h, mi, ap = int(m[1]), int(m[2]), (m[3] or "").lower()
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
        t = time(h, mi)
    else:
        t = default_time
    return datetime.combine(bs_to_ad(bs), t, tzinfo=NPT)


def deadline_from_raw(raw: str) -> tuple[str, datetime]:
    """For Scout: (deadline_bs_iso, deadline as NPT datetime) from deadline_bs_raw."""
    return parse_bs_date(raw).iso(), parse_bs_datetime(raw)


def days_in_bs_month(year: int, month: int) -> int:
    a = nd.date(year, month, 1).to_datetime_date()
    b = nd.date(year + (month == 12), month % 12 + 1, 1).to_datetime_date()
    return (b - a).days


def fiscal_year_of(bs: BSDate) -> str:
    """FY starts Shrawan 1 (month 4). 2082-04-01 -> '2082/83'."""
    start = bs.year if bs.month >= 4 else bs.year - 1
    return f"{start}/{(start + 1) % 100:02d}"


def fiscal_year_bounds(fy: str) -> tuple[BSDate, BSDate]:
    s = int(fy[:4])
    return BSDate(s, 4, 1), BSDate(s + 1, 3, days_in_bs_month(s + 1, 3))


def _now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(NPT)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(NPT)


def current_fiscal_year(now: datetime | None = None) -> str:
    return fiscal_year_of(ad_to_bs(_now(now).date()))


def days_left(deadline: date | datetime | BSDate, now: datetime | None = None) -> int:
    """Calendar days from today (NPT) to the deadline's NPT date; negative once passed."""
    if isinstance(deadline, BSDate):
        d = bs_to_ad(deadline)
    elif isinstance(deadline, datetime):
        d = deadline.astimezone(NPT).date()
    else:
        d = deadline
    return (d - _now(now).date()).days


def format_bs(bs: BSDate, *, long: bool = False, ne: bool = False) -> str:
    """iso: '2083-06-15'; long: '15 Asoj 2083'; ne=True uses Devanagari."""
    s = f"{bs.day} {(MONTHS_NE if ne else MONTHS_EN)[bs.month - 1]} {bs.year}" if long else bs.iso()
    return to_devanagari_digits(s) if ne else s
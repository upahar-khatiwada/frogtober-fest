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


# --- deadline strings as notices print them -----------------------------------------
# BS and AD years never overlap in practice (BS = AD + ~57), so the year decides the era.
BS_MIN_YEAR = 2060

MONTHS_AD = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
             "october", "november", "december"]
_AD_MONTHS = {m: i for i, m in enumerate(MONTHS_AD, 1)} | {m[:3]: i for i, m in enumerate(MONTHS_AD, 1)} | {"sept": 9}

_DSEP = r"\s*[-/.।]\s*"
_YMD = re.compile(rf"(?<!\d)(\d{{4}}){_DSEP}(\d{{1,2}}){_DSEP}(\d{{1,2}})(?![\d:])")
_DMY = re.compile(rf"(?<![\d:])(\d{{1,2}}){_DSEP}(\d{{1,2}}){_DSEP}(\d{{4}})(?!\d)")
_MONTH_ALT = "|".join(sorted({*map(re.escape, _MONTHS), *_AD_MONTHS}, key=len, reverse=True))
_DAY_MONTH_YEAR = re.compile(rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_ALT})\.?,?\s+(\d{{4}})(?!\d)", re.I)
_MONTH_DAY_YEAR = re.compile(rf"(?<![\wऀ-ॿ])({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})(?!\d)", re.I)

_CLOCK = re.compile(r"(?<![\d:])(\d{1,2})\s*:\s*(\d{2})(?!\d)\s*(a\.?m\.?|p\.?m\.?)?", re.I)
_HOUR_AMPM = re.compile(r"(?<![\d:])(\d{1,2})\s*(a\.?m\.?|p\.?m\.?)(?![a-z])", re.I)
_HOUR_BAJE = re.compile(r"(?<![\d:])(\d{1,2})\s*बजे")
_NOON = re.compile(r"\bnoon\b|मध्यान्ह", re.I)
# Nepali day-part words before a clock time: "दिनको २:०० बजे" is 2 pm, "बेलुका ५ बजे" is 5 pm.
_PM_WORDS = ("दिउँसो", "बेलुका", "साँझ", "बेलुकी")
_DAY_WORD = "दिनको"


class DeadlineParse(NamedTuple):
    """What a deadline string says, read deterministically. `deadline` is None if `issues`."""

    bs: BSDate | None
    ad: date | None
    time_of_day: time | None
    deadline: datetime | None
    issues: tuple[str, ...]


def _era_date(y: int, m: int, d: int, issues: list[str]) -> tuple[str, date | BSDate] | None:
    try:
        if y >= BS_MIN_YEAR:
            return "bs", _validate(y, m, d)
        return "ad", date(y, m, d)
    except ValueError as exc:
        issues.append(str(exc))
        return None


def _find_dates(t: str, issues: list[str]) -> tuple[list[BSDate], list[date], str]:
    """All dates in `t` (ASCII digits); returns BS dates, AD dates and `t` with them blanked out."""
    found: list[tuple[str, date | BSDate]] = []

    def take(m: re.Match, y: int, mo: int, d: int) -> str:
        if (hit := _era_date(y, mo, d, issues)) is not None:
            found.append(hit)
        return " " * len(m.group())

    def month_number(name: str, y: int) -> int | None:
        key = unicodedata.normalize("NFC", name).casefold().rstrip(".")
        bs_month, ad_month = _MONTHS.get(key), _AD_MONTHS.get(key)
        return bs_month if y >= BS_MIN_YEAR else ad_month

    def named(m: re.Match, day_first: bool) -> str:
        day, name = (m[1], m[2]) if day_first else (m[2], m[1])
        y = int(m[3])
        mo = month_number(name, y)
        if mo is None:
            issues.append(f"month {name!r} does not fit a {'BS' if y >= BS_MIN_YEAR else 'AD'} year in {m.group()!r}")
            return " " * len(m.group())
        return take(m, y, mo, int(day))

    t = _DAY_MONTH_YEAR.sub(lambda m: named(m, True), t)
    t = _MONTH_DAY_YEAR.sub(lambda m: named(m, False), t)
    t = _YMD.sub(lambda m: take(m, int(m[1]), int(m[2]), int(m[3])), t)

    def dmy(m: re.Match) -> str:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        if y < BS_MIN_YEAR and d <= 12 and mo <= 12 and d != mo:
            issues.append(f"AD date {m.group()!r} could be day/month or month/day")
            return " " * len(m.group())
        return take(m, y, mo, d)

    t = _DMY.sub(dmy, t)
    bs = list(dict.fromkeys(v for era, v in found if era == "bs"))
    ad = list(dict.fromkeys(v for era, v in found if era == "ad"))
    return bs, ad, t


def _find_time(t: str, issues: list[str]) -> time | None:
    times: list[time] = []

    def pm_context(start: int) -> tuple[bool, bool]:
        before = t[max(0, start - 12):start]
        return any(w in before for w in _PM_WORDS), _DAY_WORD in before

    for m in _CLOCK.finditer(t):
        h, mi, ap = int(m[1]), int(m[2]), (m[3] or "").lower().replace(".", "")
        pm_word, day_word = pm_context(m.start())
        if ap == "pm" or pm_word or (day_word and 1 <= h <= 5):
            h = h + 12 if h < 12 else h
        elif ap == "am" and h == 12:
            h = 0
        if h > 23 or mi > 59:
            issues.append(f"invalid time {m.group()!r}")
            continue
        times.append(time(h, mi))
    rest = _CLOCK.sub(" ", t)
    for m in _HOUR_AMPM.finditer(rest):
        h, ap = int(m[1]), m[2].lower().replace(".", "")
        times.append(time((h % 12) + (12 if ap == "pm" else 0), 0))
    rest = _HOUR_AMPM.sub(" ", rest)
    for m in _HOUR_BAJE.finditer(rest):
        h = int(m[1])
        pm_word, day_word = pm_context(m.start())
        if (pm_word or (day_word and 1 <= h <= 5)) and h < 12:
            h += 12
        if h > 23:
            issues.append(f"invalid time {m.group()!r}")
            continue
        times.append(time(h, 0))
    if _NOON.search(t) and not times:
        times.append(time(12, 0))
    distinct = list(dict.fromkeys(times))
    if len(distinct) > 1:
        issues.append(f"several times of day: {', '.join(x.strftime('%H:%M') for x in distinct)}")
        return None
    return distinct[0] if distinct else None


def parse_deadline(raw: str) -> DeadlineParse:
    """Read a submission deadline as a notice prints it. Never guesses.

    Handles BS and AD in one string ('2083-08-05 B.S. (2026-11-21 A.D.)'), Devanagari digits
    and the danda separator, BS and English month names, and times as '12:00 hours',
    '12 noon', '2 PM' or '१२ बजे'. A date-only deadline is end of day NPT. Any of these is an
    issue and leaves `deadline` None: no date, two different dates of one era, a BS date
    that does not convert to the printed AD date, an invalid date, or two different times.
    """
    issues: list[str] = []
    t = to_ascii_digits(unicodedata.normalize("NFC", raw))
    bs_dates, ad_dates, rest = _find_dates(t, issues)
    tod = _find_time(rest, issues)
    if len(bs_dates) > 1:
        issues.append(f"several BS dates: {', '.join(d.iso() for d in bs_dates)}")
    if len(ad_dates) > 1:
        issues.append(f"several AD dates: {', '.join(d.isoformat() for d in ad_dates)}")
    bs = bs_dates[0] if len(bs_dates) == 1 else None
    ad = ad_dates[0] if len(ad_dates) == 1 else None
    if bs and ad and bs_to_ad(bs) != ad:
        issues.append(f"BS {bs.iso()} is AD {bs_to_ad(bs).isoformat()}, but the text says AD {ad.isoformat()}")
    if not bs_dates and not ad_dates and not issues:
        issues.append(f"no date found in {raw!r}")
    if issues:
        return DeadlineParse(bs, ad, tod, None, tuple(issues))
    day = ad or bs_to_ad(bs)
    bs = bs or ad_to_bs(day)
    return DeadlineParse(bs, day, tod, datetime.combine(day, tod or END_OF_DAY, tzinfo=NPT), ())


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
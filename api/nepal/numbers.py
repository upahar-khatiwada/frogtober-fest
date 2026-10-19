"""NPR amounts and Devanagari numerals (NEPAL_CONTEXT.md section 9)."""

import re
from decimal import Decimal

_TO_ASCII = str.maketrans("०१२३४५६७८९", "0123456789")
_TO_DEV = str.maketrans("0123456789", "०१२३४५६७८९")

_UNITS = {
    "thousand": 10**3, "हजार": 10**3,
    "lakh": 10**5, "lakhs": 10**5, "lac": 10**5, "lacs": 10**5, "लाख": 10**5,
    "million": 10**6, "mn": 10**6, "मिलियन": 10**6,
    "crore": 10**7, "crores": 10**7, "cr": 10**7, "करोड": 10**7,
    "arab": 10**9, "billion": 10**9, "अर्ब": 10**9,
}
_UNIT_RE = re.compile(r"\s*(" + "|".join(sorted(map(re.escape, _UNITS), key=len, reverse=True)) + r")(?![a-z])", re.I)
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_FOREIGN_RE = re.compile(r"[$€₹]|\b(usd|eur|inr)\b", re.I)


# Western (1,234,567) or South Asian (1,23,45,678) digit grouping. Anything else, e.g. the
# mis-keyed "1,50,000,00", is rejected rather than read as some number (NEPAL_CONTEXT section 9).
_GROUPING_RE = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3}|\d+)(?:\.\d+)?$")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|per\s*cent\b|percent\b|प्रतिशत)", re.I)
_DAYS_RE = re.compile(r"(\d+)\s*(?:\(\s*[^)]*\)\s*)?(?:calendar\s+)?(?:days?\b|दिन)", re.I)
_THOUSANDS_MARKERS = ("in thousand", "in '000", "('000)", "हजारमा")


def to_ascii_digits(text: str) -> str:
    return text.translate(_TO_ASCII)


def to_devanagari_digits(text: str) -> str:
    return text.translate(_TO_DEV)


def _number(token: str, source: str) -> Decimal:
    if not _GROUPING_RE.match(token):
        raise ValueError(f"invalid digit grouping {token!r} in {source!r}")
    return Decimal(token.replace(",", ""))


def parse_npr(text: str) -> int:
    """'Rs. 1,25,00,000' / 'NPR 12.5 million' / '१.२५ करोड' / 'रु. ३२ लाख ५० हजार' -> integer NPR.

    Strict: no foreign currency, no fractional rupees, valid digit grouping only. Several
    numbers are accepted only as a compound amount where every number carries a unit and the
    units strictly decrease ('32 lakh 50 thousand'); anything else is ambiguous.
    """
    t = to_ascii_digits(text)
    if _FOREIGN_RE.search(t):
        raise ValueError(f"not an NPR amount: {text!r}")
    matches = list(_NUM_RE.finditer(t))
    if not matches:
        raise ValueError(f"no amount in {text!r}")
    parts = []
    for m in matches:
        unit = _UNIT_RE.match(t, m.end())
        parts.append((_number(m.group(), text), _UNITS[unit.group(1).lower()] if unit else None))
    if len(parts) > 1:
        units = [u for _, u in parts]
        if None in units or any(a <= b for a, b in zip(units, units[1:])):
            raise ValueError(f"expected exactly one amount in {text!r}")
    value = sum((n * (u or 1) for n, u in parts), Decimal(0))
    if value != value.to_integral_value():
        raise ValueError(f"fractional rupees in {text!r}")
    return int(value)


def parse_percent(text: str) -> float:
    """'2.5%' / '5 percent' / '२.५ प्रतिशत' -> 2.5. Exactly one percentage, 0 < p <= 100."""
    found = _PERCENT_RE.findall(to_ascii_digits(text))
    if len(found) != 1:
        raise ValueError(f"expected exactly one percentage in {text!r}")
    value = float(found[0])
    if not 0 < value <= 100:
        raise ValueError(f"percentage out of range in {text!r}")
    return value


def parse_days(text: str) -> int:
    """'valid for 148 days' / '१२० दिन' -> 148. Exactly one day count."""
    found = {int(n) for n in _DAYS_RE.findall(to_ascii_digits(text))}
    if len(found) != 1:
        raise ValueError(f"expected exactly one day count in {text!r}")
    days = found.pop()
    if days <= 0:
        raise ValueError(f"non-positive day count in {text!r}")
    return days


def has_thousands_marker(text: str) -> bool:
    """True if the text says its figures are in thousands ('रु. हजारमा', "in '000")."""
    t = text.casefold()
    return any(m in t for m in _THOUSANDS_MARKERS)


def format_npr(amount: int) -> str:
    """102000 -> 'Rs 1,02,000' (lakh/crore grouping)."""
    sign, s = ("-" if amount < 0 else ""), str(abs(amount))
    head, tail, groups = s[:-3], s[-3:], []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}Rs {','.join(groups + [tail])}"


def humanize_npr(amount: int) -> str:
    """12500000 -> '1.25 crore'; below one lakh the plain integer."""
    for unit, name in ((10**9, "arab"), (10**7, "crore"), (10**5, "lakh")):
        if abs(amount) >= unit:
            return f"{(Decimal(amount) / unit).normalize():f} {name}"
    return str(amount)
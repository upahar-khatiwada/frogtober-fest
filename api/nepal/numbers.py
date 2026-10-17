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


def to_ascii_digits(text: str) -> str:
    return text.translate(_TO_ASCII)


def to_devanagari_digits(text: str) -> str:
    return text.translate(_TO_DEV)


def parse_npr(text: str) -> int:
    """'Rs. 1,25,00,000' / 'NPR 12.5 million' / '१.२५ करोड' -> integer NPR.

    Strict: exactly one number, no foreign currency, no fractional rupees.
    """
    t = to_ascii_digits(text)
    if _FOREIGN_RE.search(t):
        raise ValueError(f"not an NPR amount: {text!r}")
    numbers = _NUM_RE.findall(t)
    if len(numbers) != 1:
        raise ValueError(f"expected exactly one amount in {text!r}")
    m = _NUM_RE.search(t)
    value = Decimal(m.group().replace(",", ""))
    if unit := _UNIT_RE.match(t, m.end()):
        value *= _UNITS[unit.group(1).lower()]
    if value != value.to_integral_value():
        raise ValueError(f"fractional rupees in {text!r}")
    return int(value)


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
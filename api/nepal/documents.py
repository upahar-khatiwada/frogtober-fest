"""Required-document names -> DocType, and the BS fiscal year a document must cover.

Deterministic keyword tables (English + Nepali) built from PPR Rule 40(2) and the notice
wording in NEPAL_CONTEXT.md section 3. One notice line often names several documents
("registration certificate and construction licence renewed for F/Y 2083/84"), so
`classify_document` returns every type it finds, in text order. Each keyword match consumes
its span, so "VAT and PAN registration certificate" is pan_vat only, not also
company_registration.
"""

import re
import unicodedata

from nepal.numbers import to_ascii_digits
from schemas.enums import DocType

# Most specific first: a pattern consumes its text before later ones run.
_PATTERNS: list[tuple[DocType, str]] = [
    (DocType.TAX_CLEARANCE, r"tax\s*clearance|कर\s*चुक्ता"),
    (DocType.TAX_RETURN, r"tax\s*returns?|कर\s*विवरण"),
    (DocType.PAN_VAT, r"(?<![a-z])(?:vat|pan)(?![a-z])(?:\s*(?:and|&|/|,)\s*(?:vat|pan)(?![a-z]))?(?:\s*registration)?(?:\s*certificates?)?"
                      r"|मू\.?\s*अ\.?\s*कर(?:\s*/\s*स्थायी\s*लेखा\s*नम्बर)?(?:\s*दर्ता)?(?:\s*प्रमाणपत्र)?"
                      r"|मूल्य\s*अभिवृद्धि\s*कर(?:\s*दर्ता)?(?:\s*प्रमाणपत्र)?|स्थायी\s*लेखा\s*नम्बर(?:\s*दर्ता)?(?:\s*प्रमाणपत्र)?"),
    (DocType.LICENCE_RENEWAL, r"renew(?:ed|al)|नवीकरण|नविकरण"),
    (DocType.JV_AGREEMENT, r"(?:joint\s*venture|(?<![a-z])jv)\s*agreement|संयुक्त\s*उपक्रम(?:\s*\(jv\))?\s*सम्झौता"),
    (DocType.POWER_OF_ATTORNEY, r"power\s*of\s*attorney|अख्तियारनामा|अख्तियारी"),
    (DocType.SELF_DECLARATION, r"self[\s-]*declaration|स्व\s*घोषणा|स्वघोषणा"),
    (DocType.BID_SECURITY, r"bid\s*(?:security|bond|guarantee)|धरौटी|बोलपत्र\s*जमानत"),
    (DocType.AUDIT_REPORT, r"audit(?:ed)?(?:\s*(?:report|financial\s*statements?))?|लेखा\s*परीक्षण|लेखापरीक्षण"),
    (DocType.EXPERIENCE_CERTIFICATE, r"experience|completion\s*certificate|अनुभव"),
    (DocType.COMPANY_PROFILE, r"company\s*profile|firm\s*profile"),
    (DocType.COMPANY_REGISTRATION, r"(?:firm|company|organi[sz]ation|business)?\s*(?:/\s*(?:firm|company)\s*)?registration"
                                   r"|फर्म\s*दर्ता|कम्पनी\s*दर्ता|संस्था\s*दर्ता|फर्म\s*/\s*कम्पनी\s*दर्ता"),
    (DocType.BUSINESS_LICENCE, r"licen[cs]e|इजाजत\s*पत्र|इजाजतपत्र"),
]
_COMPILED = [(t, re.compile(p, re.I)) for t, p in _PATTERNS]

# "2082/83", "2082-83", "2082/2083", "082/83" (BS), not a date like "2083/08/10".
_FY_RE = re.compile(r"(?<![\d/.-])(20\d{2}|0\d{2})\s*[/-]\s*(\d{2}|20\d{2})(?![\d/.-]?\d)")


def _norm(text: str) -> str:
    return to_ascii_digits(unicodedata.normalize("NFC", text))


def classify_document(text: str) -> list[DocType]:
    """Every DocType named in `text`, in order of appearance; [] if none is recognised."""
    t = _norm(text)
    hits: list[tuple[int, DocType]] = []
    for doc_type, pattern in _COMPILED:
        def consume(m: re.Match, doc_type: DocType = doc_type) -> str:
            if m.group().strip():
                hits.append((m.start(), doc_type))
            return " " * len(m.group())

        t = pattern.sub(consume, t)
    return list(dict.fromkeys(doc_type for _, doc_type in sorted(hits, key=lambda h: h[0])))


def find_fiscal_years(text: str) -> list[str]:
    """Distinct BS fiscal years ('YYYY/YY') written in `text`, in order. Non-consecutive pairs are skipped."""
    found = []
    for m in _FY_RE.finditer(_norm(text)):
        start = int(m[1]) if len(m[1]) == 4 else 2000 + int(m[1])
        end = int(m[2]) % 100
        if start < 2060 or (start + 1) % 100 != end:
            continue
        found.append(f"{start}/{end:02d}")
    return list(dict.fromkeys(found))

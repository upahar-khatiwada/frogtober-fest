"""Scout agent: raw notice text -> TenderRecord (spec sections 8.1, 8.2).

Two halves, split along CLAUDE.md hard rule 5:

1. `extract_tender` asks the LLM (via `pipeline.llm`, temperature 0, schema =
   `TenderExtraction`) to copy values verbatim: dates, amounts, percentages and
   document names exactly as printed, each with the sentence it came from.
2. `postprocess` (pure, no LLM) turns those strings into typed values with the
   Nepal layer: `parse_deadline` (BS/AD, Devanagari, NPT), `parse_npr` (lakh /
   crore / grouping), `normalize_location`, `classify_document`. Every value is
   checked against the notice text and stored with its quote and character span
   (`TenderRecord.sources`). When a parser cannot read a raw string, or the raw
   string is not in the notice, the value stays null, the raw string is kept,
   and a `ReviewFlag` sets `needs_review`. Nothing is guessed.

`run_scout` writes the result to the `tenders` row and sets `extracted`, or
`failed` when the LLM output was invalid after one retry. The LLM client records
the agent_runs row (hard rule 9).

Dev CLI (from api/):  uv run python -m api.agents.scout --seed [--only 001,005] [--db] [--json out.json]
(`python -m agents.scout` is the same module; `api.` resolves through the api/api alias package.)
"""

import argparse
import json
import re
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import Tender
from nepal.dates import NPT, parse_deadline
from nepal.documents import classify_document, find_fiscal_years
from nepal.geography import normalize_location
from nepal.numbers import has_thousands_marker, parse_days, parse_npr, parse_percent, to_ascii_digits
from nepal.rules import calc_bid_security
from pipeline.llm import LLMClient, LLMError
from schemas import (
    BidSecurity,
    DocType,
    FieldSource,
    Grounded,
    NoticeLanguage,
    RequiredDoc,
    ReviewFlag,
    Stage,
    TenderCriteria,
    TenderExtraction,
    TenderRecord,
    TenderStatus,
)

T = TypeVar("T")

# --- prompt -------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You extract fields from ONE Nepali public procurement notice. The notice may be in English, in Nepali \
(Devanagari), or mixed. Reply with JSON only, matching the schema.

COPY, DO NOT CONVERT. For every field that has "value" and "quote":
- value: copy the characters exactly as they appear in the notice. Keep Devanagari digits as Devanagari \
(२०८३।०८।०५), keep "Rs.", "NPR", "रु.", "/-", "lakh", "लाख", "crore", "करोड", "B.S.", commas and brackets. \
Never convert BS dates to AD or AD to BS, never compute, total or reformat an amount, never translate.
- quote: copy the whole sentence, line or table row that contains the value, exactly as written.
- If the notice does not state a field, use null. Never invent or infer a value.

Fields:
- title: name of the work / contract / goods. reference_no: contract, IFB or ठेक्का नं. number. \
buyer: the procuring office. buyer_address. location: the site or delivery place (ward, municipality, district).
- scope: the ONLY value you write yourself: a one-sentence English summary of what is procured. \
Its quote is the notice text it summarises.
- deadline: the last date AND time for SUBMITTING bids or quotations (अन्तिम मिति, "on or before"). \
Copy the date and the time as one span, e.g. "12:00 hours on 2083-08-05 B.S. (2026-11-21 A.D.)" or \
"२०८३।०८।०३ गते दिनको १२:०० बजेसम्म". Not the publication date, the document purchase date or the opening date. \
In a corrigendum (शुद्धिपत्र), copy only the NEW deadline.
- estimated_cost: the cost estimate (लागत अनुमान) with its currency and unit words, e.g. "Rs. 1,48,75,000/-", \
"NPR 18.50 crore", "रु. ३२ लाख ५० हजार". In a table, copy the table cell.
- bid_security: bid security / bid bond / bid guarantee / धरौटी / बोलपत्र जमानत, amount or percentage as written.
- bid_security_validity: e.g. "valid for 148 days" or "valid until 2083-12-15 B.S.". bid_validity: the bid \
validity period. bid_doc_fee: bid document or form fee (दस्तुर). performance_security: the performance security percentage.
- min_avg_turnover: the minimum average annual turnover amount. min_similar_contract_value: the minimum value \
of a similar completed contract.
- procurement_type: works (construction), goods (supply, purchase), consulting (consultancy, DPR, design, \
supervision, studies, training), non_consulting (security, cleaning, vehicle or equipment hire and other services), \
or unknown. method: ncb (national open bidding, राष्ट्रिय स्तरको खुला बोलपत्र), icb (international), eoi, rfp, \
quotation (sealed quotation, सिलबन्दी दरभाउपत्र), other. evaluation_method: only if the notice states it. \
buyer_level: federal (ministry, department, federal agency or state-owned company), province (प्रदेश ministry or office), \
local (महानगरपालिका, उपमहानगरपालिका, नगरपालिका, गाउँपालिका, ward office). Put the words each choice is based on in its *_quote field.
- jv_allowed: true if joint ventures (JV, संयुक्त उपक्रम) are allowed, false if barred, null if not stated. \
domestic_preference: true only if a preference for domestic goods or bidders is stated.
- required_docs: one entry per document the bidder must submit (registration, licence, licence renewal, VAT/PAN, \
tax clearance, tax return, self-declaration, power of attorney, bid security, audit report, experience certificate, \
JV agreement, others). name: the document name exactly as written, including its fiscal year if one is given. \
If one line names several documents, make one entry per document, each quoting that line.
- requirements: each qualification criterion (turnover, experience, licence class, personnel, equipment, \
eligibility): a short English text, mandatory, category, and its verbatim source_quote.

Nepali terms: बोलपत्र = bid, दरभाउपत्र = quotation, अन्तिम मिति = last date, गते = day of month, बजे = o'clock, \
बजेसम्म = by ... o'clock, लागत अनुमान = cost estimate, धरौटी / जमानत = security, कर चुक्ता प्रमाणपत्र = tax clearance, \
कर विवरण = tax return, इजाजतपत्र = licence, नवीकरण = renewal, फर्म दर्ता = firm registration, मू.अ.कर = VAT, \
स्थायी लेखा नम्बर = PAN, आ.व. = fiscal year, संयुक्त उपक्रम = joint venture, स्वघोषणा = self-declaration."""


def build_messages(raw_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Notice text:\n<<<\n{raw_text}\n>>>"},
    ]


# --- grounding: is this string really in the notice? -----------------------------------

_PUNCT = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", " ": " "})
_BANNER = re.compile(r"^\[SYNTHETIC SEED NOTICE[^\n]*\]\s*")


def _norm_chars(text: str) -> tuple[str, list[int]]:
    """Text folded for matching (NFC, ASCII digits, casefold, one space per whitespace run) + index map."""
    out: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(unicodedata.normalize("NFC", text)):
        folded = to_ascii_digits(ch.translate(_PUNCT)).casefold()
        for c in folded:
            if c.isspace():
                if out and out[-1] == " ":
                    continue
                c = " "
            out.append(c)
            index.append(i)
    return "".join(out), index


class Grounder:
    """Locates LLM-copied strings in the notice; tolerant only of whitespace, case, digit script and quote style."""

    def __init__(self, text: str) -> None:
        self.text = unicodedata.normalize("NFC", text)
        self._norm, self._index = _norm_chars(self.text)

    def locate(self, s: str | None) -> tuple[int, int] | None:
        if not s:
            return None
        needle = _norm_chars(s)[0].strip()
        if not needle:
            return None
        pos = self._norm.find(needle)
        if pos < 0:
            return None
        return self._index[pos], self._index[pos + len(needle) - 1] + 1


def detect_language(text: str) -> NoticeLanguage:
    """Deterministic: share of Devanagari letters among all letters (thresholds fit the seed set)."""
    body = _BANNER.sub("", text)
    dev = len(re.findall(r"[ऀ-ॣॱ-ॿ]", body))
    lat = len(re.findall(r"[A-Za-z]", body))
    ratio = dev / (dev + lat) if dev + lat else 0.0
    if ratio < 0.02:
        return NoticeLanguage.EN
    if ratio > 0.92:
        return NoticeLanguage.NE
    return NoticeLanguage.MIXED


# --- post-processing ------------------------------------------------------------------

_CURRENCY_RE = re.compile(r"rs\.?|npr|nrs|रु|रू|रुपैयाँ|rupees", re.I)
_UNIT_WORD_RE = re.compile(r"thousand|lakh|lac|million|crore|arab|billion|हजार|लाख|करोड|अर्ब|मिलियन", re.I)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                 "ten": 10, "एक": 1, "दुई": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पाँच": 5, "छ": 6, "सात": 7, "आठ": 8, "नौ": 9, "दश": 10}
_YEARS_RE = re.compile(r"(\d{1,2}|" + "|".join(map(re.escape, _NUMBER_WORDS)) + r")\s*(?:\(\s*\w+\s*\)\s*)?(?:fiscal\s+|financial\s+|आर्थिक\s+)?(?:years?\b|वर्ष)", re.I)


def count_years(text: str) -> int | None:
    """'over the last three years' -> 3. None if no count or several ('best 3 of the last 5 years')."""
    found = {int(n) if n.isdigit() else _NUMBER_WORDS[n.casefold()] for n in _YEARS_RE.findall(to_ascii_digits(text))}
    return found.pop() if len(found) == 1 else None


@dataclass
class _Post:
    x: TenderExtraction
    g: Grounder
    sources: list[FieldSource] = field(default_factory=list)
    flags: list[ReviewFlag] = field(default_factory=list)

    def flag(self, name: str, reason: str, raw: str | None = None) -> None:
        self.flags.append(ReviewFlag(field=name, reason=reason, raw=raw))

    def source(self, name: str, value: Any, raw: str | None, quote: str | None) -> tuple[int, int] | None:
        span = self.g.locate(quote) or self.g.locate(raw)
        self.sources.append(FieldSource(field=name, value=value, raw=raw, quote=quote, span=span, quote_found=span is not None))
        return span

    def text(self, name: str, gr: Grounded | None) -> str | None:
        """A display string. Kept even if not found, but flagged as possibly not from the notice."""
        if gr is None:
            return None
        written = name == "scope"  # the one value the LLM writes itself: only its quote is checked
        if self.source(name, gr.value, None if written else gr.value, gr.quote) is None:
            self.flag(name, "quote not found in the notice text" if written else "value and quote not found in the notice text",
                      gr.quote if written else gr.value)
        return gr.value

    def parsed(self, name: str, gr: Grounded | None, parse: Callable[[str], T], show: Callable[[T], Any] = lambda v: v) -> T | None:
        """A deterministic value from a verbatim raw string; null + flag if it is not verbatim or does not parse."""
        if gr is None:
            return None
        value: T | None = None
        if self.g.locate(gr.value) is None:
            self.flag(name, "raw value is not verbatim in the notice text; not parsed", gr.value)
        else:
            try:
                value = parse(gr.value)
            except ValueError as exc:
                self.flag(name, f"cannot read: {exc}", gr.value)
        self.source(name, None if value is None else show(value), gr.value, gr.quote)
        return value

    def amount(self, raw: str) -> int:
        if has_thousands_marker(self.g.text) and not (_CURRENCY_RE.search(raw) or _UNIT_WORD_RE.search(raw)):
            raise ValueError("the notice states some figures in thousands and this one has no currency or unit")
        return parse_npr(raw)


def _deadline(p: _Post, record: dict[str, Any]) -> None:
    gr = p.x.deadline
    if gr is None:
        return
    if p.g.locate(gr.value) is None:
        p.flag("deadline", "raw value is not verbatim in the notice text; not parsed", gr.value)
        p.source("deadline_ad", None, gr.value, gr.quote)
        return
    parsed = parse_deadline(gr.value)
    for issue in parsed.issues:
        p.flag("deadline", issue, gr.value)
    if parsed.deadline is None:
        p.source("deadline_ad", None, gr.value, gr.quote)
        return
    record["deadline_ad"] = parsed.deadline
    record["deadline_bs_iso"] = parsed.bs.iso()
    if re.search(r"(?<!\d)20[6-9]\d(?!\d)", to_ascii_digits(gr.value)):
        record["deadline_bs_raw"] = gr.value
    p.source("deadline_ad", parsed.deadline.isoformat(), gr.value, gr.quote)
    p.source("deadline_bs_iso", parsed.bs.iso(), gr.value, gr.quote)


def _bid_security(p: _Post, record: dict[str, Any]) -> None:
    x = p.x
    amount = percent = None
    if x.bid_security is not None:
        if re.search(r"%|percent|per\s*cent|प्रतिशत", x.bid_security.value, re.I):
            percent = p.parsed("bid_security.percent", x.bid_security, parse_percent)
        else:
            amount = p.parsed("bid_security.amount_npr", x.bid_security, p.amount)
    validity_days = None
    gr = x.bid_security_validity
    if gr is not None:
        if re.search(r"days?\b|दिन", gr.value, re.I):
            validity_days = p.parsed("bid_security.validity_days", gr, parse_days)
        else:
            validity_days = p.parsed("bid_security.validity_days", gr, lambda raw: _days_until(raw, record))
    if amount is not None or percent is not None:
        record["bid_security"] = BidSecurity(amount_npr=amount, percent=percent, validity_days=validity_days)
    elif validity_days is not None:
        p.flag("bid_security", "validity stated but no readable amount or percentage", x.bid_security.value if x.bid_security else None)


def _days_until(raw: str, record: dict[str, Any]) -> int:
    """'valid until 2083-12-15 B.S.' -> days after the submission deadline (the rules count validity from it)."""
    until = parse_deadline(raw)
    if until.deadline is None:
        raise ValueError("; ".join(until.issues))
    deadline = record.get("deadline_ad")
    if deadline is None:
        raise ValueError("validity is a date but the submission deadline is unknown")
    days = (until.ad - deadline.astimezone(NPT).date()).days
    if days <= 0:
        raise ValueError(f"validity date {until.ad.isoformat()} is not after the deadline")
    return days


def _location(p: _Post, record: dict[str, Any]) -> None:
    x = p.x
    for name, gr in (("location", x.location), ("buyer_address", x.buyer_address), ("buyer", x.buyer)):
        if gr is None:
            continue
        loc = normalize_location(gr.value)
        if loc.candidates and not loc.district:
            p.flag("district", f"location names several districts: {', '.join(loc.candidates)}", gr.value)
        if loc.district or loc.province:
            record["district"], record["province"] = loc.district, loc.province
            p.source("district", loc.district, gr.value, gr.quote)
            p.source("province", loc.province.value if loc.province else None, gr.value, gr.quote)
            return


def _required_docs(p: _Post, record: dict[str, Any]) -> list[RequiredDoc]:
    docs: list[RequiredDoc] = []
    seen: set[tuple[DocType, str | None]] = set()
    for i, d in enumerate(p.x.required_docs):
        name = f"required_docs[{i}]"
        span = p.source(name, d.name, d.name, d.source_quote)
        if span is None:
            p.flag(name, "document name and quote not found in the notice text", d.name)
        types = classify_document(d.name) or classify_document(d.source_quote) or [DocType.OTHER]
        if DocType.TAX_CLEARANCE in types and DocType.TAX_RETURN in types:
            types.remove(DocType.TAX_RETURN)  # "clearance, or proof of tax return": the Rule 40(2)(d) alternative
        years = find_fiscal_years(d.name) or find_fiscal_years(d.source_quote)
        if len(years) > 1:
            p.flag(name, f"several fiscal years named: {', '.join(years)}", d.name)
        for doc_type in types:
            fy = years[0] if len(years) == 1 and doc_type in _FY_DOCS else None
            if (doc_type, fy) in seen:
                continue
            seen.add((doc_type, fy))
            docs.append(RequiredDoc(doc_type=doc_type, description=d.name, fiscal_year_bs=fy, mandatory=d.mandatory,
                                    source_quote=d.source_quote))
    if record.get("bid_security") is not None and not any(doc.doc_type is DocType.BID_SECURITY for doc in docs):
        gr = p.x.bid_security
        docs.append(RequiredDoc(doc_type=DocType.BID_SECURITY, description=gr.value, source_quote=gr.quote))
    return docs


_FY_DOCS = {DocType.TAX_CLEARANCE, DocType.TAX_RETURN, DocType.LICENCE_RENEWAL, DocType.AUDIT_REPORT}


def postprocess(x: TenderExtraction, raw_text: str) -> TenderRecord:
    """Deterministic: verbatim LLM strings -> typed, grounded TenderRecord. No LLM, no guessing."""
    p = _Post(x, Grounder(raw_text))
    record: dict[str, Any] = {}

    record["title"] = p.text("title", x.title)
    record["reference_no"] = p.text("reference_no", x.reference_no)
    record["buyer"] = p.text("buyer", x.buyer)
    record["buyer_address"] = p.text("buyer_address", x.buyer_address)
    record["location"] = p.text("location", x.location)
    record["scope"] = p.text("scope", x.scope)
    for name in ("procurement_type", "method", "evaluation_method"):
        value = getattr(x, name)
        record[name] = value
        p.source(name, value.value if value else None, None, getattr(x, f"{name}_quote"))
    record["buyer_level"] = x.buyer_level
    record["language"] = detect_language(raw_text)

    _deadline(p, record)
    record["estimated_cost_npr"] = p.parsed("estimated_cost_npr", x.estimated_cost, p.amount)
    _bid_security(p, record)
    record["bid_validity_days"] = p.parsed("bid_validity_days", x.bid_validity, parse_days)
    record["bid_doc_fee_npr"] = p.parsed("bid_doc_fee_npr", x.bid_doc_fee, p.amount)
    record["performance_security_percent"] = p.parsed("performance_security_percent", x.performance_security, parse_percent)
    _location(p, record)

    record["jv_allowed"] = x.jv_allowed
    p.source("jv_allowed", x.jv_allowed, None, x.jv_quote)
    record["domestic_preference"] = x.domestic_preference
    p.source("domestic_preference", x.domestic_preference, None, x.domestic_preference_quote)

    turnover = p.parsed("criteria.min_avg_turnover_npr", x.min_avg_turnover, p.amount)
    record["criteria"] = TenderCriteria(
        min_avg_turnover_npr=turnover,
        turnover_years=count_years(x.min_avg_turnover.quote) if turnover is not None else None,
        min_similar_value_npr=p.parsed("criteria.min_similar_value_npr", x.min_similar_contract_value, p.amount),
    )

    record["required_docs"] = _required_docs(p, record)
    for i, req in enumerate(x.requirements):
        if p.source(f"requirements[{i}]", req.text, None, req.source_quote) is None:
            p.flag(f"requirements[{i}]", "source quote not found in the notice text", req.source_quote)
    record["requirements"] = list(x.requirements)

    tender = TenderRecord(**record, sources=p.sources, review_flags=p.flags, needs_review=bool(p.flags))
    tender.bid_security_due = calc_bid_security(tender) if tender.bid_security else None
    return tender


# --- LLM call and DB write ------------------------------------------------------------

def extract_tender(client: LLMClient, raw_text: str, *, tender_id: int | None = None) -> TenderRecord:
    """One Scout run. Raises LLMOutputError / LLMTransportError (agent_runs row already recorded)."""
    if not raw_text or not raw_text.strip():
        raise ValueError("empty notice text")
    extraction = client.chat(stage=Stage.SCOUT, messages=build_messages(raw_text), schema=TenderExtraction,
                             tender_id=tender_id)
    return postprocess(extraction, raw_text)


def apply_record(tender: Tender, record: TenderRecord) -> None:
    """Fill the denormalised tenders columns from the record (spec section 11 + Nepal columns)."""
    tender.record_json = record.model_dump(mode="json")
    tender.title = record.title
    tender.buyer = record.buyer
    tender.deadline = record.deadline_ad
    tender.location = record.location
    tender.procurement_type = record.procurement_type.value
    tender.method = record.method.value
    tender.province = record.province.value if record.province else None
    tender.district = record.district
    tender.deadline_bs = record.deadline_bs_iso
    tender.estimated_cost_npr = record.estimated_cost_npr
    tender.language = record.language.value


def run_scout(session: Session, client: LLMClient, tender: Tender) -> TenderRecord | None:
    """Extract one tender row: status `extracted` with the record, or `failed` (record left empty)."""
    try:
        record = extract_tender(client, tender.raw_text or "", tender_id=tender.id)
    except (LLMError, ValueError):
        tender.status = TenderStatus.FAILED.value
        tender.updated_at = func.now()
        session.commit()
        return None
    apply_record(tender, record)
    tender.status = TenderStatus.EXTRACTED.value
    tender.updated_at = func.now()
    session.commit()
    return record


def scout_new_tenders(session: Session, client: LLMClient, tender_ids: list[int] | None = None) -> dict[int, TenderRecord | None]:
    """Run Scout on every `new` tender (or just these ids, if still `new`)."""
    query = select(Tender).where(Tender.status == TenderStatus.NEW.value).order_by(Tender.id)
    if tender_ids is not None:
        query = query.where(Tender.id.in_(tender_ids))
    return {t.id: run_scout(session, client, t) for t in session.scalars(query)}


# --- dev CLI ----------------------------------------------------------------------------

def _short(value: Any, width: int) -> str:
    s = "-" if value is None else str(value)
    return s if len(s) <= width else s[: width - 1] + "~"


def format_table(rows: list[tuple[str, TenderRecord | None, str | None]]) -> str:
    """One line per notice: id, deadline BS/AD, cost, bid security, doc types, flags."""
    head = f"{'id':<4} {'status':<9} {'deadline_bs':<11} {'deadline_ad (NPT)':<17} {'cost_npr':>13} {'bid_sec':>11} " \
           f"{'lang':<5} {'district':<12} {'docs':<44} flags"
    lines = [head, "-" * len(head)]
    for nid, rec, error in rows:
        if rec is None:
            lines.append(f"{nid:<4} {'FAILED':<9} {_short(error, 120)}")
            continue
        bs = rec.bid_security
        sec = (bs.amount_npr if bs.amount_npr is not None else f"{bs.percent}%") if bs else None
        docs = ",".join(sorted({d.doc_type.value for d in rec.required_docs}))
        flags = "; ".join(f"{f.field}: {f.reason}" for f in rec.review_flags)
        ad = rec.deadline_ad.astimezone(NPT).strftime("%Y-%m-%d %H:%M") if rec.deadline_ad else None
        lines.append(f"{nid:<4} {'review' if rec.needs_review else 'ok':<9} {_short(rec.deadline_bs_iso, 11):<11} {_short(ad, 17):<17} "
                     f"{_short(rec.estimated_cost_npr, 13):>13} {_short(sec, 11):>11} {rec.language.value:<5} "
                     f"{_short(rec.district, 12):<12} {_short(docs, 44):<44} {_short(flags, 160)}")
    return "\n".join(lines)


def run_seed_offline(client: LLMClient, seed_dir: Path, only: set[str] | None) -> list[tuple[str, TenderRecord | None, str | None]]:
    from ingest.seed_tenders import load_manifest

    rows = []
    for entry in load_manifest(seed_dir)["notices"]:
        if only and entry["id"] not in only:
            continue
        text = (seed_dir / entry["file"]).read_text(encoding="utf-8")
        print(f"scout {entry['id']} ...", file=sys.stderr, flush=True)
        try:
            rows.append((entry["id"], extract_tender(client, text), None))
        except (LLMError, ValueError) as exc:
            rows.append((entry["id"], None, str(exc)))
    return rows


def run_seed_db(client_factory: Callable[[Callable], LLMClient], seed_dir: Path, only: set[str] | None, database_url: str):
    from sqlalchemy.orm import sessionmaker

    from db.runs import make_run_recorder
    from db.session import make_engine
    from ingest.notices import upsert_notices
    from ingest.seed_tenders import load_manifest, load_seed_notices, seed_source_url

    factory = sessionmaker(make_engine(database_url), expire_on_commit=False)
    ids_by_url = {seed_source_url(e["file"]): e["id"] for e in load_manifest(seed_dir)["notices"]}
    notices = [n for n in load_seed_notices(seed_dir) if not only or ids_by_url[n.source_url] in only]
    rows = []
    with factory() as session, client_factory(make_run_recorder(factory)) as client:
        _, tender_ids = upsert_notices(session, notices)
        for tender in session.scalars(select(Tender).where(Tender.id.in_(tender_ids)).order_by(Tender.id)):
            nid = ids_by_url[tender.source_url]
            print(f"scout {nid} (tender {tender.id}) ...", file=sys.stderr, flush=True)
            record = run_scout(session, client, tender)
            rows.append((nid, record, None if record else "LLM output invalid or unreachable; status=failed (see agent_runs)"))
    return rows


def main(argv: list[str] | None = None) -> int:
    from config import get_settings

    ap = argparse.ArgumentParser(prog="python -m api.agents.scout", description="Run Scout over the seed notices.")
    ap.add_argument("--seed", action="store_true", required=True, help="use data/seed_tenders (the only source for now)")
    ap.add_argument("--only", help="comma-separated seed ids, e.g. 001,005")
    ap.add_argument("--db", action="store_true", help="upsert into DATABASE_URL, write tenders rows + agent_runs")
    ap.add_argument("--json", type=Path, help="also write {seed_id: TenderRecord | null} to this file")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    only = set(args.only.split(",")) if args.only else None
    runs: list = []
    if args.db:
        rows = run_seed_db(lambda rec: LLMClient(rec, settings), settings.seed_tenders_dir, only, settings.database_url)
    else:
        with LLMClient(runs.append, settings) as client:
            rows = run_seed_offline(client, settings.seed_tenders_dir, only)
    print(format_table(rows))
    ok = sum(1 for _, r, _ in rows if r is not None)
    print(f"\n{ok}/{len(rows)} extracted, {sum(1 for _, r, _ in rows if r and r.needs_review)} need review, model {settings.llm_model}")
    if args.json:
        args.json.write_text(json.dumps({nid: r.model_dump(mode="json") if r else None for nid, r, _ in rows},
                                        ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

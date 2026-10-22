"""Proposal agent: tender + compliance report + KB chunks retrieved per section -> ProposalSection[] (spec section 8.1).

Code and model split the work so that nothing in the document is invented:

- **Section plan (code, `plan_sections`).** A template per procurement family (`*_BASE`, kept in `*_ORDER`): goods/works/
  non-consulting get cover letter, bidder information and eligibility, technical specification compliance,
  delivery or work plan, relevant experience, financial capacity, declarations; consulting gets cover letter,
  understanding of the ToR, methodology, work plan, team, relevant experience. The notice adds sections (its
  personnel / equipment / eligibility / financial requirements, a self-declaration it asks for) and an EOI
  reorders them (experience leads shortlisting). Each requirement is routed to one section by its category.
- **Per-section retrieval (spec section 10.4).** Query = section topic + the requirements the section answers;
  top-k chunks (`PROPOSAL_TOP_K`). No chunk -> no model call: the section is a stub flagged `no_kb_material`.
- **Text (model, `generate_section`).** One `ProposalSectionDraft` per section at the proposal temperature
  (0.4, hard rule 7). The model returns the chunk ids it used and writes every identifier and figure as a
  placeholder: `{{company.pan}}`, `{{tender.deadline}}`, or `{{fact.<key>}}` for a value it copied verbatim
  from an excerpt.
- **Rendering (code, `build_section`).** Placeholders are filled from the company record, the tender record,
  the clock, or a fact whose quote is verbatim in its cited chunk. A missing value renders `[MISSING: ...]`;
  any amount, PAN-like number, id or 4+ digit figure the model wrote itself is masked `⟦unsourced: ...⟧`.
  A section with no valid citation is kept and flagged `ungrounded` (hard rule 8), for Review and the person.

Language: the notice's (`en` -> English; `ne` and `mixed` -> Nepali) unless English is forced
(`PROPOSAL_FORCE_ENGLISH` or the request). Dates render in BS and AD when the notice used BS.

`run_proposal` stores a new `proposals` version (old ones are kept) and sets the tender `drafted`, or `failed`
if a model or embedding call fails (no partial version is stored).
"""

import hashlib
import json
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.compliance import RetrievalError, compliance_view, proposal_allowed
from agents.matching import load_company
from agents.scout import Grounder
from config import Settings, get_settings
from db.models import AgentRunRow, ProposalRow, Tender
from db.runs import report_progress
from db.search import ChunkHit, retrieve
from nepal.dates import NPT, ad_to_bs, format_bs
from nepal.numbers import format_npr, to_ascii_digits, to_devanagari_digits
from pipeline.llm import LLMClient, LLMError
from schemas import (CompanyProfile, NoticeLanguage, ProcurementMethod, ProcurementType, ProgressItem, Proposal,
                     ProposalLanguage, ProposalSection, ProposalSectionDraft, ProposalStatus, ProposalSummary,
                     RequirementCategory, ResolvedPlaceholder, SectionFlag, SectionFlagKind, SectionProgress, Stage,
                     StageProgress, TenderRecord, TenderStatus)
from schemas.enums import DocType

K = SectionFlagKind
DETERMINISTIC_MODEL = "deterministic"  # agent_runs.model for the planning/rendering row (no LLM call)

# --- section templates ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionTemplate:
    key: str
    title_en: str
    title_ne: str  # model-written Nepali, [VERIFY] with a native reader (PROGRESS issue 60)
    topic: str  # retrieval query stem
    guidance: str  # what the section must say (shown to the model)
    with_scope: bool = False  # add the tender scope to the retrieval query

    def title(self, language: ProposalLanguage) -> str:
        return self.title_ne if language is ProposalLanguage.NE else self.title_en


TEMPLATES: dict[str, SectionTemplate] = {t.key: t for t in (
    SectionTemplate("cover_letter", "Cover letter", "आवरण पत्र",
                    "company name, registration, services offered, office address and contact; intent to bid",
                    "A short formal letter to {{tender.buyer}} submitting the bid for {{tender.title}} "
                    "(ref. {{tender.reference_no}}) before {{tender.deadline}}, signed for {{company.name}}. Say who the "
                    "company is in one or two sentences from the excerpts."),
    SectionTemplate("bidder_info", "Bidder information and eligibility", "बोलपत्रदाताको विवरण तथा योग्यता",
                    "company registration certificate, PAN/VAT registration, construction or business licence class "
                    "and renewal, tax clearance, eligibility to bid",
                    "Legal name, address, registration date, PAN/VAT and licence (type, class, number, renewal year) "
                    "as placeholders, then the eligibility documents the excerpts show the company holds. Do not claim a "
                    "document the excerpts do not show."),
    SectionTemplate("technical_compliance", "Compliance with technical specifications", "प्राविधिक विवरण अनुरूपता",
                    "technical capability, specifications, materials, standards, quality control and testing",
                    "How the company will meet the specifications and quality requirements, using the capability the "
                    "excerpts describe.", with_scope=True),
    SectionTemplate("delivery_plan", "Delivery schedule", "आपूर्ति तालिका",
                    "delivery schedule, supply chain, logistics, warehousing and after-sales support",
                    "How and when the goods will be supplied, delivered and supported, within the period the notice "
                    "sets.", with_scope=True),
    SectionTemplate("work_plan", "Work plan and schedule", "कार्य योजना तथा तालिका",
                    "work plan, construction schedule, mobilisation, site management, safety and quality assurance",
                    "Phases of the work in order (mobilisation, main works, completion), site management, safety and "
                    "quality control, based on how the company has run similar work.", with_scope=True),
    SectionTemplate("team", "Team and key personnel", "टोली तथा प्रमुख जनशक्ति",
                    "key personnel, engineers, team leader, staff qualifications and years of experience",
                    "The people the company will assign and their roles and qualifications, only as the excerpts give "
                    "them (names and figures as facts)."),
    SectionTemplate("key_equipment", "Key equipment", "प्रमुख उपकरण",
                    "equipment and machinery owned or hired: excavator, roller, tipper, mixer, batching plant",
                    "Equipment the company owns or can hire for this work, only as the excerpts list it."),
    SectionTemplate("relevant_experience", "Relevant experience", "सम्बन्धित अनुभव",
                    "completed similar projects, experience certificates, contract values, clients and completion",
                    "Completed contracts similar to this one: client, work, value and completion, each as a fact copied "
                    "from the excerpts. Explain briefly why each is similar.", with_scope=True),
    SectionTemplate("financial_capacity", "Financial capacity", "आर्थिक क्षमता",
                    "annual turnover, audited financial statements, bank details, credit facility, liquid assets",
                    "Average annual turnover ({{company.turnover_average}}) and the most recent year "
                    "({{company.turnover_latest}}), plus any bank, credit or liquid-asset evidence in the excerpts."),
    SectionTemplate("declarations", "Declarations", "घोषणा",
                    "self-declaration, not blacklisted, no conflict of interest, eligible to bid, power of attorney",
                    "The bidder's declarations: eligible to bid, not blacklisted or debarred, no conflict of interest, "
                    "bid valid for {{tender.bid_validity_days}} days. State that the signed forms of the bidding document "
                    "are attached; do not invent signatories."),
    SectionTemplate("understanding_tor", "Understanding of the Terms of Reference", "कार्यादेश (ToR) को बुझाइ",
                    "understanding of the assignment, objectives, scope of services, deliverables",
                    "The objectives and scope of the assignment in the company's words, and what matters most for "
                    "the client.", with_scope=True),
    SectionTemplate("methodology", "Approach and methodology", "कार्य विधि",
                    "approach and methodology, consulting services method, quality assurance, reporting",
                    "How the company will carry out the assignment, step by step, based on how it has done similar "
                    "assignments.", with_scope=True),
)}

# Order of every section a family can have; the plan keeps the selected ones in this order.
GOODS_WORKS_ORDER = ("cover_letter", "bidder_info", "technical_compliance", "delivery_plan", "work_plan", "team",
                     "key_equipment", "relevant_experience", "financial_capacity", "declarations")
CONSULTING_ORDER = ("cover_letter", "bidder_info", "understanding_tor", "methodology", "work_plan", "team",
                    "relevant_experience", "financial_capacity", "declarations")
# EOI (PPR Rule 70): shortlisting is on experience and team, and there is no methodology yet.
EOI_ORDER = ("cover_letter", "bidder_info", "relevant_experience", "team", "understanding_tor", "financial_capacity",
             "declarations")

GOODS_BASE = ("cover_letter", "bidder_info", "technical_compliance", "delivery_plan", "relevant_experience",
              "financial_capacity", "declarations")
WORKS_BASE = ("cover_letter", "bidder_info", "technical_compliance", "work_plan", "relevant_experience",
              "financial_capacity", "declarations")
CONSULTING_BASE = ("cover_letter", "understanding_tor", "methodology", "work_plan", "team", "relevant_experience")
EOI_BASE = ("cover_letter", "relevant_experience", "team", "understanding_tor")

C = RequirementCategory
GOODS_WORKS_ROUTES = {C.ELIGIBILITY: "bidder_info", C.FINANCIAL: "financial_capacity", C.EXPERIENCE: "relevant_experience",
                      C.TECHNICAL: "technical_compliance", C.PERSONNEL: "team", C.EQUIPMENT: "key_equipment",
                      C.OTHER: "technical_compliance"}
CONSULTING_ROUTES = {C.ELIGIBILITY: "bidder_info", C.FINANCIAL: "financial_capacity", C.EXPERIENCE: "relevant_experience",
                     C.TECHNICAL: "methodology", C.PERSONNEL: "team", C.EQUIPMENT: "methodology",
                     C.OTHER: "understanding_tor"}
EOI_ROUTES = CONSULTING_ROUTES | {C.TECHNICAL: "understanding_tor", C.EQUIPMENT: "understanding_tor"}


@dataclass
class PlannedSection:
    template: SectionTemplate
    requirement_indices: list[int] = field(default_factory=list)

    @property
    def key(self) -> str:
        return self.template.key


def _family(record: TenderRecord) -> tuple[tuple[str, ...], tuple[str, ...], dict]:
    """(base sections, order, requirement routes) for the tender's procurement type and method."""
    if record.procurement_type is ProcurementType.CONSULTING:
        if record.method is ProcurementMethod.EOI:
            return EOI_BASE, EOI_ORDER, EOI_ROUTES
        return CONSULTING_BASE, CONSULTING_ORDER, CONSULTING_ROUTES
    base = GOODS_BASE if record.procurement_type is ProcurementType.GOODS else WORKS_BASE
    return base, GOODS_WORKS_ORDER, GOODS_WORKS_ROUTES


def plan_sections(record: TenderRecord) -> list[PlannedSection]:
    """The section plan: the family template, plus sections the notice's requirements call for, in family order."""
    base, order, routes = _family(record)
    routed: dict[str, list[int]] = {}
    for index, req in enumerate(record.requirements):
        routed.setdefault(routes[req.category], []).append(index)
    selected = set(base) | set(routed)
    if any(d.doc_type in (DocType.SELF_DECLARATION, DocType.POWER_OF_ATTORNEY) for d in record.required_docs):
        selected.add("declarations")
    return [PlannedSection(TEMPLATES[key], routed.get(key, [])) for key in order if key in selected]


_QUERY_CHARS = 500


def section_query(section: PlannedSection, record: TenderRecord) -> str:
    """Retrieval query: the section topic plus the tender requirements it answers (spec section 10.4)."""
    parts = [section.template.topic]
    if section.template.with_scope:
        parts.append(record.scope)
    parts += [record.requirements[i].text for i in section.requirement_indices]
    return ". ".join(parts)[:_QUERY_CHARS]


# --- language and dates ---------------------------------------------------------------------------------------

_BS_YEAR = re.compile(r"(?<!\d)20[6-9]\d(?!\d)")


def proposal_language(record: TenderRecord, *, force_english: bool = False) -> ProposalLanguage:
    """The notice's language; `mixed` notices are mostly local-body Nepali notices, so they get Nepali."""
    if force_english or record.language is NoticeLanguage.EN:
        return ProposalLanguage.EN
    return ProposalLanguage.NE


def uses_bs(record: TenderRecord, raw_text: str | None = None) -> bool:
    """The notice wrote a BS date (its deadline, or a BS year anywhere in the text)."""
    return record.deadline_bs_raw is not None or bool(raw_text and _BS_YEAR.search(to_ascii_digits(raw_text)))


def format_date(value: date | datetime, language: ProposalLanguage, *, with_bs: bool) -> str:
    """'5 Mangsir 2083 BS (21 November 2026 AD)' / '५ मंसिर २०८३ (२०२६-११-२१)'; AD only when the notice used no BS."""
    when = ""
    if isinstance(value, datetime):
        local = value.astimezone(NPT)
        if (local.hour, local.minute) != (23, 59):
            when = f", {local:%H:%M} NPT"
        value = local.date()
    ne = language is ProposalLanguage.NE
    ad = to_devanagari_digits(value.isoformat()) if ne else f"{value.day} {value:%B %Y}"
    if not with_bs:
        return (ad + when) if not ne else to_devanagari_digits(ad + when)
    bs = format_bs(ad_to_bs(value), long=True, ne=ne)
    text = f"{bs} ({ad}){when}" if ne else f"{bs} BS ({ad} AD){when}"
    return to_devanagari_digits(text) if ne else text


def format_money(amount: int, language: ProposalLanguage) -> str:
    text = format_npr(amount)  # Rs 1,48,75,000 (lakh/crore grouping)
    return to_devanagari_digits(text.replace("Rs ", "रु. ")) if language is ProposalLanguage.NE else text


# --- placeholders ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Placeholder:
    value: str | None
    source: str
    description: str


@dataclass
class ProposalContext:
    record: TenderRecord
    company: CompanyProfile
    language: ProposalLanguage
    now: datetime
    with_bs: bool
    tender_id: int | None = None
    placeholders: dict[str, Placeholder] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.placeholders = placeholder_values(self.company, self.record, self.language, self.now, with_bs=self.with_bs)


def placeholder_values(company: CompanyProfile, record: TenderRecord, language: ProposalLanguage, now: datetime, *,
                       with_bs: bool) -> dict[str, Placeholder]:
    """Every placeholder the model may use, with its value from the records (None = not on record)."""
    def money(amount: int | None) -> str | None:
        return format_money(amount, language) if amount is not None else None

    def day(value: date | datetime | None) -> str | None:
        return format_date(value, language, with_bs=with_bs) if value is not None else None

    licence = company.licences[0] if company.licences else None
    years = sorted(company.turnover, key=lambda t: t.fiscal_year_bs)[-3:]  # the profile's latest three FYs
    average = sum(t.amount_npr for t in years) // len(years) if years else None
    bid_security = record.bid_security_due.amount_npr if record.bid_security_due else (
        record.bid_security.amount_npr if record.bid_security else None)
    co, td = "company", "tender"
    raw: dict[str, tuple[Any, str, str]] = {
        "company.name": (company.name, co, "company legal name"),
        "company.pan": (company.pan_number, co, "PAN number"),
        "company.vat": (company.vat_number, co, "VAT number"),
        "company.address": (company.location, co, "registered office address"),
        "company.registration_date": (day(company.registration_date), co, "company registration date"),
        "company.licence_type": (licence.licence_type if licence else None, co, "licence type"),
        "company.licence_class": (licence.licence_class.value if licence and licence.licence_class else None, co,
                                  "contractor licence class"),
        "company.licence_number": (licence.licence_number if licence else None, co, "licence number"),
        "company.licence_issuer": (licence.issuing_body if licence else None, co, "licence issuing body"),
        "company.licence_renewed_fy": (licence.last_renewed_fy_bs if licence else None, co,
                                       "fiscal year the licence was last renewed"),
        "company.turnover_average": (money(average), co, f"average annual turnover of the last {len(years)} fiscal years"),
        "company.turnover_latest": (money(years[-1].amount_npr) if years else None, co,
                                    f"turnover of FY {years[-1].fiscal_year_bs}" if years else "latest turnover"),
        "company.districts_served": (", ".join(company.districts_served) or None, co, "districts the company works in"),
        "company.jv_partner": (company.jv_partners[0].name if company.jv_partners else None, co, "joint-venture partner"),
        "tender.title": (record.title, td, "tender title"),
        "tender.reference_no": (record.reference_no, td, "tender / IFB reference number"),
        "tender.buyer": (record.buyer, td, "procuring entity"),
        "tender.buyer_address": (record.buyer_address, td, "procuring entity address"),
        "tender.location": (record.location or record.district, td, "site / delivery location"),
        "tender.deadline": (day(record.deadline_ad), td, "bid submission deadline"),
        "tender.estimated_cost": (money(record.estimated_cost_npr), td, "cost estimate"),
        "tender.bid_security": (money(bid_security), td, "bid security amount"),
        "tender.bid_validity_days": (str(record.bid_validity_days) if record.bid_validity_days else None, td,
                                     "bid validity in days"),
        "today": (day(now.astimezone(NPT).date()), "clock", "today's date"),
    }
    if language is ProposalLanguage.NE:
        for name in ("tender.bid_validity_days", "company.licence_renewed_fy"):
            value, source, desc = raw[name]
            raw[name] = (to_devanagari_digits(value) if value else None, source, desc)
    return {name: Placeholder(None if value in (None, "") else str(value), source, desc)
            for name, (value, source, desc) in raw.items()}


_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][\w]*(?:\.[\w]+)*)\s*\}\}")
_D = r"[0-9०-९]"
# Figures the model must not write itself: amounts, ids with digits, and any 4+ digit number (PAN, years, dates).
_UNSOURCED = re.compile(
    rf"(?:\b(?:Rs|NRs|NPR|INR)\.?|रु\.?)\s*{_D}[0-9०-९,.]*(?:\s*(?:lakh|crore|million|arab|लाख|करोड))?"
    rf"|{_D}[0-9०-९,.]*\s*(?:lakhs?|crores?|million|arab|लाख|करोड)\b"
    rf"|\b(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9/-]*\d)[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)+"
    rf"|(?<![\w.]){_D}(?:{_D}|[,./।-](?={_D})){{3,}}",
    re.I)
UNSOURCED_MARK = "⟦unsourced: {}⟧"


def mask_unsourced(text: str) -> tuple[str, list[str]]:
    """Mask figures written outside placeholders. Returns (text, masked figures)."""
    found: list[str] = []

    def mask(m: re.Match) -> str:
        found.append(m.group(0).strip())
        return UNSOURCED_MARK.format(m.group(0).strip())

    pieces, last = [], 0
    for m in _PLACEHOLDER.finditer(text):
        pieces.append(_UNSOURCED.sub(mask, text[last:m.start()]))
        pieces.append(m.group(0))
        last = m.end()
    pieces.append(_UNSOURCED.sub(mask, text[last:]))
    return "".join(pieces), found


def resolve_placeholders(text: str, values: dict[str, Placeholder], facts: dict[str, tuple[str, int] | None]
                         ) -> tuple[str, list[ResolvedPlaceholder], list[SectionFlag]]:
    """Fill {{name}} from the records or verified facts; unknown or empty ones become visible markers + flags.

    `facts` maps a fact key to (verbatim quote, chunk id), or None if its quote failed the verbatim check.
    """
    resolved: dict[str, ResolvedPlaceholder] = {}
    flags: list[SectionFlag] = []

    def fill(m: re.Match) -> str:
        name = m.group(1)
        if name.startswith("fact."):
            key = name[5:]
            if key not in facts:
                return _flag_once(name, f"[UNKNOWN: {name}]", K.UNKNOWN_PLACEHOLDER, f"{{{{{name}}}}} has no matching fact")
            if facts[key] is None:
                return _flag_once(name, f"[UNVERIFIED: {name}]", K.FACT_NOT_VERBATIM,
                                  f"{{{{{name}}}}}: its quote is not verbatim in the cited excerpt")
            quote, chunk_id = facts[key]
            resolved[name] = ResolvedPlaceholder(name=name, value=quote, source=f"chunk {chunk_id}")
            return quote
        if name not in values:
            return _flag_once(name, f"[UNKNOWN: {name}]", K.UNKNOWN_PLACEHOLDER, f"{{{{{name}}}}} is not a known placeholder")
        ph = values[name]
        resolved[name] = ResolvedPlaceholder(name=name, value=ph.value, source=ph.source)
        if ph.value is None:
            return _flag_once(name, f"[MISSING: {name}]", K.MISSING_VALUE, f"{ph.description} ({name}) is not on record")
        return ph.value

    seen: set[str] = set()

    def _flag_once(name: str, marker: str, kind: SectionFlagKind, detail: str) -> str:
        if name not in seen:
            seen.add(name)
            flags.append(SectionFlag(kind=kind, detail=detail))
        return marker

    rendered = _PLACEHOLDER.sub(fill, text)
    return rendered, list(resolved.values()), flags


# --- one section ----------------------------------------------------------------------------------------------

SYSTEM_PROMPT = """You write ONE section of a bid or proposal that a company in Nepal will submit for a public tender.

Use ONLY the tender facts and the knowledge-base excerpts given; each excerpt is marked [chunk N].
Rules:
- Never type a number, amount, date, year, PAN/VAT number, registration/licence/certificate number, or project name
  yourself. Write a placeholder instead:
  * one from the PLACEHOLDERS list, e.g. {{{{company.pan}}}}, or
  * a value copied from an excerpt: add {{"key": "...", "chunk_id": N, "quote": "..."}} to facts, copying the quote
    character for character from that excerpt, and write {{{{fact.<key>}}}} in the body.
- Do not invent experience, staff, equipment, certificates or capabilities. If the excerpts do not support something
  the section needs, leave it out and name it in "missing".
- cited_chunk_ids: the chunk numbers your text relies on; [] if no excerpt is relevant.
- body: Markdown paragraphs or bullet points, no heading, about 80-250 words, formal and factual.
- Write the body in {language}.
Reply with JSON only."""

_LANGUAGE_NAME = {ProposalLanguage.EN: "English", ProposalLanguage.NE: "Nepali (Devanagari script)"}
_CHUNK_CHARS = 900


def build_messages(section: PlannedSection, ctx: ProposalContext, chunks: Sequence[ChunkHit]) -> list[dict[str, str]]:
    record = ctx.record
    reqs = "\n".join(f"- ({'mandatory' if record.requirements[i].mandatory else 'optional'}) {record.requirements[i].text}"
                     for i in section.requirement_indices) or "- (none specific; follow the section guidance)"
    available = "\n".join(f"{{{{{name}}}}} - {ph.description}" for name, ph in ctx.placeholders.items()
                          if ph.value is not None)
    kb = "\n\n".join(f"[chunk {c.chunk_id}] ({c.doc_type.value}, {c.filename})\n{c.content[:_CHUNK_CHARS]}" for c in chunks)
    user = (f"TENDER\nTitle: {record.title}\nProcuring entity: {record.buyer}\nType: {record.procurement_type.value}; "
            f"method: {record.method.value}\nScope: {record.scope}\n\n"
            f"SECTION: {section.template.title(ctx.language)}\nWhat it must cover: {section.template.guidance}\n\n"
            f"TENDER REQUIREMENTS THIS SECTION ANSWERS\n{reqs}\n\n"
            f"COMPANY\n{ctx.company.name}; sectors: {', '.join(ctx.company.sectors) or '-'}\n\n"
            f"PLACEHOLDERS (code fills the values)\n{available}\n\n"
            f"KNOWLEDGE BASE EXCERPTS\n{kb}")
    system = SYSTEM_PROMPT.format(language=_LANGUAGE_NAME[ctx.language])
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


_NO_MATERIAL = {
    ProposalLanguage.EN: "_No supporting material was found in the company knowledge base for this section. "
                         "Upload documents that cover it ({topic}) and regenerate, or write it by hand._",
    ProposalLanguage.NE: "_यस खण्डका लागि कम्पनीको ज्ञान-आधारमा कुनै सामग्री भेटिएन। सम्बन्धित कागजात ({topic}) "
                         "अपलोड गरेर फेरि तयार गर्नुहोस्, वा हातैले लेख्नुहोस्।_",
}


def build_section(section: PlannedSection, draft: ProposalSectionDraft | None, chunks: Sequence[ChunkHit],
                  ctx: ProposalContext) -> ProposalSection:
    """Check the draft in code and render it: citations, facts, placeholders, unsourced figures, flags."""
    title = section.template.title(ctx.language)
    if draft is None:  # nothing retrieved: no model call, nothing fabricated
        body = _NO_MATERIAL[ctx.language].format(topic=section.template.topic)
        return ProposalSection(key=section.key, title=title, body=body, body_template=body, grounded=False,
                               requirement_indices=section.requirement_indices,
                               flags=[SectionFlag(kind=K.NO_KB_MATERIAL, detail="no knowledge-base chunk was retrieved")])
    by_id = {c.chunk_id: c for c in chunks}
    flags: list[SectionFlag] = []
    if unknown := [i for i in dict.fromkeys(draft.cited_chunk_ids) if i not in by_id]:
        flags.append(SectionFlag(kind=K.UNKNOWN_CITATION, detail=f"cited chunk(s) {unknown} were not shown; dropped"))
    cited = [i for i in dict.fromkeys(draft.cited_chunk_ids) if i in by_id]

    facts: dict[str, tuple[str, int] | None] = {}
    for fact in draft.facts:
        chunk = by_id.get(fact.chunk_id)
        span = Grounder(chunk.content).locate(fact.quote) if chunk else None
        if span is None:
            facts[fact.key] = None
            continue
        facts[fact.key] = (chunk.content[span[0]:span[1]], fact.chunk_id)  # the KB's own text, not the model's copy
        if fact.chunk_id not in cited:
            cited.append(fact.chunk_id)

    masked, figures = mask_unsourced(draft.body)
    if figures:
        flags.append(SectionFlag(kind=K.UNSOURCED_FIGURE,
                                 detail=f"figures written without a source were masked: {', '.join(figures)}"))
    body, resolved, ph_flags = resolve_placeholders(masked, ctx.placeholders, facts)
    flags += ph_flags
    if not cited:
        flags.append(SectionFlag(kind=K.UNGROUNDED, detail="no valid knowledge-base citation; check before use"))
    if draft.missing:
        flags.append(SectionFlag(kind=K.GAPS_REPORTED, detail="; ".join(draft.missing)))
    return ProposalSection(key=section.key, title=title, body=body, body_template=draft.body, cited_chunk_ids=cited,
                           grounded=bool(cited), flags=flags, requirement_indices=section.requirement_indices,
                           placeholders=resolved)


RetrieveFn = Callable[[str], list[ChunkHit]]


def generate_section(client: LLMClient, section: PlannedSection, ctx: ProposalContext, retrieve_fn: RetrieveFn
                     ) -> ProposalSection:
    """Retrieve for this section, draft it (one schema-constrained call), and render it in code.

    No chunk retrieved -> no model call and a flagged stub. Raises LLMError (its agent_runs row is already recorded).
    """
    chunks = retrieve_fn(section_query(section, ctx.record))
    if not chunks:
        return build_section(section, None, chunks, ctx)
    draft = client.chat(stage=Stage.PROPOSAL, messages=build_messages(section, ctx, chunks),
                        schema=ProposalSectionDraft, tender_id=ctx.tender_id)
    return build_section(section, draft, chunks, ctx)


def citation_rate(sections: Sequence[ProposalSection]) -> float:
    """The Proposal metric: share of sections with at least one valid KB citation."""
    return sum(s.grounded for s in sections) / len(sections) if sections else 0.0


ProgressFn = Callable[[StageProgress], None]


def draft_proposal(ctx: ProposalContext, *, client: LLMClient, retrieve_fn: RetrieveFn,
                   on_progress: ProgressFn | None = None) -> list[ProposalSection]:
    """Plan, then generate section by section, reporting progress after each. Raises LLMError."""
    plan = plan_sections(ctx.record)
    items = [ProgressItem(key=s.key, title=s.template.title(ctx.language)) for s in plan]
    progress = StageProgress(done=0, total=len(plan), items=items)
    sections: list[ProposalSection] = []
    for index, planned in enumerate(plan):
        items[index].status, progress.current = SectionProgress.RUNNING, items[index].title
        if on_progress:
            on_progress(progress.model_copy(deep=True))
        try:
            section = generate_section(client, planned, ctx, retrieve_fn)
        except LLMError:
            items[index].status, progress.current = SectionProgress.FAILED, None
            if on_progress:
                on_progress(progress.model_copy(deep=True))
            raise
        sections.append(section)
        items[index].status = SectionProgress.FLAGGED if section.flags else SectionProgress.OK
        progress.done = index + 1
        progress.current = None
        if on_progress:
            on_progress(progress.model_copy(deep=True))
    return sections


# --- DB -------------------------------------------------------------------------------------------------------

DRAFTABLE = {TenderStatus.CHECKED}


def can_draft(session: Session, tender: Tender) -> tuple[bool, str]:
    """The Proposal gate for the API: `proposal_allowed`, or a failed tender whose last good state is `checked`."""
    if tender.status == TenderStatus.FAILED.value:
        from pipeline.orchestrator import resume_status  # the orchestrator imports this module

        view = compliance_view(session, tender.id)
        if resume_status(session, tender) is TenderStatus.CHECKED and view is not None and view.proposal_allowed:
            return True, "ok"
    return proposal_allowed(session, tender)


def proposal_from_row(row: ProposalRow) -> Proposal:
    sections = [ProposalSection.model_validate(s) for s in row.sections]
    return Proposal(id=row.id, tender_id=row.tender_id, version=row.version,
                    language=row.language or ProposalLanguage.EN, sections=sections, review=row.review_json,
                    status=row.status, approved_at=row.approved_at, created_at=row.created_at,
                    citation_rate=citation_rate(sections))


def summary_from_row(row: ProposalRow) -> ProposalSummary:
    sections = [ProposalSection.model_validate(s) for s in row.sections]
    return ProposalSummary(id=row.id, version=row.version, language=row.language or ProposalLanguage.EN,
                           status=row.status, created_at=row.created_at, sections_total=len(sections),
                           sections_grounded=sum(s.grounded for s in sections),
                           sections_flagged=sum(bool(s.flags) for s in sections))


def list_proposals(session: Session, tender_id: int) -> list[ProposalRow]:
    return list(session.scalars(select(ProposalRow).where(ProposalRow.tender_id == tender_id)
                                .order_by(ProposalRow.version.desc())))


def latest_proposal(session: Session, tender_id: int) -> ProposalRow | None:
    return session.scalars(select(ProposalRow).where(ProposalRow.tender_id == tender_id)
                           .order_by(ProposalRow.version.desc()).limit(1)).first()


def _record_code_run(session: Session, tender: Tender, payload: dict[str, Any], started: float, *,
                     output: dict[str, Any] | None = None, error: str | None = None) -> None:
    """agent_runs row for planning + rendering, or a failed KB retrieval (hard rule 9). Model calls record their own."""
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    session.add(AgentRunRow(
        tender_id=tender.id, stage=Stage.PROPOSAL.value, model=DETERMINISTIC_MODEL, input_hash=digest,
        output_json=output, latency_ms=int((time.perf_counter() - started) * 1000), ok=error is None, attempts=1,
        error=error,
    ))


def run_proposal(session: Session, client: LLMClient, tender: Tender, *, settings: Settings | None = None,
                 now: datetime | None = None, force_english: bool | None = None) -> Proposal | None:
    """Draft a new proposal version for a checked tender: store it and set `drafted` (`failed` on LLMError)."""
    settings = settings or get_settings()
    if TenderStatus(tender.status) not in DRAFTABLE or tender.record_json is None:
        raise ValueError(f"tender {tender.id} is {tender.status}; Proposal runs on checked tenders")
    allowed, why = proposal_allowed(session, tender)
    if not allowed:
        raise ValueError(f"tender {tender.id}: {why}")
    loaded = load_company(session)
    if loaded is None:
        raise ValueError("no company profile; POST /company first")
    company_row, company = loaded
    record = TenderRecord.model_validate(tender.record_json)
    force = settings.proposal_force_english if force_english is None else force_english
    ctx = ProposalContext(record=record, company=company, language=proposal_language(record, force_english=force),
                          now=now or datetime.now(NPT), with_bs=uses_bs(record, tender.raw_text), tender_id=tender.id)
    started = time.perf_counter()
    payload = {"tender": tender.record_json, "company": company_row.profile_json, "stage": "proposal",
               "language": ctx.language.value, "with_bs": ctx.with_bs, "now": ctx.now}

    def retrieve_fn(query: str) -> list[ChunkHit]:
        try:
            hits = retrieve(session, client, query, settings.proposal_top_k, company_id=company_row.id)
        except LLMError as exc:
            raise RetrievalError(str(exc)) from exc
        return [h for h in hits if h.similarity >= settings.proposal_min_similarity]

    try:
        sections = draft_proposal(ctx, client=client, retrieve_fn=retrieve_fn, on_progress=report_progress)
    except LLMError as exc:
        # A chat failure is already in agent_runs (client); an embedding failure is not, so record it here.
        if isinstance(exc, RetrievalError):
            _record_code_run(session, tender, payload, started, error=f"KB retrieval failed: {exc}")
        tender.status = TenderStatus.FAILED.value
        tender.updated_at = func.now()
        session.commit()
        return None

    version = (session.scalar(select(func.max(ProposalRow.version)).where(ProposalRow.tender_id == tender.id)) or 0) + 1
    row = ProposalRow(tender_id=tender.id, version=version, sections=[s.model_dump(mode="json") for s in sections],
                      language=ctx.language.value, status=ProposalStatus.DRAFT.value)
    session.add(row)
    _record_code_run(session, tender, payload, started, output={
        "version": version, "language": ctx.language.value, "with_bs": ctx.with_bs,
        "plan": [s.key for s in sections], "citation_rate": citation_rate(sections),
        "flags": {s.key: [f.kind.value for f in s.flags] for s in sections if s.flags},
    })
    tender.status = TenderStatus.DRAFTED.value
    tender.updated_at = func.now()
    session.commit()
    return proposal_from_row(row)

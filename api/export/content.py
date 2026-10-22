"""The bid package as one document model, built by code from stored records. `docx.py` and `pdf.py` render it.

Contents (NEPAL_CONTEXT section 16), in the proposal's language:

0. **Internal cover sheet** (not part of the bid): tender, bidder, proposal version, review verdict, approval, and the
   reminder that Tenderly never submits anything (hard rule 6).
1. **Cover letter**: a dated letter to the procuring entity. Its body is the proposal's `cover_letter` section when
   there is one (model prose, placeholders resolved by code), else a fixed sentence.
2. **Bid form (skeleton)**: the usual undertakings of a Nepali bid form with the notice's own figures (bid validity,
   bid security, performance security %) and **blanks for the price and the signatory**. It is a convenience copy:
   the bidding document's own form is the authority, and Tenderly never writes a price.
3. **Declarations**: the PPR Rule 40(2)(e) self-declaration (eligible, not blacklisted, no conflict of interest, not
   punished for a business offence) plus fraud/collusion and truthfulness, with a signature block.
4. **Technical proposal**: every other proposal section, with its KB citations (hard rule 8) and review flags.
5. **Attachment checklist**: every document the notice lists, plus the statutory ones (PPR Rule 40(2)), marked
   present / expiring / missing from the KB documents with the same matching as the compliance rules, with the
   compliance rule's status and expiry dates in BS and AD.

Everything here is deterministic. The Nepali fixed text was written by the model, not a native reader [VERIFY].
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from agents.proposal import format_date, format_money
from nepal.dates import NPT, ad_to_bs
from nepal.numbers import to_devanagari_digits
from nepal.rules import DOC_LABELS, DOC_RULES, DocumentMeta
from schemas import (ChecklistItem, ChecklistStatus, CompanyProfile, ComplianceItem, ComplianceStatus, ComplianceView,
                     DocType, Proposal, ProposalLanguage, ProposalSection, ReviewReport, TenderRecord)

EN, NE = ProposalLanguage.EN, ProposalLanguage.NE

# --- document model ---------------------------------------------------------------------------------------------


@dataclass
class Inline:
    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class Block:
    """title | h1 | h2 | p | bullet | number | note | table | pagebreak. Tables: rows[0] is the header."""

    kind: str
    inlines: list[Inline] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    widths: tuple[float, ...] = ()

    @property
    def text(self) -> str:
        return "".join(i.text for i in self.inlines)


def para(text: str, kind: str = "p", *, bold: bool = False, italic: bool = False) -> Block:
    return Block(kind, [Inline(text, bold=bold, italic=italic)])


def table(rows: list[list[str]], widths: tuple[float, ...] = ()) -> Block:
    return Block("table", rows=rows, widths=widths)


@dataclass
class BidPackage:
    language: ProposalLanguage
    title: str
    file_stem: str
    blocks: list[Block]
    checklist: list[ChecklistItem]

    @property
    def text(self) -> str:
        """All text, for tests and checks."""
        parts = []
        for b in self.blocks:
            parts.append(b.text)
            parts += [" | ".join(r) for r in b.rows]
        return "\n".join(parts)


# --- a little Markdown (what the Proposal model writes) ----------------------------------------------------------

_INLINE = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1|(?<![\w*])([*_])(?=\S)(.+?)(?<=\S)\3(?![\w*])")
_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
_NUMBER = re.compile(r"^\s*(?:\d+|[०-९]+)[.)]\s+(.*)$")
_HEADING = re.compile(r"^\s*#{1,6}\s+(.*)$")


def inlines(text: str) -> list[Inline]:
    """**bold**, __bold__, *italic*, _italic_; everything else literal."""
    out, last = [], 0
    for m in _INLINE.finditer(text):
        if m.start() > last:
            out.append(Inline(text[last:m.start()]))
        out.append(Inline(m.group(2), bold=True) if m.group(1) else Inline(m.group(4), italic=True))
        last = m.end()
    if last < len(text):
        out.append(Inline(text[last:]))
    return out or [Inline("")]


def markdown_blocks(text: str) -> list[Block]:
    """Paragraphs (blank-line separated, inner lines joined), bullets, numbered items, headings -> h2-level text."""
    blocks: list[Block] = []
    lines: list[str] = []

    def flush() -> None:
        if lines:
            blocks.append(Block("p", inlines(" ".join(s.strip() for s in lines))))
            lines.clear()

    for raw in text.splitlines():
        if not raw.strip():
            flush()
        elif m := _BULLET.match(raw):
            flush()
            blocks.append(Block("bullet", inlines(m.group(1).strip())))
        elif m := _NUMBER.match(raw):
            flush()
            blocks.append(Block("number", inlines(m.group(1).strip())))
        elif m := _HEADING.match(raw):
            flush()
            blocks.append(Block("p", [Inline(m.group(1).strip(), bold=True)]))
        else:
            lines.append(raw)
    flush()
    return blocks


# --- fixed text (en / ne) -----------------------------------------------------------------------------------------

T = {
    EN: {
        "package": "Bid submission package",
        "internal": "Internal cover sheet: not part of the bid. Remove before submission.",
        "not_submitted": "Prepared with Tenderly for review and signature. Tenderly never submits bids: submit this "
                         "package yourself through the procuring entity's channel (e.g. the PPMO e-GP system) before the "
                         "deadline.",
        "tender": "Tender", "reference": "Reference no.", "entity": "Procuring entity", "deadline": "Submission deadline",
        "bidder": "Bidder", "pan_vat": "PAN / VAT", "version": "Proposal version", "verdict": "Review verdict",
        "approved": "Approved by", "generated": "Generated", "contents": "Contents",
        "toc": ["1. Cover letter", "2. Bid form (skeleton)", "3. Declarations", "4. Technical proposal",
                "5. Attachment checklist"],
        "h_cover": "1. Cover letter", "h_form": "2. Bid form (skeleton)", "h_decl": "3. Declarations",
        "h_tech": "4. Technical proposal", "h_check": "5. Attachment checklist",
        "date": "Date: {date}", "to": "To,", "subject": "Subject: Submission of bid for {title}{ref}",
        "ref_suffix": " (Ref. {ref})", "cover_default": "In response to your notice, we, {company}, submit our bid for "
                                                          "the above work in accordance with the bidding document.",
        "sincerely": "Sincerely,", "for": "For {company}",
        "name": "Name: ____________________", "designation": "Designation: ____________________",
        "signature": "Signature and seal: ____________________", "sign_date": "Date: ____________________",
        "form_note": "A convenience copy only. Use the bid form in the procuring entity's bidding document; the blanks "
                     "are for the authorised signatory. Tenderly never fills in prices.",
        "form_to": "To: {entity}",
        "f_examined": "We have examined the bidding document for {title}{ref}, including addenda no. ______, and have "
                      "no reservations.",
        "f_offer": "We offer to carry out the work in conformity with the bidding document for the total bid price of "
                   "NPR ____________ (in words: ______________________), as stated in the price schedule.",
        "f_validity": "Our bid shall remain valid for {days} days from the bid submission deadline ({deadline}) and "
                      "shall remain binding upon us until then.",
        "f_security": "We enclose a bid security of {amount}, valid until {until}.",
        "f_perf_pct": "If our bid is accepted, we will furnish a performance security of {pct}% of the contract price.",
        "f_perf": "If our bid is accepted, we will furnish the performance security the bidding document requires.",
        "f_once": "We are not taking part in more than one bid for this procurement, alone or as a joint-venture "
                  "partner (PPR Rule 28(1)).",
        "f_lowest": "We understand that you are not bound to accept the lowest or any bid you receive.",
        "bidder_info": "Bidder information",
        "b_name": "Name of bidder", "b_address": "Address", "b_pan": "PAN", "b_vat": "VAT", "b_reg": "Registration date",
        "b_licence": "Licence (type, class, no.)", "b_signatory": "Authorised signatory",
        "decl_intro": "We, the undersigned, on behalf of {company} (PAN {pan}), declare that:",
        "decl": ["we are eligible to take part in this procurement and are not disqualified under the Public "
                 "Procurement Act, 2063 and its Rules;",
                 "we have not been blacklisted or debarred from public procurement (PPR Rules 39 and 141), and no such "
                 "action is pending against us;",
                 "we have no conflict of interest in this procurement;",
                 "we have not been punished for a professional or business-related offence (PPR Rule 40(2)(e));",
                 "we have not engaged, and will not engage, in corrupt, fraudulent, collusive or coercive practices in "
                 "this procurement;",
                 "the information and documents in this bid are true and complete."],
        "decl_note": "Self-declaration content per PPR Rule 40(2)(e). If the bidding document has its own declaration "
                     "form, use that form.",
        "sources": "Sources: knowledge-base chunks {ids}.", "no_sources": "Sources: none (no knowledge-base citation).",
        "flags": "Review flags: {flags}.",
        "check_intro": "Documents the notice asks for, and the statutory eligibility documents (PPR Rule 40(2)), checked "
                       "against the company's knowledge base. Submission deadline: {deadline}.{validity}",
        "check_validity": " The bid must stay valid until {end}.",
        "cols": ["#", "Document", "Status", "File(s)", "Valid until (BS / AD)", "Notes"],
        "status": {ChecklistStatus.PRESENT: "Present", ChecklistStatus.EXPIRING: "Expiring",
                   ChecklistStatus.MISSING: "Missing"},
        "statutory": " (statutory, PPR Rule 40(2))", "optional": " (optional)",
        "verdicts": {"pass": "Pass", "needs_work": "Needs work", "fail": "Fail"},
        "n_present": "On file: {files}.",
        "n_expiring": "On file, but it expires on {date}, before the bid validity period ends ({end}). Renew it.",
        "n_unreadable": "On file but not readable ({files}; scanned copies are not read, no OCR). Upload a text copy.",
        "n_expired": "Only an expired copy is on file ({files}, expired {date}).",
        "n_other_fy": "On file for another fiscal year only ({fys}); the notice asks for F/Y {fy}.",
        "n_fy_expired": "{fy}, expired {date}",
        "n_none": "Not on file.",
        "n_declaration": "Signed for each bid: sign the declaration in section 3 of this package.",
        "n_poa": "Signed for each bid: prepare a power of attorney for the signatory.",
        "n_bid_security": "Arrange a bank guarantee of {amount}{until}.",
        "n_until": ", valid until {date}",
        "n_action": " Action: {action}",
        "none": "-",
    },
    # Model-written Nepali, [VERIFY] with a native reader (PROGRESS issue 60).
    NE: {
        "package": "बोलपत्र पेस गर्ने प्याकेज",
        "internal": "आन्तरिक पाना: बोलपत्रको अंश होइन। पेस गर्नुअघि हटाउनुहोस्।",
        "not_submitted": "Tenderly मा समीक्षा र दस्तखतका लागि तयार पारिएको। Tenderly ले बोलपत्र पेस गर्दैन: यो प्याकेज "
                         "अन्तिम मितिअघि सार्वजनिक निकायको माध्यम (जस्तै PPMO e-GP प्रणाली) बाट आफैँ पेस गर्नुहोस्।",
        "tender": "खरिद कार्य", "reference": "सन्दर्भ नं.", "entity": "सार्वजनिक निकाय",
        "deadline": "बोलपत्र पेस गर्ने अन्तिम मिति", "bidder": "बोलपत्रदाता", "pan_vat": "स्थायी लेखा नं. / मू.अ.कर नं.",
        "version": "प्रस्ताव संस्करण", "verdict": "समीक्षा नतिजा", "approved": "स्वीकृत गर्ने", "generated": "तयार मिति",
        "contents": "विषयसूची",
        "toc": ["१. आवरण पत्र", "२. बोलपत्र फाराम (ढाँचा)", "३. स्वघोषणा", "४. प्राविधिक प्रस्ताव",
                "५. संलग्न कागजातको सूची"],
        "h_cover": "१. आवरण पत्र", "h_form": "२. बोलपत्र फाराम (ढाँचा)", "h_decl": "३. स्वघोषणा",
        "h_tech": "४. प्राविधिक प्रस्ताव", "h_check": "५. संलग्न कागजातको सूची",
        "date": "मिति: {date}", "to": "श्रीमान्,", "subject": "विषय: {title}{ref} को बोलपत्र पेस गरिएको सम्बन्धमा।",
        "ref_suffix": " (सन्दर्भ नं. {ref})",
        "cover_default": "उपर्युक्त सम्बन्धमा तपाईंको सूचना तथा बोलपत्र कागजात बमोजिम {company} को बोलपत्र पेस गरेका छौँ।",
        "sincerely": "भवदीय,", "for": "{company} को तर्फबाट",
        "name": "नाम: ____________________", "designation": "पद: ____________________",
        "signature": "दस्तखत र छाप: ____________________", "sign_date": "मिति: ____________________",
        "form_note": "सुविधाका लागि मात्र। सार्वजनिक निकायको बोलपत्र कागजातमा भएको फाराम प्रयोग गर्नुहोस्; खाली ठाउँ "
                     "अधिकार प्राप्त दस्तखतकर्ताले भर्ने। Tenderly ले कहिल्यै मूल्य भर्दैन।",
        "form_to": "श्री {entity}",
        "f_examined": "हामीले {title}{ref} को बोलपत्र कागजात, संशोधन नं. ______ सहित, अध्ययन गरेका छौँ र कुनै आपत्ति छैन।",
        "f_offer": "बोलपत्र कागजात बमोजिम मूल्य तालिकामा उल्लेख गरिए अनुसार कुल रु. ____________ (अक्षरमा: "
                   "______________________) मा काम गर्न प्रस्ताव गर्दछौँ।",
        "f_validity": "यो बोलपत्र पेस गर्ने अन्तिम मिति ({deadline}) देखि {days} दिनसम्म मान्य रहनेछ र सो अवधिसम्म हामीलाई "
                      "बाध्यकारी हुनेछ।",
        "f_security": "{amount} को बोलपत्र जमानत संलग्न गरेका छौँ, जुन {until} सम्म मान्य छ।",
        "f_perf_pct": "बोलपत्र स्वीकृत भएमा सम्झौता रकमको {pct} प्रतिशत कार्यसम्पादन जमानत बुझाउनेछौँ।",
        "f_perf": "बोलपत्र स्वीकृत भएमा बोलपत्र कागजातले तोके बमोजिमको कार्यसम्पादन जमानत बुझाउनेछौँ।",
        "f_once": "यस खरिदमा हामी एकल वा संयुक्त उपक्रम साझेदारका रूपमा एकभन्दा बढी बोलपत्रमा सहभागी छैनौँ "
                  "(सार्वजनिक खरिद नियमावलीको नियम २८(१))।",
        "f_lowest": "सबैभन्दा कम वा कुनै पनि बोलपत्र स्वीकार गर्न तपाईं बाध्य हुनुहुन्न भन्ने हामीलाई जानकारी छ।",
        "bidder_info": "बोलपत्रदाताको विवरण",
        "b_name": "बोलपत्रदाताको नाम", "b_address": "ठेगाना", "b_pan": "स्थायी लेखा नं.", "b_vat": "मू.अ.कर नं.",
        "b_reg": "दर्ता मिति", "b_licence": "इजाजतपत्र (किसिम, वर्ग, नं.)", "b_signatory": "अधिकार प्राप्त दस्तखतकर्ता",
        "decl_intro": "{company} (स्थायी लेखा नं. {pan}) को तर्फबाट हामी तल दस्तखत गर्ने घोषणा गर्दछौँ कि:",
        "decl": ["हामी यस खरिदमा भाग लिन योग्य छौँ र सार्वजनिक खरिद ऐन, २०६३ तथा नियमावली बमोजिम अयोग्य छैनौँ;",
                 "हामी सार्वजनिक खरिदमा कालोसूचीमा परेका वा प्रतिबन्धित छैनौँ (नियम ३९ र १४१), र हाम्रा विरुद्ध त्यस्तो "
                 "कारबाही विचाराधीन छैन;",
                 "यस खरिदमा हाम्रो कुनै स्वार्थको द्वन्द्व छैन;",
                 "पेसा वा व्यवसायसम्बन्धी कसुरमा हामीले सजाय पाएका छैनौँ (नियम ४०(२)(ङ));",
                 "यस खरिदमा हामी भ्रष्टाचार, जालसाजी, मिलेमतो वा दबाबजन्य कार्यमा संलग्न छैनौँ र हुने छैनौँ;",
                 "यस बोलपत्रमा दिइएका विवरण तथा कागजात सत्य र पूर्ण छन्।"],
        "decl_note": "स्वघोषणाको व्यहोरा सार्वजनिक खरिद नियमावलीको नियम ४०(२)(ङ) बमोजिम। बोलपत्र कागजातमा छुट्टै घोषणा "
                     "फाराम भए सोही प्रयोग गर्नुहोस्।",
        "sources": "स्रोत: ज्ञान-आधार खण्ड {ids}।", "no_sources": "स्रोत: छैन (ज्ञान-आधारको सन्दर्भ छैन)।",
        "flags": "समीक्षा सङ्केत: {flags}।",
        "check_intro": "सूचनाले माग गरेका र वैधानिक योग्यतासम्बन्धी (नियम ४०(२)) कागजात, कम्पनीको ज्ञान-आधारसँग जाँच "
                       "गरिएको। बोलपत्र पेस गर्ने अन्तिम मिति: {deadline}।{validity}",
        "check_validity": " बोलपत्र {end} सम्म मान्य रहनुपर्छ।",
        "cols": ["क्र.सं.", "कागजात", "अवस्था", "फाइल", "मान्य मिति (वि.सं. / ई.सं.)", "कैफियत"],
        "status": {ChecklistStatus.PRESENT: "उपलब्ध", ChecklistStatus.EXPIRING: "म्याद सकिँदै",
                   ChecklistStatus.MISSING: "छैन"},
        "statutory": " (वैधानिक, नियम ४०(२))", "optional": " (ऐच्छिक)",
        "verdicts": {"pass": "उत्तीर्ण", "needs_work": "सुधार आवश्यक", "fail": "असफल"},
        "n_present": "फाइलमा छ: {files}।",
        "n_expiring": "फाइलमा छ, तर {date} मा म्याद सकिन्छ, बोलपत्र मान्य अवधि ({end}) सकिनुअघि। नवीकरण गर्नुहोस्।",
        "n_unreadable": "फाइलमा छ तर पढ्न सकिँदैन ({files}; स्क्यान गरिएको प्रति पढिँदैन)। पाठ भएको प्रति अपलोड गर्नुहोस्।",
        "n_expired": "म्याद सकिएको प्रति मात्र छ ({files}, {date} मा म्याद सकिएको)।",
        "n_other_fy": "अर्को आर्थिक वर्षको मात्र छ ({fys}); सूचनाले आ.व. {fy} को माग गरेको छ।",
        "n_fy_expired": "{fy}, {date} मा म्याद सकिएको",
        "n_none": "फाइलमा छैन।",
        "n_declaration": "हरेक बोलपत्रमा दस्तखत गरिने: यस प्याकेजको खण्ड ३ को स्वघोषणामा दस्तखत गर्नुहोस्।",
        "n_poa": "हरेक बोलपत्रमा दस्तखत गरिने: दस्तखतकर्ताका लागि अख्तियारनामा तयार गर्नुहोस्।",
        "n_bid_security": "{amount} को बैंक जमानत{until} व्यवस्था गर्नुहोस्।",
        "n_until": " ({date} सम्म मान्य)",
        "n_action": " कार्य: {action}",
        "none": "-",
    },
}

# Model-written Nepali names for document types [VERIFY]; English uses nepal.rules.DOC_LABELS.
DOC_LABELS_NE = {
    DocType.COMPANY_REGISTRATION: "फर्म/कम्पनी दर्ता प्रमाणपत्र", DocType.BUSINESS_LICENCE: "व्यवसाय/निर्माण इजाजतपत्र",
    DocType.LICENCE_RENEWAL: "इजाजतपत्र नवीकरण", DocType.PAN_VAT: "स्थायी लेखा नं./मू.अ.कर दर्ता प्रमाणपत्र",
    DocType.TAX_CLEARANCE: "कर चुक्ता प्रमाणपत्र", DocType.TAX_RETURN: "कर विवरण पेस गरेको प्रमाण",
    DocType.SELF_DECLARATION: "स्वघोषणा", DocType.POWER_OF_ATTORNEY: "अख्तियारनामा",
    DocType.BID_SECURITY: "बोलपत्र जमानत (बैंक जमानत)", DocType.AUDIT_REPORT: "लेखापरीक्षण प्रतिवेदन",
    DocType.EXPERIENCE_CERTIFICATE: "कार्य सम्पन्न (अनुभव) प्रमाणपत्र", DocType.JV_AGREEMENT: "संयुक्त उपक्रम सम्झौता",
    DocType.COMPANY_PROFILE: "कम्पनी प्रोफाइल", DocType.OTHER: "कागजात",
}


def doc_label(doc_type: DocType, language: ProposalLanguage) -> str:
    return DOC_LABELS_NE[doc_type] if language is NE else DOC_LABELS[doc_type].capitalize()


# --- dates --------------------------------------------------------------------------------------------------------


def bs_ad(day: date, language: ProposalLanguage) -> str:
    """'2084-03-32 BS / 2027-07-16 AD' ('२०८४-०३-३२ / २०२७-०७-१६' in Nepali): checklist dates."""
    bs = ad_to_bs(day).iso()
    return to_devanagari_digits(f"{bs} / {day.isoformat()}") if language is NE else f"{bs} BS / {day.isoformat()} AD"


def long_date(value: date | datetime, language: ProposalLanguage) -> str:
    """'5 Mangsir 2083 BS (21 November 2026 AD), 12:00 NPT': letters and forms always carry both calendars."""
    return format_date(value, language, with_bs=True)


# --- attachment checklist ----------------------------------------------------------------------------------------

# Documents that satisfy a listed type (PPR Rule 40(2)(d): tax clearance OR proof of a filed return), as the rules do.
ALTERNATIVES = {DocType.TAX_CLEARANCE: (DocType.TAX_CLEARANCE, DocType.TAX_RETURN),
                DocType.LICENCE_RENEWAL: (DocType.LICENCE_RENEWAL, DocType.BUSINESS_LICENCE)}
FY_TYPES = {DocType.TAX_CLEARANCE, DocType.TAX_RETURN, DocType.AUDIT_REPORT, DocType.LICENCE_RENEWAL}
PER_BID = {DocType.SELF_DECLARATION, DocType.POWER_OF_ATTORNEY}
# PPR Rule 40(2)(a)-(c), (e): listed even when the notice does not (NEPAL_CONTEXT section 3).
STATUTORY = (DocType.COMPANY_REGISTRATION, DocType.BUSINESS_LICENCE, DocType.PAN_VAT, DocType.SELF_DECLARATION)
_WORST = {ComplianceStatus.FAIL: 0, ComplianceStatus.UNCLEAR: 1, ComplianceStatus.PASS: 2}


def _fy_ok(doc_type: DocType, doc: DocumentMeta, fy: str | None) -> bool:
    """The notice's fiscal year, as the rules match it: exact for tax/audit, that FY or later for a licence renewal."""
    if fy is None:
        return True
    if doc_type is DocType.LICENCE_RENEWAL:
        return (doc.fiscal_year_bs or "") >= fy
    return doc.fiscal_year_bs == fy


def _rule_item(items: Sequence[ComplianceItem], doc_type: DocType, description: str) -> ComplianceItem | None:
    """The compliance item that checked this document: its rule's worst item, or NP-OTHER-DOCS' item for it."""
    rule = DOC_RULES.get(doc_type)
    own = [i for i in items if i.rule_id == rule and rule is not None]
    other = [i for i in items if i.rule_id == "NP-OTHER-DOCS" and i.requirement == f"Notice document: {description}"]
    candidates = own or other
    return min(candidates, key=lambda i: _WORST[i.status]) if candidates else None


def build_checklist(record: TenderRecord, items: Sequence[ComplianceItem], documents: Sequence[DocumentMeta],
                    now: datetime, language: ProposalLanguage) -> list[ChecklistItem]:
    """One row per document the notice lists (+ statutory ones), matched against the KB like the compliance rules."""
    language = ProposalLanguage(language)
    t = T[language]
    ref = (record.deadline_ad or now).astimezone(NPT).date()  # documents must be valid at the deadline
    end = ref + timedelta(days=record.bid_validity_days) if record.deadline_ad and record.bid_validity_days else None
    wanted = [(d.doc_type, d.description, d.fiscal_year_bs, d.mandatory, False) for d in record.required_docs]
    listed = {d.doc_type for d in record.required_docs}
    wanted += [(dt, doc_label(dt, EN), None, True, True) for dt in STATUTORY if dt not in listed]

    rows: list[ChecklistItem] = []
    for doc_type, description, fy, mandatory, statutory in wanted:
        types = ALTERNATIVES.get(doc_type, (doc_type,))
        fy = fy if doc_type in FY_TYPES else None
        all_docs = [d for d in documents if d.doc_type in types]
        docs = [d for d in all_docs if _fy_ok(doc_type, d, fy)]
        live = [d for d in docs if d.expiry is None or d.expiry >= ref]
        usable = [d for d in live if d.chunk_id is not None]  # readable text in the KB
        item = _rule_item(items, doc_type, description)
        name = (doc_label(doc_type, language) + t["statutory"] if statutory
                else description + ("" if mandatory else t["optional"]))

        def files(ds: Sequence[DocumentMeta]) -> str:
            return ", ".join(d.filename or f"document {d.document_id}" for d in ds)

        expiry = min((d.expiry for d in usable if d.expiry), default=None)
        if usable:
            lapsing = [d for d in usable if d.expiry and end and d.expiry < end]
            if lapsing:
                status = ChecklistStatus.EXPIRING
                note = t["n_expiring"].format(date=bs_ad(min(d.expiry for d in lapsing), language), end=bs_ad(end, language))
            else:
                status, note = ChecklistStatus.PRESENT, t["n_present"].format(files=files(usable))
            attached = usable
        else:
            status, attached = ChecklistStatus.MISSING, []
            if doc_type is DocType.SELF_DECLARATION:
                note = t["n_declaration"]
            elif doc_type is DocType.POWER_OF_ATTORNEY:
                note = t["n_poa"]
            elif doc_type is DocType.BID_SECURITY:
                due = record.bid_security_due
                amount = due.amount_npr if due and due.amount_npr is not None else (
                    record.bid_security.amount_npr if record.bid_security else None)
                until = t["n_until"].format(date=bs_ad(due.valid_until, language)) if due and due.valid_until else ""
                note = t["n_bid_security"].format(amount=format_money(amount, language) if amount is not None else "____",
                                                  until=until)
            elif live:
                note = t["n_unreadable"].format(files=files(live))
            elif docs:
                expired = max(d.expiry for d in docs if d.expiry)
                note = t["n_expired"].format(files=files(docs), date=bs_ad(expired, language))
                expiry = expired
            elif all_docs and fy:
                fys = ", ".join(sorted({
                    t["n_fy_expired"].format(fy=d.fiscal_year_bs or "?", date=bs_ad(d.expiry, language))
                    if d.expiry and d.expiry < ref else (d.fiscal_year_bs or "?") for d in all_docs}))
                note = t["n_other_fy"].format(fys=fys, fy=fy)
            else:
                note = t["n_none"]
            if item is not None and item.action_needed and doc_type not in PER_BID:
                note += t["n_action"].format(action=item.action_needed)
        rows.append(ChecklistItem(
            document=name, doc_type=doc_type, mandatory=mandatory, fiscal_year_bs=fy, status=status,
            files=[d.filename or str(d.document_id) for d in attached],
            document_ids=[d.document_id for d in attached if d.document_id is not None],
            expires_on=expiry, expires_on_bs=ad_to_bs(expiry).iso() if expiry else None,
            rule_id=item.rule_id if item else DOC_RULES.get(doc_type), compliance_status=item.status if item else None,
            note=note))
    return rows


# --- the package ---------------------------------------------------------------------------------------------------


def _ref(record: TenderRecord, t: dict) -> str:
    return t["ref_suffix"].format(ref=record.reference_no) if record.reference_no else ""


def _signature(t: dict, company: CompanyProfile) -> list[Block]:
    return [para(t["for"].format(company=company.name), bold=True)] + [
        para(t[k]) for k in ("name", "designation", "signature", "sign_date")]


def build_package(*, record: TenderRecord, company: CompanyProfile, proposal: Proposal,
                  compliance: ComplianceView | None, documents: Sequence[DocumentMeta], now: datetime,
                  tender_id: int) -> BidPackage:
    """The whole package as blocks. Pure code: no model call, no I/O."""
    language = proposal.language
    t = T[language]
    ne = language is NE
    dash = t["none"]
    deadline = long_date(record.deadline_ad, language) if record.deadline_ad else dash
    today = long_date(now.astimezone(NPT).date(), language)
    review: ReviewReport | None = proposal.review
    blocks: list[Block] = []

    # 0. internal cover sheet
    pan_vat = " / ".join(x for x in (company.pan_number, company.vat_number) if x) or dash
    approval = (f"{proposal.approved_by}, {long_date(proposal.approved_at, language)}"
                if proposal.approved_by and proposal.approved_at else dash)
    version = to_devanagari_digits(str(proposal.version)) if ne else str(proposal.version)
    blocks += [
        para(t["package"], "title"),
        para(t["internal"], "note", italic=True),
        table([[t["tender"], record.title], [t["reference"], record.reference_no or dash], [t["entity"], record.buyer],
               [t["deadline"], deadline], [t["bidder"], company.name], [t["pan_vat"], pan_vat],
               [t["version"], version], [t["verdict"], t["verdicts"][review.verdict.value] if review else dash],
               [t["approved"], approval], [t["generated"], today]], widths=(0.3, 0.7)),
        para(t["not_submitted"], "note", italic=True),
        para(t["contents"], "h2"),
        *[para(line) for line in t["toc"]],
        Block("pagebreak"),
    ]

    # 1. cover letter
    by_key = {s.key: s for s in proposal.sections}
    cover = by_key.get("cover_letter")
    blocks += [para(t["h_cover"], "h1"), para(t["date"].format(date=today)), para(t["to"]), para(record.buyer)]
    if record.buyer_address:
        blocks.append(para(record.buyer_address))
    blocks.append(para(t["subject"].format(title=record.title, ref=_ref(record, t)), bold=True))
    blocks += markdown_blocks(cover.body) if cover else [para(t["cover_default"].format(company=company.name))]
    blocks += [para(t["sincerely"])] + _signature(t, company) + [Block("pagebreak")]

    # 2. bid form skeleton
    clauses = [t["f_examined"].format(title=record.title, ref=_ref(record, t)), t["f_offer"]]
    days = record.bid_validity_days
    clauses.append(t["f_validity"].format(days=(to_devanagari_digits(str(days)) if ne else days) if days else "______",
                                          deadline=deadline))
    if record.bid_security is not None:
        due = record.bid_security_due
        amount = due.amount_npr if due and due.amount_npr is not None else record.bid_security.amount_npr
        until = long_date(due.valid_until, language) if due and due.valid_until else "______"
        clauses.append(t["f_security"].format(amount=format_money(amount, language) if amount is not None else "NPR ______",
                                              until=until))
    pct = record.performance_security_percent
    clauses.append(t["f_perf_pct"].format(pct=to_devanagari_digits(f"{pct:g}") if ne else f"{pct:g}") if pct else t["f_perf"])
    clauses += [t["f_once"], t["f_lowest"]]
    licence = company.licences[0] if company.licences else None
    licence_text = ", ".join(x for x in (licence.licence_type, licence.licence_class.value if licence.licence_class else None,
                                         licence.licence_number) if x) if licence else dash
    blocks += [para(t["h_form"], "h1"), para(t["form_note"], "note", italic=True),
               para(t["form_to"].format(entity=record.buyer)),
               *[para(c, "number") for c in clauses],
               para(t["bidder_info"], "h2"),
               table([[t["b_name"], company.name], [t["b_address"], company.location or dash],
                      [t["b_pan"], company.pan_number or dash], [t["b_vat"], company.vat_number or dash],
                      [t["b_reg"], long_date(company.registration_date, language) if company.registration_date else dash],
                      [t["b_licence"], licence_text], [t["b_signatory"], "______________________"]], widths=(0.35, 0.65)),
               *_signature(t, company), Block("pagebreak")]

    # 3. declarations
    blocks += [para(t["h_decl"], "h1"),
               para(t["decl_intro"].format(company=company.name, pan=company.pan_number or "______")),
               *[para(line, "bullet") for line in t["decl"]],
               para(t["decl_note"], "note", italic=True),
               *_signature(t, company), Block("pagebreak")]

    # 4. technical proposal
    blocks.append(para(t["h_tech"], "h1"))
    for section in proposal.sections:
        if section.key == "cover_letter":
            continue
        blocks.append(para(section.title, "h2"))
        blocks += markdown_blocks(section.body)
        blocks.append(_sources(section, t, ne))
        if section.flags:
            blocks.append(para(t["flags"].format(flags=", ".join(dict.fromkeys(f.kind.value for f in section.flags))),
                               "note", italic=True))
    blocks.append(Block("pagebreak"))

    # 5. attachment checklist
    checklist = build_checklist(record, compliance.items if compliance else [], documents, now, language)
    end = (record.deadline_ad.astimezone(NPT).date() + timedelta(days=record.bid_validity_days)
           if record.deadline_ad and record.bid_validity_days else None)
    validity = t["check_validity"].format(end=long_date(end, language)) if end else ""
    rows = [t["cols"]] + [
        [to_devanagari_digits(str(n)) if ne else str(n), row.document, t["status"][row.status],
         ", ".join(row.files) or dash, bs_ad(row.expires_on, language) if row.expires_on else dash, row.note]
        for n, row in enumerate(checklist, 1)]
    blocks += [para(t["h_check"], "h1"), para(t["check_intro"].format(deadline=deadline, validity=validity)),
               table(rows, widths=(0.07, 0.19, 0.1, 0.18, 0.16, 0.3))]

    stem = f"tender{tender_id}_proposal_v{proposal.version}"
    return BidPackage(language=language, title=f"{t['package']}: {record.title}", file_stem=stem, blocks=blocks,
                      checklist=checklist)


def _sources(section: ProposalSection, t: dict, ne: bool) -> Block:
    if not section.cited_chunk_ids:
        return para(t["no_sources"], "note", italic=True)
    ids = ", ".join(str(i) for i in section.cited_chunk_ids)
    return para(t["sources"].format(ids=to_devanagari_digits(ids) if ne else ids), "note", italic=True)

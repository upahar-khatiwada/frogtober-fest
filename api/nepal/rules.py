"""Rules evaluator and security calculators. Deterministic: no LLM, no statutory defaults.

Every result is a `ComplianceItem` with `rule_id` set, the documents it looked at
(`evidence_document_ids`) and, unless it passed, a plain-language `action_needed`. A "pass" needs
evidence: a readable KB document (its chunk id), or a field of the tender notice itself
(`evidence_ref="tender.*"`). Profile entries the user typed are not evidence on their own, so
anything else is downgraded to "unclear" (CLAUDE.md hard rule 8).
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from nepal.dates import NPT, ad_to_bs, days_left, fiscal_year_of, parse_bs_datetime
from nepal.numbers import format_npr
from schemas import (CompanyProfile, ComplianceItem, ComplianceStatus, DocType, ItemSource, ProcurementMethod, ProcurementType,
                     RequirementCategory, Severity, TenderRecord)
from schemas._base import Contract, FiscalYearBS
from schemas.tender import SecurityCalc, TenderCriteria  # noqa: F401  (re-exported: nepal.TenderCriteria)

RULES_PATH = Path(__file__).with_name("rules.yaml")
P, F, U = ComplianceStatus.PASS, ComplianceStatus.FAIL, ComplianceStatus.UNCLEAR


# --- models -----------------------------------------------------------------

class AppliesTo(Contract):
    procurement_types: list[ProcurementType] = []
    methods: list[ProcurementMethod] = []  # empty list = applies to all


class Rule(Contract):
    id: str
    description: str
    applies_to: AppliesTo = AppliesTo()
    check: str
    parameters: dict[str, Any] = {}
    severity: Severity
    source: str
    verified: bool
    notes: str | None = None


class DocumentMeta(Contract):
    """What the KB knows about one uploaded document (from ingest, not from the LLM).

    `chunk_id` is the document's first KB chunk, set only when it was ingested `ready` (readable text);
    `agents.compliance.load_document_meta` builds these from the `documents` table.
    """
    doc_type: DocType
    chunk_id: int | None = None
    document_id: int | None = None
    filename: str | None = None
    expiry: date | None = None
    fiscal_year_bs: FiscalYearBS | None = None
    value_npr: int | None = Field(None, ge=0, description="Guarantee amount or contract value.")
    similar: bool | None = Field(None, description="Experience certificate similar to this tender? None = not classified.")


@lru_cache
def load_rules(path: Path = RULES_PATH) -> tuple[Rule, ...]:
    return tuple(Rule.model_validate(r) for r in yaml.safe_load(path.read_text(encoding="utf-8"))["rules"])


# --- calculators ------------------------------------------------------------

def _deadline(t: TenderRecord) -> datetime | None:
    if t.deadline_ad:
        return t.deadline_ad if t.deadline_ad.tzinfo else t.deadline_ad.replace(tzinfo=NPT)
    for raw in (t.deadline_bs_raw, t.deadline_bs_iso):
        if raw:
            try:
                return parse_bs_datetime(raw)
            except ValueError:
                continue
    return None


def _price(t: TenderRecord, bid_price: int | None) -> tuple[int | None, str]:
    if bid_price:
        return bid_price, "bid price"
    if t.estimated_cost_npr:
        return t.estimated_cost_npr, "estimated cost (bid price not given)"
    return None, "no bid price or estimate"


def _ceil_pct(price: int, pct: float) -> int:
    return int((Decimal(price) * Decimal(str(pct)) / 100).to_integral_value(ROUND_CEILING))


def calc_bid_security(t: TenderRecord, *, bid_price_npr: int | None = None) -> SecurityCalc:
    """Amount and valid-until date, from the notice only (NEPAL_CONTEXT section 4)."""
    bs = t.bid_security
    if bs is None:
        return SecurityCalc(amount_npr=None, basis="notice states no bid security")
    if bs.amount_npr is not None:
        amount, basis = bs.amount_npr, "fixed amount in notice"
    else:
        price, what = _price(t, bid_price_npr)
        amount, basis = (_ceil_pct(price, bs.percent) if price else None), f"{bs.percent}% of {what}"
    dl = _deadline(t)
    until = dl.astimezone(NPT).date() + timedelta(days=bs.validity_days) if dl and bs.validity_days else None
    return SecurityCalc(amount_npr=amount, valid_until=until, valid_until_bs=ad_to_bs(until).iso() if until else None, basis=basis)


def calc_performance_security(t: TenderRecord, *, contract_price_npr: int | None = None) -> SecurityCalc:
    pct = t.performance_security_percent
    if pct is None:
        return SecurityCalc(amount_npr=None, basis="notice states no performance security percent")
    price, what = _price(t, contract_price_npr)
    return SecurityCalc(amount_npr=_ceil_pct(price, pct) if price else None, basis=f"{pct}% of {what}")


# --- evaluator --------------------------------------------------------------

DOC_LABELS = {
    DocType.COMPANY_REGISTRATION: "company registration certificate", DocType.BUSINESS_LICENCE: "business/construction licence",
    DocType.LICENCE_RENEWAL: "licence renewal record", DocType.PAN_VAT: "PAN/VAT registration certificate",
    DocType.TAX_CLEARANCE: "tax clearance certificate", DocType.TAX_RETURN: "tax-return filing proof",
    DocType.SELF_DECLARATION: "self-declaration", DocType.POWER_OF_ATTORNEY: "power of attorney",
    DocType.BID_SECURITY: "bid security (bank guarantee)", DocType.AUDIT_REPORT: "audited financial statements",
    DocType.EXPERIENCE_CERTIFICATE: "work completion (experience) certificate", DocType.JV_AGREEMENT: "JV agreement",
    DocType.COMPANY_PROFILE: "company profile", DocType.OTHER: "document",
}


def label(t: DocType) -> str:
    return DOC_LABELS[t]


def labels(types) -> str:
    return ", ".join(label(DocType(t)) for t in types)


@dataclass
class Ctx:
    tender: TenderRecord
    company: CompanyProfile
    docs: list[DocumentMeta]
    criteria: TenderCriteria
    now: datetime
    bid_price: int | None
    deadline: datetime | None
    prior: list[ComplianceItem] = field(default_factory=list)

    @property
    def ref_date(self) -> date:
        return (self.deadline or self.now).astimezone(NPT).date()

    @property
    def fy(self) -> str:
        return fiscal_year_of(ad_to_bs(self.ref_date))

    def docs_of(self, *types: DocType) -> list[DocumentMeta]:
        return [d for d in self.docs if d.doc_type in types]

    def live(self, docs: list[DocumentMeta]) -> list[DocumentMeta]:
        return [d for d in docs if d.expiry is None or d.expiry >= self.ref_date]


@dataclass
class Outcome:
    status: ComplianceStatus
    requirement: str
    why: str
    chunk_ids: list[int]
    doc_ids: list[int]
    ref: str | None
    action: str | None


def o(status, req, why, ids=(), ev=None, *, docs=(), action=None) -> Outcome:
    """One outcome. The single place that enforces 'never pass without evidence'.

    `ids` are KB chunk ids, `docs` the DocumentMeta records looked at, `ev` a named field. Only chunk ids or a
    tender-notice field (`ev="tender.*"`) can back a pass; a pass on anything else becomes unclear.
    """
    ids = list(ids)
    if status is P and not (ids or (ev or "").startswith("tender.")):
        status, why = U, why + " No document evidence in the KB, so not marked pass."
    if status is P:
        action = None
    doc_ids = list(dict.fromkeys(d.document_id for d in docs if d.document_id is not None))
    return Outcome(status, req, why + (f" Evidence: {ev}." if ev else ""), ids, doc_ids, ev, action)


def _find(c: Ctx, *types: DocType, fy: str | None = None):
    """(all, unexpired, unexpired with a chunk id) documents of the given types."""
    docs = [d for d in c.docs_of(*types) if fy is None or d.fiscal_year_bs == fy]
    live = c.live(docs)
    return docs, live, [d for d in live if d.chunk_id is not None]


def _has_req(c: Ctx, cat: RequirementCategory) -> bool:
    return any(r.mandatory and r.category is cat for r in c.tender.requirements)


def _needed(c: Ctx, p) -> list[DocType]:
    need = [DocType(x) for x in p["statutory_doc_types"]]
    need += [d.doc_type for d in c.tender.required_docs if d.mandatory and d.doc_type.value in p["also_from_notice"]]
    return list(dict.fromkeys(need))


def _deadline_check(c, p):
    req = "Submission deadline not passed"
    if c.deadline is None:
        return [o(U, req, "Notice has no parseable deadline.", action="Confirm the submission deadline in the notice.")]
    if c.now > c.deadline:
        return [o(F, req, f"Deadline {c.deadline.astimezone(NPT):%Y-%m-%d %H:%M} NPT has passed.",
                  action="None possible: the submission deadline has passed. Do not bid.")]
    return [o(P, req, f"{days_left(c.deadline, c.now)} day(s) left (deadline {c.deadline.astimezone(NPT):%Y-%m-%d %H:%M} NPT).", ev="tender.deadline")]


def _reg_docs(c, p):
    miss, exp, noev, ids, seen = [], [], [], [], []
    for t in _needed(c, p):
        docs, live, ev = _find(c, t)
        seen += docs
        if not docs:
            miss.append(t)
        elif not live:
            exp.append(t)
        elif not ev:
            noev.append(t)
        ids += [d.chunk_id for d in ev]
    req = "Registration documents"
    if miss or exp:
        steps = [f"Upload the {labels(miss)}."] if miss else []
        if exp:
            steps.append(f"Renew the {labels(exp)} (expired before the deadline, {c.ref_date}) and upload the renewed copy.")
        return [o(F, req, f"Missing: {[t.value for t in miss] or '-'}; expired before {c.ref_date}: {[t.value for t in exp] or '-'}.",
                  docs=seen, action=" ".join(steps))]
    if noev:
        return [o(U, req, f"On file but without a KB chunk id: {[t.value for t in noev]}.", docs=seen,
                  action=f"Re-upload the {labels(noev)} as a text-readable file (scanned copies are not read; no OCR).")]
    return [o(P, req, "All required registration documents on file and unexpired.", ids, docs=seen)]


def _bid_forms(c, p):
    """Forms the bidder signs for each bid (self-declaration, power of attorney): not KB documents, so never a fail."""
    out = []
    for t in _needed(c, p):
        docs, live, ev = _find(c, t)
        req = f"{label(t).capitalize()} (signed for this bid)"
        if ev:
            out.append(o(P, req, f"A {label(t)} is on file; check it names this tender.", [d.chunk_id for d in ev], docs=docs))
        else:
            out.append(o(U, req, f"A {label(t)} is signed for each bid, so it is not expected in the KB.", docs=docs,
                         action=f"Prepare and sign the {label(t)} in the bidding document's format and attach it to this bid."))
    return out


def _pan_vat(c, p):
    req = "PAN/VAT registration"
    note = " PAN format not validated." + ("" if c.company.vat_number else " No VAT number on profile.")
    docs, live, ev = _find(c, DocType.PAN_VAT)
    if not (c.company.pan_number or "").strip():
        return [o(F, req, "No PAN number on company profile." + note, docs=docs, action="Add the company's PAN number to the company profile.")]
    if not docs:
        return [o(F, req, "No pan_vat document on file." + note, action="Upload the PAN/VAT registration certificate.")]
    if not live:
        return [o(F, req, f"pan_vat document expired before {c.ref_date}." + note, docs=docs,
                  action="Upload a current PAN/VAT registration certificate.")]
    if not ev:
        return [o(U, req, "pan_vat document has no KB chunk id." + note, docs=docs,
                  action="Re-upload the PAN/VAT certificate as a text-readable file (scanned copies are not read).")]
    return [o(P, req, "PAN on profile and certificate on file." + note, [d.chunk_id for d in ev], docs=docs)]


def _tax(c, p):
    out = []
    for r in (d for d in c.tender.required_docs if d.doc_type is DocType.TAX_CLEARANCE and d.mandatory):
        fy = r.fiscal_year_bs
        if not fy:
            out.append(o(U, "Tax clearance (F/Y not stated)", "Notice does not state the fiscal year.",
                         action="Check which fiscal year's tax clearance the notice asks for."))
            continue
        req = f"Tax clearance for F/Y {fy}"
        renew = (f"Renew tax clearance for F/Y {fy} (or get proof of tax-return filing for F/Y {fy}) from the Inland "
                 f"Revenue Office and upload it before submission.")
        docs, live, ev = _find(c, DocType.TAX_CLEARANCE, DocType.TAX_RETURN, fy=fy)
        if not docs:
            others = sorted(c.docs_of(DocType.TAX_CLEARANCE, DocType.TAX_RETURN), key=lambda d: d.fiscal_year_bs or "")
            on_file = [f"F/Y {d.fiscal_year_bs or '?'}" + (f" (expired {d.expiry})" if d.expiry and d.expiry < c.ref_date
                                                          else f" (valid to {d.expiry})" if d.expiry else "") for d in others]
            out.append(o(F, req, f"No clearance or tax-return proof for {fy}; on file: {', '.join(on_file) or 'none'}.",
                         docs=others, action=renew))
        elif not live:
            out.append(o(F, req, f"Document for {fy} expired on {max(d.expiry for d in docs)}, before the deadline ({c.ref_date}).",
                         docs=docs, action=renew))
        elif not ev:
            out.append(o(U, req, "Document has no KB chunk id.", docs=docs,
                         action=f"Re-upload the F/Y {fy} tax clearance as a text-readable file (scanned copies are not read)."))
        else:
            out.append(o(P, req, f"Document for {fy} on file.", [d.chunk_id for d in ev], docs=docs))
    return out


def _licence(c, p):
    req = f"Construction licence renewed for F/Y {c.fy}"
    renew = f"Renew the construction licence for F/Y {c.fy} and upload the renewed licence."
    lic = [l for l in c.company.licences if p["licence_type_contains"] in l.licence_type.lower()]
    if not lic:
        return [o(F, req, "No construction licence on company profile.",
                  action="Add the construction licence to the company profile and upload a copy.")]
    best = max(l.last_renewed_fy_bs or "" for l in lic)
    if not best:
        return [o(U, req, "Licence on profile has no last_renewed_fy_bs.",
                  action="Enter the licence's last renewal F/Y in the company profile.")]
    if best < c.fy:
        return [o(F, req, f"Last renewed for F/Y {best}; need {c.fy}.", action=renew)]
    renewals = c.docs_of(DocType.LICENCE_RENEWAL)
    if renewals and not c.live(renewals):
        return [o(F, req, f"Renewal document expired before {c.ref_date}.", docs=renewals, action=renew)]
    # Evidence: a live renewal record, or a licence copy recorded as renewed for the deadline's FY.
    proof = c.live(renewals) + [d for d in c.live(c.docs_of(DocType.BUSINESS_LICENCE)) if (d.fiscal_year_bs or "") >= c.fy]
    ids = [d.chunk_id for d in proof if d.chunk_id is not None]
    return [o(P, req, f"Profile shows renewal for F/Y {best}.", ids, ev="company.licences[].last_renewed_fy_bs", docs=proof,
              action=f"Upload the construction licence showing renewal for F/Y {best}.")]


def _turnover(c, p):
    k, req = c.criteria, "Minimum average annual turnover"
    if k.min_avg_turnover_npr is None:
        if not _has_req(c, RequirementCategory.FINANCIAL):
            return []
        return [o(U, req, "Notice has financial requirements but no structured turnover criterion was extracted.",
                  action="Read the notice's turnover requirement and check it by hand.")]
    need = format_npr(k.min_avg_turnover_npr)
    if not k.turnover_years:
        return [o(U, req, f"Minimum {need}, but the look-back years were not extracted from the notice.",
                  action=f"Check the notice's turnover period (e.g. 'best 3 of the last 5 years') against the {need} minimum.")]
    n = k.turnover_years
    prior = sorted((t for t in c.company.turnover if t.fiscal_year_bs < c.fy), key=lambda t: t.fiscal_year_bs, reverse=True)[:n]
    if len(prior) < n:
        return [o(U, req, f"Profile has {len(prior)} completed-FY turnover entries; notice needs {n}.",
                  action=f"Add turnover for the last {n} completed fiscal years to the company profile.")]
    total = sum(t.amount_npr for t in prior)
    fys = [t.fiscal_year_bs for t in prior]
    if total < k.min_avg_turnover_npr * n:
        return [o(F, req, f"Average {format_npr(total // n)} over {fys} is below required {need}.",
                  action=f"Turnover is below the {need} minimum. Bid only with a JV partner whose combined turnover meets it "
                         f"(if the notice allows JV), or skip this tender.")]
    audits = {fy: _find(c, DocType.AUDIT_REPORT, fy=fy) for fy in fys}
    if missing := [fy for fy, (_, _, ev) in audits.items() if not ev]:
        return [o(U, req, f"Profile figures meet the threshold but no evidenced audit report for {missing}.",
                  docs=[d for docs, _, _ in audits.values() for d in docs],
                  action=f"Upload audited financial statements for F/Y {', '.join(missing)}.")]
    evidenced = [d for _, _, ev in audits.values() for d in ev]
    return [o(P, req, f"Average {format_npr(total // n)} over {fys} meets {need}.", [d.chunk_id for d in evidenced], docs=evidenced)]


def _experience(c, p):
    k, req = c.criteria, "Similar-experience projects"
    value = f" of at least {format_npr(k.min_similar_value_npr)}" if k.min_similar_value_npr else ""
    docs = c.docs_of(DocType.EXPERIENCE_CERTIFICATE)
    if k.min_similar_projects is None:
        if not _has_req(c, RequirementCategory.EXPERIENCE):
            return []
        return [o(U, req, f"Notice has experience requirements{value} but the number of contracts was not extracted.", docs=docs,
                  action=f"Check the notice's similar-work requirement{value} against the completion certificates.")]

    def big_enough(d):
        return k.min_similar_value_npr is None or (d.value_npr is not None and d.value_npr >= k.min_similar_value_npr)

    match = [d for d in docs if d.similar is True and big_enough(d)]
    ev = [d for d in match if d.chunk_id is not None]
    undecided = [d for d in docs if d.similar is None and big_enough(d)]
    n = k.min_similar_projects
    if len(ev) >= n:
        return [o(P, req, f"{len(ev)} qualifying project(s); need {n}.", [d.chunk_id for d in ev], docs=ev)]
    if len(match) + len(undecided) >= n:
        return [o(U, req, f"{len(match)} confirmed similar ({len(match) - len(ev)} without chunk id), {len(undecided)} not classified; need {n}.",
                  docs=match + undecided, action=f"Confirm that {n} completion certificate(s){value} are for work similar to this tender.")]
    return [o(F, req, f"{len(match)} qualifying project(s){value}; need {n}.", docs=docs,
              action=f"No {n} similar contract(s){value} on file. Upload qualifying completion certificates, or bid with a "
                     f"JV partner whose experience meets it (if the notice allows JV).")]


def _bid_security(c, p):
    req, calc = "Bid security", calc_bid_security(c.tender, bid_price_npr=c.bid_price)
    if c.tender.bid_security is None:
        return []
    if calc.amount_npr is None:
        return [o(U, req, f"Amount not computable: {calc.basis}.", action="Work out the bid security from your bid price.")]
    need = f"{format_npr(calc.amount_npr)} ({calc.basis})" + (f", valid until {calc.valid_until} AD / {calc.valid_until_bs} BS" if calc.valid_until else ", validity not stated")
    until = f" valid until at least {calc.valid_until} AD ({calc.valid_until_bs} BS)" if calc.valid_until else ""
    arrange = f"Arrange a bank guarantee of {format_npr(calc.amount_npr)}{until} (or the cash deposit the notice allows) before submission."
    docs = c.docs_of(DocType.BID_SECURITY)
    if not docs:
        return [o(U, req, f"Required: {need}. No guarantee on file yet.", action=arrange)]
    cands = [d for d in docs if d.chunk_id is not None]
    if not cands:
        return [o(U, req, f"Required: {need}. Guarantee on file has no KB chunk id.", docs=docs,
                  action="Re-upload the bank guarantee as a text-readable file so its amount and expiry can be checked.")]
    ok = [d for d in cands if d.value_npr is not None and d.value_npr >= calc.amount_npr and calc.valid_until and d.expiry and d.expiry >= calc.valid_until]
    if ok:
        return [o(P, req, f"Guarantee covers {need}.", [d.chunk_id for d in ok], docs=ok)]
    if calc.valid_until is None:
        return [o(U, req, f"Required: {need}. Cannot verify expiry.", docs=docs, action="Check the guarantee's validity against the notice.")]
    return [o(F, req, f"Required: {need}. Guarantee on file is too small or expires too early.", docs=docs, action=arrange)]


def _perf_security(c, p):
    calc = calc_performance_security(c.tender, contract_price_npr=c.bid_price)
    if c.tender.performance_security_percent is None:
        return []
    amt = format_npr(calc.amount_npr) if calc.amount_npr is not None else "not computable (no price)"
    return [o(U, "Performance security", f"{calc.basis} = {amt}. Furnished after award; not checkable now.",
              action=f"If awarded, furnish a performance security of {calc.basis} ({amt}).")]


def _jv(c, p):
    if not any(i.status is F and i.rule_id in p["when_failed"] for i in c.prior):
        return []
    req, jv, partners = "Joint venture route", c.tender.jv_allowed, c.company.jv_partners
    if jv is False:
        return [o(F, req, "A qualification rule failed and the notice does not allow JV.",
                  action="No JV route: the notice bars joint ventures, so a partner cannot cover the failed qualification.")]
    if jv is None:
        return [o(U, req, "A qualification rule failed; notice is silent on JV.", action="Ask the buyer whether a JV bid is accepted.")]
    if not partners:
        return [o(F, req, "JV allowed but no JV partner on company profile.",
                  action="Find a JV partner whose turnover/experience covers the gap and add them to the company profile.")]
    agreements = c.live(c.docs_of(DocType.JV_AGREEMENT))
    names = ", ".join(pt.name for pt in partners)
    return [o(P, req, f"JV allowed; partner(s) on profile: {names}. Pooled qualification (PPR Rule 28(4)) is not evaluated.",
              [d.chunk_id for d in agreements if d.chunk_id is not None], docs=agreements,
              action=f"Sign a JV agreement with {names}, check the partners' combined qualifications, and upload the agreement.")]


def _domestic(c, p):
    if not c.tender.domestic_preference:
        return []
    return [o(U, "Domestic preference", "Notice grants domestic preference; company's eligibility to claim it is not determined. No percentage applied.",
              action="Check whether the company qualifies for the domestic preference and claim it in the bid.")]


def _doc_validity(c, p):
    """Eligibility documents that are valid at the deadline but lapse while the bid must stay valid."""
    days = c.tender.bid_validity_days
    if not days or c.deadline is None:
        return []
    end = c.ref_date + timedelta(days=days)
    types = ({DocType(x) for x in p["doc_types"]} | {d.doc_type for d in c.tender.required_docs if d.mandatory}) - \
        {DocType(x) for x in p["exclude"]}
    dated = [d for d in c.live(c.docs_of(*types)) if d.expiry is not None]
    if not dated:
        return []
    lapsing = [d for d in dated if d.expiry < end]
    req = f"Documents valid through the bid validity period ({days} days, to {end})"
    if lapsing:
        names = "; ".join(f"{label(d.doc_type)} expires {d.expiry}" for d in lapsing)
        return [o(U, req, f"Valid at the deadline but lapsing before {end}: {names}.", docs=lapsing,
                  action=f"Renew the {labels(dict.fromkeys(d.doc_type for d in lapsing))} before {min(d.expiry for d in lapsing)}: "
                         f"it lapses during the bid validity period (until {end} AD / {ad_to_bs(end).iso()} BS).")]
    return [o(P, req, f"{len(dated)} dated document(s) stay valid until at least {end}.",
              [d.chunk_id for d in dated if d.chunk_id is not None], docs=dated)]


# Which rule checks each document type a notice can ask for. Used by NP-OTHER-DOCS (so a listed document is never
# dropped) and by agents.compliance (a requirement naming only these types is left to the rules, not the model).
DOC_RULES: dict[DocType, str] = {
    DocType.COMPANY_REGISTRATION: "NP-REG-DOCS", DocType.BUSINESS_LICENCE: "NP-REG-DOCS",
    DocType.SELF_DECLARATION: "NP-BID-FORMS", DocType.POWER_OF_ATTORNEY: "NP-BID-FORMS", DocType.PAN_VAT: "NP-PAN-VAT",
    DocType.TAX_CLEARANCE: "NP-TAX-CLEARANCE", DocType.TAX_RETURN: "NP-TAX-CLEARANCE",
    DocType.LICENCE_RENEWAL: "NP-LICENCE-RENEWAL", DocType.BID_SECURITY: "NP-BID-SECURITY",
    DocType.AUDIT_REPORT: "NP-TURNOVER", DocType.EXPERIENCE_CERTIFICATE: "NP-EXPERIENCE", DocType.JV_AGREEMENT: "NP-JV",
}


def _other_docs(c, p):
    """Mandatory notice documents no other rule checked (type `other`, or a tracked type whose rule did not fire).

    Runs last. A document on file is a pass; otherwise unclear with an action, never a fail: this rule only makes sure
    nothing the notice lists is silently dropped.
    """
    fired = {i.rule_id for i in c.prior}
    out = []
    for r in c.tender.required_docs:
        if not r.mandatory or (r.doc_type is not DocType.OTHER and DOC_RULES.get(r.doc_type) in fired):
            continue
        req = f"Notice document: {r.description}"
        if r.doc_type is DocType.OTHER:
            out.append(o(U, req, "Not a document type Tenderly tracks, so it is not checked automatically.",
                         action=f"Prepare '{r.description}' for the bid, as the notice asks."))
            continue
        docs, live, ev = _find(c, r.doc_type, fy=r.fiscal_year_bs)
        if ev:
            out.append(o(P, req, f"A {label(r.doc_type)} is on file.", [d.chunk_id for d in ev], docs=ev))
            continue
        why = f"No unexpired, readable {label(r.doc_type)} on file" + (f" for F/Y {r.fiscal_year_bs}" if r.fiscal_year_bs else "") + "."
        hint = " (needed only if you bid as a joint venture)" if r.doc_type is DocType.JV_AGREEMENT else ""
        out.append(o(U, req, why, docs=docs, action=f"Upload the {label(r.doc_type)}{hint}, as the notice asks."))
    return out


CHECKS = {
    "deadline_not_passed": _deadline_check, "required_documents_present": _reg_docs, "bid_forms": _bid_forms,
    "pan_vat_present": _pan_vat, "tax_clearance_current": _tax, "licence_renewed": _licence, "min_avg_turnover": _turnover,
    "similar_experience": _experience, "bid_security_check": _bid_security, "performance_security_info": _perf_security,
    "jv_route": _jv, "domestic_preference_flag": _domestic, "documents_valid_through_bid_validity": _doc_validity,
    "other_notice_documents": _other_docs,
}


def _applies(rule: Rule, t: TenderRecord) -> bool:
    a = rule.applies_to
    return (not a.procurement_types or t.procurement_type in a.procurement_types) and (not a.methods or t.method in a.methods)


def evaluate_rules(
    tender: TenderRecord,
    company: CompanyProfile,
    documents: list[DocumentMeta],
    *,
    criteria: TenderCriteria | None = None,
    bid_price_npr: int | None = None,
    now: datetime | None = None,
    rules: tuple[Rule, ...] | None = None,
) -> list[ComplianceItem]:
    now = now or datetime.now(NPT)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    c = Ctx(tender, company, documents, criteria or tender.criteria, now, bid_price_npr, _deadline(tender))
    items: list[ComplianceItem] = []
    for rule in rules or load_rules():
        if not _applies(rule, tender):
            continue
        for out in CHECKS[rule.check](c, rule.parameters):
            item = ComplianceItem(
                requirement=out.requirement, status=out.status, severity=rule.severity, source=ItemSource.RULE,
                rule_id=rule.id, evidence_chunk_ids=out.chunk_ids, evidence_document_ids=out.doc_ids, evidence_ref=out.ref,
                explanation=out.why + ("" if rule.verified else " [rule unverified: see NEPAL_CONTEXT.md]"),
                action_needed=out.action,
            )
            c.prior.append(item)
            items.append(item)
    return items

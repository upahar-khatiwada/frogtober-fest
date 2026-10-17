"""Rules evaluator and security calculators. Deterministic: no LLM, no statutory defaults.

Every result is a `ComplianceItem` with `rule_id` set. A "pass" needs evidence (KB chunk ids from
document metadata, or a named profile/notice field); otherwise it is downgraded to "unclear".
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
from schemas import CompanyProfile, ComplianceItem, ComplianceStatus, DocType, ProcurementMethod, ProcurementType, RequirementCategory, Severity, TenderRecord
from schemas._base import Contract, FiscalYearBS

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
    """What the KB knows about one uploaded document (from ingest, not from the LLM)."""
    doc_type: DocType
    chunk_id: int | None = None
    expiry: date | None = None
    fiscal_year_bs: FiscalYearBS | None = None
    value_npr: int | None = Field(None, ge=0, description="Guarantee amount or contract value.")
    similar: bool | None = Field(None, description="Experience certificate similar to this tender? None = not classified.")


class TenderCriteria(Contract):
    """Numeric qualification criteria extracted from the notice. TODO: move into TenderRecord (Scout)."""
    min_avg_turnover_npr: int | None = Field(None, ge=0)
    turnover_years: int | None = Field(None, gt=0)
    min_similar_projects: int | None = Field(None, gt=0)
    min_similar_value_npr: int | None = Field(None, ge=0)


class SecurityCalc(Contract):
    amount_npr: int | None
    valid_until: date | None = None
    valid_until_bs: str | None = None
    basis: str


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


def o(status, req, why, ids=(), ev=None):
    """One outcome. The single place that enforces 'never pass without evidence'."""
    ids = list(ids)
    if status is P and not (ids or ev):
        status, why = U, why + " No evidence available, so not marked pass."
    return status, req, why + (f" Evidence: {ev}." if ev else ""), ids


def _find(c: Ctx, *types: DocType, fy: str | None = None):
    """(all, unexpired, unexpired with a chunk id) documents of the given types."""
    docs = [d for d in c.docs_of(*types) if fy is None or d.fiscal_year_bs == fy]
    live = c.live(docs)
    return docs, live, [d for d in live if d.chunk_id is not None]


def _has_req(c: Ctx, cat: RequirementCategory) -> bool:
    return any(r.mandatory and r.category is cat for r in c.tender.requirements)


def _deadline_check(c, p):
    req = "Submission deadline not passed"
    if c.deadline is None:
        return [o(U, req, "Notice has no parseable deadline.")]
    if c.now > c.deadline:
        return [o(F, req, f"Deadline {c.deadline.astimezone(NPT):%Y-%m-%d %H:%M} NPT has passed.")]
    return [o(P, req, f"{days_left(c.deadline, c.now)} day(s) left (deadline {c.deadline.astimezone(NPT):%Y-%m-%d %H:%M} NPT).", ev="tender.deadline")]


def _reg_docs(c, p):
    need = [DocType(x) for x in p["statutory_doc_types"]]
    need += [d.doc_type for d in c.tender.required_docs if d.mandatory and d.doc_type.value in p["also_from_notice"]]
    miss, exp, noev, ids = [], [], [], []
    for t in dict.fromkeys(need):
        docs, live, ev = _find(c, t)
        if not docs:
            miss.append(t.value)
        elif not live:
            exp.append(t.value)
        elif not ev:
            noev.append(t.value)
        ids += [d.chunk_id for d in ev]
    req = "Registration documents"
    if miss or exp:
        return [o(F, req, f"Missing: {miss or '-'}; expired before {c.ref_date}: {exp or '-'}.")]
    if noev:
        return [o(U, req, f"On file but without a KB chunk id: {noev}.")]
    return [o(P, req, "All required registration documents on file and unexpired.", ids)]


def _pan_vat(c, p):
    req = "PAN/VAT registration"
    note = " PAN format not validated." + ("" if c.company.vat_number else " No VAT number on profile.")
    docs, live, ev = _find(c, DocType.PAN_VAT)
    if not (c.company.pan_number or "").strip():
        return [o(F, req, "No PAN number on company profile." + note)]
    if not docs:
        return [o(F, req, "No pan_vat document on file." + note)]
    if not live:
        return [o(F, req, f"pan_vat document expired before {c.ref_date}." + note)]
    if not ev:
        return [o(U, req, "pan_vat document has no KB chunk id." + note)]
    return [o(P, req, "PAN on profile and certificate on file." + note, [d.chunk_id for d in ev])]


def _tax(c, p):
    out = []
    for r in (d for d in c.tender.required_docs if d.doc_type is DocType.TAX_CLEARANCE and d.mandatory):
        fy = r.fiscal_year_bs
        if not fy:
            out.append(o(U, "Tax clearance (F/Y not stated)", "Notice does not state the fiscal year."))
            continue
        req = f"Tax clearance for F/Y {fy}"
        docs, live, ev = _find(c, DocType.TAX_CLEARANCE, DocType.TAX_RETURN, fy=fy)
        if not docs:
            other = sorted({d.fiscal_year_bs for d in c.docs_of(DocType.TAX_CLEARANCE) if d.fiscal_year_bs})
            out.append(o(F, req, f"No clearance or tax-return proof for {fy}; clearances on file: {other or 'none'}."))
        elif not live:
            out.append(o(F, req, f"Document for {fy} expired before {c.ref_date}."))
        elif not ev:
            out.append(o(U, req, "Document has no KB chunk id."))
        else:
            out.append(o(P, req, f"Document for {fy} on file.", [d.chunk_id for d in ev]))
    return out


def _licence(c, p):
    req = f"Construction licence renewed for F/Y {c.fy}"
    lic = [l for l in c.company.licences if p["licence_type_contains"] in l.licence_type.lower()]
    if not lic:
        return [o(F, req, "No construction licence on company profile.")]
    best = max(l.last_renewed_fy_bs or "" for l in lic)
    if not best:
        return [o(U, req, "Licence on profile has no last_renewed_fy_bs.")]
    if best < c.fy:
        return [o(F, req, f"Last renewed for F/Y {best}; need {c.fy}.")]
    renewals = c.docs_of(DocType.LICENCE_RENEWAL)
    if renewals and not c.live(renewals):
        return [o(F, req, f"Renewal document expired before {c.ref_date}.")]
    ids = [d.chunk_id for d in c.live(renewals) if d.chunk_id is not None]
    return [o(P, req, f"Profile shows renewal for F/Y {best}.", ids, ev="company.licences[].last_renewed_fy_bs")]


def _turnover(c, p):
    k, req = c.criteria, "Minimum average annual turnover"
    if k.min_avg_turnover_npr is None:
        return [o(U, req, "Notice has financial requirements but no structured turnover criterion was extracted.")] if _has_req(c, RequirementCategory.FINANCIAL) else []
    if not k.turnover_years:
        return [o(U, req, "Look-back years not extracted from the notice.")]
    n = k.turnover_years
    prior = sorted((t for t in c.company.turnover if t.fiscal_year_bs < c.fy), key=lambda t: t.fiscal_year_bs, reverse=True)[:n]
    if len(prior) < n:
        return [o(U, req, f"Profile has {len(prior)} completed-FY turnover entries; notice needs {n}.")]
    total = sum(t.amount_npr for t in prior)
    fys = [t.fiscal_year_bs for t in prior]
    if total < k.min_avg_turnover_npr * n:
        return [o(F, req, f"Average {format_npr(total // n)} over {fys} is below required {format_npr(k.min_avg_turnover_npr)}.")]
    audits = {fy: _find(c, DocType.AUDIT_REPORT, fy=fy)[2] for fy in fys}
    if missing := [fy for fy, ev in audits.items() if not ev]:
        return [o(U, req, f"Profile figures meet the threshold but no evidenced audit report for {missing}.")]
    return [o(P, req, f"Average {format_npr(total // n)} over {fys} meets {format_npr(k.min_avg_turnover_npr)}.", [d.chunk_id for ev in audits.values() for d in ev])]


def _experience(c, p):
    k, req = c.criteria, "Similar-experience projects"
    if k.min_similar_projects is None:
        return [o(U, req, "Notice has experience requirements but no structured criterion was extracted.")] if _has_req(c, RequirementCategory.EXPERIENCE) else []

    def big_enough(d):
        return k.min_similar_value_npr is None or (d.value_npr is not None and d.value_npr >= k.min_similar_value_npr)

    docs = c.docs_of(DocType.EXPERIENCE_CERTIFICATE)
    match = [d for d in docs if d.similar is True and big_enough(d)]
    ev = [d for d in match if d.chunk_id is not None]
    undecided = [d for d in docs if d.similar is None and big_enough(d)]
    n = k.min_similar_projects
    if len(ev) >= n:
        return [o(P, req, f"{len(ev)} qualifying project(s); need {n}.", [d.chunk_id for d in ev])]
    if len(match) + len(undecided) >= n:
        return [o(U, req, f"{len(match)} confirmed similar ({len(match) - len(ev)} without chunk id), {len(undecided)} not classified; need {n}.")]
    return [o(F, req, f"{len(match)} qualifying project(s); need {n}.")]


def _bid_security(c, p):
    req, calc = "Bid security", calc_bid_security(c.tender, bid_price_npr=c.bid_price)
    if c.tender.bid_security is None:
        return []
    if calc.amount_npr is None:
        return [o(U, req, f"Amount not computable: {calc.basis}.")]
    need = f"{format_npr(calc.amount_npr)} ({calc.basis})" + (f", valid until {calc.valid_until} AD / {calc.valid_until_bs} BS" if calc.valid_until else ", validity not stated")
    docs = c.docs_of(DocType.BID_SECURITY)
    if not docs:
        return [o(U, req, f"Required: {need}. No guarantee on file yet.")]
    cands = [d for d in docs if d.chunk_id is not None]
    if not cands:
        return [o(U, req, f"Required: {need}. Guarantee on file has no KB chunk id.")]
    ok = [d for d in cands if d.value_npr is not None and d.value_npr >= calc.amount_npr and calc.valid_until and d.expiry and d.expiry >= calc.valid_until]
    if ok:
        return [o(P, req, f"Guarantee covers {need}.", [d.chunk_id for d in ok])]
    if calc.valid_until is None:
        return [o(U, req, f"Required: {need}. Cannot verify expiry.")]
    return [o(F, req, f"Required: {need}. Guarantee on file is too small or expires too early.")]


def _perf_security(c, p):
    calc = calc_performance_security(c.tender, contract_price_npr=c.bid_price)
    if c.tender.performance_security_percent is None:
        return []
    amt = format_npr(calc.amount_npr) if calc.amount_npr is not None else "not computable (no price)"
    return [o(U, "Performance security", f"{calc.basis} = {amt}. Furnished after award; not checkable now.")]


def _jv(c, p):
    if not any(i.status is F and i.rule_id in p["when_failed"] for i in c.prior):
        return []
    req, jv, partners = "Joint venture route", c.tender.jv_allowed, c.company.jv_partners
    if jv is False:
        return [o(F, req, "A qualification rule failed and the notice does not allow JV.")]
    if jv is None:
        return [o(U, req, "A qualification rule failed; notice is silent on JV.")]
    if not partners:
        return [o(F, req, "JV allowed but no JV partner on company profile.")]
    return [o(P, req, f"JV allowed; {len(partners)} partner(s) on profile. Pooled qualification (PPR Rule 28(4)) is not evaluated.", ev=f"company.jv_partners ({len(partners)})")]


def _domestic(c, p):
    if not c.tender.domestic_preference:
        return []
    return [o(U, "Domestic preference", "Notice grants domestic preference; company's eligibility to claim it is not determined. No percentage applied.")]


CHECKS = {
    "deadline_not_passed": _deadline_check, "required_documents_present": _reg_docs, "pan_vat_present": _pan_vat,
    "tax_clearance_current": _tax, "licence_renewed": _licence, "min_avg_turnover": _turnover,
    "similar_experience": _experience, "bid_security_check": _bid_security, "performance_security_info": _perf_security,
    "jv_route": _jv, "domestic_preference_flag": _domestic,
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
    c = Ctx(tender, company, documents, criteria or TenderCriteria(), now, bid_price_npr, _deadline(tender))
    items: list[ComplianceItem] = []
    for rule in rules or load_rules():
        if not _applies(rule, tender):
            continue
        for status, req, why, ids in CHECKS[rule.check](c, rule.parameters):
            item = ComplianceItem(
                requirement=req, status=status, severity=rule.severity, evidence_chunk_ids=ids,
                explanation=why + ("" if rule.verified else " [rule unverified: see NEPAL_CONTEXT.md]"), rule_id=rule.id,
            )
            c.prior.append(item)
            items.append(item)
    return items
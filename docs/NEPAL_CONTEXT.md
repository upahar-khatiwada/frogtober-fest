# Nepal Procurement Context (reference for Tenderly)

> **Status:** researched 2026-10-15 (BS 2083). This is a working reference for prompts, schemas, seed data and deterministic rules. It is **not legal advice**.
>
> **Citation rule:** every number or rule cites a source. Anything not confirmed from an official or primary text is marked **`[VERIFY]`**. Do **not** hard-code a `[VERIFY]` value as a gate in code. Make it configurable, or extract it from the tender notice itself (the notice is always the authority for that tender).

## 0. Sources and how current they are

| Key | Source | Notes |
|---|---|---|
| **PPA** | Public Procurement Act, 2063 (2007), English text section by section: <https://nepallaws.com/Laws/public-procurement-act-2063/> | Secondary host of the official translation. Official publisher: Nepal Law Commission (lawcommission.gov.np). The Act has been amended (first amendment 2016 per <https://pioneerlaw.com/amendment-to-public-procurement-law/>). |
| **PPR-EN** | Public Procurement Rules, 2064 (2007), Law Commission English translation, **amended only up to the 2nd Amendment (2065 / Dec 2008)**: <https://www.fsmtoolbox.com/assets/pdf/32._Public-procurement-rule-2064.pdf> (mirror of a lawcommission.gov.np PDF) | Primary text, but **out of date**. Many amounts below come from this 2008 text and have since been revised. |
| **PPR-NE** | सार्वजनिक खरिद नियमावली, २०६४ (Nepali consolidated text listing amendments up to the 11th Amendment, 2078): <https://vpn.gov.np/rules/सार्वजनिक-खरिद-नियमावली-२०६४-1650875022.pdf> | Not parsed in this pass. **TODO:** extract current thresholds from it. |
| **12th amendment** | Samriddhi analysis of the 12th amendment of the PPR: <https://samriddhi.org/uncategorized/twelfth-amendment-of-public-procurement-regulation-implications-on-construction-regime/> | Secondary. Not read in detail. |
| **Pending law change** | A "Bill to Amend the Public Procurement Act, 2063, 2082" (reverse auction; bids 50% below or 30% above the estimate flagged as abnormal): <https://english.ratopati.com/story/58295/reverse-auction-in-government-contracts-price-can-be-reduced-by-looking-at-the-bid>. An amendment ordinance on e-bidding and low bids was reported on 2083 Baisakh 17: <https://www.onlinekhabar.com/?p=1921882> | `[VERIFY]` whether either is in force. |

**Implication for Tenderly:** treat the law's amounts as *context*. The deterministic compliance checks should read the bid-security amount, validity, deadline and required documents **from each tender notice**, not from statutory defaults.

---

## 1. Procurement types

The Act and Rules distinguish **goods**, **construction works**, **consultancy services**, and **other (non-consulting) services**. PPA §8(1)(a) covers "goods, construction works or other services", and §8(1)(b) covers consultancy services separately. Source: <https://nepallaws.com/Laws/public-procurement-act-2063/chapter-2-provision-relating-to-responsibility-for-procurement-and-procurement-methods/section-8-procurement-method-to-be-selected/>

Suggested enum for `TenderRecord.procurement_type`: `goods | works | consulting | non_consulting | unknown`.

## 2. Procurement methods

### 2.1 Methods named in the Act (PPA §8)

For goods, works and other services (§8(1)(a)): international open bidding (ICB), national open bidding (NCB), sealed quotation, direct procurement, users' committee / beneficiary group, force account, lump-sum (percentage) bid, catalogue shopping, limited tendering, and buy-back. For consultancy (§8(1)(b)): competitive proposals and direct negotiation. §8 forbids splitting a procurement "in piecemeal as to limit competition". It sets **no amounts** and says the method depends on value "as prescribed" in the Rules. Source: PPA §8 (URL above).

**When ICB is required (PPA §15):** fewer than two domestic suppliers can supply competitively; an NCB drew no bids; a donor agreement requires it; or the goods or works are complex and specialised. The ICB notice and documents must be in English. Source: <https://nepallaws.com/Laws/public-procurement-act-2063/chapter-3-provisions-relating-to-bid/section-15-international-level-bidding/>

**Prequalification:** used when invitation to bid follows prequalification. PPR-EN Rules 32–36 cover the prequalification documents, criteria and evaluation. Under PPA §25, bids from non-prequalified bidders are excluded in that case. Sources: PPR-EN (Rules 32–36); <https://nepallaws.com/Laws/public-procurement-act-2063/chapter-3-provisions-relating-to-bid/section-25-evaluation-of-bids/>

**EOI → RFP (consulting):** a public notice invites letters of intent (EOI) to make a short list (PPR-EN Rule 70), then a request for proposals goes to the short list (Rule 71). Source: PPR-EN.

### 2.2 Value thresholds

| Rule (PPR-EN, 2008 text) | Amount in 2008 text | Current value |
|---|---|---|
| Rule 31(1): goods, works or services must go through a **tender** above | NPR 1,000,000 (10 lakh) | `[VERIFY]` revised by later amendments |
| Rule 84(1): **sealed quotation** allowed up to | NPR 1,000,000 | `[VERIFY]`. PPMO SBD templates found on municipal sites are labelled "works up to NRs 2 million" and "goods NRs 0.5–2.0 million (health equipment/drugs 0.5–5.0 million)": <https://sigasmun.gov.np/sites/sigasmun.gov.np/files/SQ%2015%20bed%20health_0.pdf>, <https://www.kankaimun.gov.np/sites/kankaimun.gov.np/files/sanatary%20pad.pdf> |
| Rule 85(1): **direct procurement** up to | NPR 150,000 | `[VERIFY]` |
| Rule 70(1): consulting above this value needs a public **EOI** | NPR 1,000,000 | `[VERIFY]` |
| Rule 70(2): **international EOI** for consulting above | NPR 30,000,000 | `[VERIFY]` |
| Rule 72(1): consulting below this may use the standing list | NPR 1,000,000 | `[VERIFY]` |
| Rule 101: no **review committee** application below | NPR 30,000,000 | `[VERIFY]` |
| PPMO NCB works SBD scope | "works between NRs 2 million and NRs 20 million" (SBD of Jan 2017, revised) per <https://www.guthichaurmun.gov.np/sites/guthichaurmun.gov.np/files/Standard%20Bid%20Doc.%20for%20Adhalikhola%20MHP.pdf> | `[VERIFY]` (secondary; seen in a municipal copy) |

Do **not** use these to decide anything in code. They are for UI hints and seed-data realism only.

### 2.3 Evaluation methods

- **Goods, works, services: lowest evaluated substantially responsive bid.** The bid with the lowest evaluated price is checked against the qualification criteria. If it fails, the next lowest is checked. Minor deviations are priced in, and deviations above **15%** of the bid price make a bid substantially non-responsive. Source: PPA §25 <https://nepallaws.com/Laws/public-procurement-act-2063/chapter-3-provisions-relating-to-bid/section-25-evaluation-of-bids/>
- **Sealed quotation:** an evaluation committee evaluates the quotations, and acceptance follows PPA §40(5) within 15 days of opening. Source: PPR-EN Rule 84(9)–(10). (Rule 89, which covers ration procurement only, says to accept the lowest bidder.) `[VERIFY]` that lowest-price acceptance is the general SQ rule.
- **Consulting (PPR-EN Rule 74):** Quality and Cost Based Selection (**QCBS**), Quality Based Selection (**QBS**, needs the departmental head's approval for complex or policy work), **Budget Ceiling** (fixed budget stated in the RFP), and **Least Cost Selection** (routine work such as audits). Source: PPR-EN Rule 74.
- **QCBS weights (PPR-EN Rule 71(4)(a)):** technical **70–90**, financial **30–10**, total 100. Technical sub-weights (Rule 71(6)): firm's specific experience up to 10%, methodology 20–50%, key personnel 30–60%, technology transfer/training up to 10%, participation of nationals up to 10% (not applied to national proposals). `[VERIFY]` against current amendments. Source: PPR-EN.

## 3. Eligibility and qualification documents

**Statutory list (PPR-EN Rule 40(2)):** the tender documents must state the eligibility documents, which are:
1. (a) Firm, organisation or company **registration certificate**
2. (b) **Business registration licence**. For works this means the construction entrepreneur's licence under the construction business law.
3. (c) **VAT registration** and **PAN** certificate
4. (d) **Tax clearance** from the Inland Revenue Department, *or* proof of tax-return submission for the period the entity specifies
5. (e) Written **self-declaration**: not disqualified, no conflict of interest, not punished for a profession or business offence
6. (f) Other documents the entity considers necessary

A bid missing these "shall not be entertained" (Rule 40(4)). Source: PPR-EN Rule 40.

**What real notices ask for (secondary, municipal notices 2019–2024):**
- Firm registration, business licence, VAT and PAN certificate, tax clearance, self-declaration, power of attorney, bid security, sufficient bid validity: <https://panchakanyamun.gov.np/sites/panchakanyamun.gov.np/files/BID%20DOCUMENT.pdf>
- Tax clearance **for a named fiscal year** (e.g. "F/Y 2077-78"), *or* tax-return submission evidence, *or* evidence of a tax time extension: <https://www.dakshinkalimun.gov.np/sites/dakshinkalimun.gov.np/files/%5BDownload%5D%20Bolpatra%202078-07-17.pdf>
- VAT, PAN and tax clearance listed as "other eligibility" for **domestic bidders**, and each JV partner must meet them: <https://www.bhokrahamun.gov.np/sites/bhokrahamun.gov.np/files/BID%20DOCUMENT_3.pdf>
- Copies of registration, VAT and tax clearance of F/Y 2078/79 required: <https://kageshworimanoharamun.gov.np/sites/kageshworimanoharamun.gov.np/files/tendor%20notice.pdf>

**Licence renewal and contractor classes:**
- Construction licences have classes **A, B, C, D**. A, B and C are issued by the federal government on committee recommendation, and D is issued by local government. Source: <https://lawbhandari.com/publication/construction-company-registration-process-in-nepal> `[VERIFY]` (secondary). Sources **disagree** on the capital and contract-value limits per class (compare that page with <https://primelawnepal.com/?p=4370>), so do not encode class limits.
- Construction licences must be **renewed each fiscal year** (Construction Business Act 2055, §4(3), as reported). The ministry revoked 44 licences for non-renewal in July 2026: <https://www.sharesansar.com/newsdetail/ministry-of-infrastructure-development-revokes-licenses-of-44-construction-firms-2026-07-08> `[VERIFY]` against the Act text.
- Business or trade licence renewal for non-construction firms (e.g. municipal business registration): rules vary by issuer. `[VERIFY]`

**Financial and experience criteria:** PPR-EN Rule 28(3) (for JV partners) lists average annual turnover, specific experience and major works, available cash flow, human resources, and equipment. Actual figures (e.g. "average turnover ≥ X × estimate", "similar works ≥ Y") are **set per tender** in the bidding data sheet. Extract them from the notice. Audited financial statements and similar-experience completion certificates are the usual evidence. `[VERIFY]` (no official source read for the exact wording).

**Blacklisting:** PPR-EN Rule 39 refers to blacklisting under Rule 141. Bidders declare they are not disqualified (Rule 40(2)(e)). PPMO publishes a blacklist. `[VERIFY]` (URL not confirmed).

**Joint ventures (PPR-EN Rule 28):**
- A bidder may bid only **once**, either alone or as a JV partner (Rule 28(1) proviso).
- The entity may set a minimum share per partner and minimum qualifications for the lead and other partners (28(2)).
- **Partners' qualifications are added together** to test the JV against the minimum criteria (28(4)).
- If selected, the JV must register PAN/VAT with the Inland Revenue Office with joint and several liability (28(6)).
- The bid guarantee must be in the names of **all partners** (28(7)).

Source: PPR-EN Rule 28.

## 4. Bid security and performance security

| Item | Rule (PPR-EN, 2008 text unless noted) | Value |
|---|---|---|
| Bid (tender) security | Rule 53(1) | **At least 2.5% of the bid price**, cash or commercial-bank guarantee. A foreign-bank guarantee needs a Nepali bank counter-guarantee (53(4)). Current practice: the notice states a **fixed NPR amount**. Example: a Nepal Rastra Bank tender asked for Rs 1,02,000 on an estimate of about Rs 34.3 lakh (≈3%), per a web-search snippet of an nrb.org.np/gsd/ notice (page not opened). `[VERIFY]` current % range |
| Bid security validity | Rule 53(2) | At least **30 days beyond** bid validity |
| Bid validity | Rule 54 | **90 days** if estimate ≤ NPR 100 million; **120 days** if above. `[VERIFY]` current |
| Bid validity (Act) | PPA §20 | Set by the bidding documents, counted from the submission deadline. Extension needs bidder consent, and bid security must be extended to match: <https://nepallaws.com/Laws/public-procurement-act-2063/chapter-3-provisions-relating-to-bid/section-20-validity-period-of-bid/> |
| Bid security forfeiture | PPA §21 | Forfeited for withdrawal or modification during validity, refusing arithmetic correction, not signing the contract, not furnishing performance security, or changing price in clarification. Returned after contract signing: <https://nepallaws.com/Laws/public-procurement-act-2063/chapter-3-provisions-relating-to-bid/section-21-bid-security/> |
| Sealed-quotation security | Rule 84(6) | 2.5% of quoted price, bank guarantee valid **75 days**. Quotation validity **45 days** (84(7)) |
| Performance security | Rule 110(2) | **5% of contract price**, valid at least **one month beyond** the latest delivery / defects period (110(4)) |
| Sealed-quotation performance security | Rule 84(12) | 5% of quoted price |
| Additional security for very low bids (works) | Rule 65(3), 2008 text | **8% of bid price** if the low-price explanation is accepted. Later amendments replaced this with a formula for bids more than 15% below estimate (5% up to 15% below, more beyond): <https://www.slideshare.net/slideshow/procurement-of-works/250067640> `[VERIFY]` (secondary; exact formula not confirmed) |

**Tenderly rule:** compute *nothing* from these percentages. Extract `bid_security_amount_npr`, `bid_security_validity` and `bid_validity_days` from the notice. Deterministic checks compare the company's available guarantee/expiry dates against those values.

## 5. Domestic preference

- **Goods made in Nepal:** public entities shall procure domestically manufactured goods even if they cost **up to 10% more** than foreign goods. Source: PPR-EN Rule 17. `[VERIFY]` (still 10% after amendments?)
- **Evaluation:** if the tender documents grant preference to domestic goods or local construction entrepreneurs, the committee adds the preference amount to the **foreign bidder's** price. Source: PPR-EN Rule 64(4).
- PPA §25 (evaluation) and §15 (ICB) contain **no** preference percentages: <https://nepallaws.com/Laws/public-procurement-act-2063/chapter-3-provisions-relating-to-bid/section-15-international-level-bidding/>
- Margin of preference for domestic **contractors/consultants** in ICB: `[VERIFY]`. Typical donor-funded rules differ by project. Check the bid data sheet.

## 6. Notices, deadlines and where tenders are published

**Statutory publication (PPA §14):** a notice in **a daily newspaper of national circulation**, *and* on the entity's website or the PPMO website. International bids may also use international media. Minimum submission period: **30 days (national)** and **45 days (international)**. Required contents: entity name and address; nature and time limit of the work and place of delivery; bid security amount and validity; bid validity; how, where and for what fee to get documents; where, how and by when to submit; opening place, date and time. Source: <https://nepallaws.com/Laws/public-procurement-act-2063/chapter-3-provisions-relating-to-bid/section-14-invitation-to-bids/>

Corrections or amendments to eligibility documents are published in a national daily, and the deadline is extended if needed. Source: PPR-EN Rule 40(3).

These map directly onto `TenderRecord` fields: `buyer`, `buyer_address`, `scope`, `location`, `bid_security_amount`, `bid_security_validity`, `bid_validity_days`, `doc_fee`, `submission_deadline`, `opening_datetime`, `required_docs[]`.

**e-GP portal:** <https://bolpatra.gov.np/egp/>, run by the **Public Procurement Monitoring Office (PPMO)**. Notices say electronic bids must be submitted through the PPMO e-GP system by a stated time (e.g. "on or before 12:00"), and late bids are rejected. Bid-document fees are paid to a bank account named in the notice. Sources:
- <https://old.fcgo.gov.np/storage/uploads/tabnoticelist/2024-09-18/20240920144754_Bid%20Notice.pdf>
- <https://www.nea.org.np/tender_prequalification>
- <https://www.ird.gov.np/public/pdf/1908149037.pdf>

**Other channels:**
- PPMO website: <https://www.ppmo.gov.np/>
- Entity websites (e.g. NEA, FCGO, municipal `*.gov.np` sites, which publish notice PDFs)
- National dailies. Gorkhapatra is commonly used. `[VERIFY]` (no source read)

**Scraping, ToS and robots (checked 2026-10-15):**
- `https://www.ppmo.gov.np/robots.txt` returned `User-agent: * / Crawl-delay: 10`. **Honour 10 s between requests.**
- `https://bolpatra.gov.np/robots.txt` returned **HTTP 403** to a non-browser client. With a browser user-agent it returned a **"System Under Maintenance"** HTML page, not a robots file. `https://bolpatra.gov.np/egp/` returned HTTP 200. The robots policy and terms of use are **unknown** `[VERIFY]`.
- The e-GP site appears to block non-browser clients. **Do not** evade this (no UA spoofing or CAPTCHA solving in the product). Prefer public notice PDFs on entity websites (e.g. NEA or municipal sites), throttle to ≥10 s, cache aggressively, and keep the **seeded dataset as the primary demo source** (spec §17).
- No official open-data or API feed (e.g. OCDS) was found. `[VERIFY]`
- No portal login or submission ever (CLAUDE.md hard rule 6).

## 7. Calendar: Bikram Sambat (BS) and the fiscal year

- Official documents use **Bikram Sambat**. Example from the Rules' title page: "Date of Publication in Nepal Gazette: 2064-5-3 B.S. (20 August 2007 A.D.)" (PPR-EN). BS runs about **56 years 8 months ahead** of AD (2064 BS ≈ 2007 AD, same source).
- **Date formats seen in notices:** `YYYY-MM-DD` / `YYYY/MM/DD` in BS (e.g. file names `invitation-bids-2079-07-29`: <https://nepalpolice.gov.np/media/filer_public/b7/d1/b7d137c9-b8f1-4cf7-97bc-9a36100dd313/invitation-bids-2079-07-29.pdf>, `Bolpatra 2078-07-17`), sometimes with Devanagari digits (e.g. `२०८१।०५।१५`, where `।` is used as a separator), and often with an AD date in brackets. Times are Nepal Time (**UTC+05:45**) `[VERIFY]` (no official source read; this is standard).
- **BS→AD conversion cannot be done arithmetically.** BS month lengths (29–32 days) vary year to year and come from published tables. Use a vetted lookup-table library (e.g. a `nepali-datetime` / `bikram-sambat` package, which must be checked before adoption) and unit-test it against known pairs (2064-05-03 = 2007-08-20). `[VERIFY]` library choice.
- **Months, in order:** Baisakh, Jestha, Asar (Ashadh), Shrawan, Bhadra, Asoj (Ashwin), Kartik, Mangsir, Poush, Magh, Falgun, Chaitra. `[VERIFY]` spelling variants (no source read; standard).
- **Fiscal year:** begins **Shrawan 1** (mid-July) and ends on the last day of **Asar**. It is written as `2083/84` or `2083-84`. Sources (secondary): <https://app.khataacademy.com/pages/fiscal-year>; FY 2083/84 revenue reporting for its first month (Shrawan): <https://english.ratopati.com/story/75009/increase-in-government-revenue-in-the-month-of-shrawan-office-of-the-comptroller-and-auditor-general>. `[VERIFY]` against mof.gov.np. Tax clearance in notices is tied to an FY (§3 above), and this drives the document-expiry logic. Rule 85 of PPR-EN also refers to "one financial year".

## 8. Government levels and geography

- **Three levels:** Federal, Province (7), Local (753 local levels). The 753 are **6 Metropolitan Cities** (Mahanagarpalika), **11 Sub-Metropolitan Cities** (Upa-Mahanagarpalika), **276 Municipalities** (Nagarpalika) and **460 Rural Municipalities** (Gaunpalika), split into about 6,743 wards. Sources: <https://en.wikipedia.org/wiki/Local_government_in_Nepal>, <https://en.wikipedia.org/wiki/Administrative_divisions_of_Nepal> `[VERIFY]` against MoFAGA (mofaga.gov.np).
- **7 provinces** (Constitution of 2015, Schedule 4) and **77 districts**. Two districts (Nawalparasi, Rukum) are split across provinces. Source: <https://en.wikipedia.org/wiki/Administrative_divisions_of_Nepal>
- **Province names:** Koshi, Madhesh, Bagmati, Gandaki, Lumbini, Karnali, Sudurpashchim. `[VERIFY]` (names fixed by the provincial assemblies; Province No. 1 became Koshi in 2023)
- The buyer's level is useful for matching. Federal buyers are ministries, departments and SOEs (e.g. NEA). Province buyers are provincial ministries. Local buyers have `*mun.gov.np` / `*.gov.np` domains (e.g. `kankaimun.gov.np`). Store `buyer_level ∈ {federal, province, local}` plus `district` and `province`.
- A canonical 77-district list should be loaded from an official dataset when the seed data is built. `[VERIFY]` source (not fetched).

## 9. Numbers and currency

- **Currency:** Nepalese Rupee, code **NPR**. Notices write `Rs`, `Rs.`, `NRs`, or `रु.`. Seen in PPMO SBD labels ("NRs. 2.00 Million") and in notices.
- **Lakh and crore:** 1 lakh = 100,000 and 1 crore = 10,000,000 = 100 lakh. Notices group digits the South Asian way, e.g. **"Rs 1,02,000.00"** (= 102,000) in the NRB notice cited in §4. Notices also mix "Million" and "lakh". Source for definitions: <https://en.wikipedia.org/wiki/Lakh>, <https://en.wikipedia.org/wiki/Crore> (secondary).
- **Arab/Kharab:** 1 arab = 100 crore = 1,000,000,000. `[VERIFY]`
- **Devanagari digits:** ० १ २ ३ ४ ५ ६ ७ ८ ९ (U+0966–U+096F): <https://www.unicode.org/charts/PDF/U0900.pdf>. The Scout must normalise them to ASCII before parsing amounts and dates.
- **Devanagari in PDFs (observed 2026-10-17, Prompt 4):** text extraction is only as good as the PDF's font mapping. Legacy fonts (Preeti, Kantipur, etc.) map Devanagari glyphs onto ASCII codes, so extraction yields Latin garbage. Unicode fonts with incomplete ToUnicode maps lose conjuncts (e.g. PyMuPDF-generated `प्रमाणपत्र` extracts as `Śमाणपŕ`). `ingest/parse_docs.py` flags both cases with a warning and does not attempt conversion. A Preeti→Unicode converter is a possible later addition `[VERIFY]` (no library vetted).
- **Deterministic parser requirements:** strip `Rs/NRs/रु.`, normalise Devanagari digits, remove commas in either grouping style, handle `lakh/लाख`, `crore/करोड`, `million`. Store the integer amount in NPR (`BIGINT`, per spec §11). Unit-test all of these.

## 10. Open `[VERIFY]` list (summary)

1. Current thresholds for tender, sealed quotation, direct purchase, EOI, ICB and review (PPR amendments 3–12+). Parse PPR-NE.
2. Current bid-security % range and the low-bid performance-security formula.
3. Current bid-validity day counts.
4. Domestic-preference % for goods (still 10%?) and any margin for domestic contractors/consultants.
5. Contractor licence class limits (sources conflict) and the renewal rule text.
6. e-GP robots.txt, terms of use, and any open-data feed.
7. Whether the 2082 amendment bill / 2083 ordinance is in force.
8. Official sources for the fiscal-year start, province names, district list, and NPT offset.
9. BS↔AD conversion library choice.
10. PPMO blacklist URL.
11. PAN / VAT number format (not validated in `CompanyProfile` until confirmed).

## 11. Schema enums (as implemented in `api/schemas/enums.py`)

The Pydantic contracts encode these Nepal facts as enums. The JSON schema the LLM is constrained by uses the same values, so the Scout cannot emit anything else. Change an enum here and in code together.

| Enum | Values | Basis |
|---|---|---|
| `ProcurementType` | `goods`, `works`, `consulting`, `non_consulting`, `unknown` | §1 (PPA §8) |
| `ProcurementMethod` | `ncb`, `icb`, `eoi`, `rfp`, `quotation` (sealed quotation), `other` | §2.1. Direct procurement, users' committee, force account etc. map to `other`. |
| `EvaluationMethod` | `lowest_evaluated`, `qcbs`, `qbs`, `fixed_budget` (budget ceiling), `least_cost`, `other`. The field is nullable (notice silent). | §2.3 (PPA §25, PPR Rule 74) |
| `BuyerLevel` | `federal`, `province`, `local`, `other` | §8 |
| `Province` | `koshi`, `madhesh`, `bagmati`, `gandaki`, `lumbini`, `karnali`, `sudurpashchim` | §8 `[VERIFY]` names. `district` stays free text until the 77-district list is loaded. |
| `NoticeLanguage` | `en`, `ne`, `mixed` | §6, §7 (Devanagari notices) |
| `DocType` | `company_registration`, `business_licence`, `licence_renewal`, `pan_vat`, `tax_clearance`, `tax_return`, `self_declaration`, `power_of_attorney`, `bid_security`, `audit_report`, `experience_certificate`, `jv_agreement`, `company_profile`, `other` | §3 (PPR Rule 40(2) list + real notices). `tax_return` is the Rule 40(2)(d) alternative to tax clearance. `company_profile` (added Prompt 4) is the bidder's capability statement (projects, personnel, equipment). It is not a statutory eligibility document, but it is the main proposal-RAG source. The same enum is the CHECK constraint on `documents.doc_type`, so a new value needs a migration. |
| `RequirementCategory` | `eligibility`, `financial`, `experience`, `technical`, `personnel`, `equipment`, `other` | §3 (PPR Rule 28(3) criteria) |
| `ContractorClass` | `A`, `B`, `C`, `D` | §3. Per-class limits are **not** encoded (sources conflict, `[VERIFY]`). |

**Field formats:**
- BS fiscal years are `"YYYY/YY"` with consecutive years (`"2082/83"`), per §7. `"2082-83"` is rejected rather than normalised, so a normaliser must run before validation.
- `deadline_bs_iso` is a **BS** date `YYYY-MM-DD` with ASCII digits, month 01–12 and day 01–32 (BS months reach 32 days). Deterministic code fills it from `deadline_bs_raw`, and the LLM's value is never trusted. It is not an AD date.
- `deadline_ad` is an AD datetime, set only when the notice prints an AD date. BS→AD conversion stays deterministic (§7, `[VERIFY]` library).
- Amounts are integer NPR (`estimated_cost_npr`, `bid_security.amount_npr`, `bid_doc_fee_npr`), produced by the §9 normaliser. No statutory % is ever used to fill a value (§4).
- `jv_allowed` is nullable: `null` means the notice is silent, which is different from `false`.
- PAN/VAT numbers are stored as free strings. No format check is enforced because the format is not in this document. `[VERIFY]`


## 12. Rules implemented (api/nepal/rules.yaml)

| Rule id | Check | Basis in this doc | Verified | Severity |
|---|---|---|---|---|
| NP-DEADLINE | deadline not passed (NPT) | PPA s.14, hard rule 5 | yes | hard |
| NP-REG-DOCS | registration, business licence, self-declaration (+ power of attorney if the notice lists it) on file, unexpired | PPR-EN Rule 40(2)(a),(b),(e) | yes (2008 text) | hard |
| NP-PAN-VAT | PAN on profile + pan_vat doc; number format NOT validated | Rule 40(2)(c); section 10 item 11 | yes (presence only) | hard |
| NP-TAX-CLEARANCE | clearance or tax-return proof for the notice's FY | Rule 40(2)(d), real notices (section 3) | yes | hard |
| NP-LICENCE-RENEWAL | construction licence renewed for the deadline's FY (works only) | section 3, Construction Business Act reported secondhand | NO [VERIFY] | soft |
| NP-TURNOVER | avg of last N completed FYs >= notice minimum; needs audit reports | Rule 28(3) wording [VERIFY] | NO | hard (threshold from notice) |
| NP-EXPERIENCE | count and value of similar projects >= notice minimums | Rule 28(3) [VERIFY] | NO | hard (threshold from notice) |
| NP-BID-SECURITY | amount and valid-until from notice; compares guarantee on file | PPA s.14, s.20; no statutory % used | yes | soft |
| NP-PERF-SECURITY | amount from the notice's percent; never pass | Rule 110(2) | yes | soft |
| NP-JV | JV route exists if turnover/experience failed; pooling (28(4)) not evaluated | Rule 28 | yes | soft |
| NP-DOMESTIC-PREF | flag only, no percentage applied | Rules 17, 64(4) [VERIFY] | NO | soft |

Assumptions (unverified): security validity counts from the submission deadline; turnover window is the N most recent completed FYs before the deadline's FY; date-only deadlines mean end of day NPT.
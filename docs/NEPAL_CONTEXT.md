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

**Scraper source check (2026-10-19, Prompt 5).** Each request below was made once with an honest UA (`TenderlyBot/0.1 ...`), and nothing was retried to get past a refusal:

| Source | robots.txt | Terms | Outcome |
|---|---|---|---|
| `www.ppmo.gov.np` | connection reset (today); 2026-10-15: `Crawl-delay: 10` | not checked | not used |
| `bolpatra.gov.np` | **HTTP 403** (nginx) | unknown `[VERIFY]` | **not used** (blocks non-browser clients) |
| `www.nea.org.np` | a "Security Access Restricted" HTML page instead of robots | unknown | **not used** (WAF block) |
| `pokharamun.gov.np` | connection reset | not checked | not used |
| **`kankaimun.gov.np`** (Kankai Municipality, Jhapa, Koshi) | standard Drupal 7 file: `User-agent: *`, **`Crawl-delay: 10`**; disallows only `/admin/`, `/user/*`, `/search/`, `/node/add/`, install/cron files and asset dirs. The notice board `/ne/public-procurement-tender-notices`, notice pages `/ne/content/*` and attachments under `/sites/<host>/files/` are **not disallowed**. | **No terms-of-use, disclaimer or copyright policy page found.** The footer reads "© 2026 कनकाई नगरपालिका". Notices are public under PPA §14 (publication on the entity's website). | **Chosen source** for `api/ingest/scraper.py` |

What the Kankai board actually contains: a Drupal view (10 rows per page, `?page=N`, 14 pages) that **mixes procurement notices with exam, meeting and holiday notices**, so the scraper filters titles by keyword. A notice page usually has **no body text**; the notice is a PDF in "Supporting Documents". Both tender PDFs checked on 2026-10-19 (`Suchana Dosro.pdf`, `Suchana.pdf`) were **scanned images with no text layer** (1 page, 0 characters). Without OCR (out of scope) they yield nothing, so **the live scraper currently produces few or no usable notices**. It skips and reports them. That is why the seed set (`data/seed_tenders/`) stays the demo source. One intermittent connection reset on robots.txt was also seen. The scraper then fetches nothing, as designed.

Scraper rules as implemented: robots.txt is read first (a 401/403/5xx or network error means nothing is fetched); `can_fetch` is checked per URL; ≥10 s between requests (or the robots Crawl-delay if larger); GET only, same host only, no login, no cookies used; 401/403/429 stops the run with no retry; every page and attachment is cached raw on disk (`api/.cache/scraper/`), and notice pages are never refetched. Terms of use may change. Re-check before any heavier use `[VERIFY]`.

## 7. Calendar: Bikram Sambat (BS) and the fiscal year

- Official documents use **Bikram Sambat**. Example from the Rules' title page: "Date of Publication in Nepal Gazette: 2064-5-3 B.S. (20 August 2007 A.D.)" (PPR-EN). BS runs about **56 years 8 months ahead** of AD (2064 BS ≈ 2007 AD, same source).
- **Date formats seen in notices:** `YYYY-MM-DD` / `YYYY/MM/DD` in BS (e.g. file names `invitation-bids-2079-07-29`: <https://nepalpolice.gov.np/media/filer_public/b7/d1/b7d137c9-b8f1-4cf7-97bc-9a36100dd313/invitation-bids-2079-07-29.pdf>, `Bolpatra 2078-07-17`), sometimes with Devanagari digits (e.g. `२०८१।०५।१५`, where `।` is used as a separator), and often with an AD date in brackets. Times are Nepal Time (**UTC+05:45**) `[VERIFY]` (no official source read; this is standard).
- **BS→AD conversion cannot be done arithmetically.** BS month lengths (29–32 days) vary year to year and come from published tables. Use a vetted lookup-table library (e.g. a `nepali-datetime` / `bikram-sambat` package, which must be checked before adoption) and unit-test it against known pairs (2064-05-03 = 2007-08-20). `[VERIFY]` library choice.
- **Libraries disagree on future BS years (observed 2026-10-19).** `nepali-datetime` (Python, used by `api/nepal/dates.py`) and the npm package `nepali-date-converter` 3.4.0 give the same date for every day from AD 2010 through BS 2083, but differ in BS **2084–2087** (e.g. Jestha 2084: 31 vs 32 days) and after 2090. Future BS month lengths are projections until the official calendar is published, so a date in that range (bid validity, licence expiry such as 2084-03-32) is only as good as the table `[VERIFY]` against the published 2084+ calendar. Tenderly uses one table everywhere: the web app's `web/lib/nepal/bs-calendar.json` is exported from `nepali-datetime` (`api/scripts/export_bs_calendar.py`, drift-tested).
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
6. e-GP robots.txt, terms of use, and any open-data feed. (2026-10-19: still HTTP 403. Kankai municipality's robots.txt was checked instead and has no terms page, see section 6.)
7. Whether the 2082 amendment bill / 2083 ordinance is in force.
8. Official sources for the fiscal-year start, province names, district list, and NPT offset.
9. BS↔AD conversion library choice, and the BS 2084+ month lengths, where libraries disagree (§7).
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
- `deadline_ad` is an aware NPT datetime, set by Scout's code (since Prompt 5b): the printed AD date, or the BS date converted with the lookup table. It is null when the deadline could not be confirmed (see §13). BS→AD conversion stays deterministic (§7, `[VERIFY]` library).
- Amounts are integer NPR (`estimated_cost_npr`, `bid_security.amount_npr`, `bid_doc_fee_npr`), produced by the §9 normaliser. No statutory % is ever used to fill a value (§4).
- `jv_allowed` is nullable: `null` means the notice is silent, which is different from `false`.
- PAN/VAT numbers are stored as free strings. No format check is enforced because the format is not in this document. `[VERIFY]`


## 12. Rules implemented (api/nepal/rules.yaml)

| Rule id | Check | Basis in this doc | Verified | Severity |
|---|---|---|---|---|
| NP-DEADLINE | deadline not passed (NPT) | PPA s.14, hard rule 5 | yes | hard |
| NP-REG-DOCS | registration and business/construction licence on file, unexpired at the deadline | PPR-EN Rule 40(2)(a),(b) | yes (2008 text) | hard |
| NP-BID-FORMS | self-declaration (+ power of attorney if the notice lists it): signed per bid, so never a fail; pass only if a signed copy is in the KB (Prompt 7) | PPR-EN Rule 40(2)(e) | yes | hard (unclear never blocks) |
| NP-PAN-VAT | PAN on profile + pan_vat doc; number format NOT validated | Rule 40(2)(c); section 10 item 11 | yes (presence only) | hard |
| NP-TAX-CLEARANCE | clearance or tax-return proof for the notice's FY | Rule 40(2)(d), real notices (section 3) | yes | hard |
| NP-LICENCE-RENEWAL | construction licence renewed for the deadline's FY (works only) | section 3, Construction Business Act reported secondhand | NO [VERIFY] | soft |
| NP-TURNOVER | avg of last N completed FYs >= notice minimum; needs audit reports | Rule 28(3) wording [VERIFY] | NO | hard (threshold from notice) |
| NP-EXPERIENCE | count and value of similar projects >= notice minimums | Rule 28(3) [VERIFY] | NO | hard (threshold from notice) |
| NP-BID-SECURITY | amount and valid-until from notice; compares guarantee on file | PPA s.14, s.20; no statutory % used | yes | soft |
| NP-PERF-SECURITY | amount from the notice's percent; never pass | Rule 110(2) | yes | soft |
| NP-JV | JV route exists if turnover/experience failed; pooling (28(4)) not evaluated | Rule 28 | yes | soft |
| NP-DOMESTIC-PREF | flag only, no percentage applied | Rules 17, 64(4) [VERIFY] | NO | soft |
| NP-DOC-VALIDITY | dated eligibility documents valid at the deadline but lapsing before deadline + bid validity days: unclear + "renew before" action, never fail (Prompt 7) | PPA s.20 (validity counted from the deadline); whether documents must stay valid that long is [VERIFY] | NO | soft |
| NP-OTHER-DOCS | mandatory notice documents no other rule checked (type `other`, or a tracked type whose rule did not fire): listed with an action, never fail. Runs last (Prompt 7) | PPR-EN Rule 40(2)(f) | yes | soft |

Assumptions (unverified): security validity counts from the submission deadline; turnover window is the N most recent completed FYs before the deadline's FY; date-only deadlines mean end of day NPT.

**Evidence (Prompt 7).** A rule `pass` needs a readable KB document (its first chunk id; the `documents` row id is kept in `evidence_document_ids`) or a field of the notice itself (`tender.*`, e.g. the deadline). A company-profile entry alone (licence renewal FY, JV partner) is not evidence, so NP-LICENCE-RENEWAL and NP-JV are `unclear` until the licence copy / JV agreement is uploaded. Every non-pass item carries a plain-language `action_needed` (e.g. "Renew tax clearance for F/Y 2082/83 ... before submission").

**What fired on the demo (Prompt 7, oracle records of seeds 001 and 002, demo KB with the new `06_construction_licence.txt`, clock 2026-10-19 12:00 NPT, rules only):**

| Rule | 001 Bhanu road (strong match) | 002 Seti river training (hard fail) |
|---|---|---|
| NP-DEADLINE | pass | pass |
| NP-REG-DOCS | pass (registration + licence copy) | pass |
| NP-BID-FORMS | unclear (sign self-declaration) | unclear |
| NP-PAN-VAT | pass | pass |
| NP-TAX-CLEARANCE | **fail, hard**: needs F/Y 2082/83; only F/Y 2081/82 on file, expired 2026-07-16 | **fail, hard** (same) |
| NP-LICENCE-RENEWAL | pass (licence copy recorded for F/Y 2083/84) | pass |
| NP-TURNOVER | unclear (look-back "best 3 of 5" not extracted; no audit reports) | **fail, hard**: avg Rs 5.03 crore < Rs 25 crore |
| NP-EXPERIENCE | unclear (certificate not classified as similar) | **fail, hard**: no Rs 9 crore similar contract |
| NP-BID-SECURITY | unclear (arrange Rs 4,46,000 guarantee) | unclear (Rs 55,50,000) |
| NP-PERF-SECURITY | - | unclear (5%) |
| NP-JV | - (nothing failed) | fail, soft: JV barred |
| NP-DOC-VALIDITY | pass (registration/licence valid to 2027-07-16 > 2027-02-19) | pass |
| NP-DOMESTIC-PREF, NP-OTHER-DOCS | - | - |

Both tenders are `blocked`. 001 is blocked only by the expired tax clearance (the demo beat: upload an FY 2082/83 clearance, or override). On all 7 labelled seeds NP-TAX-CLEARANCE is the shared hard fail, because every current notice asks for FY 2082/83.

Licence classes for the model layer: क = A, ख = B, ग = C, घ = D (A highest). This ordering is used only in the Compliance prompt; per-class value limits are still not encoded (§3 [VERIFY]).
## 13. Scout parsing conventions (as implemented, Prompt 5b)

The Scout LLM copies strings verbatim (`schemas/scout.py::TenderExtraction`). Everything below is deterministic code in `api/nepal/` and `api/agents/scout.py`. When a rule cannot decide, the value is **null**, the raw string is kept, and `needs_review` is set. Nothing is guessed.

**Deadlines (`nepal.dates.parse_deadline`).**
- Era by year: a year ≥ 2060 is BS, a smaller one is AD (BS ≈ AD + 57, §7). `B.S.` / `A.D.` markers are not needed.
- Formats read: `YYYY-MM-DD`, `YYYY/MM/DD`, `YYYY.MM.DD`, the danda `YYYY।MM।DD`, `DD/MM/YYYY` (BS), Devanagari digits, BS month names (§7 aliases), and English month names for AD (`December 14, 2026`, `30 November 2026`).
- A BS date and an AD date in one string must agree through the lookup table. If they don't, it is an issue (`deadline` null).
- An AD `DD/MM/YYYY` with both parts ≤ 12 is an issue (day/month order unknown).
- Two different dates of one era (e.g. a corrigendum's old and new date) are an issue. Two different times of day (e.g. submission and opening) are also an issue.
- Times: `12:00`, `12:00 hours`, `2 PM`, `12 noon`, `मध्यान्ह`, `१२ बजे`. Nepali day-part words make a time PM: `दिउँसो`, `बेलुका`, `साँझ`, and `दिनको` before an hour of 1–5 (so `दिनको २:०० बजे` = 14:00). `[VERIFY]` that heuristic against real notices; seed notices only use it for opening times. A date with no time is 23:59:59 NPT (decision in PROGRESS.md).

**Amounts (`nepal.numbers.parse_npr`).**
- Digit grouping must be valid Western (`1,234,567`) or South Asian (`1,23,45,678`). A mis-keyed figure such as `1,50,000,00` is rejected, never read as some number.
- Compound amounts are summed only when every number has a unit and the units strictly decrease (`रु. ३२ लाख ५० हजार` = 3,250,000).
- If the notice says some figures are "in thousands" (`रु. हजारमा`, `in '000`), Scout rejects any amount that has neither a currency marker nor a unit word. That covers table cells, whose scale is unknown.

**Percent and days.** `parse_percent` and `parse_days` accept exactly one number (`२.५ प्रतिशत`, `120 दिन`, `90 (ninety) days`). A bid-security validity printed as a date ("valid until 2083-12-15 B.S.") becomes days after the submission deadline. This matches `calc_bid_security`, which counts validity from the deadline (an assumption, §4).

**Documents (`nepal.documents`).**
- An English + Nepali keyword table maps each document name to `DocType`s (§3, §11): कर चुक्ता → tax_clearance, कर विवरण → tax_return, मू.अ.कर / स्थायी लेखा नम्बर → pan_vat, नवीकरण → licence_renewal, इजाजतपत्र → business_licence, फर्म दर्ता → company_registration, स्वघोषणा → self_declaration, अख्तियारनामा → power_of_attorney, धरौटी / बोलपत्र जमानत → bid_security, लेखापरीक्षण → audit_report, अनुभव → experience_certificate, संयुक्त उपक्रम सम्झौता → jv_agreement.
- One line can yield several types. Each keyword match consumes its text, so "VAT and PAN registration certificate" is not also company_registration.
- "Tax clearance or tax return" is kept as tax_clearance only. Rule 40(2)(d) treats them as alternatives, and `NP-TAX-CLEARANCE` accepts either.
- Fiscal years are read as `2082/83`, `2082-83`, `2082/2083` or `082/83` and must be consecutive. They are attached to tax clearance, tax return, licence renewal and audit report.
- An unrecognised name becomes `other`.

**Language** is computed, not asked of the LLM. Let *share* be the fraction of letters that are Devanagari. Below 0.02 the notice is `en`, above 0.92 it is `ne`, otherwise `mixed`. These thresholds fit all 37 seed notices. `[VERIFY]` them on real notices.

## 14. Matching conventions (as implemented, Prompt 6)

Matching (`api/agents/matching.py`) uses **no procurement-law threshold**. Every hard-skip check is either a fact from the notice compared with the company's own profile, or a company policy setting:

| Signal | Check | Source of the number | Hard skip when |
|---|---|---|---|
| Procurement type | `TenderRecord.procurement_type` vs `CompanyProfile.procurement_types` (§1 enum) | company profile | the type is known and not listed (`unknown` = half points) |
| Geography | notice district vs `districts_served`; if only a province is known, does it contain a served district (§8 district → province table in `nepal/geography.py`) | company profile | the district is not served, or the province has no served district |
| Budget capacity | estimated cost / average turnover of the last `MATCH_TURNOVER_YEARS` FYs in the profile | **company policy** `MATCH_MAX_COST_TO_TURNOVER` (default 2.0). This is not a PPR rule. The notice's own turnover criterion (`TenderCriteria`) is left to Compliance (`NP-TURNOVER`). | the ratio is above the limit |
| Deadline | `deadline_ad` ≤ now, both in NPT (UTC+05:45, §7) | the notice | the deadline has passed |

- Contractor licence class limits are **not** used to judge capacity (sources conflict, §3 `[VERIFY]`).
- A missing value (no district, no cost, no confirmed deadline) costs points but never skips. Scout leaves values null rather than guessing (§13), so the tender stays visible for a human.
- **Deadline display (GET /tenders):** `DeadlineView` gives the AD datetime in NPT, the BS date from the lookup table (`ad_to_bs`, §7), `"5 Mangsir 2083"` and `"५ मंसिर २०८३"` forms, and `days_left` (calendar days between NPT dates; negative once passed). `deadline_within_days=N` means not passed and at most N NPT calendar days away.
- The `district` filter accepts English, Nepali or a common spelling and normalises with `normalize_location` (`तनहुँ` → Tanahun).

## 15. Proposal conventions (as implemented, Proposal prompt)

The Proposal agent (`api/agents/proposal.py`) writes the bidder's narrative sections. It does **not** fill the PPMO standard bidding document (SBD) forms (bid form, price schedule, BOQ). Those stay as the notice's own forms, which the person signs. Section templates live in code, so the structure is deterministic and testable.

**Templates and why:**

| Family | Sections (in order) | Why this structure |
|---|---|---|
| Goods, works, non-consulting, unknown | cover letter; bidder information and eligibility; technical specification compliance; delivery schedule (goods) / work plan (works); relevant experience; financial capacity; declarations | These are evaluated as the "lowest evaluated substantially responsive" bid (PPA §25, §2.3). A bid is first checked for **responsiveness and qualification**, and only then on price. So the narrative follows the qualification evidence: eligibility documents (PPR-EN Rule 40(2), §3), conformity with specifications, ability to deliver, similar experience and financial criteria (Rule 28(3) list, §3), and the self-declaration (Rule 40(2)(e)). |
| Consulting, RFP | cover letter; understanding of the ToR; methodology; work plan; team; relevant experience | QCBS technical scoring weights methodology 20–50%, key personnel 30–60% and firm experience up to 10% (PPR-EN Rule 71(6), §2.3 `[VERIFY]` against current amendments). The sections map one-to-one onto what is scored. |
| Consulting, EOI | cover letter; relevant experience; team; understanding of the ToR | An EOI builds a **short list** (Rule 70, §2.1) mostly on experience and capacity, and there is no methodology yet. So experience comes first and methodology is left out. |

**Tender-specific additions (code, from Scout's `requirements[]` categories):** an eligibility requirement adds *bidder information*, a financial one *financial capacity*, personnel adds *team*, and equipment adds *key equipment* (works). A notice that lists a self-declaration or power of attorney adds *declarations* (also for consulting). Each requirement is answered in exactly one section, and its text joins that section's retrieval query (spec §10.4).

**Values the model never writes:**
- PAN/VAT numbers, registration, licence and certificate numbers, amounts, dates and project names come only from the company record, the tender record, or a verbatim KB quote. Code inserts them through placeholders (`{{company.pan}}`, `{{tender.deadline}}`, `{{fact.<key>}}`).
- The PAN/VAT format is still not validated (§10 item 11). The value is copied as stored, never generated.
- A figure the model typed itself (an amount, a lakh/crore phrase, an id with digits, any number of 4+ digits including BS years) is masked `⟦unsourced: …⟧` and flagged.

**Language:** an English notice gets an English proposal, and Nepali and `mixed` notices get a Nepali one (`mixed` notices are mostly local-body Nepali notices with English terms, §13 Language). English can be forced (`PROPOSAL_FORCE_ENGLISH`, or per request). The Nepali section titles and stub text were written by the model, not a native reader `[VERIFY]` (PROGRESS issue 60).

**Dates:** when the notice wrote a BS date (its deadline, or any BS year 2060–2099 in the text), dates in the proposal show both calendars: `5 Mangsir 2083 BS (21 November 2026 AD), 12:00 NPT`, or in Nepali `५ मंसिर २०८३ (२०२६-११-२१)`. Otherwise they are AD only. Conversion uses the same lookup table (§7). Money uses lakh/crore grouping (`Rs 1,48,75,000`, `रु. १,४८,७५,०००`, §9).

**Not encoded:** the order or wording of PPMO SBD sections `[VERIFY]` against a current SBD. The templates follow the evaluation criteria above, not a form.

## 16. Bid package contents (as implemented, Prompt 10)

`GET /proposals/{id}/package` builds a ZIP for an **approved** proposal version (`api/export/`). Tenderly never submits it (hard rule 6): the person submits it through the procuring entity's channel, e.g. the PPMO e-GP system (§6). The documents are in the proposal's language (English, or Nepali for `ne`/`mixed` notices, §15).

| File | Contents |
|---|---|
| `01_<stem>.pdf` / `.docx` | The bid package below. The PDF embeds Noto Sans + Noto Sans Devanagari, is HarfBuzz-shaped, and extracts as the same Unicode. The DOCX is the editable copy. |
| `02_attachment_checklist.csv` | One row per document (UTF-8 with BOM for Excel). |
| `03_audit_summary.json` | Tender, proposal, review, approval (who/when), compliance report and override, checklist, every `agent_runs` row, file hashes, `submitted: false`. |
| `attachments/` | The KB originals of documents the checklist marks present or expiring. |

**Inside the PDF/DOCX:**

0. **Internal cover sheet** (marked "remove before submission"): tender, reference, entity, deadline (BS + AD), bidder, PAN/VAT, proposal version, review verdict, approval.
1. **Cover letter**: date (BS + AD), the procuring entity, subject "Submission of bid for <title> (Ref. <no.>)", the body (the proposal's `cover_letter` section), and a signature block (name, designation, signature and seal, date).
2. **Bid form (skeleton)**:
   - the usual undertakings:
     - bidding document and addenda examined;
     - offer at a total price;
     - bid validity in days from the deadline (§4, PPA §20);
     - bid security amount and valid-until (from the notice / `calc_bid_security`, §4);
     - performance security % if the notice states one (else "as the bidding document requires", PPR Rule 110(2));
     - one bid per bidder alone or in a JV (PPR Rule 28(1), §3);
     - the entity is not bound to accept the lowest bid;
   - a bidder-information table.
   - **Price, addenda numbers and signatory are left blank**: Tenderly never writes a price. It is marked as a convenience copy: the bidding document's own form is the authority. Wording follows common SBD practice `[VERIFY]` against a current PPMO SBD.
3. **Declarations**: the PPR Rule 40(2)(e) self-declaration (eligible, not disqualified; not punished for a professional or business offence; no conflict of interest), not blacklisted/debarred (PPR Rules 39, 141, §3), no corrupt/fraudulent/collusive/coercive practice, and the information is true, with a signature block. Use the bidding document's declaration form if it has one.
4. **Technical proposal**: the remaining proposal sections (§15), each with its KB chunk citations and any review flags. Unresolved `[MISSING: …]` markers stay visible.
5. **Attachment checklist**: every document the notice lists, plus the statutory eligibility documents of PPR Rule 40(2)(a)–(c),(e) the notice did not list (registration, business/construction licence, PAN/VAT, self-declaration). Columns: document, status, file(s), valid until (BS / AD), notes. Matching uses the same logic as the compliance rules (§12):
   - **present**: a readable (chunked), unexpired document of that type (and of the notice's fiscal year for tax clearance / tax return / audit report; that FY or later for a licence renewal) that stays valid through deadline + bid validity days;
   - **expiring**: valid at the deadline but lapsing before deadline + bid validity (NP-DOC-VALIDITY, §12, `[VERIFY]` whether documents must stay valid that long);
   - **missing**: none on file, only expired copies, only other fiscal years (listed with their expiry), a scanned copy with no text, or a per-bid form (self-declaration, power of attorney: sign the one in this package). A bid-security row names the amount and the valid-until date to arrange. The compliance rule's `action_needed` is appended. A tax-return proof for the notice's FY satisfies a tax-clearance row (Rule 40(2)(d)).

**Dates** in the package always carry both calendars: long form `5 Mangsir 2083 BS (21 November 2026 AD)` (`५ मंसिर २०८३ (२०२६-११-२१)` in Nepali), and in the checklist `2084-03-32 BS / 2027-07-16 AD`. Conversion uses the same lookup table (§7, `[VERIFY]` 2084+). The Nepali fixed text was written by the model, not a native reader `[VERIFY]`.

**Approval gate before export (agents/review.py):** a version is exported only after a person approves it. Approval needs a review whose verdict is not `fail`, plus an explicit open of the version after its review. Review's deterministic checks are: every mandatory requirement answered, no placeholders, bid security stated when the notice asks for one, deadline not passed (NPT), sections cite the KB. Thresholds are company policy (`REVIEW_PASS_MIN_SCORE` 70, `REVIEW_FAIL_BELOW_SCORE` 40), not law.

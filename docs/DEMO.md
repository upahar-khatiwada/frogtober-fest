# Demo guide

Everything for the final presentation: the 5-minute pitch outline, the live demo script, the 3-minute video script,
who talks and who drives, a pre-flight checklist, a fallback plan, and prepared answers. It follows spec §16.

**Read this first: what is and is not rehearsed.** As of v1.0 the full demo path has been exercised only against
mock data (the Playwright test with `E2E_MOCKS=1`) and with fake models in the backend tests. The replay cache
(`data/demo_cache/llm_cache.json`) has **not been recorded**, and no run against the real model is recorded, so
the live timings below are targets, not measurements. The pre-flight checklist below is how the team closes that
gap. Rehearse at least twice on a clean checkout before recording (spec §13).

## 1. The company and the three prepared tenders

One fictional company: **Annapurna Demo Nirman Sewa Pvt. Ltd.** (Pokhara, Kaski; class C construction licence;
serves Kaski, Tanahun, Syangja, Parbat, Lamjung; average turnover about Rs 5 crore) with six knowledge-base
documents. Its **tax clearance covers F/Y 2081/82 and expired on 2083-03-32 BS (16 July 2026)**, on purpose. All
tenders are the synthetic seed notices. Everything is labelled fictional.

Spec §16.2 asks for three tenders that show the AI changing system behaviour:

| Role | Seed notice | What the system does | Why |
|---|---|---|---|
| **Strong match, carried through** | **001** Bhanu Municipality, road gravelling, drains and culverts, Tanahun. Rs 1,48,75,000 (1.49 crore), NCB, JV allowed, bid security Rs 4,46,000, deadline 2083-08-05 BS (2026-11-21). | Matching `pursue`; Compliance **blocks** on the expired tax clearance; a named person overrides; Proposal, Review, approval, package. | Works, district, size and experience all fit. The notice asks for an F/Y 2082/83 clearance, the company has only 2081/82. |
| **Blocked by compliance, stays blocked** | **019** Bhimad, gabion wall and drain, Tanahun. Rs 72.4 lakh, English notice. | Matching `pursue`; Compliance **blocks** on the same expired clearance; "Generate proposal" stays disabled (the API answers 409). | Same hard failure, no override. Shows that a hard failure stops the pipeline. |
| **Skipped as irrelevant** | **003** DoHS ICU ventilators, federal ICB, Rs 9.24 crore. | Matching `skip` from deterministic signals (goods, not works); **Compliance never runs**. | Nothing to do with a civil-works SME. |

Two things the team must know before presenting:

1. **001 is both the strong match and a tender that hits the expired clearance.** Every current seed notice asks for
   an F/Y 2082/83 clearance (`docs/NEPAL_CONTEXT.md` §12), so any pursued tender blocks until a person acts. That is
   the demo beat, not a bug: the demo shows the block, then the documented human override (name, reason, which
   failures), which the audit log records.
2. **Do not use 002 as the blocked tender.** The manifest labels it `hard_fail` (needs class A/B, a 25 crore average
   turnover, JV barred), but its cost is 3.7 times the company's average turnover, so **Matching skips it before
   Compliance runs** (`MATCH_MAX_COST_TO_TURNOVER` = 2.0). Its compliance failures show only when Compliance is forced
   (`score_compliance`). It makes a good extra "skipped for capacity" example. The default `precache_demo` tenders are
   001, 002, 003, so use `--only 001,019,003` (below).

## 2. Who talks, who drives

Three roles (spec §12.1). Names are assigned by the team; one person only talks and one only drives, so the
narrator never looks away from the audience.

| Role | Does | Why this person |
|---|---|---|
| **Narrator: Member C** (frontend and product lead) | Problem, solution, live-demo narration, results and close. Does not touch the keyboard. | Owns the story, the UX flow and the pitch. |
| **Driver: Member B** (backend and data lead) | Drives the screen and the terminal. Owns pre-flight, the fallback video, and the Stack and data questions (data protection, rules currency). | Knows the stack well enough to recover quietly. |
| **AI voice: Member A** (AI pipeline lead) | Takes over the "How AI is used" slice (45 s) while the driver shows the audit log, and answers the model-accuracy and hallucination questions. | Owns the agents, the prompts and the evaluation. |

Hand-offs: C to B on "let's open the dashboard"; C to A on "how is AI actually used here"; A to C on "results and limits".

## 3. Pre-flight

**Day before (needs the demo machine with the GPU and Ollama):**

```bash
docker compose down -v                                   # fresh DB: chunk ids in the cache must match
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
./scripts/setup.sh
docker compose exec ollama ollama ps                      # PROCESSOR must say 100% GPU after the first call
docker compose exec api python -m scripts.seed_demo --data-dir /data/demo_company
# record the replay cache on the pinned clock, then verify it offline
cd api && uv run python -m api.scripts.precache_demo --only 001,019,003 --through-review 001 \
    --now 2026-10-22T10:00:00+05:45 --database-url postgresql://tenderly:tenderly@localhost:5432/tenderly
cd api && uv run python -m api.scripts.precache_demo --only 001,019,003 --through-review 001 \
    --now 2026-10-22T10:00:00+05:45 --check
```

If a native Postgres also listens on 5432 (common on Windows), `localhost:5432` reaches it instead of Compose. Run the
recording inside the api container or stop the native one. Record the real timings (Scout, Matching, Compliance,
Proposal, Review) in `PROGRESS.md`; they replace the targets in this file.

Check the recording against the table in section 1: 001 must end `blocked` then reviewed after the override; 019 must
end `blocked`; 003 must end `skipped`. If Scout on the real model extracts 019 differently (a null FY, a flag), pick
another pursued seed (015, 016, 027 or 029 all hit the same rule) and re-record.

**Before each rehearsal and before presenting:**

1. Reset to a fresh state: `docker compose down -v`, then start with `DEMO_NOW=2026-10-22T10:00:00+05:45` in `.env`
   (Review replays only at the clock it was recorded at), `docker compose up -d`, seed the company again.
2. Open http://localhost:3000, language English, calendar BS. Check `/company`: six documents `ready`, the F/Y 2081/82
   tax clearance shows **Expired**.
3. Click **Load tenders** (37 notices). Pre-analyze **003** and **019** (Analyze on each) so the dashboard already
   shows skipped and blocked. Leave **001** untouched for the live run.
4. Browser at 1366 x 768 or the projector's resolution (the pages were checked at 1024 x 768 with no sideways
   scroll). Close other tabs, silence notifications, zoom 110% if the room is large.
5. Keep a terminal open and **leave the API logs visible**. Keep the fallback video on the desktop, in a player, paused.
6. Run `cd web && E2E_MOCKS=1 bunx playwright test` once as a smoke test of the UI build (or `bunx playwright test`
   against the stack, which approves tender 001: reset again afterwards).

## 4. The 5-minute pitch (spec §16.1)

| Time | Part | Who | Content |
|---|---|---|---|
| 0:00 to 0:45 | **Problem** (45 s) | C | The Pokhara contractor story: a good fit, a Rs 1.49 crore municipal road job, an expired tax clearance, a bid "not entertained" under PPR Rule 40(4), and the bid security wasted. The four ways SMEs lose: discovery, triage, compliance, proposal effort. |
| 0:45 to 1:15 | **Solution** (30 s) | C | The pipeline diagram (README): Scout, Matching, Compliance, Proposal, Review, human approval, package. "Each stage emits typed JSON, and code uses it to skip, block or gate the next step." |
| 1:15 to 3:45 | **Live demo** (2.5 min) | C narrates, B drives | Section 5. Dashboard, compliance matrix with the failing requirement, proposal generation, review gaps, approval and package. |
| 3:45 to 4:30 | **How AI is used** (45 s) | A (B on the audit log) | Structured outputs drive routing, blocking and gating (three examples from the demo). Show the audit log once. Everything runs on open-weight models (Qwen2.5-7B-Instruct, bge-m3 through Ollama). |
| 4:30 to 5:00 | **Results and limits** (30 s) | A, then C | Honest numbers (below), what is not built, what comes next. |

**Results line (use only what is true on the day).** "Matching and Compliance's code layer, on 37 synthetic notices:
all 54 mandatory requirements covered, **0 false hard failures**, hard-fail recall 82% before the model layer, and top-3
precision 100% for relevant tenders. We have not yet measured the model-in-the-loop numbers" (or give them, if the
evaluation was run before the presentation: `cd api && uv run python -m api.eval`, then update this line and the
README table). "Not built: automatic submission, OCR, a second portal, multi-tenant. Next: assisted submission with a
human confirmation at every irreversible step, more portals, OCR, Nepali fine-tuning, win/loss feedback."

## 5. The live demo script (2.5 minutes)

State: fresh DB, company seeded, 37 tenders loaded, 003 skipped and 019 blocked already, 001 untouched.
Narrator speaks, driver clicks. Times are targets.

| Time | Driver | Narrator says | Proof point |
|---|---|---|---|
| 0:00 | Dashboard, ranked list. | "This is a Pokhara contractor's day. 37 notices, ranked against their profile. Two are already analysed." | Ranked list, scores, BS deadline with countdown. |
| 0:15 | Point at **003** (skipped). Expand its reasons. | "The ventilator tender was skipped. The reason is a rule, not a vibe: goods, and this company builds. Compliance never ran." | `[deterministic]` reason tag; status `skipped`. |
| 0:30 | Open **001**. Click **Analyze**. Stages tick. | "Now a fresh one. Scout reads the notice, Matching scores it, Compliance checks it." | Stages with durations (cached: seconds; live: minutes). |
| 0:45 | Extracted fields: deadline, cost, bid security. Hover a quote. | "Every value sits next to the sentence it came from. The deadline is converted in code: 2083-08-05 BS, 21 November 2026. Rs 1,48,75,000. Bid security Rs 4,46,000." | Value beside verbatim quote, BS and AD. |
| 1:00 | Compliance matrix, expand the red **NP-TAX-CLEARANCE** row. | "This is the moment that matters. The notice wants a tax clearance for F/Y 2082/83. We only hold 2081/82, and it expired on 16 July. A rule decided this, with the document and its expiry as evidence. The bid is blocked, so the proposal button is off." | Red row, evidence with the document and expiry (BS), action text, disabled **Generate proposal**. Optionally flip to **019**: same block, no override. |
| 1:30 | **Override and generate...**: name and reason ("FY 2082/83 clearance issued, uploading before submission"). | "A named person can accept that risk. It is recorded: who, why, which failures." | Dialog with the failures listed. |
| 1:45 | Proposal run, section progress, then **Open proposal**. Expand one citation. | "The draft is written section by section from the company's own documents. Every section cites the knowledge-base chunk it used. Click it, and there is the source text." | Section cards, grounded badge, citation expanding to chunk text. |
| 2:05 | Review panel: three scores and verdict. Click one gap. Mention a `[MISSING: ...]` marker if present. | "A reviewer scores completeness, relevance and compliance. Code sets the verdict, from checks and thresholds. Gaps link to the exact section. Where the company lacks a fact, it says missing, it does not invent one." | Three meters with threshold ticks, verdict, gap jump, highlighted markers. |
| 2:20 | **Approve...**: name and note, then download the **ZIP**. Show the checklist table. | "Approval is only possible once the page has shown this version after its review. Then the package: PDF, Word, a checklist, and the originals. The expired clearance shows as missing. We never submit anything." | Approval gate, downloads, checklist row `missing`. |

If **Generate proposal** is slow live, narrate over the progress bar: "Seven sections, each its own retrieval and its own
model call, so each is auditable." Do not fill silence with claims about quality.

### The audit log (the "How AI is used" segment, 45 s)

| Driver | AI voice says |
|---|---|
| Open **/runs**. Expand a `human` row (the approval): show the 64-character input hash and the output JSON. | "Every stage writes a row: model, input hash, output, latency. This one is a person's approval." |
| Expand a model row (a Compliance call) and the pipeline run's stage list. | "Three examples of AI output driving code. One: the model's match score ranks the list and a threshold decides whether Compliance runs at all. Two: a hard compliance failure sets the status to blocked, and the proposal route returns 409. Three: the review verdict gates approval. In each case the model fills a narrow schema, and code decides." |
| Optional: point at a `cached` row. | "Rows marked cached came from our pre-analysed replay. The model's answer is re-validated the same way." |
| | "All of it runs on open-weight models through Ollama. No proprietary APIs." |

## 6. The 3-minute video script

Record at 1080p after two full rehearsals, with the stack in the pinned-clock state (section 3). Voice-over about
150 words per minute. Captions on: the audience may not read Nepali.

| Time | On screen | Voice-over |
|---|---|---|
| 0:00 to 0:20 | A notice (`seed_tenders/001`), then a red "bid not entertained" graphic. | "In Nepal, a small contractor can do everything right and still lose a bid on a technicality: an expired tax clearance, a bid security that lapses early. Under the Public Procurement Rules, a bid missing an eligibility document is not entertained." |
| 0:20 to 0:35 | Pipeline diagram. | "Tenderly is a pipeline of agents: scout, match, check compliance, draft a proposal, review it, and wait for a human. Each stage produces structured data, and code uses it to decide what happens next." |
| 0:35 to 0:55 | Dashboard in Nepali and English, BS and AD toggle. | "It reads notices in English and Nepali, in Bikram Sambat dates, and ranks them against the company's profile. Here, the ventilator tender is skipped by rule. Compliance never runs." |
| 0:55 to 1:25 | Tender 001: fields next to quotes; Analyze; matrix with the red row. | "This road tender fits the company. Every extracted value shows the sentence it came from. Now the compliance check: the notice needs a tax clearance for fiscal year 2082/83, and the company's has expired. A deterministic rule found it, with the document as evidence, and the bid is blocked." |
| 1:25 to 1:40 | Override dialog. | "A named person can accept a risk, and that decision is logged." |
| 1:40 to 2:10 | Proposal page: sections, citation expanding, Nepali section if available. | "The proposal is drafted from the company's own documents. Every section cites its sources. Facts the model cannot find are marked missing, never invented." |
| 2:10 to 2:30 | Review panel, gap link. | "A reviewer scores the draft and points at gaps. Code sets the verdict." |
| 2:30 to 2:45 | Approve, ZIP downloads, checklist. | "Only after a person has seen the reviewed version can it be approved. The package has a cover letter, a bid-form skeleton, declarations, a checklist of attachments and an audit trail. Tenderly never submits anything." |
| 2:45 to 3:00 | /runs audit log; README results table; end card. | "Every model call is logged. It runs entirely on open-weight models. We report our numbers honestly, including what we have not measured, and the limits are in the README. Tenderly: from a raw notice to a reviewed, compliant package, with a human approving each critical step." |

## 7. Fallbacks

| Failure | Do |
|---|---|
| Live model slow or timing out | Use the replay cache: `LLM_REPLAY_CACHE` set (Compose does it by default) and `DEMO_NOW` equal to the recorded clock. Analyze the third tender before going on stage. |
| Cache misses (a run calls the live model) | The `/runs` page shows rows without the `cached` mark. Say it plainly and carry on; do not re-run. |
| A stage fails | The tender shows `failed` with the error; click **Analyze** again, and it resumes from the last good state. |
| The stack does not come up | Play the recorded video (kept paused on the desktop). The video is the guaranteed backup (spec §14). |
| Network down | Nothing in the path needs the network (seed notices, local models, local DB). |
| Wrong state (tender already approved) | Reset: `docker compose down -v`, restart, re-seed. |

## 8. Prepared answers

**Why not auto-submit?**
Three reasons. First, legal and operational exposure: submission means logging in to a portal (with CAPTCHAs and
signed documents), and a wrong submission cannot be undone, so a person should press that button.
Second, the stakes: a tender is a binding offer with a bid security at risk, and a 7B model is not accountable.
Third, scope: spec §1 puts it out of scope, and hard rule 6 forbids any stage logging in to, posting to or uploading
to a portal. What we do instead is make the human step small and informed: a reviewed package, a checklist and an
audit trail. Assisted submission, with a human confirmation at every irreversible step, is our first item of future work.

**How accurate is a 7B model?**
Honest answer: we have **not yet measured the model's accuracy** on our golden set. The evaluation harness is built
(`cd api && uv run python -m api.eval`, 15 hand-labelled notices for Scout, labels for Matching and Compliance), but
the model rows in `docs/EVAL.md` are empty until it is run, and we do not quote numbers we do not have.
What we can say: the labels are synthetic and written by us, so even a good score would not estimate accuracy on real notices.
What we have measured is the deterministic layer: 54 of 54 labelled mandatory requirements covered, 0 false hard
failures, 82% hard-fail recall before the model layer adds its part. And the design assumes the model is
sometimes wrong, so it is boxed in: it copies strings that code then verifies in the notice and converts (a value not
found verbatim becomes null and is flagged "needs review"); it never sets a deadline, an amount, an expiry, a
threshold or a verdict; its compliance evidence must cite a retrieved chunk and a verbatim quote, otherwise it is
downgraded to `unclear`; and a person approves everything.

**What happens on a hallucinated requirement?**
There are two cases. If the model invents a requirement or a required document at extraction, the code checks its
supporting quote against the notice. The quote will not be there, so the item is flagged `needs_review` and the
tender page shows a "Needs review" badge with the missing quote next to it. The item is kept (not silently dropped),
so a human sees it. If a flagged item then fails a rule, the failure is visible with its evidence, and the worst case is a
false block, which is the conservative direction and needs a named person to override, so it is logged. If the model
claims evidence at compliance time, `ground()` checks the cited chunk was shown and the quote is verbatim in it,
otherwise the item becomes `unclear` and never `pass`. In the proposal, any amount, date or identifier the model
types is masked as unsourced and flagged, and a section with no valid citation is marked ungrounded. We cannot
claim this removes all errors: a plausible but wrong requirement whose words do appear in the notice would pass
these checks, which is why the human approval gate exists.

**How is the company's data protected?**
In this build, by keeping it local. The documents, the database and the model all run on the team's own machine
in Docker, so company data is never sent to a third-party AI service, and there are no proprietary APIs. The scraper
reads only public notices and never logs in. Nothing is submitted externally. Limits, stated plainly: there is no
authentication or multi-user access control (single tenant, one company), uploaded originals are stored in the
database unencrypted, and if someone points `LLM_BASE_URL` at a hosted open-weight provider, prompts containing company text
go to that provider. A production version needs authentication, per-company isolation, encryption at rest, and a
data-processing agreement for any hosted model. All demo data is synthetic.

**How do you keep Nepal's rules current?**
By keeping them as data and refusing to hard-code what we cannot verify. The 14 compliance rules live in
`api/nepal/rules.yaml`, each with a source and a `verified` flag; 5 are unverified and the UI says so. Thresholds
(turnover, experience, bid security amount, validity, required documents) are read from **each notice**, never from
statute, because the notice is the authority for that tender. The English Rules text we had is from 2008, and the
open `[VERIFY]` items (current thresholds, validity days, domestic preference, licence class limits) are listed in
`docs/NEPAL_CONTEXT.md` §10. To update: a procurement adviser reads the current consolidated Nepali text (the Rules
amended through the 11th amendment, and the 12th amendment is not yet read), the change is made in the YAML with the new
source, the test suite covers each rule, and the `verified` flag is flipped only when a person has confirmed the text.
The Bikram Sambat calendar comes from one lookup table exported from the backend, and it is a projection after BS
2083 (libraries disagree from 2084), which is flagged in the docs. We do not yet have an automated feed from the
regulator, and we say so.

**Short answers for other likely questions**

- *Is the data real?* No. The company, the 37 notices, the labels and the bank figures are synthetic and marked so.
- *Why Qwen2.5-7B?* Open weights, good structured output at 7B, and it runs on a single laptop GPU. Llama 3.1 8B is the fallback.
- *Why not an agent framework?* A plain state machine is easier to debug, audit and explain (`pipeline/orchestrator.py`).
- *Does it work in Nepali?* The UI, the date handling, the notice parsing and the PDF export do. Generation quality is
  English-first, and Nepali proposals are the weakest output (not reviewed by a native speaker).
- *What if the portal changes?* The live scraper is a bonus on one municipal board. The demo uses the seed set.

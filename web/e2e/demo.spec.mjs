// @ts-check
/**
 * The demo path, end to end (spec section 12, "From a raw tender notice to a compliance-checked, reviewed proposal
 * package in minutes, with a human approving every critical step"):
 *
 *   load seed notices -> tender 001 -> Analyze (Scout, Matching, Compliance) -> blocked by the expired tax clearance
 *   -> a named override -> Proposal + Review -> open the proposal (sections, citations, requirements, review panel)
 *   -> Approve (name + note) -> DOCX / PDF / ZIP downloads + attachment checklist -> the approval in the audit log
 *   (both checked at projector resolution).
 *
 * On the real stack every model answer should come from the replay cache (precache_demo --through-review 001), so
 * the run is fast and the verdict is the recorded one. See playwright.config.ts for E2E_MOCKS=1.
 *
 * Plain ESM + JSDoc on purpose: under Bun (no Node), Playwright does not strip TypeScript types from spec files.
 */
import { expect, test } from "./fixtures.mjs";

const MOCKS = process.env.E2E_MOCKS === "1";
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const PERSON = "Sita Demo Thapa";
/** A whole pipeline stage on the real stack (cache hits are fast; a miss calls Ollama). */
const STAGE_MS = MOCKS ? 20_000 : 10 * 60_000;

/** The DB id of a seed notice (`seed://seed_tenders/001_...`); the mocks use the seed number as the id. */
/**
 * @param {import("@playwright/test").APIRequestContext} request
 * @param {string} seed
 * @returns {Promise<number>}
 */
async function tenderId(request, seed) {
  if (MOCKS) return Number(seed);
  const resp = await request.get(`${API}/tenders?limit=500`);
  expect(resp.ok(), `GET ${API}/tenders`).toBeTruthy();
  /** @type {{ id: number; source_url?: string | null }[]} */
  const rows = await resp.json();
  const row = rows.find((r) => r.source_url?.includes(`/${seed}_`));
  expect(row, `seed ${seed} is loaded`).toBeTruthy();
  return /** @type {{ id: number }} */ (row).id;
}

/** @param {import("@playwright/test").Page} page */
async function tenderStatus(page) {
  return (await page.locator("header [data-status]").first().getAttribute("data-status")) ?? "";
}

/** @param {import("@playwright/test").Page} page */
async function noHorizontalScroll(page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, `horizontal overflow on ${page.url()}`).toBeLessThanOrEqual(1);
}

test("demo path: seed notice to approved, downloadable package with an audit trail", async ({ page, request }) => {
  // 1. Dashboard: load the 37 synthetic seed notices.
  if (!MOCKS) {
    const company = await request.get(`${API}/company`);
    expect(company.ok(), "the demo company is seeded (scripts.seed_demo)").toBeTruthy();
  }
  await page.goto("/");
  await page.getByRole("button", { name: "Load tenders" }).click();
  await expect(page.getByText(/\d+ new, \d+ updated, \d+ unchanged/)).toBeVisible();
  await expect(page.getByTestId("tender-row").first()).toBeVisible();

  // 2. Tender 001 (strong match): Analyze unless a previous run already got it there.
  const id = await tenderId(request, "001");
  await page.goto(`/tenders/${id}`);
  let status = await tenderStatus(page);
  expect(status, "tender 001 is approved already: use a fresh DB (see CLAUDE.md)").not.toBe("approved");
  if (["new", "extracted", "matched", "failed"].includes(status)) {
    await page.getByRole("button", { name: "Analyze", exact: true }).click();
    await expect(page.locator("header [data-status]").first()).toHaveAttribute("data-status", /^(blocked|checked)$/, {
      timeout: STAGE_MS,
    });
    status = await tenderStatus(page);
  }

  // 3. Compliance: the matrix is shown; the expired FY 2081/82 tax clearance blocks the bid until a person overrides.
  if (["blocked", "checked"].includes(status)) {
    await expect(page.getByTestId("cm-row").first()).toBeVisible();
    if (status === "blocked") {
      await expect(page.getByRole("button", { name: "Generate proposal" })).toBeDisabled();
      await page.getByRole("button", { name: "Override and generate…" }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByLabel("Your name").fill(PERSON);
      await dialog.getByLabel("Reason").fill("FY 2082/83 clearance issued; the copy is uploaded before submission.");
      await dialog.getByRole("button", { name: "Record override and generate" }).click();
      await expect(dialog).toBeHidden();
    } else {
      await page.getByRole("button", { name: "Generate proposal" }).click();
    }
  }

  // 4. Proposal + Review run (section-by-section progress), then the proposal page.
  const openProposal = page.getByTestId("open-proposal");
  await expect(openProposal).toBeVisible({ timeout: 2 * STAGE_MS });
  await openProposal.click();
  await expect(page).toHaveURL(/\/tenders\/\d+\/proposal/);

  // 5. Sections with sources that expand to the KB chunk; the review panel with three scores and a verdict.
  const sections = page.getByTestId("proposal-section");
  await expect(sections.first()).toBeVisible();
  const review = page.getByTestId("review-panel");
  await expect(review.getByRole("meter")).toHaveCount(3);
  const verdict = await review.getByTestId("verdict").getAttribute("data-verdict");
  expect(verdict, "the demo proposal's review verdict").not.toBe("fail");
  const grounded = page.locator('[data-testid="proposal-section"][data-grounded="true"]').first();
  const citation = grounded.getByRole("button", { name: /^Chunk \d+/ }).first();
  await citation.click();
  await expect(citation).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator(`#${await citation.getAttribute("aria-controls")}`)).toBeVisible();

  // Requirements side by side with the text that answers them.
  await page.getByRole("tab", { name: /Requirements and responses/ }).click();
  await expect(page.getByTestId("requirement-row").first()).toBeVisible();
  await page.getByRole("tab", { name: /Sections/ }).click();

  // 6. Approve: enabled once the page has recorded the open (verdict is not fail, latest version).
  const approve = page.getByRole("button", { name: "Approve…" });
  await expect(approve).toBeEnabled();
  await approve.click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Your name").fill(PERSON);
  await dialog.getByLabel("Note (optional)").fill("Checked against the notice; E2E run.");
  await dialog.getByRole("button", { name: /^Approve version \d+$/ }).click();
  await expect(page.getByTestId("approved")).toContainText(PERSON);

  // 7. Downloads (DOCX, PDF, package ZIP) and the attachment checklist inline.
  const extension = { docx: /\.docx$/, pdf: /\.pdf$/, zip: /\.zip$/ };
  for (const kind of /** @type {const} */ (["docx", "pdf", "zip"])) {
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId(`download-${kind}`).click()]);
    if (!MOCKS) expect(download.suggestedFilename()).toMatch(extension[kind]);
    expect(await download.failure()).toBeNull();
  }
  const checklist = page.getByTestId("checklist");
  await expect(checklist.locator("tbody tr").first()).toBeVisible();
  await expect(checklist.locator('tr[data-status="missing"]').first()).toBeVisible(); // the expired clearance

  // 8. Projector resolution (1024x768): the approved proposal page and the audit log fit without sideways scrolling.
  await page.setViewportSize({ width: 1024, height: 768 });
  await noHorizontalScroll(page);

  // 9. The audit log: the approval is a `human` row; expand it for its input hash and output JSON.
  await page.goto("/runs");
  const human = page.locator('[data-testid="agent-run-row"][data-model="human"]').first();
  await expect(human).toBeVisible();
  await human.getByRole("button", { name: /Show the input hash and output/ }).click();
  const details = page.getByTestId("run-details").first();
  await expect(details.getByTestId("input-hash")).toHaveText(/^[0-9a-f]{64}$/);
  await expect(details.getByTestId("output-json")).toContainText('"approve"');
  await expect(page.getByTestId("pipeline-runs")).toBeVisible();
  await noHorizontalScroll(page);
});

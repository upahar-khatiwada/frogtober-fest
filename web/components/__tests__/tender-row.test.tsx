import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PrefToggles } from "@/components/app-shell/pref-toggles";
import { TenderRow } from "@/components/tenders/tender-row";
import type { TenderListItem } from "@/lib/api/tenderly";
import { CALENDAR_KEY, LANG_KEY, PreferencesProvider } from "@/lib/prefs";

const NOW = new Date("2026-10-19T12:00:00+05:45");

// Shaped like a real GET /tenders row (deadline values from api/tests/test_tenders_list_api.py).
const TENDER: TenderListItem = {
  rank: 1,
  id: 29,
  status: "blocked",
  title: "माछापुच्छ्रे गाउँपालिका ग्रामीण सडक मर्मत सम्भार",
  buyer: "माछापुच्छ्रे गाउँपालिका",
  buyer_level: "local",
  procurement_type: "works",
  method: "ncb",
  province: "gandaki",
  district: "Kaski",
  language: "ne",
  estimated_cost_npr: 14_875_000,
  deadline: {
    ad: "2026-11-21T12:00:00+05:45",
    ad_date: "2026-11-21",
    bs: "2083-08-05",
    bs_long: "5 Mangsir 2083",
    bs_ne: "५ मंसिर २०८३",
    days_left: 33,
    passed: false,
  },
  score: 82,
  decision: "pursue",
  reasons: ["[deterministic] Kaski district is served by the company", "[model] Road maintenance fits the company [chunk 5]", "[deterministic] other"],
  hard_failures: 1,
  needs_review: false,
  source_url: "seed://seed_tenders/029_machhapuchchhre_road_maintenance.txt",
};

function renderRow(tender: TenderListItem = TENDER) {
  return render(
    <PreferencesProvider>
      <PrefToggles />
      <ol>
        <TenderRow tender={tender} />
      </ol>
    </PreferencesProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ now: NOW, toFake: ["Date"] });
  window.localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  window.localStorage.clear();
  document.documentElement.lang = "en";
});

describe("TenderRow", () => {
  it("renders Nepali labels, BS date, NPR and Devanagari data intact", async () => {
    window.localStorage.setItem(LANG_KEY, "ne");
    renderRow();
    const row = screen.getByTestId("tender-row");

    // Devanagari data from the API is rendered unchanged (same code points, NFC, no mojibake).
    const title = within(row).getByRole("heading");
    expect(title.textContent).toBe(TENDER.title);
    expect(title.textContent!.normalize("NFC")).toBe(title.textContent);
    expect(title).toHaveAttribute("lang", "ne");
    expect(title.textContent).toMatch(/^[ऀ-ॿ .]+$/);

    // UI labels from the Nepali dictionary.
    expect(within(row).getByText("रोकियो")).toBeInTheDocument(); // status: blocked
    expect(within(row).getByText("निर्माण कार्य")).toBeInTheDocument(); // works
    expect(within(row).getByText("स्थानीय")).toBeInTheDocument(); // local
    expect(within(row).getByText("गण्डकी / Kaski")).toBeInTheDocument();
    expect(within(row).getByText("अगाडि बढाउने")).toBeInTheDocument(); // pursue
    expect(within(row).getByText("१ अनिवार्य सर्त पूरा भएनन्")).toBeInTheDocument();
    expect(within(row).getByText("रु. १.४९ करोड")).toHaveAttribute("title", "रु. १,४८,७५,०००");

    // Deadline: BS first (default calendar), Nepali form from the API, plus a live NPT countdown.
    const deadline = within(row).getByTestId("deadline");
    expect(deadline).toHaveTextContent("५ मंसिर २०८३ BS, १२:०० NPT");
    expect(deadline).toHaveTextContent("२१ नोभेम्बर २०२६ AD");
    expect(await within(deadline).findByText("३३ दिन बाँकी")).toBeInTheDocument();

    // Reasons preview leads with the model's reason; the rest are counted.
    expect(within(row).getByText("Road maintenance fits the company [chunk 5]")).toBeInTheDocument();
    expect(within(row).getByText("+१ थप")).toBeInTheDocument();

    expect(document.documentElement.lang).toBe("ne");
  });

  it("switches language and calendar from the toggles and remembers them", async () => {
    const user = userEvent.setup();
    renderRow();
    const row = screen.getByTestId("tender-row");
    expect(within(row).getByText("Blocked")).toBeInTheDocument();
    expect(within(row).getByTestId("deadline")).toHaveTextContent(/^.*5 Mangsir 2083 BS, 12:00 NPT21 Nov 2026 AD$/);

    await user.click(screen.getByRole("button", { name: "नेपाली" }));
    expect(within(row).getByText("रोकियो")).toBeInTheDocument();
    expect(window.localStorage.getItem(LANG_KEY)).toBe("ne");
    expect(screen.getByRole("button", { name: "नेपाली" })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "AD" }));
    expect(within(row).getByTestId("deadline")).toHaveTextContent("२१ नोभेम्बर २०२६ AD, १२:०० NPT५ मंसिर २०८३ BS");
    expect(window.localStorage.getItem(CALENDAR_KEY)).toBe("AD");
  });

  it("shows an unextracted notice without inventing values", () => {
    renderRow({ ...TENDER, title: null, buyer: null, score: null, decision: null, reasons: [], deadline: null, hard_failures: null, estimated_cost_npr: null, status: "new" });
    const row = screen.getByTestId("tender-row");
    expect(within(row).getByText("Untitled notice (not extracted yet)")).toBeInTheDocument();
    expect(within(row).getByText("Not scored")).toBeInTheDocument();
    expect(within(row).getByText("Deadline not confirmed")).toBeInTheDocument();
    expect(within(row).getByText("New")).toBeInTheDocument();
  });

  it("re-renders when another tab changes the stored language", () => {
    renderRow();
    act(() => {
      window.localStorage.setItem(LANG_KEY, "ne");
      window.dispatchEvent(new StorageEvent("storage", { key: LANG_KEY }));
    });
    expect(within(screen.getByTestId("tender-row")).getByText("रोकियो")).toBeInTheDocument();
  });
});

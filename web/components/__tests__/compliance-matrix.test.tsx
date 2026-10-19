import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ComplianceMatrix } from "@/components/tender-detail/compliance-matrix";
import type {
  CompanyDocumentView,
  ComplianceItem,
  ComplianceView,
  KBChunkView,
  RuleView,
} from "@/lib/api/tenderly";

const RULES: Record<string, RuleView> = {
  "NP-TAX-CLEARANCE": {
    id: "NP-TAX-CLEARANCE",
    description:
      "Tax clearance (or tax-return proof) on file for each fiscal year the notice requires.",
    severity: "hard",
    source: "https://example.test/rule-40",
    verified: true,
    notes: "PPR-EN Rule 40(2)(d)",
  },
  "NP-TURNOVER": {
    id: "NP-TURNOVER",
    description: "Average annual turnover meets the notice's minimum.",
    severity: "hard",
    source: "https://example.test/rule-28",
    verified: false,
    notes: null,
  },
};

const DOCS: Record<number, CompanyDocumentView> = {
  2: {
    id: 2,
    filename: "03_tax_clearance_2081-82.pdf",
    doc_type: "tax_clearance",
    expires_on: "2026-07-16",
    is_expired: true,
    fiscal_year_bs: "2081/82",
    ingest_status: "ready",
    chunk_count: 1,
    uploaded_at: "2026-10-17T10:05:30+05:45",
  },
};

const CHUNKS: Record<number, KBChunkView> = {
  12: {
    chunk_id: 12,
    document_id: 3,
    filename: "06_construction_licence.txt",
    doc_type: "business_licence",
    chunk_index: 0,
    content:
      'Licence No.: DEMO-C-0421\nClass: "C" class (general civil construction)\nRenewed for FY 2083/84.',
    expires_on: "2027-07-16",
    is_expired: false,
    fiscal_year_bs: "2083/84",
  },
};

const FAIL: ComplianceItem = {
  requirement: "Tax clearance for F/Y 2082/83",
  status: "fail",
  severity: "hard",
  source: "rule",
  rule_id: "NP-TAX-CLEARANCE",
  evidence_document_ids: [2],
  explanation:
    "No clearance for 2082/83; F/Y 2081/82 on file (expired 2026-07-16).",
  action_needed:
    "Renew tax clearance for F/Y 2082/83 and upload it before submission.",
};
const PASS_MODEL: ComplianceItem = {
  requirement: 'Construction licence of class "D" or above',
  status: "pass",
  severity: "hard",
  source: "model",
  evidence_chunk_ids: [12],
  evidence_quote: 'Class: "C" class (general civil construction)',
  explanation: "The licence is class C, above D.",
};
const UNCLEAR: ComplianceItem = {
  requirement: "Minimum average annual turnover",
  status: "unclear",
  severity: "hard",
  source: "rule",
  rule_id: "NP-TURNOVER",
  action_needed: "Check the turnover period against the minimum.",
};
const PASS_RULE_NO_META: ComplianceItem = {
  requirement: "Submission deadline not passed",
  status: "pass",
  severity: "hard",
  source: "rule",
  rule_id: "NP-DEADLINE",
  evidence_ref: "tender.deadline",
};
const PASS_MISSING_CHUNK: ComplianceItem = {
  ...PASS_MODEL,
  requirement: "Key personnel",
  evidence_chunk_ids: [99],
  evidence_quote: undefined,
};

function view(
  items: ComplianceItem[],
  over: Partial<ComplianceView> = {},
): ComplianceView {
  const count = (s: ComplianceItem["status"]) =>
    items.filter((i) => i.status === s).length;
  const hard = items.filter(
    (i) => i.status === "fail" && i.severity === "hard",
  ).length;
  return {
    items,
    override: null,
    blocked: hard > 0,
    hard_failures: hard,
    counts: {
      pass: count("pass"),
      fail: count("fail"),
      unclear: count("unclear"),
    },
    proposal_allowed: hard === 0,
    ...over,
  };
}

function renderMatrix(compliance: ComplianceView | null) {
  return render(
    <ComplianceMatrix
      compliance={compliance}
      rules={RULES}
      chunks={CHUNKS}
      documents={DOCS}
    />,
  );
}

describe("ComplianceMatrix", () => {
  it("shows an empty state before compliance has run", () => {
    renderMatrix(null);
    expect(
      screen.getByText("Compliance has not run yet. Click Analyze."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("cm-row")).not.toBeInTheDocument();
  });

  it("treats a report with no items as empty too", () => {
    renderMatrix(view([]));
    expect(
      screen.getByText("Compliance has not run yet. Click Analyze."),
    ).toBeInTheDocument();
  });

  it("renders one coloured row per status, with counts and a blocked banner", () => {
    renderMatrix(view([FAIL, PASS_RULE_NO_META, UNCLEAR, PASS_MODEL]));
    const rows = screen.getAllByTestId("cm-row");
    expect(rows.map((r) => r.getAttribute("data-status"))).toEqual([
      "fail",
      "pass",
      "unclear",
      "pass",
    ]);
    expect(within(rows[0]).getByText("Fail")).toBeInTheDocument(); // status is text, not colour alone
    expect(rows[0].className).toContain("bg-red-50");
    expect(rows[1].className).toContain("bg-emerald-50");
    expect(rows[2].className).toContain("bg-amber-50");
    expect(screen.getByText("2 pass · 1 fail · 1 unclear")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      /Blocked by 1 hard compliance failure/,
    );
  });

  it("shows no blocked banner when there are no hard failures", () => {
    renderMatrix(view([PASS_MODEL, UNCLEAR]));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("No hard failures.")).toBeInTheDocument();
  });

  it("shows the action needed column, or 'Nothing to do' for a pass", () => {
    renderMatrix(view([FAIL, PASS_MODEL]));
    const [fail, pass] = screen.getAllByTestId("cm-row");
    expect(
      within(fail).getByText(
        "Renew tax clearance for F/Y 2082/83 and upload it before submission.",
      ),
    ).toBeInTheDocument();
    expect(within(pass).getByText("Nothing to do")).toBeInTheDocument();
  });

  it("links rule badges to the rule reference and shows verified / unverified", () => {
    renderMatrix(view([FAIL, UNCLEAR, PASS_RULE_NO_META, PASS_MODEL]));
    const [fail, unclear, noMeta, model] = screen.getAllByTestId("cm-row");

    const taxLink = within(fail).getByRole("link", {
      name: "NP-TAX-CLEARANCE",
    });
    expect(taxLink).toHaveAttribute("href", "#rule-NP-TAX-CLEARANCE");
    expect(taxLink).toHaveAttribute(
      "title",
      RULES["NP-TAX-CLEARANCE"].description,
    );
    expect(within(fail).getByText("Verified rule")).toBeInTheDocument();
    expect(within(unclear).getByText("Unverified rule")).toBeInTheDocument();

    // A rule the API did not describe still links, without a verified label.
    expect(
      within(noMeta).getByRole("link", { name: "NP-DEADLINE" }),
    ).toHaveAttribute("title", "Rule details unavailable");
    expect(within(noMeta).queryByText(/rule$/)).not.toBeInTheDocument();

    // Model items are tagged, not linked.
    expect(within(model).getByText("Model")).toBeInTheDocument();
    expect(within(model).queryByRole("link")).not.toBeInTheDocument();

    // The link target exists in the rules reference.
    const target = document.getElementById("rule-NP-TAX-CLEARANCE");
    expect(target).not.toBeNull();
    expect(target).toHaveTextContent(RULES["NP-TAX-CLEARANCE"].description);
    expect(target).toHaveTextContent("Verified rule");
    expect(
      within(target as HTMLElement).getByRole("link", { name: "Source" }),
    ).toHaveAttribute("href", "https://example.test/rule-40");
    expect(document.getElementById("rule-NP-TURNOVER")).toHaveTextContent(
      "Unverified rule",
    );
  });

  it("expands document evidence: name, fiscal year, expiry and expired badge", async () => {
    const user = userEvent.setup();
    renderMatrix(view([FAIL]));
    const toggle = screen.getByRole("button", { name: /Show evidence/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("evidence-document")).not.toBeInTheDocument();

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const doc = screen.getByTestId("evidence-document");
    expect(doc).toHaveTextContent("03_tax_clearance_2081-82.pdf");
    expect(doc).toHaveTextContent("FY 2081/82");
    expect(doc).toHaveTextContent("Expires 32 Asar 2083"); // 2026-07-16 in BS, the default calendar
    expect(within(doc).getByText("Expired")).toBeInTheDocument();
    expect(screen.getByText(/F\/Y 2081\/82 on file/)).toBeInTheDocument(); // explanation

    await user.click(screen.getByRole("button", { name: /Hide evidence/ }));
    expect(screen.queryByTestId("evidence-document")).not.toBeInTheDocument();
  });

  it("expands chunk evidence with the excerpt text, document and highlighted quote", async () => {
    const user = userEvent.setup();
    renderMatrix(view([PASS_MODEL]));
    await user.click(screen.getByRole("button", { name: /Show evidence/ }));

    const chunk = screen.getByTestId("evidence-chunk");
    expect(chunk).toHaveTextContent("Knowledge-base excerpt #12");
    expect(chunk).toHaveTextContent("06_construction_licence.txt");
    expect(chunk).toHaveTextContent("Business licence");
    expect(chunk).toHaveTextContent("Licence No.: DEMO-C-0421");
    expect(chunk.querySelector("mark")).toHaveTextContent(
      'Class: "C" class (general civil construction)',
    );
    expect(within(chunk).queryByText("Expired")).not.toBeInTheDocument();
  });

  it("says so when the cited excerpt could not be loaded", async () => {
    const user = userEvent.setup();
    renderMatrix(view([PASS_MISSING_CHUNK]));
    await user.click(screen.getByRole("button", { name: /Show evidence/ }));
    expect(screen.getByTestId("evidence-chunk")).toHaveTextContent(
      "Excerpt text unavailable",
    );
  });

  it("expands rows independently", async () => {
    const user = userEvent.setup();
    renderMatrix(view([FAIL, PASS_MODEL]));
    const [first, second] = screen.getAllByRole("button", {
      name: /Show evidence/,
    });
    await user.click(second);
    expect(screen.getByTestId("evidence-chunk")).toBeInTheDocument();
    expect(screen.queryByTestId("evidence-document")).not.toBeInTheDocument();
    expect(first).toHaveAttribute("aria-expanded", "false");
  });

  it("shows who accepted the hard failures when an override is active", () => {
    renderMatrix(
      view([FAIL, PASS_MODEL], {
        proposal_allowed: true,
        override: {
          id: 1,
          overridden_by: "Sita Demo Thapa",
          reason: "Clearance issued; upload pending.",
          overridden_at: "2026-10-19T10:00:00+05:45",
          hard_failures: ["NP-TAX-CLEARANCE:Tax clearance for F/Y 2082/83"],
          active: true,
        },
      }),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      /1 hard failure\(s\) accepted by an override/,
    );
    const note = screen.getByTestId("override-note");
    expect(note).toHaveTextContent(
      "Override by Sita Demo Thapa: Clearance issued; upload pending.",
    );
    expect(note).toHaveTextContent("Active");
  });
});

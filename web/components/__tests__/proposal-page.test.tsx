import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApprovalPanel } from "@/components/proposal/approval-panel";
import { RequirementsView } from "@/components/proposal/requirements-view";
import { ReviewPanel } from "@/components/proposal/review-panel";
import { SectionCard } from "@/components/proposal/section-card";
import { AgentRunsTable } from "@/components/runs/agent-runs-table";
import type { AgentRunView, KBChunkView, Proposal, ProposalSection, ReviewReport } from "@/lib/api/tenderly";
import { approvalGates } from "@/lib/proposal";

const CHUNK: KBChunkView = {
  chunk_id: 7,
  document_id: 5,
  filename: "04_experience_certificate.docx",
  doc_type: "experience_certificate",
  chunk_index: 0,
  content: "Vyas Municipality certifies the Vyas-Damauli link road. Contract amount: Rs 1,85,40,000.",
};

const GROUNDED: ProposalSection = {
  key: "relevant_experience",
  title: "Relevant experience",
  body: "The company completed the Vyas-Damauli link road.",
  body_template: "",
  cited_chunk_ids: [7],
  grounded: true,
  requirement_indices: [0],
};

const UNGROUNDED: ProposalSection = {
  key: "declarations",
  title: "Declarations",
  body: "We are not disqualified. VAT [MISSING: company.vat].",
  body_template: "",
  cited_chunk_ids: [],
  grounded: false,
  flags: [{ kind: "ungrounded", detail: "no chunk cited" }],
};

const REVIEW: ReviewReport = {
  scores: { completeness: 74, relevance: 35, compliance: 90 },
  checks: [{ check: "sections_cited", passed: false, severity: "soft", detail: "1 of 2 sections cite the KB" }],
  gaps: [
    { source: "check", check: "sections_cited", section_key: "declarations", issue: "No citation.", severity: "soft" },
    { source: "model", requirement_index: 1, issue: "Equipment list missing.", severity: "hard" },
  ],
  verdict: "fail",
  verdict_reasons: ["[model] lowest score 35 is below 40"],
  pass_min_score: 70,
  fail_below_score: 40,
};

describe("SectionCard", () => {
  const props = { chunks: { 7: CHUNK }, editable: true, onSave: vi.fn(), onRequirement: vi.fn() };

  it("expands a citation to the KB chunk text", async () => {
    render(<SectionCard section={GROUNDED} {...props} />);
    expect(screen.getByText("Cites the knowledge base")).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /Chunk 7/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/Contract amount/)).not.toBeInTheDocument();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Contract amount: Rs 1,85,40,000/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Requirement 1" }));
    expect(props.onRequirement).toHaveBeenCalledWith(0);
  });

  it("warns about an ungrounded section and highlights unresolved values", () => {
    render(<SectionCard section={UNGROUNDED} {...props} />);
    expect(screen.getByRole("note")).toHaveTextContent(/cites no knowledge-base chunk/);
    expect(screen.getByText("[MISSING: company.vat]").tagName).toBe("MARK");
    expect(screen.getByText("No knowledge-base sources.")).toBeInTheDocument();
  });

  it("saves an edit with the person's name, and explains when editing is off", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const { unmount } = render(<SectionCard section={GROUNDED} {...props} onSave={onSave} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const save = screen.getByRole("button", { name: "Save as a new version" });
    expect(save).toBeDisabled(); // unchanged text, no name
    await userEvent.type(screen.getByLabelText("Section text (Markdown)"), " Certified complete.");
    await userEvent.type(screen.getByLabelText("Your name"), "Sita");
    await userEvent.click(save);
    expect(onSave).toHaveBeenCalledWith(`${GROUNDED.body} Certified complete.`, "Sita", null);
    unmount();

    render(<SectionCard section={GROUNDED} {...props} editable={false} />);
    expect(screen.getByRole("button", { name: "Edit" })).toBeDisabled();
    expect(screen.getByText(/Only the latest version/)).toBeInTheDocument();
  });
});

describe("ReviewPanel", () => {
  it("shows the verdict, three scores and gaps linked to sections and requirements", async () => {
    const onSection = vi.fn();
    const onRequirement = vi.fn();
    render(
      <ReviewPanel
        review={REVIEW}
        sections={[GROUNDED, UNGROUNDED]}
        canRunReview={false}
        reviewing={false}
        onRunReview={vi.fn()}
        onSection={onSection}
        onRequirement={onRequirement}
      />,
    );
    expect(screen.getByTestId("verdict")).toHaveAttribute("data-verdict", "fail");
    const meters = screen.getAllByRole("meter");
    expect(meters.map((m) => m.getAttribute("aria-valuenow"))).toEqual(["74", "35", "90"]);
    expect(screen.getByText("[model] lowest score 35 is below 40")).toBeInTheDocument();
    const gaps = within(screen.getByTestId("review-gaps"));
    await userEvent.click(gaps.getByRole("button", { name: "→ Declarations" }));
    expect(onSection).toHaveBeenCalledWith("declarations");
    await userEvent.click(gaps.getByRole("button", { name: "→ Requirement 2" }));
    expect(onRequirement).toHaveBeenCalledWith(1);
  });

  it("offers Run review for an unreviewed latest version", () => {
    const onRunReview = vi.fn();
    render(
      <ReviewPanel
        review={null}
        sections={[]}
        canRunReview
        reviewing={false}
        onRunReview={onRunReview}
        onSection={vi.fn()}
        onRequirement={vi.fn()}
      />,
    );
    expect(screen.getByText("Not reviewed yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run review" })).toBeEnabled();
  });
});

describe("ApprovalPanel", () => {
  const base: Proposal = {
    id: 9,
    tender_id: 1,
    version: 2,
    language: "en",
    sections: [GROUNDED],
    citation_rate: 1,
    status: "reviewed",
    review: { ...REVIEW, verdict: "needs_work" },
    reviewed_at: "2026-10-22T04:00:00Z",
  };

  it("keeps Approve disabled until the version has been opened after its review", () => {
    render(<ApprovalPanel proposal={base} gates={approvalGates(base, [base])} opening onApprove={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Approve…" })).toBeDisabled();
    expect(screen.getByText(/You opened this version/).closest("li")).toHaveAttribute("data-met", "false");
    expect(screen.getByText("Approval stays disabled until every condition is met.")).toBeInTheDocument();
  });

  it("keeps Approve disabled on a fail verdict even when opened", () => {
    const failed = { ...base, review: REVIEW, opened_at: "2026-10-22T05:00:00Z" };
    render(<ApprovalPanel proposal={failed} gates={approvalGates(failed, [failed])} opening={false} onApprove={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Approve…" })).toBeDisabled();
  });

  it("approves with a name and note once every gate is met", async () => {
    const opened = { ...base, opened_at: "2026-10-22T05:00:00Z" };
    const onApprove = vi.fn().mockResolvedValue(undefined);
    render(<ApprovalPanel proposal={opened} gates={approvalGates(opened, [opened])} opening={false} onApprove={onApprove} />);
    await userEvent.click(screen.getByRole("button", { name: "Approve…" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.clear(within(dialog).getByLabelText("Your name")); // prefilled from the remembered name
    await userEvent.type(within(dialog).getByLabelText("Your name"), "Sita Demo Thapa");
    await userEvent.type(within(dialog).getByLabelText("Note (optional)"), "Checked.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve version 2" }));
    expect(onApprove).toHaveBeenCalledWith("Sita Demo Thapa", "Checked.");
  });

  it("shows who approved and when (NPT, in the preferred calendar)", () => {
    const approved = { ...base, status: "approved" as const, approved_by: "Sita Demo Thapa", approved_at: "2026-10-22T04:15:00Z" };
    render(<ApprovalPanel proposal={approved} gates={approvalGates(approved, [approved])} opening={false} onApprove={vi.fn()} />);
    expect(screen.getByTestId("approved")).toHaveTextContent("Approved by Sita Demo Thapa on 5 Kartik 2083 BS, 10:00 NPT");
  });
});

describe("RequirementsView", () => {
  it("puts each requirement next to the text that answers it, and flags unanswered ones", async () => {
    const onSection = vi.fn();
    render(
      <RequirementsView
        requirements={[
          { text: "One similar road contract", mandatory: true, category: "experience", source_quote: "at least one similar road work" },
          { text: "Equipment list", mandatory: true, category: "equipment", source_quote: "one vibratory roller" },
        ]}
        sections={[GROUNDED, UNGROUNDED]}
        review={REVIEW}
        onSection={onSection}
      />,
    );
    const [first, second] = screen.getAllByTestId("requirement-row");
    expect(within(first).getByText("at least one similar road work")).toBeInTheDocument();
    expect(within(first).getByText(GROUNDED.body)).toBeInTheDocument();
    await userEvent.click(within(first).getByRole("button", { name: /Go to the section/ }));
    expect(onSection).toHaveBeenCalledWith("relevant_experience");
    expect(within(second).getByText("No section addresses this requirement.")).toBeInTheDocument();
    expect(within(second).getByText("Equipment list missing.")).toBeInTheDocument();
  });
});

describe("AgentRunsTable", () => {
  it("expands a row to its input hash and output JSON", async () => {
    const row: AgentRunView = {
      id: 12,
      tender_id: 1,
      tender_title: "Bhanu road",
      stage: "review",
      model: "human",
      input_hash: "a".repeat(64),
      output_json: { action: "approve", approved_by: "Sita" },
      latency_ms: 0,
      ok: true,
      attempts: 1,
      cached: false,
      created_at: "2026-10-22T04:15:00Z",
    };
    render(<AgentRunsTable rows={[row, { ...row, id: 11, model: "qwen2.5:7b-instruct", ok: false, output_json: null, error: "timed out", cached: true }]} />);
    const rows = screen.getAllByTestId("agent-run-row");
    expect(within(rows[0]).getByText("person")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Failed")).toBeInTheDocument();
    expect(within(rows[1]).getByText("cached")).toBeInTheDocument();
    expect(screen.queryByTestId("run-details")).not.toBeInTheDocument();
    const toggle = within(rows[0]).getByRole("button", { name: "Show the input hash and output of row 12" });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("input-hash")).toHaveTextContent("a".repeat(64));
    expect(screen.getByTestId("output-json")).toHaveTextContent('"action": "approve"');
    await userEvent.click(within(rows[1]).getByRole("button", { name: /row 11/ }));
    expect(screen.getByText("No output (the call failed).")).toBeInTheDocument();
    expect(screen.getByText("timed out")).toBeInTheDocument();
  });
});

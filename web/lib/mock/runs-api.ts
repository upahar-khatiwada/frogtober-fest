/**
 * Mock audit log (NEXT_PUBLIC_USE_MOCKS=1): agent_runs rows and pipeline runs for the SYNTHETIC demo tenders,
 * shaped like GET /agent-runs and GET /runs. Hashes and outputs are illustrative, not from a real model.
 */
import type {
  AgentRunFilters,
  AgentRunView,
  PipelineRunView,
} from "@/lib/api/tenderly";

const delay = (ms = 100) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

const TITLE_1 =
  "Upgrading and Gravelling of Bhanu-Satiswara Road (3.2 km) including Side Drains and Slab Culverts, Bhanu-6, Tanahun";
const TITLE_3 = "Supply and delivery of ICU ventilators (ICB)";
const BASE = Date.parse("2026-10-22T03:30:00Z");

/** A stable fake sha256 (64 hex chars) per row, so the UI and tests see realistic input hashes. */
function hash(seed: number): string {
  let h = 2166136261 ^ seed;
  let out = "";
  while (out.length < 64) {
    h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0;
    out += h.toString(16).padStart(8, "0");
  }
  return out.slice(0, 64);
}

type Row = Omit<
  AgentRunView,
  "id" | "input_hash" | "created_at" | "attempts" | "cached"
> & { attempts?: number; cached?: boolean };

const ROWS: Row[] = [
  {
    tender_id: 3,
    tender_title: TITLE_3,
    stage: "scout",
    model: "qwen2.5:7b-instruct",
    latency_ms: 41_200,
    ok: true,
    cached: true,
    pipeline_run_id: 1,
    output_json: { title: { value: TITLE_3, quote: TITLE_3 }, procurement_type: "goods" },
  },
  {
    tender_id: 3,
    tender_title: TITLE_3,
    stage: "matching",
    model: "deterministic",
    latency_ms: 12,
    ok: true,
    pipeline_run_id: 1,
    output_json: {
      score: 59,
      decision: "skip",
      reasons: ["[deterministic] SKIP: procurement type goods is not one the company bids on"],
    },
  },
  {
    tender_id: 1,
    tender_title: TITLE_1,
    stage: "scout",
    model: "qwen2.5:7b-instruct",
    latency_ms: 38_400,
    ok: false,
    attempts: 2,
    cached: false,
    pipeline_run_id: 2,
    error: "attempt 2: /api/chat timed out after 180.0s",
    output_json: null,
  },
  {
    tender_id: 1,
    tender_title: TITLE_1,
    stage: "scout",
    model: "qwen2.5:7b-instruct",
    latency_ms: 36_900,
    ok: true,
    cached: true,
    pipeline_run_id: 3,
    output_json: {
      title: { value: TITLE_1, quote: `Name of Work: ${TITLE_1}` },
      deadline: {
        value: "12:00 hours on 2083-08-05 B.S. (2026-11-21 A.D.)",
        quote: "on or before 12:00 hours on 2083-08-05 B.S. (2026-11-21 A.D.)",
      },
    },
  },
  {
    tender_id: 1,
    tender_title: TITLE_1,
    stage: "matching",
    model: "qwen2.5:7b-instruct",
    latency_ms: 6_100,
    ok: true,
    cached: true,
    pipeline_run_id: 3,
    output_json: { semantic_score: 70, reasons: ["Rural road gravelling is the company's core service [chunk 21]"] },
  },
  {
    tender_id: 1,
    tender_title: TITLE_1,
    stage: "compliance",
    model: "deterministic",
    latency_ms: 18,
    ok: true,
    pipeline_run_id: 3,
    output_json: { rules: 14, hard_failures: ["NP-TAX-CLEARANCE:Tax clearance for F/Y 2082/83"], blocked: true },
  },
  {
    tender_id: 1,
    tender_title: TITLE_1,
    stage: "compliance",
    model: "qwen2.5:7b-instruct",
    latency_ms: 4_800,
    ok: true,
    cached: true,
    pipeline_run_id: 3,
    output_json: {
      status: "pass",
      evidence_chunk_ids: [12],
      evidence_quote: 'Class: "C" class (general civil construction)',
      explanation: "The licence is class C, above D.",
    },
  },
  {
    tender_id: 1,
    tender_title: TITLE_1,
    stage: "proposal",
    model: "deterministic",
    latency_ms: 31,
    ok: true,
    pipeline_run_id: 4,
    output_json: {
      version: 1,
      plan: ["cover_letter", "bidder_info", "work_plan", "relevant_experience", "key_equipment", "financial_capacity", "declarations"],
      citation_rate: 0.71,
    },
  },
  {
    tender_id: 1,
    tender_title: TITLE_1,
    stage: "review",
    model: "qwen2.5:7b-instruct",
    latency_ms: 9_300,
    ok: true,
    cached: true,
    pipeline_run_id: 4,
    output_json: { scores: { completeness: 74, relevance: 81, compliance: 78 }, gaps: [] },
  },
  {
    tender_id: 1,
    tender_title: TITLE_1,
    stage: "review",
    model: "human",
    latency_ms: 0,
    ok: true,
    pipeline_run_id: null,
    output_json: {
      action: "approve",
      proposal_id: 102,
      version: 2,
      verdict: "needs_work",
      approved_by: "Sita Demo Thapa",
      note: "Checked against the notice.",
    },
  },
];

function agentRuns(): AgentRunView[] {
  return ROWS.map((row, i) => ({
    attempts: 1,
    error: null,
    raw_output: null,
    cached: false,
    ...row,
    id: i + 1,
    input_hash: hash(i + 1),
    created_at: new Date(BASE + i * 47_000).toISOString(),
  })).reverse();
}

export async function listAgentRuns(
  filters: AgentRunFilters = {},
): Promise<AgentRunView[]> {
  await delay();
  return agentRuns()
    .filter((r) => !filters.stage || r.stage === filters.stage)
    .filter((r) => filters.ok == null || r.ok === filters.ok)
    .filter((r) => !filters.tender_id || r.tender_id === filters.tender_id)
    .filter(
      (r) =>
        !filters.pipeline_run_id ||
        r.pipeline_run_id === filters.pipeline_run_id,
    )
    .slice(0, filters.limit ?? 50);
}

const RUNS: PipelineRunView[] = [
  {
    id: 4,
    tender_id: 1,
    tender_title: TITLE_1,
    target: "reviewed",
    status: "succeeded",
    start_status: "checked",
    end_status: "reviewed",
    stages: [
      { stage: "proposal", status: "ok", from_status: "checked", to_status: "drafted", duration_ms: 64_000 },
      { stage: "review", status: "ok", from_status: "drafted", to_status: "reviewed", duration_ms: 21_500 },
    ],
    created_at: new Date(BASE + 7 * 47_000).toISOString(),
    started_at: new Date(BASE + 7 * 47_000).toISOString(),
    finished_at: new Date(BASE + 7 * 47_000 + 85_500).toISOString(),
    duration_ms: 85_500,
  },
  {
    id: 3,
    tender_id: 1,
    tender_title: TITLE_1,
    target: "checked",
    status: "stopped",
    start_status: "failed",
    resumed_from: "failed",
    end_status: "blocked",
    stages: [
      { stage: "scout", status: "ok", from_status: "new", to_status: "extracted", duration_ms: 37_000 },
      { stage: "matching", status: "ok", from_status: "extracted", to_status: "matched", duration_ms: 6_300 },
      { stage: "compliance", status: "branched", from_status: "matched", to_status: "blocked", duration_ms: 5_100 },
    ],
    created_at: new Date(BASE + 3 * 47_000).toISOString(),
    started_at: new Date(BASE + 3 * 47_000).toISOString(),
    finished_at: new Date(BASE + 3 * 47_000 + 48_400).toISOString(),
    duration_ms: 48_400,
  },
  {
    id: 2,
    tender_id: 1,
    tender_title: TITLE_1,
    target: "checked",
    status: "failed",
    start_status: "new",
    end_status: "failed",
    stages: [
      { stage: "scout", status: "failed", from_status: "new", to_status: "failed", duration_ms: 38_400, error: "attempt 2: /api/chat timed out after 180.0s" },
      { stage: "matching", status: "not_run", from_status: "extracted" },
      { stage: "compliance", status: "not_run", from_status: "matched" },
    ],
    error: "scout: attempt 2: /api/chat timed out after 180.0s",
    created_at: new Date(BASE + 2 * 47_000).toISOString(),
    started_at: new Date(BASE + 2 * 47_000).toISOString(),
    finished_at: new Date(BASE + 2 * 47_000 + 38_400).toISOString(),
    duration_ms: 38_400,
  },
  {
    id: 1,
    tender_id: 3,
    tender_title: TITLE_3,
    target: "checked",
    status: "stopped",
    start_status: "new",
    end_status: "skipped",
    stages: [
      { stage: "scout", status: "ok", from_status: "new", to_status: "extracted", duration_ms: 41_300 },
      { stage: "matching", status: "branched", from_status: "extracted", to_status: "skipped", duration_ms: 40 },
      { stage: "compliance", status: "not_run", from_status: "matched" },
    ],
    created_at: new Date(BASE).toISOString(),
    started_at: new Date(BASE).toISOString(),
    finished_at: new Date(BASE + 41_340).toISOString(),
    duration_ms: 41_340,
  },
];

export async function listRuns(limit = 20): Promise<PipelineRunView[]> {
  await delay();
  return structuredClone(RUNS.slice(0, limit));
}

"""Pipeline orchestrator: the tender status state machine (spec section 10.3).

new -> extracted -> matched -> checked -> drafted -> reviewed -> approved
                                                 branches: skipped, blocked

TODO (next prompt): each transition writes an agent_runs row (stage, model,
input hash, output JSON, latency, ok - CLAUDE.md hard rule 9). Match score
below threshold -> skipped (Compliance does not run). Any hard compliance
failure -> blocked (Proposal does not run unless overridden).
"""
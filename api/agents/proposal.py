"""Proposal agent: tender + compliance report + retrieved KB chunks -> ProposalSection[].

TODO (next prompt): generate_section(...) per section (e.g. "relevant
experience", "technical approach"), retrieving top-k KB chunks per section
(spec section 10.4). Sections must cite KB chunk ids (CLAUDE.md hard rule
8). Low-moderate temperature, not 0 (hard rule 7).
"""
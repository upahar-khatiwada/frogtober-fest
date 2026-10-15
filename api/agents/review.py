"""Review agent: proposal + requirements -> ReviewReport.

TODO (next prompt): review_proposal(...) -> ReviewReport (scores, gaps,
verdict). A "fail" verdict feeds one optional revision pass back to
Proposal (spec section 10.3). Temperature 0 (CLAUDE.md hard rule 7).
"""
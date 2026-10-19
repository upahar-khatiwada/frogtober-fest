"""The web app's BS calendar table must match `nepal.dates` (it is an export, not a second source)."""

import json

from scripts import export_bs_calendar


def test_committed_export_matches_library():
    committed = json.loads(export_bs_calendar.OUT_PATH.read_text(encoding="utf-8"))
    assert committed == export_bs_calendar.build(), "run: uv run python -m api.scripts.export_bs_calendar"


def test_export_anchor_and_lengths():
    table = export_bs_calendar.build()
    assert table["years"]["2064"]["start_ad"] == "2007-04-14"  # 2064-05-03 = 2007-08-20 (NEPAL_CONTEXT section 7)
    for year in table["years"].values():
        assert len(year["months"]) == 12
        assert all(29 <= n <= 32 for n in year["months"])

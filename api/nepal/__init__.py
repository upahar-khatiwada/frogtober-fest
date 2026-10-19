"""Deterministic Nepal layer. No LLM calls in this package (CLAUDE.md hard rule 5)."""

from nepal.dates import (BSDate, DeadlineParse, NPT, ad_to_bs, bs_to_ad, current_fiscal_year, days_left, deadline_from_raw,
                         fiscal_year_bounds, fiscal_year_of, format_bs, parse_bs_date, parse_bs_datetime, parse_deadline)
from nepal.geography import Location, normalize_location
from nepal.numbers import format_npr, has_thousands_marker, humanize_npr, parse_days, parse_npr, parse_percent, to_ascii_digits
from nepal.rules import (DocumentMeta, TenderCriteria, calc_bid_security, calc_performance_security,
                         evaluate_rules, load_rules)
"""Unit tests for the audit regex patterns.

These tests exercise the personal-marker detection without touching Qdrant.
Run with: uv run pytest tests/concepts/test_audit_patterns.py
"""
from __future__ import annotations

import pytest

from scripts.concepts.patterns import PERSONAL_PATTERNS


# (marker_name, text_that_should_match, expected_min_hits)
SHOULD_MATCH = [
    ("Heather", "HEATHER lacks the requisite knowledge", 1),
    ("Heather", "the respondent (Heather Atagan) filed", 1),
    ("Joel", "Joel Thorarinson, Pro Se", 1),
    ("Joel", "JOEL has failed to demonstrate", 1),
    ("Atagan", "Heather Atagan", 1),
    ("Atagan", "ATAGAN'S RESPONSE", 1),
    ("Thorarinson", "Joel Thorarinson", 1),
    ("Tarara", "Fitzpatrick Tarara Family Law", 1),
    ("Tarara", "TARARA filed", 1),
    ("Eisler", "Eisler Capital terminated", 1),
    ("Jannusch", "before Judge Jannusch", 1),
    ("Conniff", "John A. Conniff appearance", 1),
    ("Hertz", "Hertz Corporation v.", 1),
    ("Uhlig", "v. Uhlig", 1),
    ("case_number_24D6724", "Case No. 2024D006724", 1),
    ("case_number_24D6724", "Case No. 2024 D 006724", 1),
    ("case_number_24D6724", "2024d6724", 1),
    ("Cook_County", "filed in Cook County DR", 1),
    ("specific_dollar_cents", "the arrearage of $97,379.00", 1),
    ("specific_dollar_cents", "bonus $305,454.86", 1),
    ("specific_dollar_cents", "monthly $21,463.56", 1),
]

# (marker_name, text_that_should_NOT_match)
SHOULD_NOT_MATCH = [
    ("Heather", "the respondent provided"),
    ("Joel", "the petitioner provided"),
    ("Atagan", "the respondent filed"),
    ("Thorarinson", "the moving party"),
    ("Tarara", "opposing counsel argued"),
    ("Eisler", "the prior employer terminated"),
    ("Jannusch", "before the trial judge"),
    ("Hertz", "the rental car carrier sued"),  # abstracted
    ("case_number_24D6724", "Case No. [#]"),
    ("Cook_County", "the trial court ordered"),
    # Whole word — should NOT match substrings
    ("Joel", "Joelle Vasquez argued"),
    ("Joel", "rejoel"),
    # Dollar amounts without cents are fine
    ("specific_dollar_cents", "the order required $20,000"),
    ("specific_dollar_cents", "fees of $50K"),
]


@pytest.mark.parametrize("marker,text,min_hits", SHOULD_MATCH)
def test_should_match(marker: str, text: str, min_hits: int) -> None:
    pat = PERSONAL_PATTERNS[marker]
    hits = pat.findall(text)
    assert len(hits) >= min_hits, f"{marker!r} failed to match in {text!r}; got {hits}"


@pytest.mark.parametrize("marker,text", SHOULD_NOT_MATCH)
def test_should_not_match(marker: str, text: str) -> None:
    pat = PERSONAL_PATTERNS[marker]
    hits = pat.findall(text)
    assert hits == [], f"{marker!r} false-positive on {text!r}: {hits}"


def test_pattern_coverage() -> None:
    """Sanity: every pattern has at least one positive-match test fixture."""
    covered = {m for m, _, _ in SHOULD_MATCH}
    missing = set(PERSONAL_PATTERNS.keys()) - covered
    assert not missing, f"Patterns lack positive-match test coverage: {missing}"

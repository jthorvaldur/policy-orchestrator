"""Unit tests for the substitution scrubber.

Run with: uv run pytest tests/concepts/test_scrub.py
"""
from __future__ import annotations

import pytest

from scripts.concepts.patterns import scrub_text


# (input_text, expected_substring_in_output, expected_substring_NOT_in_output)
TRANSFORMATIONS = [
    # Party names
    ("HEATHER lacks the requisite knowledge",
     "the respondent lacks the requisite knowledge", "HEATHER"),
    ("JOEL has failed to demonstrate",
     "the petitioner has failed to demonstrate", "JOEL"),
    ("Joel Thorarinson, Pro Se", "the petitioner, Pro Se", "Joel"),
    ("Heather Atagan filed", "the respondent filed", "Atagan"),
    ("Heather Kim Atagan", "the respondent", "Heather"),
    # Judicial actors
    ("Judge Matthew William Jannusch", "the trial judge", "Jannusch"),
    ("before Judge Jannusch", "before the trial judge", "Jannusch"),
    # Opposing counsel
    ("Annemarie Tarara argued", "opposing lead counsel argued", "Tarara"),
    ("Fitzpatrick Tarara Family Law, LLC",
     "opposing counsel's firm", "Tarara"),
    ("Cora Leeuwenburg sent", "opposing associate counsel sent", "Cora"),
    ("Lynnea Ellis emailed", "opposing paralegal emailed", "Lynnea"),
    ("John A. Conniff appeared", "prior counsel appeared", "Conniff"),
    # Employer
    ("Eisler Capital terminated", "the prior employer terminated", "Eisler"),
    # Case caption / number
    ("Case No. 2024D006724", "Case No. [Case No.]", "2024D006724"),
    ("Case No. 2024 D 006724", "Case No. [Case No.]", "2024D006724"),
    ("filed in Cook County DR", "filed in the trial court DR", "Cook County"),
    # Hertz consumer collection
    ("Hertz Corporation sued", "the rental car carrier sued", "Hertz"),
    ("v. Uhlig", "v. the defendant", "Uhlig"),
    # Dollar amounts get cents stripped
    ("the arrearage of $97,379.00", "$97,379.XX", "$97,379.00"),
    ("bonus $305,454.86", "$305,454.XX", "$305,454.86"),
    # Envelope ids
    ("Envelope 38226867 accepted", "Envelope [#] accepted", "38226867"),
    # Email addresses (the gap that bypassed name word-boundaries)
    ("contact joel.thorarinson@gmail.com today", "[petitioner-email]", "joel.thorarinson"),
    ("respondent heather.atagan@gmail.com refused", "[respondent-email]", "heather.atagan"),
    ("emailed atarara@ftfamilylawyers.com", "[opposing-counsel-email]", "ftfamilylawyers.com"),
]


@pytest.mark.parametrize("input_text,expected_present,expected_absent", TRANSFORMATIONS)
def test_scrub_transformation(input_text: str, expected_present: str, expected_absent: str) -> None:
    out, n = scrub_text(input_text)
    assert expected_present in out, f"\n  in:       {input_text!r}\n  expected: {expected_present!r}\n  got:      {out!r}"
    assert expected_absent.lower() not in out.lower(), (
        f"\n  in:       {input_text!r}\n  should not contain: {expected_absent!r}\n  got: {out!r}"
    )
    assert n > 0


def test_clean_text_unchanged() -> None:
    clean = "The petitioner moved to compel discovery from the respondent."
    out, n = scrub_text(clean)
    assert out == clean
    assert n == 0


def test_no_partial_word_match() -> None:
    # Whole-word boundaries should keep substrings safe
    text = "Joelle's project rejoels the queue at 50.00 percent."
    out, n = scrub_text(text)
    assert "Joelle" in out
    assert "rejoels" in out


def test_dollar_amount_preserves_magnitude() -> None:
    # We want the rough magnitude preserved (auditors can still tell $50 vs $500K)
    out, _ = scrub_text("payments of $1,234.56 and $9,876.54")
    assert "$1,234.XX" in out
    assert "$9,876.XX" in out


def test_idempotent() -> None:
    # Re-scrubbing already-clean text should not change it
    once, _ = scrub_text("HEATHER lacks knowledge of $100.00")
    twice, _ = scrub_text(once)
    assert once == twice

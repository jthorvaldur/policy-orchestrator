"""Tests that the auditor catches personal markers embedded in concept_id slugs.

Underscores and hyphens are word characters for regex `\b`, so a naive scan
of the slug would miss leaks like `judge_profile_jannusch`. The auditor
normalizes slugs (replaces _ and - with spaces) before matching.

Run with: uv run pytest tests/concepts/test_audit_slugs.py
"""
from __future__ import annotations

import pytest

from scripts.concepts.patterns import PERSONAL_PATTERNS


def _slug_has_marker(slug: str, marker_name: str) -> bool:
    normalized = slug.replace("_", " ").replace("-", " ")
    pat = PERSONAL_PATTERNS[marker_name]
    return bool(pat.findall(normalized))


@pytest.mark.parametrize("slug,marker", [
    ("judge_profile_jannusch", "Jannusch"),
    ("judge-profile-jannusch", "Jannusch"),
    ("petition_modify_heather", "Heather"),
    ("joel_response_template", "Joel"),
    ("atagan_admissions_pattern", "Atagan"),
    ("tarara_communications_track", "Tarara"),
    ("eisler_termination_chain", "Eisler"),
    ("conniff_handoff_pattern", "Conniff"),
    ("hertz_collection_defense", "Hertz"),
    ("uhlig_response_template", "Uhlig"),
    ("case_2024d6724_filing", "case_number_24D6724"),
])
def test_slug_should_flag(slug: str, marker: str) -> None:
    assert _slug_has_marker(slug, marker), \
        f"slug {slug!r} should flag marker {marker!r} after normalization"


@pytest.mark.parametrize("slug", [
    "judge_profile",
    "judicial_calibration",
    "petition_modify_support",
    "demand_performance",
    "liar_algorithm",
    "three_layer_algo",
    "motivational_levers_rice",
    "case_law_pattern",
    "case_id_assignment",       # 'case' alone is fine
    "default_judgment_mill_detection",
    "credibility_collapse",
])
def test_slug_should_not_flag(slug: str) -> None:
    for marker in PERSONAL_PATTERNS:
        assert not _slug_has_marker(slug, marker), \
            f"slug {slug!r} false-positive on marker {marker!r}"

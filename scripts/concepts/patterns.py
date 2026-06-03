"""Pure-Python regex tables shared by audit and scrub.

Kept dependency-free so tests can import without spinning up httpx/frontmatter.
"""
from __future__ import annotations

import re

# Personal-marker regex patterns. Compile once; share across all callers.
PERSONAL_PATTERNS: dict[str, re.Pattern] = {
    "Heather": re.compile(r"\bHeather\b", re.IGNORECASE),
    "Joel": re.compile(r"\bJoel\b", re.IGNORECASE),
    "Atagan": re.compile(r"\bAtagan\b", re.IGNORECASE),
    "Thorarinson": re.compile(r"\bThorarinson\b", re.IGNORECASE),
    "Tarara": re.compile(r"\bTarara\b", re.IGNORECASE),
    "Eisler": re.compile(r"\bEisler\b", re.IGNORECASE),
    "Jannusch": re.compile(r"\bJannusch\b", re.IGNORECASE),
    "Conniff": re.compile(r"\bConniff\b", re.IGNORECASE),
    "Hertz": re.compile(r"\bHertz\b", re.IGNORECASE),
    "Uhlig": re.compile(r"\bUhlig\b", re.IGNORECASE),
    # Match 2024D006724 in any spacing/zero-padded variant: 2024 D 006724, 2024D6724, 2024 D6724
    "case_number_24D6724": re.compile(r"2024\s?[Dd]\s?0{0,2}6724"),
    "Cook_County": re.compile(r"Cook County", re.IGNORECASE),
    "specific_dollar_cents": re.compile(r"\$[\d,]+\.\d{2}"),
}

# Word-boundary substitutions (order matters — longer phrases first).
SUBS: list[tuple[re.Pattern, str]] = [
    # Email addresses — must precede any name-token substitution so we don't leave
    # `joel.the petitioner@example.com` fragments behind.
    (re.compile(r"\b[A-Za-z0-9._%+-]*joel\.thorarinson[A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.IGNORECASE),
     "[petitioner-email]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]*heather\.atagan[A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.IGNORECASE),
     "[respondent-email]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@ftfamilylawyers\.com\b", re.IGNORECASE), "[opposing-counsel-email]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@jacfamilylaw\.com\b", re.IGNORECASE), "[prior-counsel-email]"),
    # Case caption / number
    (re.compile(r"\b2024\s?[Dd]\s?00?6724\b"), "[Case No.]"),
    (re.compile(r"\bIRMO\s+Thorarinson\s*[/v.]\s*Atagan[;,]?\s*"), ""),
    (re.compile(r"\bIn re Marriage of[^.\n]{0,80}\bAtagan\b[^.\n]{0,40}", re.IGNORECASE), "In re the matter"),
    # County / venue
    (re.compile(r"Cook County Domestic Relations Division", re.IGNORECASE), "the trial court"),
    (re.compile(r"Cook County Circuit Court", re.IGNORECASE), "the trial court"),
    (re.compile(r"\bCook County\b", re.IGNORECASE), "the trial court"),
    # Judicial actors
    (re.compile(r"\bJudge\s+Matthew\s+William\s+Jannusch\b", re.IGNORECASE), "the trial judge"),
    (re.compile(r"\bJudge\s+Jannusch\b", re.IGNORECASE), "the trial judge"),
    (re.compile(r"\bJannusch\b", re.IGNORECASE), "the trial judge"),
    # Opposing counsel
    (re.compile(r"\bFitzpatrick\s+Tarara\s+Family\s+Law(\s*,?\s*LLC)?\b", re.IGNORECASE), "opposing counsel's firm"),
    (re.compile(r"\bAnnemarie\s+Tarara\b", re.IGNORECASE), "opposing lead counsel"),
    (re.compile(r"\bAnne\s+Marie\s+Tarara\b", re.IGNORECASE), "opposing lead counsel"),
    (re.compile(r"\bTarara\b"), "opposing lead counsel"),
    (re.compile(r"\bCora\s+Leeuwenburg\b", re.IGNORECASE), "opposing associate counsel"),
    (re.compile(r"\bLynnea\s+Ellis\b", re.IGNORECASE), "opposing paralegal"),
    (re.compile(r"\bLinda\s+Ellis\b", re.IGNORECASE), "opposing paralegal"),
    (re.compile(r"\bJohn\s+A\.?\s+Conniff\b", re.IGNORECASE), "prior counsel"),
    (re.compile(r"\bConniff\b"), "prior counsel"),
    # Employer
    (re.compile(r"\bEisler\s+Capital(\s+\(US\)\s+LP)?\b", re.IGNORECASE), "the prior employer"),
    (re.compile(r"\bEisler\b"), "the prior employer"),
    # Party names. Order: full → first
    (re.compile(r"\bJoel\s+Thorarinson\b"), "the petitioner"),
    (re.compile(r"\bHeather\s+Kim\s+Atagan\b", re.IGNORECASE), "the respondent"),
    (re.compile(r"\bHeather\s+Atagan\b", re.IGNORECASE), "the respondent"),
    (re.compile(r"\bHEATHER\b"), "the respondent"),
    (re.compile(r"\bJOEL\b"), "the petitioner"),
    (re.compile(r"\bHeather\b", re.IGNORECASE), "the respondent"),
    (re.compile(r"\bJoel\b"), "the petitioner"),
    (re.compile(r"\bAtagan\b", re.IGNORECASE), "the respondent"),
    (re.compile(r"\bThorarinson\b", re.IGNORECASE), "the petitioner"),
    # Hertz-specific
    (re.compile(r"\bHertz\s+Corporation\b"), "the rental car carrier"),
    (re.compile(r"\bHertz\s+v\.\s+Uhlig\b"), "the rental car suit"),
    (re.compile(r"\bv\.\s+Hertz\b"), "v. the rental car carrier"),
    (re.compile(r"\bHertz\b"), "the rental car carrier"),
    (re.compile(r"\bUhlig\b"), "the defendant"),
    # Dollar amounts with cents → placeholder
    (re.compile(r"\$([\d,]+)\.\d{2}"), r"$\1.XX"),
    # eFileIL envelope ids → placeholder
    (re.compile(r"\bEnvelope\s+\d{6,9}\b", re.IGNORECASE), "Envelope [#]"),
]


def scrub_text(text: str) -> tuple[str, int]:
    """Apply substitutions. Returns (scrubbed_text, total_replacements). Pure."""
    out = text
    total = 0
    for pat, repl in SUBS:
        out, n = pat.subn(repl, out)
        total += n
    return out, total

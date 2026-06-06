# ADR 0016: Quantitative Results Must Be Code-Generated (Reproducible)

## Status
Accepted

## Date
2026-06-06

## Context
A multi-session effort on the "Orwell Index" document-doublespeak scorer was derailed by a reproducibility failure that cost hours and produced misleading conclusions.

The original v1 visualization (`jthorvaldur.github.io/orwell/index.html`) showed a clean separation — our filings ≈0.04, opposing counsel ≈0.65–0.85. These numbers were treated as measured data and reasoned about as evidence. Git forensics showed otherwise:

- The first commit added only `index.html`, with the scores already hard-coded inline. The scorer (`orwell_score.py`) was added **two commits later**.
- The numbers matched a hand-authored **"Sample Scores"** table in `caseledger/docs/orwell_index_spec.md`, which the spec itself listed as a TODO ("engineering team: build the 7-axis scorer"). They were *target estimates*, never computed.
- When the real scorer was run on the actual documents, it produced ~0.18–0.22 for both sides (separation +0.04, not the implied 0.66). The dramatic plot was never reproducible because no algorithm ever generated it.

Root contributing factors:
1. A numeric result was authored by hand and presented as if measured.
2. Input preparation (PDF→text) was done ad-hoc at runtime (`pdftotext`) instead of as a committed pipeline step; converted md artifacts were assumed to exist but did not (`div_legal/data/incoming/defence_docs_md` was empty).

## Decision
**Any quantitative output — score, metric, ranking, statistic, weighted index, plot data — must be produced by committed code that regenerates the exact values on demand.**

1. **Math is code.** Never hand-enter, estimate, or "reason out" a number and present it as computed. If there is no script that reproduces a value, the value is an *estimate* and must be labeled as such — never plotted or tabulated as data.
2. **Ship the generator with the result.** A results artifact (`*.json`, dashboard, plot) must be accompanied by the script that produced it (e.g. `replicate_experiment.py` → `experiment_scores.json`). Re-running the script with the same inputs must reproduce the artifact.
3. **Input prep is part of the pipeline.** Format conversion (PDF→md, OCR, extraction) is a committed, re-runnable step. Prefer already-converted artifacts; do not bury one-off extraction inside a scoring script.
4. **Semantic vs. mathematical.** Qualitative/semantic reasoning (themes, interpretations, taxonomy labels, narrative) may remain in prose. Quantitative/mathematical claims may not.
5. **Specs are not data.** Worked examples and target values in a spec are estimates until an implementation reproduces them. Do not promote spec illustrations to measured results.

## Consequences
- Agents must write the algorithm before reporting its output; when blocked from doing so, they state the number is an estimate.
- Dashboards/visualizations in managed repos should load from a generated data file whose generator is in-repo, not from inline hard-coded arrays.
- Reverse-engineering a scorer to hit a previously-authored target (e.g. tuning toward 0.04/0.70) is prohibited; recalibrate to a principled definition and report whatever it yields.
- Consider a soft policy / lint check: flag visualization pages containing large inline numeric arrays with no corresponding generator script.

## References
- `jthorvaldur.github.io/orwell/replicate_experiment.py` — the reproducible experiment built in response to this incident.
- `caseledger/docs/orwell_index_spec.md` — the spec whose sample table was mistaken for data.
- Related principle in agent memory: `implement-math-as-replicable-code`.

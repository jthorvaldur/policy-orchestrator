# Evals — repeated failures, made executable

Every recurring failure gets an eval (processes/05-improvement-loop.md).
An eval is a script that **fails while the problem exists** and passes when
it is fixed. `scripts/test.sh` runs all of them; the delivery-gate hook
requires that run before any session claims "done."

## Format

- Name: `eNNN-<slug>.sh`, numbered in order of creation.
- Contract: exit 0 = pass, non-zero = fail; print one line of evidence.
- Each eval header records: date, the failure it encodes, root cause, and
  the system patch it verifies (the memory line, in-file).

## Adding one

1. Copy `e000-template.sh`.
2. Make it fail against the old (broken) behavior — verify this.
3. Apply the system patch; make it pass.
4. Add the one-line entry to the memory log and, cross-repo,
   `devctl log-feedback`.

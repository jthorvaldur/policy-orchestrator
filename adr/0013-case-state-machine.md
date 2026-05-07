---
title: Case State Machine — Cross-Repo Architecture
status: accepted
date: 2026-05-06
context: caseledger + div_legal integration
---

# ADR 0013: Case State Machine

## Context

div_legal (test case) proved that a vector-DB-backed legal document pipeline can:
- Auto-detect contradictions across filings (caught x2973 typo, $20 arithmetic gap, 7-position contradiction chain on one account)
- Generate per-audience projections (judge gets R^1 paper, counsel gets billing math, ARDC gets pattern evidence)
- Detect convergence conditions for settlement via game theory payoff analysis
- Produce court-ready output (auto-signed, auto-dated PDFs, printed binders)

## Decision

Formalize the case state machine as a CaseLedger product feature. Specification at `caseledger/docs/case_state_machine.md`.

Key components:
1. **Player model** — payoff functions, comprehension bases, belief states
2. **Contradiction detector** — scans Qdrant corpus, cross-references sworn documents
3. **Projection operators** — maps R^n case knowledge to R^k audience output (4 saturation levels)
4. **Convergence detector** — signals when settlement is Nash equilibrium
5. **Binder generator** — R^n → R^1 printed tabbed binder for court

## Data Flow

```
div_legal (raw data) → Qdrant (vectors) → CaseLedger (state machine) → Outputs
                                                                       ├── Binder (judge)
                                                                       ├── Emails (counsel)
                                                                       ├── ARDC complaints
                                                                       └── Game theory analysis
```

## Consequences

- CaseLedger gains a formal state machine architecture grounded in real case data
- div_legal remains the test case and data source
- The projection operator pattern is generalizable to any multi-party legal proceeding
- The saturation gradient (Level 0-3) from legal_math.md is integrated into the output pipeline

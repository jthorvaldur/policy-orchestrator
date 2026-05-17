# Analysis Engine (CaseLedger)

The adversarial analysis layer. Takes ingested facts + documents and finds weaknesses in opposing positions.

**Repo:** `caseledger/pipeline/analysis/`
**API:** FastAPI on :8000, routes in `caseledger/api/routes/`

## Contradiction Detector

**File:** `pipeline/analysis/contradiction_detector.py`

Finds statements that conflict with each other across the entire corpus.

**Algorithm:**
1. For each new fact, embed and search for semantically similar facts
2. Filter candidates by: same topic, different party, overlapping date range
3. Pass pairs to LLM with contradiction-detection prompt
4. If contradiction confirmed → create `fact_links` entry (type: "contradicts")
5. Downgrade confidence of weaker fact, create `fact_versions` audit entry

**LLM Prompts:**
- `CONTRADICTION_SYSTEM_PROMPT`: "Given two statements from a legal case, determine if they contradict..."
- `CORROBORATION_SYSTEM_PROMPT`: "Given two statements, determine if they independently confirm..."

**Output:** List of contradictions with severity, evidence notes, affected facts

**API:** `GET /api/{case_id}/facts/disputed`

## Cycle Detector (Adversarial Loop Detection)

**File:** `pipeline/analysis/cycle_detector.py`

Finds self-defeating obligation loops — where compliance with one court order makes compliance with another impossible.

**Algorithm:**
1. Build obligation subgraph from `graph_nodes` (type: obligation, deadline, payment)
2. Extract directed edges: `requires`, `blocks`, `violates`
3. Run cycle detection (Johnson's algorithm for elementary circuits)
4. Compute Betti number (β₁ = first homology group dimension = number of independent cycles)
5. For each cycle, calculate severity (days active, parties trapped)
6. Find circuit breakers: minimum-cost edges to cut to break each cycle

**Example Cycle:**
```
"Comply with disclosure order" → requires → "Access to financial records"
    ↑                                              ↓
    └── "Records held by opposing party" ← blocks ← "Contempt motion filed"
```

**Output:**
```json
{
  "betti_number": 3,
  "cycles": [
    {
      "nodes": ["O-001", "O-003", "O-007"],
      "severity": "critical",
      "days_active": 240,
      "description": "contempt-nondisclosure spiral",
      "circuit_breakers": [
        {"edge": "O-003→O-007", "label": "blocks", "cost": 0.8}
      ]
    }
  ]
}
```

**API:** `GET /api/{case_id}/cycles`

## Chain Engine (Logical Proof Construction)

**File:** `pipeline/analysis/chain_engine.py`

Builds court-admissible logical chains: assertion → evidence → legal rule → conclusion.

**Two Modes:**

1. **`from_facts(fact_ids, rules)`** — Build chain from specific facts + legal rules
2. **`for_standard(legal_standard)`** — Build chain around multi-prong legal tests

**Confidence Scoring:**
```
chain_confidence = ∏(link_weights)
adjusted = chain_confidence × (1 - evidence_correlation)
```
- Evidence correlation via Jaccard similarity of source documents
- Independent sources strengthen; same-source weakens

**Link Status Mapping:**
| Fact Status | Chain Link Weight |
|-------------|------------------|
| corroborated | 0.95 (verified) |
| asserted | 0.70 (inferred) |
| disputed | 0.30 (disputed) |

**Validation:** Checks for gaps (missing links) and unsupported assertions

**Output:**
```json
{
  "chain": [
    {"type": "assertion", "fact_id": "F001", "statement": "...", "confidence": 0.95},
    {"type": "evidence", "doc_id": "d7a2b3", "source": "Bank statement", "date": "2024-03-15"},
    {"type": "rule", "statute": "750 ILCS 5/503(d)", "text": "..."},
    {"type": "conclusion", "statement": "Dissipation proven", "confidence": 0.87}
  ],
  "overall_confidence": 0.87,
  "gaps": []
}
```

**API:** `POST /api/{case_id}/chain`

## Consistency Metrics (Game Theory)

**File:** `pipeline/analysis/consistency_metrics.py`

Tracks cumulative inconsistency per party over time. Uses information theory to quantify how much a party's story shifts.

**Metrics:**

1. **KL Divergence** between claim distributions at time t vs t+1:
   ```
   D_KL(P||Q) = log(σ_Q/σ_P) + (σ_P² + (μ_P - μ_Q)²)/(2σ_Q²) - 0.5
   ```

2. **Cumulative Inconsistency Score** I(party, t):
   - Accumulates each detected shift in position
   - Higher = more contradictory history
   - Renders as timeline graph

3. **Response Information Deficit** R(response, motion):
   - What portion of a motion's claims does the response address?
   - Unaddressed claims = implicit admissions (under Illinois law)
   - Score: 0.0 (fully addressed) to 1.0 (completely ignored)

4. **Disclosure Completeness**:
   - Weighted by category importance (financial > property > lifestyle)
   - Tracks what's been disclosed vs what's required
   - Gaps = potential sanctions

**Output:** Timeline of cumulative scores + per-event breakdown

**API:** `GET /api/{case_id}/consistency/{party}`

## Compliance Audit

**File:** `pipeline/analysis/compliance_audit.py`

Checks whether parties have met court-ordered obligations.

**Two Search Strategies:**
1. **Graph-only (fast):** Metadata search on fact/document nodes
2. **Qdrant-backed (thorough):** Semantic search over 1.7M chunks

**Illinois Family Law Checklist:**
- Grounds for dissolution
- Parental responsibilities allocation
- Parenting time schedule
- Child support calculation
- Maintenance (alimony)
- Property division (equitable distribution)
- Financial disclosure (Rule 13.3.1)

**Output:**
```json
{
  "items": [
    {"category": "disclosure", "requirement": "Rule 13.3.1 Financial Affidavit",
     "statute": "Ill. S.Ct. Rule 13.3.1", "status": "missing",
     "evidence": null, "due_date": "2025-01-15"}
  ],
  "score": {"met": 12, "missing": 5, "partial": 3, "unknown": 2}
}
```

**API:** `GET /api/{case_id}/audit?deep=true`

## Financial Reconciliation

**File:** `pipeline/analysis/financial_recon.py`

Detects gaps between claimed payments and acknowledged receipts.

**Tracks:**
- Categories: child_support, maintenance, medical, education, housing, insurance, attorney_fees, debt
- Methods: check, wire, cash, money_order, venmo, garnishment
- Per-period: total_claimed vs total_credited vs gap

**Output:** Gap analysis with progression over time, flagging where claimed ≠ credited

## Deadline Tracker

**File:** `pipeline/analysis/deadline_tracker.py`

Extracts obligations from ORDER nodes and tracks compliance.

**Priority Levels:**
- 1 (urgent): due within 7 days
- 2 (soon): due within 30 days  
- 3 (eventual): due later

**Status:** pending, complied, past_due, unknown

## Case Hypergraph

**File:** `pipeline/analysis/case_graph.py`

Full case knowledge graph with typed nodes and edges.

**Node Types:** FILING, ORDER, COMMUNICATION, FACT, OBLIGATION, DEADLINE, EVIDENCE, PARTY
**Edge Types:** CITES, CONTRADICTS, MODIFIES, BLOCKS, REQUIRES, RESPONDS_TO, CREATED_BY

**Subgraph views:**
- `obligation_subgraph()` — for cycle detection
- `filing_subgraph()` — chronological case history

**Persisted in:** PostgreSQL `graph_nodes` + `graph_edges` tables

**API:** `GET /api/{case_id}/graph`, `GET /api/{case_id}/graph/obligations`

## Projections (Audience-Specific Views)

**File:** `pipeline/analysis/projections.py`

Same facts, different framing:

| Audience | Style | Includes | Suppresses |
|----------|-------|----------|-----------|
| Judge | Clinical, deferential, brief | Key facts, law, relief | Strategy, speculation |
| Self | Action items, checklists | Everything, deadlines | Nothing |
| Opponent | Evidence-focused | Strong facts only | Weak points |
| Attorney | Comprehensive | Chains + strategy + risks | Nothing |

**Output:** HTML via WeasyPrint → court-ready PDF

## Rules Database

**File:** `pipeline/rules/illinois_family.yaml`

100+ rules covering:
- Statutes: 750 ILCS 5/§§, 735 ILCS 5/§§
- Case law: Sharp v. Sharp, In re Marriage of...
- Supreme Court Rules: 213, 214, 219, 201
- Topics: verification, perjury, financial_disclosure, dissipation, contempt, discovery

Used by Chain Engine to connect facts to legal authority.

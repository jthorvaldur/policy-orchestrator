# Fact Treatment — The 6-Layer Context Model

Inspired by [OpenAI's in-house data agent](https://openai.com/index/inside-our-in-house-data-agent/) architecture. Their agent serves 3,500 users across 600PB and 70K datasets. The core insight: **context is everything** — without rich, accurate context, even strong models produce wrong results.

We adapt their 6-layer grounding model from data analytics to adversarial legal intelligence.

## The 6 Layers (OpenAI → Our Equivalent)

```
┌─────────────────────────────────────────────────┐
│  6  RUNTIME CONTEXT                              │  Live queries when embedded context is stale
├─────────────────────────────────────────────────┤
│  5  MEMORY                                       │  Corrections from prior analysis, saved learnings
├─────────────────────────────────────────────────┤
│  4  INSTITUTIONAL KNOWLEDGE                      │  Emails, chats, court filings, financial records
├─────────────────────────────────────────────────┤
│  3  CODE ENRICHMENT                              │  Pipeline logic → semantic metadata (offline daily)
├─────────────────────────────────────────────────┤
│  2  HUMAN ANNOTATIONS                            │  Expert descriptions, rules DB, CLAUDE.md, INTENT.md
├─────────────────────────────────────────────────┤
│  1  SOURCE METADATA                              │  Schema, lineage, provenance chains
└─────────────────────────────────────────────────┘
```

### Layer 1: Source Metadata (We have this)
- Collection schemas in `vector-collections.yaml`
- Payload fields (doc_id, source_path, source_type, date, confidence)
- File provenance in SQLite (`provenance.db`: content hashes, lineage chains)
- TimescaleDB `file_registry` (content-addressed, cross-repo)

### Layer 2: Human Annotations (We have this)
- `CLAUDE.md` and `INTENT.md` per repo — governing rules and context
- `pipeline/rules/illinois_family.yaml` — 100+ statutes and case law rules
- Curated fact descriptions in `fact_sources` with `extraction_method: manual`
- Domain expert annotations on key collections

### Layer 3: Code Enrichment (We partially have this)
OpenAI runs a **daily offline pipeline** where Codex inspects pipeline code to extract:
- Table purpose, exact grain, primary keys
- Downstream usage patterns
- When to use alternate tables
- Freshness/refresh cadence

**Our equivalent:** We embed documents and extract facts via Ollama. But we DON'T:
- Re-analyze existing facts against newly ingested evidence (daily enrichment)
- Extract semantic relationships between facts automatically
- Score fact utility based on downstream usage (which facts appear in successful chains?)
- Track fact freshness (how old is the underlying evidence?)

**Gap to close:** Add a daily enrichment pipeline that:
1. Checks new documents against existing facts for contradictions
2. Re-scores fact confidence based on new corroborating evidence
3. Extracts new relationships between facts (graph edges)
4. Marks stale facts (source document updated but fact not re-extracted)

### Layer 4: Institutional Knowledge (Our strongest layer)
- 380K legal document vectors (emails, PDFs, filings, bank statements)
- 19K WhatsApp + Signal messages
- 96K Claude Code session vectors (anonymized re-injection)
- 5.5K ChatGPT conversation vectors
- 2K Claude.ai conversation vectors
- **Total: 2M+ vectors of institutional knowledge**

OpenAI mines Slack, Google Docs, and Notion. We mine Gmail, WhatsApp, Signal, iMessage, court filings, and financial records. Our institutional layer is deeper than theirs — we have adversary communications.

### Layer 5: Memory (Our critical gap — 3 entries)

OpenAI: *"The goal of memory is to retain and reuse non-obvious corrections, filters, and constraints that are critical for data correctness but difficult to infer from other layers alone."*

Their memory system:
- When given a correction or discovering a nuance, **prompts to save as memory**
- Future answers start from a more accurate baseline
- Memories scoped at global and personal level
- Example: agent learned that filtering for a specific analytics experiment required matching against a specific string in an experiment gate, not fuzzy matching

**Our `feedback_events` collection has 3 entries.** This should have hundreds.

**What to store in memory:**
- Fact corrections ("F001 was wrong because the date was in a different timezone")
- Search refinements ("When searching for Conniff, also check for 'John A. Conniff' and 'J. Conniff'")
- Chain failures ("Chain linking F003 to Rule 503(d) failed because the rule requires a 'knowing' standard")
- Confidence overrides ("Bank of America statements from before 2024-06 use a different format")
- Jurisdiction quirks ("Illinois Rule 219 sanctions require a motion — self-executing sanctions don't exist")

**Auto-populate from:**
- Every contradiction detected → memory: "F_X contradicts F_Y because..."
- Every superseded fact → memory: "F_X was wrong, replaced by F_Z"
- Every failed chain evaluation → memory: "This chain broke because..."
- Every user correction during analysis → memory: "User said X, system had Y"

### Layer 6: Runtime Context (We partially have this)
OpenAI: When embedded context is stale, the agent issues **live queries** to the data warehouse to inspect and query directly.

**Our equivalent:** `devctl search` queries Qdrant live. CaseLedger API queries PostgreSQL live.

**What's missing:** The agent should detect when its embedded context might be stale and automatically fall back to live queries. Currently there's no staleness detection.

## The Overconfidence Problem

OpenAI's biggest behavioral challenge: *"The agent tends to quickly pick a table it believes is correct and proceed with analysis, even when that table is not the right choice."*

**Their fix:** Prompts that explicitly instruct the model to **stay in a discovery phase longer** — gathering alternatives, comparing possible tables, validating before committing.

**Our equivalent problem:** The chain engine grabs the first matching fact and builds. No discovery phase, no comparison, no validation.

**Our fix — Fact Discovery Protocol:**

```
STEP 1: DISCOVER (don't commit yet)
  Search for candidate facts (current: done)
  Search for CONTRADICTING facts (new: actively seek counter-evidence)
  Search for CORROBORATING facts (new: find independent confirmations)
  Result: candidate pool with confidence scores

STEP 2: COMPARE
  Rank candidates by: confidence_rank × source_diversity × recency
  Flag any candidates with active CONTRADICTS links
  Flag any candidates that have been superseded
  Result: ranked shortlist with warnings

STEP 3: VALIDATE
  Check each candidate against ground truth facts (is_ground_truth=true)
  Verify provenance chain (source_document → extraction → fact)
  Apply confidence threshold for output type:
    court_filing: ≥ documented (rank 4)
    internal_analysis: ≥ asserted (rank 3)
    exploratory: ≥ inferred (rank 2)
  Result: validated facts ready for chain building

STEP 4: COMMIT
  Build chain with validated facts
  Include: alternatives considered, counter-evidence found, provenance
```

## The Eval Loop

OpenAI's evaluation pipeline:

```
Q&A Eval Pairs → Generation → OpenAI Evals Grading → Score + Reasoning
                    ↓                    ↓
              Generated SQL        Dataframe result comparison
              SQL Results          SQL comparison
                                   LLM grader (not string matching)
```

*"These evals are like unit tests that run continuously during development to identify regressions as canaries in production."*

**Our equivalent — Fact Chain Evaluation:**

```
Chain Eval Pairs → Generation → Chain Grading → Score + Reasoning
                      ↓                ↓
                Built chain       Confidence scoring (product formula)
                Evidence used     Counter-argument generation
                                  Gap detection (missing links)
                                  LLM grader: "Would a judge accept this?"
```

**The eval→regen cycle (Joel's loop):**

```
GENERATE → EVALUATE → SEARCH → REGENERATE → RE-EVALUATE
    ↑                                              |
    └─── if improved, accept; if not, flag ────────┘
```

1. **Generate:** Build chain from facts + rules
2. **Evaluate:** Score confidence, find gaps, generate counter-arguments
3. **Search:** For each gap, search for additional evidence to fill it
4. **Regenerate:** Rebuild chain with new evidence
5. **Re-evaluate:** Is the new chain stronger? If yes, accept. If no, flag for human review.
6. **Learn:** Log the entire eval cycle to memory (Layer 5)

Each cycle through this loop produces a stronger chain. The counter-argument generation is the adversarial piece — the system attacks its own work before the opponent can.

## Three Lessons Applied

### Lesson 1: Less is More
OpenAI: *"We exposed our full tool set and quickly ran into problems with overlapping functionality."*

**Our action:** Consolidate overlapping search tools. `search_unified.py`, `search_sessions.py`, and the CaseLedger `/search` endpoint all do similar things. Unify into one entry point with collection filtering.

### Lesson 2: Guide the Goal, Not the Path
OpenAI: *"Highly prescriptive prompting degraded results... By shifting to higher-level guidance and relying on GPT-5's reasoning to choose the appropriate execution path, the agent became more robust."*

**Our action:** The fact extraction prompts in `fact_extractor.py` are highly prescriptive. Loosen them — give the LLM the goal ("extract verifiable facts with dates, amounts, and parties") and let it reason about how.

### Lesson 3: Meaning Lives in Code
OpenAI: *"Pipeline logic captures assumptions, freshness guarantees, and business intent that never surface in SQL or metadata."*

**Our action:** Our extraction pipelines encode domain knowledge (e.g., "Conniff" = attorney, "750 ILCS" = Illinois family law). This knowledge is implicit in code but not searchable. Extract it into the concepts collection so future analysis can reference it.

## Confidence-Weighted Retrieval

Currently all facts get equal retrieval weight. Adapt to:

| Output Type | Min Confidence | Boost Factor | Example |
|-------------|---------------|-------------|---------|
| Court filing | documented (4) | 2.0x for verified | Motion for sanctions |
| Legal memo | asserted (3) | 1.5x for documented | Strategy document |
| Internal analysis | inferred (2) | 1.0x (no boost) | Exploratory search |
| Brainstorming | any (1+) | 0.5x disputed penalty | "What if" scenarios |

When building chains for court filings, the system should refuse to use `asserted` facts without flagging: *"This chain relies on an email claim (asserted) at link 3. A court filing should use documented or verified evidence. Search for corroboration?"*

## Daily Enrichment Pipeline (New LaunchAgent)

```
Schedule: Daily at 4:00 AM (after Qdrant backup at 3:00 AM)

1. SCAN: Find all documents ingested since last enrichment run
2. MATCH: For each new document, search fact_registry for semantically similar facts
3. CONTRADICT: Run contradiction detection on matches
4. CORROBORATE: Check if new document independently confirms existing facts
5. UPDATE: Upgrade/downgrade confidence levels based on findings
6. LINK: Create new fact_links edges (contradicts, corroborates)
7. LEARN: Log all changes to feedback_events (memory layer)
8. REPORT: Generate enrichment summary (N facts updated, M contradictions found)
```

This is the "Codex enrichment" equivalent — an offline daily job that makes the knowledge base smarter without any user action.

## Implementation Priority

1. **Memory layer** — Start actively logging to `feedback_events`. Auto-log from contradictions, supersessions, failed chains. Highest impact, lowest effort.
2. **Fact discovery protocol** — Add the compare/validate steps before chain building. Prevents overconfidence.
3. **Eval→regen loop** — The self-evaluation + regeneration cycle. This is the core differentiator.
4. **Daily enrichment pipeline** — Offline job that re-analyzes facts. Compounds over time.
5. **Confidence-weighted retrieval** — Boost/penalize based on confidence. Prevents weak facts from polluting chains.
6. **Runtime staleness detection** — Detect when embedded context is outdated, fall back to live queries.

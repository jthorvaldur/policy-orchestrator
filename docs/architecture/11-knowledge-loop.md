# Knowledge Loop (Re-injection)

The system doesn't just analyze — it learns. Every cycle through the Daylight loop adds to the knowledge base, making future cycles more effective.

## The Compounding Mechanism

```
Cycle N: Search finds 3 contradictions in financial disclosures
         → Log as facts → Embed into fact_registry → Concepts extracted

Cycle N+1: New email arrives discussing same accounts
            → Search now hits the contradictions from Cycle N
            → Chain engine links new email to existing contradictions
            → Stronger attack vector (more evidence, higher confidence)

Cycle N+2: Court filing references the same accounts
            → System already knows the contradiction history
            → Automatically generates "inconsistent with prior statement" filing
```

## Knowledge Collections

### fact_registry (Qdrant, 167+ vectors)
**What:** Classified facts with confidence levels and provenance
**When logged:** Any time a verifiable claim is identified
**Who writes:** `devctl log-fact`, contradiction detector, financial recon

```bash
devctl log-fact \
  --fact "Respondent claimed $0 in account XYZ on 2024-12-01" \
  --source-type legal_filing \
  --confidence documented \
  --domain financial \
  --source-ref "Financial Affidavit, filed 2024-12-01"
```

**Schema:** fact, source_type, confidence, confidence_rank, domain, source_ref, source_date, claimed_by, contradicts, repo, notes

### concepts (Qdrant, 444 vectors)
**What:** Strategic concepts, patterns, and learnings extracted from analysis
**When logged:** After analysis reveals a reusable pattern
**Purpose:** Institutional memory — the system recognizes patterns it's seen before

Examples:
- "When opposing party delays disclosure, file Rule 219 motion within 21 days"
- "Financial transfers between related entities often indicate dissipation"
- "Body attachment paradox: court orders compliance but prevents compliance"

### directives (Qdrant, 270 vectors)
**What:** System-level rules and strategic priorities
**Purpose:** Guide future analysis toward known attack surfaces

### feedback_events (Qdrant, 3+ vectors)
**What:** Agent calibration — what worked, what didn't
**When logged:** User corrects or confirms agent behavior

```bash
devctl log-feedback \
  --type correction \
  --signal "Don't cite case_facts without checking confidence" \
  --rule "Always verify confidence ≥ documented before citing in filings"
```

## Chat Re-injection (Anonymized)

All Claude Code sessions are ingested back into the system:

```
Session (conversation) → ingest_sessions.py → chunk → embed → claude_code_sessions (96K vectors)
```

**Why this matters:**
- Strategic discussions become searchable context
- "What did we decide about X?" → instant retrieval
- Analysis from one session informs all future sessions
- Anonymized: no user identifiers in the vector payload, just content

**Schedule:** Every 6 hours (LaunchAgent)

## The Learning Hierarchy

```
Level 1: Raw Data (emails, filings, statements)
    → Ingested, embedded, searchable
    → Never modified

Level 2: Extracted Facts (fact_registry, case_facts)
    → Structured, confidence-ranked, versioned
    → Can be superseded but never deleted

Level 3: Concepts (concepts, directives)
    → Patterns extracted from analysis
    → Guide future searches and analysis
    → The system's "intuition"

Level 4: Feedback (feedback_events)
    → Meta-knowledge about how to operate
    → Calibrates agent behavior across sessions
```

## How It Scales (AWS)

### Continuous Ingestion
```
S3 bucket (incoming/) → EventBridge rule → Step Function
├── Extract Lambda (PDF/email/image → markdown)
├── Embed Lambda (markdown → vectors via SageMaker endpoint)
├── Fact Extract Lambda (markdown → structured facts via Bedrock)
├── Contradiction Check Lambda (new facts vs existing)
└── Concept Extract Lambda (patterns → concepts collection)
```

### Scheduled Analysis
```
EventBridge (daily) → Step Function
├── Cycle Detection Lambda (find new obligation loops)
├── Consistency Update Lambda (recalculate scores)
├── Disclosure Gap Lambda (check new filings for completeness)
└── Report Generation Lambda (update timelines, dashboards)
```

### Real-Time Alerts
```
New email arrives → SES → Lambda
├── Extract + classify (is this legally significant?)
├── If yes → full pipeline (embed, fact extract, contradiction check)
├── If contradiction found → SNS alert to user
└── If deadline detected → EventBridge scheduled reminder
```

## What Makes This Adversarial

Traditional legal research: search a database, find relevant cases, manually argue.

This system:
1. **Continuous surveillance** — Every email, text, filing is ingested and cross-referenced
2. **Automatic contradiction detection** — No manual review needed to find inconsistencies
3. **Cycle exploitation** — Finds logical paradoxes the opposing side created and can't escape
4. **Cumulative scoring** — Tracks how often their story changes (KL divergence over time)
5. **Information asymmetry** — We know what they said in every channel; they don't know we know
6. **Self-reinforcing** — Each discovery makes the next discovery easier to find

The "DOS attack" metaphor: flood the legal system with precisely-targeted, evidence-backed motions at a rate no opposing counsel can manually respond to. Every response they generate becomes new data for the next cycle.

## Growth Metrics

| Metric | Current | Growth Rate |
|--------|---------|-------------|
| Total vectors | 2M+ | ~10K/week (organic) |
| Facts logged | 167+ | ~5/analysis session |
| Concepts | 444 | ~2/week (manual + auto) |
| Sessions indexed | 1,793 | ~50/week |
| Contradictions found | per-analysis | compounds with corpus size |

The corpus grows linearly. The attack surface it finds grows combinatorially (each new fact can contradict any existing fact).

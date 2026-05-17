# ADR 0015: Knowledge Graph & Tiered Query Architecture

**Status:** Proposed
**Date:** 2026-05-17
**Context:** OpenAI 6-layer gap analysis (Layer 5: memory, Layer 6: runtime context), Volkmar's IBM knowledge graph pattern

## Decision

Add Neo4j as a knowledge graph layer between the application and the vector/document stores. Implement tiered query routing that checks progressively deeper (and more expensive) sources.

## Problem

Two critical gaps in the current knowledge architecture:

1. **Layer 5 (Learning Memory):** `feedback_events` has 3 entries. Every correction, contradiction, and failed chain should auto-populate this collection. Without it, the system repeats the same mistakes.

2. **Layer 6 (Tiered Query):** Every query brute-forces the full vector space (2M+ vectors). Volkmar's IBM experience: graph-directed search reduced 15-minute queries to 5 seconds. We need a summary layer and graph traversal before falling back to vector similarity.

## Architecture

```
                          Query
                            |
                    ┌───────┴───────┐
                    │  Tier 0: Cache │  In-memory LRU (hot facts, recent chains)
                    └───────┬───────┘
                            │ miss
                    ┌───────┴───────┐
                    │  Tier 1: Graph │  Neo4j — concept nodes, fact edges
                    │    Summary     │  Pre-computed summaries per topic cluster
                    └───────┬───────┘
                            │ insufficient
                    ┌───────┴───────┐
                    │  Tier 2: Vector│  Qdrant — semantic similarity search
                    │    Search      │  Scoped by graph context (not brute-force)
                    └───────┬───────┘
                            │ need original
                    ┌───────┴───────┐
                    │  Tier 3: Source │  PostgreSQL + filesystem
                    │    Documents    │  Full document retrieval
                    └───────┬───────┘
                            │ stale?
                    ┌───────┴───────┐
                    │  Tier 4: Live   │  Daylight API, direct Qdrant
                    │    Fallback     │  Re-embed/re-extract if stale
                    └───────────────┘
```

### Neo4j Schema

```cypher
// Core node types
(:Concept {id, name, domain, description, embedding_id})
(:Fact {id, text, confidence, source_type, date, embedding_id})
(:Document {id, path, collection, date, type})
(:Person {id, name, role, aliases[]})
(:Rule {id, statute, text, jurisdiction})
(:TopicCluster {id, name, summary, fact_count, last_updated})

// Core relationships
(:Fact)-[:EXTRACTED_FROM]->(:Document)
(:Fact)-[:SUPPORTS]->(:Fact)
(:Fact)-[:CONTRADICTS]->(:Fact)
(:Fact)-[:SUPERSEDES]->(:Fact)
(:Fact)-[:ABOUT]->(:Person)
(:Fact)-[:CITES]->(:Rule)
(:Fact)-[:BELONGS_TO]->(:TopicCluster)
(:Concept)-[:RELATES_TO]->(:Concept)
(:Concept)-[:GROUNDED_BY]->(:Fact)
(:Document)-[:MENTIONS]->(:Person)

// Provenance
(:Fact)-[:CORRECTED_BY {date, reason}]->(:Fact)
(:TopicCluster)-[:SUMMARIZED_AT {date, model}]->(:TopicCluster)
```

### Tiered Query Flow (pseudocode)

```python
async def tiered_query(question: str, min_confidence: str = "asserted"):
    # Tier 0: Cache
    cached = lru_cache.get(question_hash)
    if cached and not is_stale(cached):
        return cached

    # Tier 1: Graph summary
    # Find relevant topic clusters via embedding similarity on cluster summaries
    clusters = neo4j.query("""
        MATCH (tc:TopicCluster)
        WHERE tc.embedding_similarity($question_embedding) > 0.7
        RETURN tc.summary, tc.name, tc.fact_count
        ORDER BY tc.embedding_similarity DESC LIMIT 5
    """)
    if clusters_sufficient(clusters, question):
        return format_from_summaries(clusters)

    # Tier 1b: Graph traversal
    # From clusters, traverse to specific facts
    facts = neo4j.query("""
        MATCH (tc:TopicCluster)<-[:BELONGS_TO]-(f:Fact)
        WHERE tc.name IN $cluster_names
          AND f.confidence >= $min_confidence_rank
        OPTIONAL MATCH (f)-[:CONTRADICTS]-(contra:Fact)
        OPTIONAL MATCH (f)-[:SUPPORTS]-(support:Fact)
        RETURN f, collect(contra) as contradictions, collect(support) as corroboration
        ORDER BY f.confidence DESC, f.date DESC
    """)
    if facts_sufficient(facts, question):
        return format_from_facts(facts)

    # Tier 2: Vector search (scoped by graph context)
    # Use cluster names to scope the vector search instead of brute-forcing
    collection_filter = derive_collections_from_clusters(clusters)
    vectors = qdrant.search(
        collection=collection_filter,
        query_vector=embed(question),
        limit=20,
        score_threshold=0.65,
    )

    # Tier 3: Source documents (if vectors reference originals)
    if needs_full_context(vectors, question):
        docs = fetch_source_documents(vectors)
        return format_with_sources(facts, vectors, docs)

    # Tier 4: Live fallback (if staleness detected)
    if any(is_stale(v) for v in vectors):
        live = await daylight_api.search(question)
        return format_with_live(facts, vectors, live)

    return format_from_facts_and_vectors(facts, vectors)
```

## Layer 5: Learning Memory Automation

### Auto-populate triggers

| Trigger | Source | feedback_events payload |
|---------|--------|------------------------|
| Contradiction detected | Daily enrichment pipeline | `{type: "contradiction", facts: [F_X, F_Y], reason: "..."}` |
| Fact superseded | Manual or pipeline | `{type: "supersession", old: F_X, new: F_Z, reason: "..."}` |
| Chain evaluation failed | Eval loop | `{type: "chain_failure", chain_id, gap: "...", missing: "..."}` |
| User correction | Claude session | `{type: "correction", signal: "...", learned_rule: "..."}` |
| Search refinement | User feedback | `{type: "refinement", query: "...", better_query: "..."}` |
| Confidence override | Manual review | `{type: "confidence_change", fact_id, old, new, reason}` |

### Claude Code hook for auto-logging

Add a post-session hook that scans the conversation for correction patterns and auto-logs to feedback_events:

```python
# In devctl or as a Claude Code hook
def extract_corrections(session_text: str) -> list[dict]:
    """Detect correction patterns in Claude Code sessions."""
    patterns = [
        r"(?:no|wrong|incorrect|actually|not that)",  # user correction signals
        r"(?:I see|you're right|corrected|updated)",   # agent acknowledgment
    ]
    # Extract correction pairs and log to feedback_events
```

### Target: 100+ entries within 30 days

Current: 3 entries. Sources to mine:
- Existing Claude Code sessions (45K vectors) — extract historical corrections
- Daily enrichment contradictions (~5-10 per run)
- Chain evaluation failures (~2-3 per analysis session)
- User corrections during interactive sessions (~1-2 per session)

## Infrastructure

### Docker addition

```yaml
# Add to existing docker-compose or infra stack
neo4j:
  image: neo4j:5-community
  ports:
    - "7474:7474"  # Browser
    - "7687:7687"  # Bolt
  volumes:
    - neo4j_data:/data
  environment:
    - NEO4J_AUTH=neo4j/devctl-graph
    - NEO4J_PLUGINS=["apoc","graph-data-science"]
```

### devctl integration

```
devctl graph status          # Neo4j connection + node/edge counts
devctl graph populate        # Build graph from existing facts
devctl graph query "topic"   # Tiered query via graph
devctl graph enrich          # Run daily enrichment cycle
devctl graph clusters        # Show topic clusters with summaries
```

### Population from existing data

Phase 1 (bootstrap from Qdrant):
1. Export `fact_registry` (167 facts) → create `:Fact` nodes
2. Export `legal_docs_v2` metadata → create `:Document` nodes
3. Run entity extraction on facts → create `:Person` and `:Rule` nodes
4. Build edges from fact co-occurrence and entity overlap

Phase 2 (continuous enrichment):
1. Daily pipeline adds new facts as nodes + edges
2. Eval loop logs corrections → `:CORRECTED_BY` edges
3. Concept extraction from Claude sessions → `:Concept` nodes
4. Topic clustering via graph community detection (Louvain)

## Consequences

- Adds Neo4j as fourth data store (alongside Qdrant, PostgreSQL, TimescaleDB)
- Query latency drops from ~2s (brute-force vector) to <200ms (graph-directed)
- Memory grows from 3 entries to 100+ within 30 days
- Concept web page can be auto-generated from graph structure
- `devctl health` needs to monitor Neo4j (port 7474/7687)

## Alternatives Considered

- **NetworkX in-memory**: Current approach. Rebuilds graph per request, no persistence, no advanced algorithms. Not viable at scale.
- **PostgreSQL recursive CTEs**: Could work for simple traversal but lacks graph algorithms (PageRank, community detection, shortest path).
- **Qdrant-only with metadata filters**: No graph traversal, no relationship modeling. Vector similarity is not the same as graph connectivity.

## References

- OpenAI: "Inside Our In-House Data Agent" (2025)
- Volkmar's IBM knowledge graph experience (Signal, 2026-05-16)
- `docs/architecture/12-fact-treatment.md` — 6-layer gap analysis

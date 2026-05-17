#!/usr/bin/env python3
"""Populate Neo4j knowledge graph from concept web and fact registry.

Usage:
    python scripts/populate_graph.py              # populate from concept web
    python scripts/populate_graph.py --clear      # clear graph first
    python scripts/populate_graph.py --stats      # show graph stats

Process:
    1. Connects to Neo4j at bolt://localhost:7687
    2. Creates constraint indexes for unique IDs
    3. Loads concept nodes with domain, description, source URLs
    4. Creates typed edges (GROUNDS, ENABLES, SUPPORTS, etc.)
    5. Reports node/edge counts

This is the seed layer. Future iterations will:
    - Pull facts from Qdrant fact_registry
    - Extract entities from legal_docs_v2
    - Build edges from co-occurrence and citation analysis
"""

import argparse
import json
import sys
import urllib.request

NEO4J_URL = "http://localhost:7474/db/neo4j/tx/commit"
NEO4J_AUTH = ("neo4j", "devctl-graph")

# ── Concept Web Data ──
# Same nodes/edges as concept-web.html, but structured for graph ingest

CONCEPTS = [
    {
        "id": "madison_first_principles",
        "name": "Madison's First Principles",
        "domain": "philosophy",
        "description": "Federalist No. 46: The people are the ultimate sovereign. Government legitimacy derives solely from consent. State governments serve as natural counterweights to federal overreach. The armed citizenry is the final safeguard against tyranny.",
        "source_url": "https://avalon.law.yale.edu/18th_century/fed46.asp",
        "concepts": ["popular sovereignty", "consent of governed", "state vs federal balance", "militia as safeguard", "natural counterweights"],
    },
    {
        "id": "natural_rights_dna",
        "name": "Natural Rights & DNA Claim",
        "domain": "legal",
        "description": "DNA is not evidence of standing — it IS standing. Biological parentage exists before courts, beyond jurisdiction. Natural rights > constitutional rights > statutory rights > court orders. 'Offspring' (biological fact) vs 'children' (statutory category).",
        "source_url": "https://jthorvaldur.github.io/r/rights/natural.html#dna-claim",
        "concepts": ["DNA as standing", "offspring vs children", "rights hierarchy", "pre-government rights", "Troxel v. Granville"],
    },
    {
        "id": "lending_fraud_proof",
        "name": "Lending Fraud & Proof Requirements",
        "domain": "legal",
        "description": "2026 foreclosure cases enforce: no proof, no foreclosure. Courts fatigued after 18 years of industry presumptions. Assignments of mortgage alone insufficient — must prove note enforcement chain. Nonjudicial foreclosure requires the specific instrument the statute demands.",
        "source_url": "https://x.com/LendingLiesX",
        "concepts": ["lost note doctrine", "enforcement chain", "extraordinary remedy", "Ryan v. HSBC", "Vargas v. RRA"],
    },
    {
        "id": "game_theory_enforcement",
        "name": "Game Theory of Enforcement",
        "domain": "legal",
        "description": "Nash equilibrium in rights enforcement: violation costs approach zero while compliance costs are substantial. Four-tier leverage hierarchy. Six integration principles: unimpeachable records, preserve for appeal, make non-compliance expensive, constitutional estoppel, identify incentives, find the federal hook.",
        "source_url": "https://jthorvaldur.github.io/r/reports/legal-bedrock-gametheory.html",
        "concepts": ["Nash equilibrium", "cost asymmetry", "Brady violations", "constitutional estoppel", "Monell claims", "Title IV-D conflict", "information asymmetry"],
    },
    {
        "id": "cross_tradition_commandments",
        "name": "Cross-Tradition Moral Architecture",
        "domain": "philosophy",
        "description": "9 world traditions spanning 4,000 years analyzed via factor analysis. 7 latent moral dimensions identified (85.2% variance): self-mastery, purity, embodied discipline, fairness, truth, non-violence, prohibition framing. Universal convergence: all 9 independently mandate against unjust killing, for truthfulness, charity, and against theft.",
        "source_url": "https://jthorvaldur.github.io/r/reports/commandments.html",
        "concepts": ["factor analysis", "7 moral dimensions", "universal convergence", "Eastern vs Western framing", "linguistic shifts"],
    },
    {
        "id": "openai_six_layer",
        "name": "OpenAI 6-Layer Knowledge Architecture",
        "domain": "architecture",
        "description": "6 grounding layers: (1) Source metadata, (2) Human annotations, (3) Code enrichment, (4) Institutional knowledge, (5) Learning memory, (6) Runtime context. Key insight: pipeline code reveals business logic that never surfaces in schemas. Our gaps: Layer 5 has 3 feedback entries, Layer 6 missing tiered query.",
        "source_url": "https://openai.com/index/inside-our-in-house-data-agent/",
        "concepts": ["metadata grounding", "query inference", "expert descriptions", "code > metadata", "institutional knowledge", "learning memory"],
    },
    {
        "id": "eval_regen_loop",
        "name": "Eval-Regen Loop",
        "domain": "architecture",
        "description": "Generate evidence chains, evaluate confidence gaps, search for missing evidence, regenerate with new context. Turns any analysis tool into an adversarial engine. Each cycle either confirms confidence or reveals what's missing — both outcomes are valuable.",
        "source_url": "",
        "concepts": ["adversarial evaluation", "confidence gaps", "evidence search", "regeneration cycle"],
    },
    {
        "id": "knowledge_graph_neo4j",
        "name": "Knowledge Graph (Neo4j)",
        "domain": "architecture",
        "description": "Volkmar's IBM pattern: markdown facts to document DB to Neo4j graph to directed search. 15 min brute-force queries to 5 sec with graph-directed search. Summary layer reduces context window pollution. Tiered query: summary, graph traversal, vector similarity, original document.",
        "source_url": "",
        "concepts": ["tiered query", "graph-directed search", "summary layer", "context window optimization", "PageRank", "community detection"],
    },
    {
        "id": "microstructure_research",
        "name": "Cross-Exchange Microstructure",
        "domain": "research",
        "description": "Hyperliquid vs Binance analysis: 3.8 bps discount reflects structural basis components. Adverse selection and maker economics via markout curves. HL shows independent price discovery (0.22 lead correlation). Research priorities: Hasbrouck decomposition, markout segmentation, VPIN toxicity, basis regime modeling.",
        "source_url": "https://jthorvaldur.github.io/hyperliquid/research.html",
        "concepts": ["basis decomposition", "adverse selection", "markout analysis", "information share", "VPIN toxicity"],
    },
    {
        "id": "concept_extraction_layer",
        "name": "Concept Extraction Layer",
        "domain": "architecture",
        "description": "The missing layer between raw embeddings and user-facing knowledge. Graph nodes should be concepts, not just documents. Each concept links to source documents, other concepts, and the reasoning chain connecting them. Concepts hidden in semantic are the most powerful thing to share.",
        "source_url": "https://jthorvaldur.github.io/r/concepts/concept-web.html",
        "concepts": ["semantic to concept", "graph nodes as concepts", "reasoning chains", "self-referential architecture"],
    },
]

# Typed edges — the key advantage over vector similarity
EDGES = [
    ("madison_first_principles", "GROUNDS", "natural_rights_dna",
     "First principles ground the DNA claim: sovereignty of the people precedes government authority over family"),
    ("natural_rights_dna", "ENABLES", "game_theory_enforcement",
     "Natural rights framework provides the constitutional estoppel argument"),
    ("lending_fraud_proof", "DEMONSTRATES", "game_theory_enforcement",
     "Proof requirements are the game theory enforcement mechanism — shifts the Nash equilibrium"),
    ("game_theory_enforcement", "MIRRORS", "eval_regen_loop",
     "Adversarial evaluation mirrors the legal forcing function: each cycle confirms or reveals gaps"),
    ("cross_tradition_commandments", "SUPPORTS", "natural_rights_dna",
     "Universal moral convergence across 9 traditions supports pre-government natural rights"),
    ("cross_tradition_commandments", "SHARES_METHOD", "concept_extraction_layer",
     "Factor analysis methodology — finding latent dimensions in apparent diversity — is the same pattern"),
    ("openai_six_layer", "SOLVED_BY", "knowledge_graph_neo4j",
     "Neo4j tiered query is the missing Layer 6"),
    ("eval_regen_loop", "IMPLEMENTS", "openai_six_layer",
     "Eval-regen loop implements Layer 5 learning memory"),
    ("knowledge_graph_neo4j", "APPLIES_TO", "microstructure_research",
     "Graph-directed search applies to market data: regime detection, cross-exchange signal propagation"),
    ("knowledge_graph_neo4j", "ENABLES", "concept_extraction_layer",
     "Neo4j graph is the substrate on which concept extraction operates — concepts are high-centrality nodes"),
    ("eval_regen_loop", "REFINES", "concept_extraction_layer",
     "Each eval cycle refines the concept graph: confirming edges, pruning false connections"),
    ("madison_first_principles", "SHARES_FOUNDATION", "cross_tradition_commandments",
     "Madison's social contract theory rests on the same moral foundations the commandments analysis identifies"),
    ("lending_fraud_proof", "INVOKES", "natural_rights_dna",
     "Foreclosure without proof violates natural property rights — 'extraordinary remedy' echoes natural rights hierarchy"),
    ("microstructure_research", "USES", "eval_regen_loop",
     "Trading signal validation uses the same eval-regen pattern: generate hypothesis, test, refine"),
]


def neo4j_query(statements):
    """Execute Cypher statements via Neo4j HTTP API."""
    payload = json.dumps({"statements": [{"statement": s} for s in statements]}).encode()
    req = urllib.request.Request(NEO4J_URL, data=payload, headers={"Content-Type": "application/json"})

    # Basic auth
    import base64
    creds = base64.b64encode(f"{NEO4J_AUTH[0]}:{NEO4J_AUTH[1]}".encode()).decode()
    req.add_header("Authorization", f"Basic {creds}")

    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())

    errors = result.get("errors", [])
    if errors:
        for e in errors:
            print(f"  ERROR: {e.get('message', e)}", file=sys.stderr)
        return None
    return result


def clear_graph():
    """Delete all nodes and relationships."""
    print("  Clearing graph...")
    neo4j_query(["MATCH (n) DETACH DELETE n"])
    print("  Graph cleared.")


def create_constraints():
    """Create uniqueness constraints and indexes."""
    print("  Creating constraints...")
    neo4j_query([
        "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
        "CREATE INDEX concept_domain IF NOT EXISTS FOR (c:Concept) ON (c.domain)",
        "CREATE INDEX concept_name IF NOT EXISTS FOR (c:Concept) ON (c.name)",
    ])
    print("  Constraints ready.")


def populate_concepts():
    """Create Concept nodes."""
    print(f"  Loading {len(CONCEPTS)} concepts...")
    statements = []
    for c in CONCEPTS:
        cypher = (
            "MERGE (c:Concept {id: $id}) "
            "SET c.name = $name, c.domain = $domain, c.description = $description, "
            "c.source_url = $source_url, c.tags = $concepts, c.created = datetime()"
        )
        # Use parameterized queries via the HTTP API
        # The HTTP API doesn't support $params in the simple endpoint, so inline them safely
        tags_str = json.dumps(c["concepts"])
        desc_escaped = c["description"].replace("'", "\\'").replace('"', '\\"')
        name_escaped = c["name"].replace("'", "\\'")
        stmt = (
            f"MERGE (c:Concept {{id: '{c['id']}'}}) "
            f"SET c.name = '{name_escaped}', "
            f"c.domain = '{c['domain']}', "
            f"c.description = \"{desc_escaped}\", "
            f"c.source_url = '{c['source_url']}', "
            f"c.tags = {tags_str}, "
            f"c.created = datetime()"
        )
        statements.append(stmt)

    neo4j_query(statements)
    print(f"  {len(CONCEPTS)} concepts loaded.")


def populate_edges():
    """Create typed relationships between concepts."""
    print(f"  Loading {len(EDGES)} edges...")
    statements = []
    for src, rel_type, tgt, description in EDGES:
        desc_escaped = description.replace("'", "\\'").replace('"', '\\"')
        stmt = (
            f"MATCH (a:Concept {{id: '{src}'}}), (b:Concept {{id: '{tgt}'}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"SET r.description = \"{desc_escaped}\", r.created = datetime()"
        )
        statements.append(stmt)

    neo4j_query(statements)
    print(f"  {len(EDGES)} edges loaded.")


def show_stats():
    """Show graph statistics."""
    result = neo4j_query([
        "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC",
        "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY count DESC",
        "MATCH (c:Concept) RETURN c.domain AS domain, count(c) AS count ORDER BY count DESC",
    ])
    if not result:
        return

    print("\n  Nodes:")
    for row in result["results"][0]["data"]:
        print(f"    {row['row'][0]}: {row['row'][1]}")

    print("\n  Relationships:")
    for row in result["results"][1]["data"]:
        print(f"    {row['row'][0]}: {row['row'][1]}")

    print("\n  Domains:")
    for row in result["results"][2]["data"]:
        print(f"    {row['row'][0]}: {row['row'][1]}")

    # Centrality — which concepts have the most connections
    result2 = neo4j_query([
        "MATCH (c:Concept) "
        "OPTIONAL MATCH (c)-[r]-() "
        "RETURN c.name AS concept, c.domain AS domain, count(r) AS connections "
        "ORDER BY connections DESC"
    ])
    if result2:
        print("\n  Centrality (connections):")
        for row in result2["results"][0]["data"]:
            print(f"    {row['row'][2]:>2}  {row['row'][0]}  ({row['row'][1]})")


def sample_queries():
    """Run sample queries to demonstrate graph capabilities."""
    print("\n  Sample queries:")

    # 1. Find all concepts connected to a specific one
    print("\n  Q: What connects to 'Game Theory of Enforcement'?")
    r = neo4j_query([
        "MATCH (c:Concept {id: 'game_theory_enforcement'})-[r]-(other:Concept) "
        "RETURN type(r) AS relationship, other.name AS connected_to, r.description AS why"
    ])
    if r:
        for row in r["results"][0]["data"]:
            print(f"    {row['row'][0]:>20}  {row['row'][1]}")

    # 2. Find shortest path between two concepts
    print("\n  Q: Path from Madison to Microstructure?")
    r = neo4j_query([
        "MATCH path = shortestPath((a:Concept {id: 'madison_first_principles'})-[*]-(b:Concept {id: 'microstructure_research'})) "
        "RETURN [n IN nodes(path) | n.name] AS path, length(path) AS hops"
    ])
    if r:
        for row in r["results"][0]["data"]:
            print(f"    {' -> '.join(row['row'][0])}  ({row['row'][1]} hops)")

    # 3. Find concepts by domain
    print("\n  Q: All architecture concepts?")
    r = neo4j_query([
        "MATCH (c:Concept {domain: 'architecture'}) RETURN c.name AS name ORDER BY name"
    ])
    if r:
        for row in r["results"][0]["data"]:
            print(f"    {row['row'][0]}")


def main():
    parser = argparse.ArgumentParser(description="Populate Neo4j knowledge graph")
    parser.add_argument("--clear", action="store_true", help="Clear graph before populating")
    parser.add_argument("--stats", action="store_true", help="Show graph stats only")
    parser.add_argument("--demo", action="store_true", help="Run sample queries")
    args = parser.parse_args()

    print(f"\n  Neo4j Knowledge Graph — populate")
    print(f"  {'─' * 50}\n")

    if args.stats:
        show_stats()
        print()
        return

    if args.demo:
        sample_queries()
        print()
        return

    if args.clear:
        clear_graph()

    create_constraints()
    populate_concepts()
    populate_edges()
    show_stats()

    print("\n  Open http://localhost:7474 to explore the graph visually.")
    print("  Try: MATCH (n)-[r]->(m) RETURN n, r, m")
    print()


if __name__ == "__main__":
    main()

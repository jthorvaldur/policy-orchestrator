#!/usr/bin/env python3
"""Populate Neo4j from CaseLedger Postgres (facts, parties, graph).

Usage:
    python scripts/populate_graph_caseledger.py          # load all
    python scripts/populate_graph_caseledger.py --stats   # show stats only

Pulls from local Postgres :5433 (CaseLedger) and creates:
    - :CaseFact nodes from facts table (16K+)
    - :Party nodes from parties table (attorneys, orgs, courts)
    - :CaseGraphNode from graph_nodes table
    - Edges: ABOUT_PARTY, SOURCED_FROM, typed graph edges
"""

import argparse
import json
import subprocess
import sys
import urllib.request
import base64

NEO4J_URL = "http://localhost:7474/db/neo4j/tx/commit"
_AUTH = base64.b64encode(b"neo4j:devctl-graph").decode()

BATCH_SIZE = 200  # Neo4j HTTP API handles ~200 statements well


def neo4j_query(statements):
    """Execute Cypher statements via Neo4j HTTP API."""
    if not statements:
        return None
    payload = json.dumps({"statements": [{"statement": s} for s in statements]}).encode()
    req = urllib.request.Request(
        NEO4J_URL, data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Basic {_AUTH}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    errors = result.get("errors", [])
    if errors:
        for e in errors[:3]:
            print(f"  ERR: {e.get('message', '')[:120]}", file=sys.stderr)
    return result


def pg_query(sql):
    """Run a SQL query against local CaseLedger Postgres, return JSON rows."""
    result = subprocess.run(
        ["docker", "exec", "infra-postgres-1", "psql", "-U", "caseledger", "-d", "caseledger",
         "-t", "-A", "-c", f"SELECT json_agg(t) FROM ({sql}) t"],
        capture_output=True, text=True, timeout=30,
    )
    raw = result.stdout.strip()
    if not raw or raw == "" or raw == "null":
        return []
    return json.loads(raw)


def esc(s):
    if not s:
        return ""
    return str(s).replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", " ").replace("\r", "")[:500]


def create_constraints():
    print("  Creating constraints...")
    for stmt in [
        "CREATE CONSTRAINT casefact_id IF NOT EXISTS FOR (f:CaseFact) REQUIRE f.id IS UNIQUE",
        "CREATE CONSTRAINT party_id IF NOT EXISTS FOR (p:Party) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT casegraph_id IF NOT EXISTS FOR (g:CaseGraphNode) REQUIRE g.id IS UNIQUE",
    ]:
        neo4j_query([stmt])
    # Indexes in separate calls
    for stmt in [
        "CREATE INDEX casefact_cat IF NOT EXISTS FOR (f:CaseFact) ON (f.category)",
        "CREATE INDEX casefact_conf IF NOT EXISTS FOR (f:CaseFact) ON (f.confidence)",
        "CREATE INDEX party_type IF NOT EXISTS FOR (p:Party) ON (p.party_type)",
    ]:
        neo4j_query([stmt])


def load_parties():
    """Load attorneys, courts, and named orgs as :Party nodes."""
    print("  Loading parties...")
    # Only load real named entities (not hashed persons)
    rows = pg_query("""
        SELECT id, canonical_name, party_type, role
        FROM parties
        WHERE party_type IN ('attorney', 'court')
           OR (party_type = 'organization' AND length(canonical_name) < 50
               AND canonical_name !~ '^[0-9A-Z][a-z0-9]{30,}')
        ORDER BY party_type, canonical_name
    """)
    print(f"    {len(rows)} named parties found")

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        stmts = []
        for r in batch:
            stmts.append(
                f"MERGE (p:Party {{id: '{esc(r['id'])}'}}) "
                f"SET p.name = '{esc(r['canonical_name'])}', "
                f"p.party_type = '{esc(r['party_type'])}', "
                f"p.role = '{esc(r.get('role', ''))}'"
            )
        neo4j_query(stmts)
    print(f"    {len(rows)} parties loaded")
    return len(rows)


def load_facts():
    """Load high-confidence CaseFact nodes."""
    print("  Loading case facts...")
    rows = pg_query("""
        SELECT id, left(statement, 500) as statement, date, confidence, category,
               status, exact_amount, exact_party
        FROM facts
        WHERE confidence IN ('high', 'medium')
        ORDER BY confidence DESC, category
    """)
    print(f"    {len(rows)} high/medium confidence facts found")

    loaded = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        stmts = []
        for r in batch:
            amount_str = ""
            if r.get("exact_amount"):
                amount_str = f", f.exact_amount = {r['exact_amount']}"
            party_str = ""
            if r.get("exact_party"):
                party_str = f", f.exact_party = '{esc(r['exact_party'])}'"

            stmts.append(
                f"MERGE (f:CaseFact {{id: '{esc(r['id'])}'}}) "
                f"SET f.statement = '{esc(r['statement'])}', "
                f"f.date = '{esc(r.get('date', ''))}', "
                f"f.confidence = '{esc(r['confidence'])}', "
                f"f.category = '{esc(r['category'])}', "
                f"f.status = '{esc(r.get('status', ''))}'"
                f"{amount_str}{party_str}"
            )
        neo4j_query(stmts)
        loaded += len(batch)
        if loaded % 2000 == 0 or loaded == len(rows):
            print(f"    {loaded}/{len(rows)} facts loaded")

    return len(rows)


def load_fact_party_edges():
    """Link CaseFacts to Parties via party_mentions."""
    print("  Loading fact-party edges...")
    # Get facts that mention known parties (attorneys, courts)
    rows = pg_query("""
        SELECT DISTINCT f.id as fact_id, pm.party_id
        FROM facts f
        JOIN fact_sources fs ON fs.fact_id = f.id
        JOIN documents d ON d.id = fs.document_id
        JOIN party_mentions pm ON pm.document_id = d.id
        JOIN parties p ON p.id = pm.party_id
        WHERE f.confidence IN ('high', 'medium')
          AND p.party_type IN ('attorney', 'court')
        LIMIT 5000
    """)
    print(f"    {len(rows)} fact-party links found")

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        stmts = [
            f"MATCH (f:CaseFact {{id: '{esc(r['fact_id'])}'}}), (p:Party {{id: '{esc(r['party_id'])}'}}) "
            f"MERGE (f)-[:ABOUT_PARTY]->(p)"
            for r in batch
        ]
        neo4j_query(stmts)

    print(f"    {len(rows)} edges created")
    return len(rows)


def load_graph_structure():
    """Load CaseLedger's existing graph_nodes and graph_edges."""
    print("  Loading case graph structure...")

    # Nodes
    nodes = pg_query("""
        SELECT id, node_type, state, party,
               data->>'label' as label, data->>'description' as description
        FROM graph_nodes
        ORDER BY node_type
    """)
    print(f"    {len(nodes)} graph nodes found")

    for i in range(0, len(nodes), BATCH_SIZE):
        batch = nodes[i:i + BATCH_SIZE]
        stmts = []
        for r in batch:
            label = esc(r.get('label', '') or r['id'])
            desc = esc(r.get('description', '') or '')
            stmts.append(
                f"MERGE (g:CaseGraphNode {{id: '{esc(r['id'])}'}}) "
                f"SET g.node_type = '{esc(r['node_type'])}', "
                f"g.state = '{esc(r['state'])}', "
                f"g.party = '{esc(r.get('party', ''))}', "
                f"g.label = '{label}', "
                f"g.description = '{desc}'"
            )
        neo4j_query(stmts)

    # Edges
    edges = pg_query("""
        SELECT src_id, dst_id, edge_type, data->>'label' as label
        FROM graph_edges
    """)
    print(f"    {len(edges)} graph edges found")

    for i in range(0, len(edges), BATCH_SIZE):
        batch = edges[i:i + BATCH_SIZE]
        stmts = []
        for r in batch:
            edge_type = r.get('edge_type', 'RELATED').upper().replace(' ', '_').replace('-', '_')
            # Only use valid Cypher relationship types
            if not edge_type.isidentifier():
                edge_type = 'RELATED'
            stmts.append(
                f"MATCH (a:CaseGraphNode {{id: '{esc(r['src_id'])}'}}), "
                f"(b:CaseGraphNode {{id: '{esc(r['dst_id'])}'}}) "
                f"MERGE (a)-[:{edge_type}]->(b)"
            )
        neo4j_query(stmts)

    print(f"    {len(nodes)} nodes, {len(edges)} edges loaded")
    return len(nodes), len(edges)


def link_concepts():
    """Link CaseFact categories to existing Concept nodes."""
    print("  Linking facts to concepts...")
    mappings = [
        ("financial", "game_theory_enforcement", "Financial facts relate to enforcement economics"),
        ("testimony", "natural_rights_dna", "Testimony relates to rights and parental claims"),
        ("evidence", "eval_regen_loop", "Evidence evaluation uses the eval-regen pattern"),
        ("strategy", "game_theory_enforcement", "Strategy maps to game theory of enforcement"),
        ("rules", "game_theory_enforcement", "Legal rules feed the enforcement framework"),
    ]
    stmts = []
    for category, concept_id, desc in mappings:
        stmts.append(
            f"MATCH (f:CaseFact {{category: '{category}'}}), (c:Concept {{id: '{concept_id}'}}) "
            f"MERGE (f)-[:RELATES_TO]->(c)"
        )
    neo4j_query(stmts)
    print(f"    {len(mappings)} category-concept mappings applied")


def show_stats():
    result = neo4j_query([
        "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC",
        "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY count DESC LIMIT 15",
    ])
    if not result:
        return
    print("\n  Node types:")
    for row in result["results"][0]["data"]:
        print(f"    {row['row'][1]:>6,}  {row['row'][0]}")
    print("\n  Edge types (top 15):")
    for row in result["results"][1]["data"]:
        print(f"    {row['row'][1]:>6,}  {row['row'][0]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    print(f"\n  Neo4j — CaseLedger population")
    print(f"  {'─' * 50}\n")

    if args.stats:
        show_stats()
        print()
        return

    create_constraints()
    n_parties = load_parties()
    n_facts = load_facts()
    n_edges = load_fact_party_edges()
    n_nodes, n_gedges = load_graph_structure()
    link_concepts()
    show_stats()
    print()


if __name__ == "__main__":
    main()

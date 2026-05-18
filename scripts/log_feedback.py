#!/usr/bin/env python3
"""Log a calibration event to the feedback_events Qdrant collection.

Usage:
    devctl log-feedback --type=correction --signal="user said X" --rule="learned Y"
    devctl log-feedback --type=confirmation --signal="approach worked" --rule="keep doing Y"
"""

import sys
import uuid
from datetime import datetime

from lib.embedder import embed_text
from lib.qdrant_helpers import ensure_collection, get_client
from qdrant_client.models import PointStruct

COLLECTION = "feedback_events"

EVENT_TYPES = ["correction", "confirmation", "mode_shift", "observation"]
SCOPES = ["all_sessions", "repo_specific"]


def log_feedback(
    event_type: str,
    user_signal: str,
    agent_action: str = "",
    delta: str = "",
    learned_rule: str = "",
    repo: str = "",
    scope: str = "all_sessions",
):
    """Log a structured feedback event with embedding."""
    client = get_client()
    ensure_collection(client, COLLECTION)

    # Build the text to embed — the learned rule is the most searchable part
    embed_parts = []
    if learned_rule:
        embed_parts.append(learned_rule)
    if delta:
        embed_parts.append(delta)
    if user_signal:
        embed_parts.append(f"User signal: {user_signal}")
    embed_content = "\n".join(embed_parts)

    vector = embed_text(embed_content)

    point = PointStruct(
        id=str(uuid.uuid4()),
        vector={"dense": vector},
        payload={
            "event_type": event_type,
            "user_signal": user_signal,
            "agent_action": agent_action,
            "delta": delta,
            "learned_rule": learned_rule,
            "repo": repo,
            "scope": scope,
            "timestamp": datetime.now().isoformat(),
            "text": embed_content,
        },
    )

    client.upsert(collection_name=COLLECTION, points=[point])

    info = client.get_collection(COLLECTION)
    print(f"Logged {event_type} event. Collection has {info.points_count} total events.", file=sys.stderr)

    # Also create a node in Neo4j (if available)
    _log_to_neo4j(str(point.id), event_type, user_signal, learned_rule, repo, scope)


def _log_to_neo4j(event_id, event_type, user_signal, learned_rule, repo, scope):
    """Create a FeedbackEvent node in Neo4j and link to relevant concepts."""
    import base64
    import json
    import urllib.request

    def _escape(s):
        if not s:
            return ""
        return s.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", " ")

    try:
        url = "http://localhost:7474/db/neo4j/tx/commit"
        creds = base64.b64encode(b"neo4j:devctl-graph").decode()

        # Schema changes must be in a separate transaction
        schema_payload = json.dumps({"statements": [
            {"statement": "CREATE CONSTRAINT feedback_id IF NOT EXISTS FOR (fe:FeedbackEvent) REQUIRE fe.id IS UNIQUE"},
        ]}).encode()
        schema_req = urllib.request.Request(
            url, data=schema_payload,
            headers={"Content-Type": "application/json", "Authorization": f"Basic {creds}"},
        )
        urllib.request.urlopen(schema_req, timeout=5)

        # Now create the node + edges
        stmts = [
            f"MERGE (fe:FeedbackEvent {{id: '{event_id}'}}) "
            f"SET fe.event_type = '{event_type}', "
            f"fe.signal = '{_escape(user_signal)}', "
            f"fe.rule = '{_escape(learned_rule)}', "
            f"fe.repo = '{_escape(repo)}', "
            f"fe.scope = '{scope}', "
            f"fe.created = datetime()",
        ]

        # Link to repo if specified
        if repo:
            stmts.append(
                f"MATCH (fe:FeedbackEvent {{id: '{event_id}'}}), (r:Repo {{id: '{_escape(repo)}'}}) "
                f"MERGE (fe)-[:FROM_REPO]->(r)"
            )

        payload = json.dumps({"statements": [{"statement": s} for s in stmts]}).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Basic {creds}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        errors = data.get("errors", [])
        if errors:
            print(f"Neo4j: Cypher errors: {errors}", file=sys.stderr)
        else:
            print(f"Neo4j: created FeedbackEvent node {event_id[:8]}...", file=sys.stderr)
    except Exception as e:
        # Neo4j is optional — don't fail the Qdrant write
        print(f"Neo4j: skipped ({type(e).__name__}: {e})", file=sys.stderr)


def query_feedback(
    query: str | None = None,
    repo: str | None = None,
    event_type: str | None = None,
    limit: int = 5,
):
    """Query feedback events for calibration notes."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = get_client()

    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        print(f"No '{COLLECTION}' collection. Log some events first.", file=sys.stderr)
        return

    conditions = []
    # Always include all_sessions scope, plus repo-specific if filtering
    if repo:
        conditions.append(
            Filter(should=[
                FieldCondition(key="scope", match=MatchValue(value="all_sessions")),
                FieldCondition(key="repo", match=MatchValue(value=repo)),
            ])
        )
    if event_type:
        conditions.append(FieldCondition(key="event_type", match=MatchValue(value=event_type)))

    query_filter = None
    if conditions:
        must = []
        for c in conditions:
            if isinstance(c, Filter):
                # Nest the should-filter inside must
                must.append(c)
            else:
                must.append(c)
        query_filter = Filter(must=must) if must else None

    if query:
        query_vector = embed_text(query)
        results = client.query_points(
            collection_name=COLLECTION,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
    else:
        # No query — just scroll recent events
        results = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        # scroll returns (points, next_offset)
        if isinstance(results, tuple):
            class FakeResult:
                def __init__(self, pts):
                    self.points = pts
            results = FakeResult(results[0])

    if not results.points:
        print("No feedback events found.", file=sys.stderr)
        return

    print(f"\n{'=' * 60}")
    print(f"  Feedback Events" + (f" (query: \"{query}\")" if query else ""))
    print(f"{'=' * 60}\n")

    for i, point in enumerate(results.points):
        p = point.payload
        score = getattr(point, 'score', None)
        score_str = f"  score={score:.3f}" if score else ""

        print(f"  [{i+1}]{score_str}  {p.get('event_type', '?')}  {p.get('timestamp', '?')[:16]}")
        if p.get("repo"):
            print(f"      repo: {p['repo']}  scope: {p.get('scope', '?')}")
        if p.get("user_signal"):
            print(f"      signal: {p['user_signal'][:100]}")
        if p.get("learned_rule"):
            print(f"      rule: {p['learned_rule'][:200]}")
        if p.get("delta"):
            print(f"      delta: {p['delta'][:150]}")
        print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Log or query feedback events")
    sub = parser.add_subparsers(dest="command")

    log_p = sub.add_parser("log", help="Log a new feedback event")
    log_p.add_argument("--type", required=True, choices=EVENT_TYPES, help="Event type")
    log_p.add_argument("--signal", required=True, help="What the user said/did")
    log_p.add_argument("--action", default="", help="What the agent did")
    log_p.add_argument("--delta", default="", help="What was wrong / what changed")
    log_p.add_argument("--rule", default="", help="The learned calibration rule")
    log_p.add_argument("--repo", default="", help="Which repo this applies to")
    log_p.add_argument("--scope", default="all_sessions", choices=SCOPES)

    query_p = sub.add_parser("query", help="Query feedback events")
    query_p.add_argument("query", nargs="?", default=None, help="Search query")
    query_p.add_argument("--repo", default=None, help="Filter to repo")
    query_p.add_argument("--type", default=None, choices=EVENT_TYPES)
    query_p.add_argument("--limit", type=int, default=5)

    args = parser.parse_args()

    if args.command == "log":
        log_feedback(
            event_type=args.type,
            user_signal=args.signal,
            agent_action=args.action,
            delta=args.delta,
            learned_rule=args.rule,
            repo=args.repo,
            scope=args.scope,
        )
    elif args.command == "query":
        query_feedback(
            query=args.query,
            repo=args.repo,
            event_type=getattr(args, "type", None),
            limit=args.limit,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

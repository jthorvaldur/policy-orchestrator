#!/usr/bin/env python3
"""Log and query classified facts with provenance and confidence levels.

Facts are not all equal. A bank statement showing $47,000 on 2025-03-15
is ground truth. An email claiming "I paid the mortgage" is an assertion.
This system tracks the difference.

Confidence levels:
  verified    — machine-readable source, independently confirmable
                (bank CSV, court filing stamp, tax return PDF)
  documented  — human-authored primary source, internally consistent
                (signed letter, sworn declaration, medical record)
  asserted    — claim made by a party, not independently verified
                (email statement, verbal claim, text message)
  disputed    — contradicted by another source at equal or higher confidence
                (party A says X, party B says not-X)
  inferred    — derived from other facts through reasoning
                (calculated value, timeline deduction, pattern observation)
  unknown     — confidence not yet assessed
"""

import sys
import uuid
from datetime import datetime

from lib.embedder import embed_text
from lib.qdrant_helpers import ensure_collection, get_client
from qdrant_client.models import PointStruct

COLLECTION = "fact_registry"

CONFIDENCE_LEVELS = ["verified", "documented", "asserted", "disputed", "inferred", "unknown"]
CONFIDENCE_RANK = {c: i for i, c in enumerate(CONFIDENCE_LEVELS)}

SOURCE_TYPES = [
    "financial_download",  # bank CSV, brokerage statement
    "court_document",      # filed motion, order, ruling
    "tax_document",        # W2, 1099, tax return
    "email",               # email message
    "text_message",        # SMS, iMessage, WhatsApp
    "conversation",        # verbal or chat claim
    "medical_record",      # medical document
    "legal_filing",        # attorney-filed document
    "calculation",         # derived value
    "public_record",       # government database, FOIA
    "photograph",          # image evidence
    "other",
]

DOMAINS = ["financial", "legal", "medical", "personal", "technical", "property", "employment"]


def log_fact(
    fact: str,
    source_type: str,
    confidence: str,
    domain: str,
    source_ref: str = "",
    source_date: str = "",
    claimed_by: str = "",
    contradicts: str = "",
    repo: str = "",
    notes: str = "",
):
    """Log a classified fact with embedding."""
    client = get_client()
    ensure_collection(client, COLLECTION)

    # Embed the fact itself plus context for search
    embed_parts = [fact]
    if notes:
        embed_parts.append(notes)
    if source_ref:
        embed_parts.append(f"Source: {source_ref}")
    embed_content = "\n".join(embed_parts)

    vector = embed_text(embed_content)

    point = PointStruct(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={
            "fact": fact,
            "source_type": source_type,
            "confidence": confidence,
            "confidence_rank": CONFIDENCE_RANK.get(confidence, 5),
            "domain": domain,
            "source_ref": source_ref,
            "source_date": source_date,
            "claimed_by": claimed_by,
            "contradicts": contradicts,
            "repo": repo,
            "notes": notes,
            "logged_at": datetime.now().isoformat(),
            "text": embed_content,
        },
    )

    client.upsert(collection_name=COLLECTION, points=[point])

    info = client.get_collection(COLLECTION)
    print(f"Logged [{confidence}] fact. Registry has {info.points_count} total facts.", file=sys.stderr)


def query_facts(
    query: str | None = None,
    domain: str | None = None,
    confidence: str | None = None,
    min_confidence: str | None = None,
    source_type: str | None = None,
    repo: str | None = None,
    limit: int = 10,
    show_all: bool = False,
):
    """Query the fact registry with optional confidence filtering."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    client = get_client()

    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        print(f"No '{COLLECTION}' collection. Log some facts first.", file=sys.stderr)
        return

    conditions = []
    if domain:
        conditions.append(FieldCondition(key="domain", match=MatchValue(value=domain)))
    if confidence:
        conditions.append(FieldCondition(key="confidence", match=MatchValue(value=confidence)))
    if min_confidence:
        max_rank = CONFIDENCE_RANK.get(min_confidence, 5)
        conditions.append(FieldCondition(key="confidence_rank", range=Range(lte=max_rank)))
    if source_type:
        conditions.append(FieldCondition(key="source_type", match=MatchValue(value=source_type)))
    if repo:
        conditions.append(FieldCondition(key="repo", match=MatchValue(value=repo)))

    query_filter = Filter(must=conditions) if conditions else None

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
        results_tuple = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=query_filter,
            limit=limit,
            with_payload=True,
        )

        class FakeResult:
            def __init__(self, pts):
                self.points = pts
        results = FakeResult(results_tuple[0])

    if not results.points:
        print("No facts found.", file=sys.stderr)
        return

    # Confidence display
    conf_icons = {
        "verified": "V",
        "documented": "D",
        "asserted": "A",
        "disputed": "!",
        "inferred": "~",
        "unknown": "?",
    }

    print(f"\n{'=' * 70}")
    print(f"  Fact Registry" + (f" (query: \"{query}\")" if query else ""))
    if min_confidence:
        print(f"  Minimum confidence: {min_confidence}")
    print(f"{'=' * 70}\n")

    for i, point in enumerate(results.points):
        p = point.payload
        score = getattr(point, 'score', None)
        score_str = f"  score={score:.3f}" if score else ""
        conf = p.get("confidence", "?")
        icon = conf_icons.get(conf, "?")

        print(f"  [{i+1}]{score_str}  [{icon}] {conf:<12} {p.get('domain', '?'):<12} {p.get('source_type', '?')}")
        print(f"      {p.get('fact', '?')}")
        if p.get("source_ref"):
            print(f"      source: {p['source_ref']}")
        if p.get("source_date"):
            print(f"      date: {p['source_date']}")
        if p.get("claimed_by"):
            print(f"      claimed by: {p['claimed_by']}")
        if p.get("contradicts"):
            print(f"      CONTRADICTS: {p['contradicts']}")
        if show_all and p.get("notes"):
            print(f"      notes: {p['notes']}")
        print()

    info = client.get_collection(COLLECTION)
    print(f"Showing {len(results.points)} of {info.points_count} facts", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Log or query classified facts")
    sub = parser.add_subparsers(dest="command")

    log_p = sub.add_parser("log", help="Log a new fact")
    log_p.add_argument("--fact", required=True, help="The factual claim")
    log_p.add_argument("--source-type", required=True, choices=SOURCE_TYPES)
    log_p.add_argument("--confidence", required=True, choices=CONFIDENCE_LEVELS)
    log_p.add_argument("--domain", required=True, choices=DOMAINS)
    log_p.add_argument("--source-ref", default="", help="File path, email ID, or document reference")
    log_p.add_argument("--source-date", default="", help="Date the fact pertains to (YYYY-MM-DD)")
    log_p.add_argument("--claimed-by", default="", help="Who made this claim")
    log_p.add_argument("--contradicts", default="", help="ID or description of contradicted fact")
    log_p.add_argument("--repo", default="", help="Originating repo")
    log_p.add_argument("--notes", default="", help="Additional context")

    query_p = sub.add_parser("query", help="Query facts")
    query_p.add_argument("query", nargs="?", default=None, help="Semantic search query")
    query_p.add_argument("--domain", default=None, choices=DOMAINS)
    query_p.add_argument("--confidence", default=None, choices=CONFIDENCE_LEVELS)
    query_p.add_argument("--min-confidence", default=None, choices=CONFIDENCE_LEVELS,
                         help="Show facts at this confidence or higher")
    query_p.add_argument("--source-type", default=None, choices=SOURCE_TYPES)
    query_p.add_argument("--repo", default=None)
    query_p.add_argument("--limit", type=int, default=10)
    query_p.add_argument("--all", action="store_true", help="Show all fields including notes")

    args = parser.parse_args()

    if args.command == "log":
        log_fact(
            fact=args.fact,
            source_type=args.source_type,
            confidence=args.confidence,
            domain=args.domain,
            source_ref=args.source_ref,
            source_date=args.source_date,
            claimed_by=args.claimed_by,
            contradicts=args.contradicts,
            repo=args.repo,
            notes=args.notes,
        )
    elif args.command == "query":
        query_facts(
            query=args.query,
            domain=getattr(args, "domain", None),
            confidence=getattr(args, "confidence", None),
            min_confidence=getattr(args, "min_confidence", None),
            source_type=getattr(args, "source_type", None),
            repo=args.repo,
            limit=args.limit,
            show_all=getattr(args, "all", False),
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

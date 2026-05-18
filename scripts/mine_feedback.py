#!/usr/bin/env python3
"""Mine Claude Code sessions for feedback events.

Searches claude_code_sessions for user correction patterns,
extracts the correction + context, and logs to feedback_events.

Usage:
    python scripts/mine_feedback.py              # extract and preview
    python scripts/mine_feedback.py --commit      # actually log to Qdrant + Neo4j
    python scripts/mine_feedback.py --limit 50    # limit search scope
"""

import argparse
import json
import re
import sys
import urllib.request

QDRANT_URL = "http://localhost:6333"
DOCVEC_URL = "http://localhost:8100"


def embed(text):
    """Get embedding via docvec."""
    req = urllib.request.Request(
        f"{DOCVEC_URL}/embed",
        data=json.dumps({"texts": [text[:2000]]}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["vectors"][0]


def search_sessions(query, limit=30):
    """Semantic search in claude_code_sessions for user messages."""
    vec = embed(query)
    req = urllib.request.Request(
        f"{QDRANT_URL}/collections/claude_code_sessions/points/search",
        data=json.dumps({
            "vector": {"name": "dense", "vector": vec},
            "limit": limit,
            "with_payload": True,
            "filter": {"must": [{"key": "role", "match": {"value": "user"}}]},
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["result"]


# Correction signal queries — each captures a different type of feedback
SIGNAL_QUERIES = [
    "no that's wrong, don't do that, stop, actually I wanted something different",
    "please don't mix those concepts, keep them separate, wrong approach",
    "that is a massive AI tell, remove that language, don't sound like AI",
    "don't treat this as ground truth, be skeptical, verify first",
    "I removed that, please keep that concept out, don't include",
    "lessons from previous failed attempts, what NOT to do, mistakes",
    "good approach, yes keep doing that, perfect, exactly right, thank you",
    "remember this for next time, always do X, never do Y",
]

# Patterns that indicate a correction vs just a message
CORRECTION_INDICATORS = re.compile(
    r"(?:don.t|do not|stop|never|wrong|incorrect|remove|"
    r"please (?:don.t|keep|remove|stop)|"
    r"that.s (?:wrong|not|a )|"
    r"not (?:what I|how|the right)|"
    r"actually (?:I|we|it|the)|"
    r"massive (?:ai |tell)|"
    r"lessons from|what NOT to|"
    r"keep (?:that|this|a record)|"
    r"don.t (?:mix|treat|include|add|build))",
    re.IGNORECASE,
)

CONFIRMATION_INDICATORS = re.compile(
    r"(?:good (?:approach|email|idea|work)|"
    r"yes (?:keep|please|exactly|perfect)|"
    r"thank you for (?:removing|fixing|catching)|"
    r"exactly (?:right|what)|"
    r"perfect|great job|well done|"
    r"that.s (?:correct|right|good|better))",
    re.IGNORECASE,
)


def classify_message(text):
    """Classify a user message as correction, confirmation, or skip."""
    if CORRECTION_INDICATORS.search(text):
        return "correction"
    if CONFIRMATION_INDICATORS.search(text):
        return "confirmation"
    return None


def extract_rule(text):
    """Extract the learned rule from a correction message."""
    # The rule is usually the imperative part
    lines = text.split(". ")
    for line in lines:
        if CORRECTION_INDICATORS.search(line):
            return line.strip()[:200]
    return text[:200]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="Actually log events")
    parser.add_argument("--limit", type=int, default=30, help="Results per query")
    args = parser.parse_args()

    print(f"\n  Mining Claude Code sessions for feedback")
    print(f"  {'─' * 50}\n")

    seen_ids = set()
    events = []

    for query in SIGNAL_QUERIES:
        results = search_sessions(query, limit=args.limit)
        for r in results:
            pid = r["id"]
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            text = r["payload"].get("text", "")
            if len(text) < 20 or len(text) > 2000:
                continue

            event_type = classify_message(text)
            if not event_type:
                continue

            repo = r["payload"].get("repo", "")
            score = r["score"]
            rule = extract_rule(text)

            events.append({
                "type": event_type,
                "signal": text[:300],
                "rule": rule,
                "repo": repo,
                "score": score,
                "point_id": pid,
            })

    # Deduplicate by rule similarity (exact match for now)
    unique_rules = {}
    for e in events:
        key = e["rule"][:80].lower()
        if key not in unique_rules or e["score"] > unique_rules[key]["score"]:
            unique_rules[key] = e
    events = sorted(unique_rules.values(), key=lambda x: -x["score"])

    print(f"  Found {len(events)} feedback events\n")

    corrections = [e for e in events if e["type"] == "correction"]
    confirmations = [e for e in events if e["type"] == "confirmation"]

    print(f"  Corrections ({len(corrections)}):")
    for e in corrections[:20]:
        print(f"    [{e['score']:.3f}] {e['repo']}")
        print(f"      {e['rule'][:120]}")
        print()

    print(f"  Confirmations ({len(confirmations)}):")
    for e in confirmations[:10]:
        print(f"    [{e['score']:.3f}] {e['repo']}")
        print(f"      {e['rule'][:120]}")
        print()

    if args.commit and events:
        print(f"  Committing {len(events)} events to feedback_events...")
        import subprocess as sp
        from pathlib import Path
        root = Path(__file__).parent.parent

        for i, e in enumerate(events):
            try:
                cmd = [
                    sys.executable, "-m", "policy_orchestrator.cli",
                    "log-feedback",
                    f"--type={e['type']}",
                    f"--signal={e['signal'][:500]}",
                    f"--rule={e['rule']}",
                ]
                if e["repo"]:
                    cmd.append(f"--repo={e['repo']}")
                sp.run(cmd, cwd=root, capture_output=True, timeout=15,
                       env={**__import__("os").environ, "PYTHONPATH": str(root / "scripts")})
                if (i + 1) % 5 == 0:
                    print(f"    {i + 1}/{len(events)} logged")
            except Exception as ex:
                print(f"    ERR: {ex}", file=sys.stderr)
        print(f"  Done. {len(events)} events logged.")
    elif not args.commit:
        print(f"  Run with --commit to log these events")

    print()


if __name__ == "__main__":
    main()

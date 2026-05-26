#!/usr/bin/env python3
"""Subscription registry — list, check health, show costs."""

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

REGISTRIES = Path(__file__).parent.parent / "registries"

# ANSI colors
C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[90m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "mag": "\033[35m",
    "cyan": "\033[36m",
}


def load_subscriptions():
    with open(REGISTRIES / "subscriptions.yaml") as f:
        return yaml.safe_load(f)


def _monthly_cost(sub):
    """Return effective monthly cost in USD, or None if unknown."""
    if sub.get("cost_monthly") is not None:
        return float(sub["cost_monthly"])
    cost = sub.get("cost")
    if cost is None:
        return None
    cost = float(cost)
    freq = sub.get("frequency", "monthly")
    if freq == "annual":
        return round(cost / 12, 2)
    return cost


def _status_color(status):
    if status == "active":
        return C["green"]
    if status in ("overdue",):
        return C["red"]
    if status in ("review", "expiring"):
        return C["yellow"]
    return C["dim"]


def _status_dot(status):
    color = _status_color(status)
    return f"{color}●{C['reset']}"


def list_subscriptions(status_filter=None, category_filter=None):
    """Display all subscriptions grouped by status."""
    data = load_subscriptions()
    subs = data.get("subscriptions", {})

    # Group by status
    groups = {}
    for key, sub in subs.items():
        st = sub.get("status", "unknown")
        if status_filter and st != status_filter:
            continue
        if category_filter and sub.get("category") != category_filter:
            continue
        groups.setdefault(st, []).append((key, sub))

    # Display order
    order = ["overdue", "active", "review", "expiring", "expired"]
    remaining = sorted(set(groups.keys()) - set(order))
    order = [s for s in order if s in groups] + remaining

    total_monthly = 0.0
    unknown_count = 0

    print(f"\n{C['bold']}  Subscriptions{C['reset']}\n")

    for status in order:
        items = groups[status]
        color = _status_color(status)
        label = status.upper()
        if status == "overdue":
            label = f"{C['red']}{C['bold']}OVERDUE{C['reset']}"
        elif status == "active":
            label = f"{C['green']}ACTIVE{C['reset']}"
        elif status == "review":
            label = f"{C['yellow']}NEEDS REVIEW{C['reset']}"
        elif status == "expiring":
            label = f"{C['yellow']}EXPIRING{C['reset']}"
        elif status == "expired":
            label = f"{C['dim']}EXPIRED{C['reset']}"

        print(f"  {C['bold']}{label}{C['reset']}  {C['dim']}({len(items)}){C['reset']}")
        print()

        for key, sub in sorted(items, key=lambda x: -(x[1].get("cost") or 0)):
            name = sub.get("name", key)
            monthly = _monthly_cost(sub)
            freq = sub.get("frequency", "?")
            cat = sub.get("category", "")

            if monthly is not None and status in ("active", "overdue", "review", "expiring"):
                total_monthly += monthly
                cost_str = f"${monthly:>7.2f}/mo"
            elif monthly is not None:
                cost_str = f"${monthly:>7.2f}/mo"
            else:
                cost_str = f"{'?':>10}/mo"
                if status in ("active", "review"):
                    unknown_count += 1

            dot = _status_dot(status)
            notes = sub.get("notes", "")
            rec = sub.get("recommendation", "")

            print(f"    {dot} {name:<42} {cost_str}  {C['dim']}{freq:<12}{cat}{C['reset']}")
            if notes:
                print(f"      {C['dim']}{notes}{C['reset']}")
            if rec:
                print(f"      {C['yellow']}rec: {rec}{C['reset']}")

        print()

    # Summary
    print(f"  {'─' * 60}")
    print(f"  {C['bold']}Estimated monthly burn:{C['reset']}  ${total_monthly:.2f}/mo  (${total_monthly * 12:.2f}/yr)")
    if unknown_count:
        print(f"  {C['yellow']}{unknown_count} active services with unknown cost{C['reset']}")
    print()


def check_health():
    """Run health checks and balance checks for services that support them."""
    data = load_subscriptions()
    subs = data.get("subscriptions", {})

    print(f"\n{C['bold']}  Health & Balance Checks{C['reset']}\n")

    # Health checks
    health_subs = [(k, v) for k, v in subs.items() if v.get("health_check")]
    if health_subs:
        print(f"  {C['bold']}Health Checks{C['reset']}")
        for key, sub in health_subs:
            name = sub.get("name", key)
            cmd = sub["health_check"]
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    body = result.stdout.strip()[:80]
                    print(f"    {C['green']}●{C['reset']} {name:<35} {C['dim']}{body}{C['reset']}")
                else:
                    print(f"    {C['red']}●{C['reset']} {name:<35} {C['red']}failed (exit {result.returncode}){C['reset']}")
            except subprocess.TimeoutExpired:
                print(f"    {C['red']}●{C['reset']} {name:<35} {C['red']}timeout{C['reset']}")
            except Exception as e:
                print(f"    {C['red']}●{C['reset']} {name:<35} {C['red']}{e}{C['reset']}")
        print()

    # Balance checks
    balance_subs = [(k, v) for k, v in subs.items() if v.get("balance_check")]
    if balance_subs:
        print(f"  {C['bold']}API Balances{C['reset']}")
        for key, sub in balance_subs:
            name = sub.get("name", key)
            bc = sub["balance_check"]
            last_known = sub.get("balance")

            try:
                url = _expand_env(bc["url"])
                req = urllib.request.Request(url)

                auth = bc.get("auth", "")
                if auth:
                    auth = _expand_env(auth)
                    if auth.startswith("Bearer "):
                        req.add_header("Authorization", auth)

                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = resp.read().decode()

                parse = bc.get("parse", "")
                if parse == "raw_float":
                    balance = float(raw.strip())
                    print(f"    {C['green']}●{C['reset']} {name:<35} ${balance:.2f}")
                elif parse.startswith("data."):
                    data_resp = json.loads(raw)
                    path = parse.split(".")
                    obj = data_resp
                    for p in path:
                        obj = obj[p] if isinstance(obj, dict) else getattr(obj, p)
                    print(f"    {C['green']}●{C['reset']} {name:<35} usage: {obj}")
                else:
                    print(f"    {C['green']}●{C['reset']} {name:<35} {C['dim']}{raw[:60]}{C['reset']}")
            except Exception as e:
                bal_str = f"  {C['dim']}(last known: ${last_known:.2f}){C['reset']}" if last_known else ""
                print(f"    {C['yellow']}●{C['reset']} {name:<35} {C['yellow']}check failed: {e}{C['reset']}{bal_str}")
        print()

    # Also check Railway if available
    print(f"  {C['bold']}Infrastructure{C['reset']}")
    try:
        req = urllib.request.Request("https://daylight-production-f4d1.up.railway.app/health")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data_resp = json.loads(resp.read())
            version = data_resp.get("version", "?")
            print(f"    {C['green']}●{C['reset']} Railway (Daylight)                  v{version}")
    except Exception as e:
        print(f"    {C['red']}●{C['reset']} Railway (Daylight)                  {C['red']}unreachable: {e}{C['reset']}")
    print()


def show_costs():
    """Show cost breakdown with annual projections."""
    data = load_subscriptions()
    subs = data.get("subscriptions", {})

    print(f"\n{C['bold']}  Cost Breakdown{C['reset']}\n")

    # Group by category
    by_cat = {}
    for key, sub in subs.items():
        status = sub.get("status", "unknown")
        if status not in ("active", "overdue", "review", "expiring"):
            continue
        monthly = _monthly_cost(sub)
        if monthly is None or monthly == 0:
            continue
        cat = sub.get("category", "other")
        by_cat.setdefault(cat, []).append((sub.get("name", key), monthly, status))

    total_monthly = 0.0

    for cat in sorted(by_cat, key=lambda c: -sum(x[1] for x in by_cat[c])):
        items = by_cat[cat]
        cat_total = sum(x[1] for x in items)
        total_monthly += cat_total
        print(f"  {C['cyan']}{cat}{C['reset']}  {C['dim']}${cat_total:.2f}/mo{C['reset']}")
        for name, monthly, status in sorted(items, key=lambda x: -x[1]):
            dot = _status_dot(status)
            print(f"    {dot} {name:<42} ${monthly:>7.2f}/mo  ${monthly * 12:>8.2f}/yr")
        print()

    print(f"  {'─' * 60}")
    print(f"  {C['bold']}Total:{C['reset']}  ${total_monthly:>7.2f}/mo  ${total_monthly * 12:>8.2f}/yr")

    # Savings opportunities
    savings = []
    for key, sub in subs.items():
        rec = sub.get("recommendation")
        if rec:
            monthly = _monthly_cost(sub) or 0
            savings.append((sub.get("name", key), rec, monthly))
        notes = sub.get("notes", "")
        if "switch to" in notes.lower() or "considering" in notes.lower():
            monthly = _monthly_cost(sub) or 0
            savings.append((sub.get("name", key), notes, monthly))

    if savings:
        print(f"\n  {C['bold']}Savings Opportunities{C['reset']}")
        for name, note, monthly in savings:
            print(f"    {C['yellow']}●{C['reset']} {name:<35} {C['dim']}{note}{C['reset']}")

    # Overdue items
    overdue = [(sub.get("name", k), sub) for k, sub in subs.items() if sub.get("status") == "overdue"]
    if overdue:
        print(f"\n  {C['red']}{C['bold']}Action Required{C['reset']}")
        for name, sub in overdue:
            notes = sub.get("notes", "")
            monthly = _monthly_cost(sub) or 0
            print(f"    {C['red']}●{C['reset']} {name:<35} ${monthly:.2f}/mo  {C['dim']}{notes}{C['reset']}")

    print()


def _expand_env(s):
    """Expand $VAR_NAME in a string from environment."""
    import re
    def repl(m):
        return os.environ.get(m.group(1), m.group(0))
    return re.sub(r'\$([A-Z_][A-Z0-9_]*)', repl, s)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "list"
    status_filter = None
    category_filter = None

    for arg in sys.argv[2:]:
        if arg.startswith("--status="):
            status_filter = arg.split("=", 1)[1]
        if arg.startswith("--category="):
            category_filter = arg.split("=", 1)[1]

    if action == "list":
        list_subscriptions(status_filter=status_filter, category_filter=category_filter)
    elif action == "check":
        check_health()
    elif action == "costs":
        show_costs()
    else:
        print(f"Unknown action: {action}")
        print("Usage: subscriptions.py [list|check|costs]")
        sys.exit(1)

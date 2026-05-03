#!/usr/bin/env python3
"""Audit vector collection health across all Qdrant instances."""

import sys
from pathlib import Path

import yaml
from qdrant_client import QdrantClient

REGISTRIES = Path(__file__).parent.parent / "registries"
STANDARD_MODEL = "BAAI/bge-base-en-v1.5"


def load_registry():
    with open(REGISTRIES / "vector-collections.yaml") as f:
        return yaml.safe_load(f).get("collections", {})


def audit_port(host, port, registry):
    """Audit all collections on a Qdrant port."""
    try:
        client = QdrantClient(host=host, port=port, timeout=5)
        collections = {c.name: c for c in client.get_collections().collections}
    except Exception as e:
        print(f"  UNREACHABLE: {host}:{port} — {e}", file=sys.stderr)
        return [], []

    findings = []
    warnings = []

    # Check registered collections
    for name, config in registry.items():
        if config.get("port", 6333) != port:
            continue

        if name not in collections:
            warnings.append(f"{name}: registered but NOT FOUND on :{port}")
            continue

        info = client.get_collection(name)
        points = info.points_count
        expected = config.get("points_expected", 0)
        model = config.get("embedding_model", "?")
        vtype = config.get("vector_type", "flat")
        quant = config.get("quantization", "none")
        migration = config.get("migration_note", "")

        # Check vector config
        vec_config = info.config.params.vectors
        if isinstance(vec_config, dict):
            # Named vectors (hybrid)
            actual_type = "hybrid" if len(vec_config) > 1 else "named"
            dims = [v.size for v in vec_config.values()]
            dim = dims[0] if dims else "?"
        else:
            actual_type = "flat"
            dim = vec_config.size

        # Quantization check
        actual_quant = "int8" if info.config.quantization_config else "none"

        # Model compliance
        model_ok = model == STANDARD_MODEL
        model_flag = "" if model_ok else f" ⚠ (should be {STANDARD_MODEL})"
        if migration:
            model_flag = f" [{migration}]"

        # Point count deviation
        deviation = ""
        if expected > 0:
            pct = abs(points - expected) / expected * 100
            if pct > 20:
                deviation = f" ⚠ ({pct:.0f}% off expected {expected:,})"

        findings.append({
            "name": name,
            "points": points,
            "dim": dim,
            "model": model,
            "model_ok": model_ok or bool(migration),
            "vtype": actual_type,
            "quant": actual_quant,
            "expected_quant": quant,
            "deviation": deviation,
            "model_flag": model_flag,
        })

    # Check for unregistered collections
    for name in collections:
        registered = any(
            n == name and c.get("port", 6333) == port
            for n, c in registry.items()
        )
        if not registered:
            info = client.get_collection(name)
            warnings.append(f"{name}: EXISTS on :{port} ({info.points_count:,} pts) but NOT in registry")

    return findings, warnings


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Audit vector collection health")
    parser.add_argument("--repo", default=None, help="Filter to a specific repo's collections")
    args = parser.parse_args()

    registry = load_registry()

    if args.repo:
        registry = {k: v for k, v in registry.items() if v.get("owner_repo") == args.repo}

    all_findings = []
    all_warnings = []

    ports = sorted(set(c.get("port", 6333) for c in registry.values()))
    if not ports:
        ports = [6333, 7333]

    for port in ports:
        print(f"\nPort {port}:")
        findings, warnings = audit_port("localhost", port, registry)
        all_findings.extend(findings)
        all_warnings.extend(warnings)

        if findings:
            print(f"  {'Collection':<25} {'Points':>10} {'Dim':>5} {'Type':<8} {'Quant':<6} {'Model'}")
            print(f"  {'-'*85}")
            for f in findings:
                quant_flag = ""
                if f["expected_quant"] != "none" and f["quant"] == "none":
                    quant_flag = " ⚠"
                print(f"  {f['name']:<25} {f['points']:>10,} {f['dim']:>5} {f['vtype']:<8} {f['quant']:<6}{quant_flag} {f['model']}{f['model_flag']}{f['deviation']}")

    if all_warnings:
        print(f"\nWarnings:")
        for w in all_warnings:
            print(f"  ⚠ {w}")

    # Summary
    total_points = sum(f["points"] for f in all_findings)
    non_compliant = sum(1 for f in all_findings if not f["model_ok"])
    print(f"\nSummary: {len(all_findings)} collections, {total_points:,} total points")
    if non_compliant:
        print(f"  {non_compliant} collections need model migration")
    else:
        print(f"  All collections compliant with embedding standard")


if __name__ == "__main__":
    main()

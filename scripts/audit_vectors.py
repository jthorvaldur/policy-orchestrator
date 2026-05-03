#!/usr/bin/env python3
"""Audit vector collection health across all Qdrant instances.

Checks:
- Model compliance (BGE standard vs legacy nomic)
- Sparse vector presence for hybrid collections
- Quantization status
- Point count vs expected
- Staleness (embed state vs source file counts)
- Unregistered collections with actionable recommendations
"""

import json
import sys
from pathlib import Path

import yaml
from qdrant_client import QdrantClient

REGISTRIES = Path(__file__).parent.parent / "registries"
STANDARD_MODEL = "BAAI/bge-base-en-v1.5"
STANDARD_SPARSE = "prithivida/Splade_PP_en_v1"


def load_registry():
    with open(REGISTRIES / "vector-collections.yaml") as f:
        return yaml.safe_load(f).get("collections", {})


def load_repos():
    with open(REGISTRIES / "repos.yaml") as f:
        return {r["name"]: r for r in yaml.safe_load(f).get("repos", [])}


def check_staleness(col_name, col_config, repos):
    """Check if embed state is behind source files."""
    owner = col_config.get("owner_repo")
    if not owner or owner not in repos:
        return None

    repo_path = Path(repos[owner].get("path", "")).expanduser()
    if not repo_path.exists():
        return None

    # Look for embed state files
    state_paths = [
        repo_path / "sdata" / "embed_state.json",
        repo_path / "local" / "embed_state.json",
        repo_path / ".docvec_state.json",
    ]

    state_count = None
    for sp in state_paths:
        if sp.exists():
            try:
                with open(sp) as f:
                    data = json.load(f)
                state_count = len(data.get("embedded_files", data.get("ingested_sessions", [])))
                break
            except (json.JSONDecodeError, KeyError):
                pass

    # Look for source file counts
    source_dirs = [
        repo_path / "sdata" / "md",
        repo_path / "data",
    ]

    source_count = None
    for sd in source_dirs:
        if sd.exists() and sd.is_dir():
            source_count = len(list(sd.glob("*.md"))) or len(list(sd.glob("*")))
            if source_count > 0:
                break

    if state_count is not None and source_count is not None and source_count > 0:
        return {"state": state_count, "source": source_count}

    return None


def audit_port(host, port, registry, repos):
    """Audit all collections on a Qdrant port."""
    try:
        client = QdrantClient(host=host, port=port, timeout=5)
        collections = {c.name: c for c in client.get_collections().collections}
    except Exception as e:
        print(f"  UNREACHABLE: {host}:{port} — {e}", file=sys.stderr)
        return [], []

    findings = []
    warnings = []

    for name, config in registry.items():
        if config.get("port", 6333) != port:
            continue

        if name not in collections:
            warnings.append({"msg": f"{name}: registered but NOT FOUND on :{port}", "action": None})
            continue

        info = client.get_collection(name)
        points = info.points_count
        expected = config.get("points_expected", 0)
        model = config.get("embedding_model", "?")
        vtype = config.get("vector_type", "flat")
        quant = config.get("quantization", "none")
        migration = config.get("migration_note", "")
        expected_sparse = config.get("sparse_model")

        # Vector config analysis
        vec_config = info.config.params.vectors
        has_sparse = False
        if isinstance(vec_config, dict):
            actual_type = "hybrid" if len(vec_config) > 1 else "named"
            dims = [v.size for v in vec_config.values()]
            dim = dims[0] if dims else "?"
            has_sparse = "sparse" in vec_config
        else:
            actual_type = "flat"
            dim = vec_config.size

        # Quantization
        actual_quant = "int8" if info.config.quantization_config else "none"

        # Model compliance
        model_ok = model == STANDARD_MODEL
        model_flag = "" if model_ok else f" ⚠ (should be {STANDARD_MODEL})"
        if migration:
            model_flag = f" [{migration}]"

        # Sparse compliance
        sparse_flag = ""
        if expected_sparse and not has_sparse:
            sparse_flag = " ⚠ NO SPARSE"
        elif vtype == "hybrid" and has_sparse:
            sparse_flag = " +sparse"
        elif vtype == "flat" and expected_sparse:
            sparse_flag = " ⚠ expected hybrid"

        # Point count deviation
        deviation = ""
        if expected > 0:
            pct = abs(points - expected) / expected * 100
            if pct > 20:
                deviation = f" ⚠ ({pct:.0f}% off, expected {expected:,})"

        # Quantization compliance
        quant_flag = ""
        if quant != "none" and actual_quant == "none":
            quant_flag = " ⚠ needs INT8"
        elif points > 10000 and actual_quant == "none" and quant == "none":
            quant_flag = " (recommend INT8)"

        # Staleness
        staleness = check_staleness(name, config, repos)
        stale_flag = ""
        if staleness:
            behind = staleness["source"] - staleness["state"]
            if behind > 0:
                stale_flag = f" ⚠ {behind} files not embedded ({staleness['state']}/{staleness['source']})"

        findings.append({
            "name": name,
            "points": points,
            "dim": dim,
            "model": model,
            "model_ok": model_ok or bool(migration),
            "vtype": actual_type,
            "has_sparse": has_sparse,
            "quant": actual_quant,
            "expected_quant": quant,
            "deviation": deviation,
            "model_flag": model_flag,
            "sparse_flag": sparse_flag,
            "quant_flag": quant_flag,
            "stale_flag": stale_flag,
        })

    # Unregistered collections
    for name in collections:
        registered = any(
            n == name and c.get("port", 6333) == port
            for n, c in registry.items()
        )
        if not registered:
            info = client.get_collection(name)
            pts = info.points_count

            # Actionable recommendation
            if pts == 0:
                action = "DROP (empty)"
            elif pts < 100:
                action = "REVIEW — small, may be experimental"
            elif "qwen" in name or "experimental" in name:
                action = "DROP or KEEP — experimental model, not standard"
            elif name.startswith("legal_docs") and name != "legal_docs_v2":
                action = "DROP — superseded by legal_docs_v2"
            else:
                action = "ADD to registry or DROP"

            warnings.append({
                "msg": f"{name}: on :{port} ({pts:,} pts) not in registry",
                "action": action,
            })

    return findings, warnings


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Audit vector collection health")
    parser.add_argument("--repo", default=None, help="Filter to a specific repo's collections")
    args = parser.parse_args()

    registry = load_registry()
    repos = load_repos()

    if args.repo:
        registry = {k: v for k, v in registry.items() if v.get("owner_repo") == args.repo}

    all_findings = []
    all_warnings = []

    ports = sorted(set(c.get("port", 6333) for c in registry.values()))
    if not ports:
        ports = [6333, 7333]

    for port in ports:
        print(f"\nPort {port}:")
        findings, warnings = audit_port("localhost", port, registry, repos)
        all_findings.extend(findings)
        all_warnings.extend(warnings)

        if findings:
            print(f"  {'Collection':<25} {'Points':>10} {'Dim':>5} {'Type':<8} {'Quant':<6} {'Sparse':<12} {'Model'}")
            print(f"  {'-' * 100}")
            for f in findings:
                sparse_col = f["sparse_flag"] or ("yes" if f["has_sparse"] else "no")
                print(
                    f"  {f['name']:<25} {f['points']:>10,} {f['dim']:>5} "
                    f"{f['vtype']:<8} {f['quant']:<6} {sparse_col:<12} "
                    f"{f['model']}{f['model_flag']}"
                )
                if f["deviation"]:
                    print(f"  {'':>25} {f['deviation']}")
                if f["quant_flag"]:
                    print(f"  {'':>25} {f['quant_flag']}")
                if f["stale_flag"]:
                    print(f"  {'':>25} {f['stale_flag']}")

    if all_warnings:
        print(f"\nWarnings:")
        for w in all_warnings:
            print(f"  ⚠ {w['msg']}")
            if w.get("action"):
                print(f"    → {w['action']}")

    # Summary
    total_points = sum(f["points"] for f in all_findings)
    non_compliant = sum(1 for f in all_findings if not f["model_ok"])
    no_sparse = sum(1 for f in all_findings if "NO SPARSE" in (f.get("sparse_flag") or ""))
    stale = sum(1 for f in all_findings if f.get("stale_flag"))

    print(f"\nSummary: {len(all_findings)} collections, {total_points:,} total points")
    issues = []
    if non_compliant:
        issues.append(f"{non_compliant} need model migration")
    if no_sparse:
        issues.append(f"{no_sparse} missing sparse vectors")
    if stale:
        issues.append(f"{stale} have un-embedded source files")
    if issues:
        print(f"  Issues: {' | '.join(issues)}")
    else:
        print(f"  All collections healthy")


if __name__ == "__main__":
    main()

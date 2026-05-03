#!/usr/bin/env python3
"""Trigger embedding for a repo's vector collection via docvec."""

import subprocess
import sys
from pathlib import Path

import yaml

REGISTRIES = Path(__file__).parent.parent / "registries"


def load_repos():
    with open(REGISTRIES / "repos.yaml") as f:
        return {r["name"]: r for r in yaml.safe_load(f).get("repos", [])}


def load_collections():
    with open(REGISTRIES / "vector-collections.yaml") as f:
        return yaml.safe_load(f).get("collections", {})


def embed(repo, full=False, gpu=False, collection=None):
    """Trigger embed for a repo."""
    repos = load_repos()
    collections = load_collections()

    if repo not in repos:
        print(f"Repo '{repo}' not in registry", file=sys.stderr)
        return

    repo_config = repos[repo]
    repo_path = Path(repo_config["path"]).expanduser()

    if not repo_path.exists():
        print(f"Repo path not found: {repo_path}", file=sys.stderr)
        return

    # Find collections owned by this repo
    repo_collections = {
        name: cfg for name, cfg in collections.items()
        if cfg.get("owner_repo") == repo
    }

    if collection:
        if collection in repo_collections:
            repo_collections = {collection: repo_collections[collection]}
        else:
            print(f"Collection '{collection}' not owned by repo '{repo}'", file=sys.stderr)
            return

    if not repo_collections:
        print(f"No vector collections registered for repo '{repo}'", file=sys.stderr)
        return

    for col_name, col_config in repo_collections.items():
        port = col_config.get("port", 6333)
        model = col_config.get("embedding_model", "BAAI/bge-base-en-v1.5")

        print(f"\nEmbedding: {col_name} (:{port})")
        print(f"  Repo: {repo_path}")
        print(f"  Model: {model}")
        print(f"  Mode: {'full' if full else 'incremental'}")

        # Check if repo has its own embed script
        repo_embed = repo_path / "scripts" / "embed.sh"
        repo_embed_py = repo_path / "scripts" / "embed.py"

        if repo_embed.exists():
            cmd = ["bash", str(repo_embed)]
            if full:
                cmd.append("--full")
            print(f"  Running: {' '.join(cmd)}")
            subprocess.run(cmd, cwd=str(repo_path))
        elif repo_embed_py.exists():
            cmd = ["uv", "run", "python", str(repo_embed_py)]
            if full:
                cmd.append("--full")
            print(f"  Running: {' '.join(cmd)}")
            subprocess.run(cmd, cwd=str(repo_path))
        else:
            # Use docvec directly
            print(f"  No repo-specific embed script found.")
            print(f"  To embed manually:")
            print(f"    cd {repo_path}")
            print(f"    uv run python -m docvec embed --collection {col_name} --port {port}")
            if gpu:
                print(f"  GPU mode: use Vast.ai pipeline")
                print(f"    cd {repo_path}")
                print(f"    uv run python -m src.scripts.embed_gpu --output embeddings.jsonl")
                print(f"    uv run python -m src.scripts.upsert_from_jsonl --input embeddings.jsonl --collection {col_name} --port {port}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Trigger embedding for a repo")
    parser.add_argument("--repo", required=True, help="Repo name from registry")
    parser.add_argument("--full", action="store_true", help="Full re-embed (clear state)")
    parser.add_argument("--gpu", action="store_true", help="Offload to Vast.ai GPU")
    parser.add_argument("--collection", default=None, help="Specific collection")

    args = parser.parse_args()
    embed(repo=args.repo, full=args.full, gpu=args.gpu, collection=args.collection)


if __name__ == "__main__":
    main()

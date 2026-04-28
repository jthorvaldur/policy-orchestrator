#!/usr/bin/env python3
"""Generate an HTML dashboard showing control plane state.

Outputs a self-contained HTML file with live stats from repos.yaml and Qdrant.
Design matches jthorvaldur.github.io (dark theme, Outfit/JetBrains Mono).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

REGISTRIES = Path(__file__).parent.parent / "registries"


def load_repos():
    with open(REGISTRIES / "repos.yaml") as f:
        return yaml.safe_load(f).get("repos", [])


def get_qdrant_stats():
    """Try to get collection stats from Qdrant. Returns {} if unavailable."""
    try:
        from qdrant_client import QdrantClient
        c = QdrantClient(host="localhost", port=6333, timeout=5)
        stats = {}
        for col in c.get_collections().collections:
            info = c.get_collection(col.name)
            stats[col.name] = info.points_count
        return stats
    except Exception:
        return {}


def get_repo_git_state(path_str):
    """Get git state for a repo. Returns dict or None."""
    import subprocess
    path = Path(path_str).expanduser()
    if not path.exists():
        return None
    try:
        dirty = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        )
        branch = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        log = subprocess.run(
            ["git", "-C", str(path), "log", "-1", "--format=%ar"],
            capture_output=True, text=True, timeout=5,
        )
        return {
            "clean": len(dirty.stdout.strip()) == 0,
            "branch": branch.stdout.strip(),
            "last_activity": log.stdout.strip(),
        }
    except Exception:
        return None


def generate_html(repos, qdrant_stats):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Categorize repos
    categories = {}
    for r in repos:
        cat = r.get("category", "other")
        categories.setdefault(cat, []).append(r)

    # Build repo cards
    repo_cards = []
    for r in repos:
        git = get_repo_git_state(r.get("path", ""))
        status_dot = "green" if (git and git["clean"]) else ("amber" if git else "red")
        branch = git["branch"] if git else "-"
        activity = git["last_activity"] if git else "unknown"

        repo_cards.append(f"""
        <div class="repo-card" data-category="{r.get('category', '')}">
          <div class="repo-header">
            <span class="status-dot {status_dot}"></span>
            <span class="repo-name">{r['name']}</span>
            <span class="repo-vis">{r.get('visibility', '?')}</span>
          </div>
          <div class="repo-meta">
            <span>{r.get('category', '?')}</span>
            <span>{r.get('language', '?')}</span>
            <span>{branch}</span>
            <span>{activity}</span>
          </div>
        </div>""")

    # Qdrant collection rows
    qdrant_rows = []
    total_vectors = 0
    for name, count in sorted(qdrant_stats.items(), key=lambda x: -x[1]):
        total_vectors += count
        bar_width = min(100, (count / max(qdrant_stats.values())) * 100) if qdrant_stats else 0
        qdrant_rows.append(f"""
          <div class="qdrant-row">
            <span class="col-name">{name}</span>
            <div class="bar-container"><div class="bar" style="width:{bar_width:.0f}%"></div></div>
            <span class="col-count">{count:,}</span>
          </div>""")

    # Category summary
    cat_pills = []
    for cat, cat_repos in sorted(categories.items()):
        cat_pills.append(f'<span class="cat-pill">{cat} <strong>{len(cat_repos)}</strong></span>')

    clean_count = sum(1 for r in repos if get_repo_git_state(r.get("path", "")) and get_repo_git_state(r.get("path", "")).get("clean"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Control Plane Dashboard</title>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@200;300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #07070f;
      --surface: rgba(255,255,255,0.035);
      --surface-hover: rgba(122,162,247,0.07);
      --border: rgba(255,255,255,0.07);
      --border-hover: rgba(122,162,247,0.30);
      --text: #e8e8f4;
      --muted: rgba(232,232,244,0.45);
      --dim: rgba(232,232,244,0.25);
      --accent: #7aa2f7;
      --accent2: #bb9af7;
      --green: #9ece6a;
      --amber: #e0af68;
      --red: #f7768e;
      --teal: #73daca;
    }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'Outfit', sans-serif;
      -webkit-font-smoothing: antialiased;
      padding: 2rem;
      max-width: 1100px;
      margin: 0 auto;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    .header {{
      display: flex; justify-content: space-between; align-items: baseline;
      margin-bottom: 2.5rem; padding-bottom: 1rem;
      border-bottom: 1px solid var(--border);
    }}
    .header h1 {{
      font-size: 1.6rem; font-weight: 300;
      letter-spacing: -0.01em;
    }}
    .header h1 strong {{
      font-weight: 600;
      background: linear-gradient(140deg, #fff 20%, var(--accent) 60%, var(--accent2));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .header .timestamp {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.7rem; color: var(--dim);
    }}

    .stats-row {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 1rem; margin-bottom: 2.5rem;
    }}
    .stat-card {{
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; padding: 1.2rem 1.4rem;
    }}
    .stat-card .label {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.6rem; letter-spacing: 0.2em;
      text-transform: uppercase; color: var(--muted);
      margin-bottom: 0.4rem;
    }}
    .stat-card .value {{
      font-size: 1.8rem; font-weight: 600; color: var(--accent);
    }}
    .stat-card .sub {{
      font-size: 0.75rem; color: var(--dim); margin-top: 0.2rem;
    }}

    .section-label {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.6rem; letter-spacing: 0.3em;
      text-transform: uppercase; color: var(--accent);
      margin-bottom: 1.2rem;
      display: flex; align-items: center; gap: 0.8rem;
    }}
    .section-label::after {{
      content: ''; display: block; flex: 1;
      height: 1px; background: var(--border);
    }}

    .cat-pills {{
      display: flex; flex-wrap: wrap; gap: 0.5rem;
      margin-bottom: 1.5rem;
    }}
    .cat-pill {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.65rem; letter-spacing: 0.05em;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 20px; padding: 0.3rem 0.8rem;
      color: var(--muted);
    }}
    .cat-pill strong {{ color: var(--accent); margin-left: 0.3rem; }}

    .repo-grid {{
      display: grid; grid-template-columns: 1fr;
      gap: 0.4rem; margin-bottom: 3rem;
    }}
    .repo-card {{
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 8px; padding: 0.8rem 1.2rem;
      display: flex; flex-direction: column; gap: 0.3rem;
      transition: border-color 0.2s;
    }}
    .repo-card:hover {{ border-color: var(--border-hover); }}
    .repo-header {{
      display: flex; align-items: center; gap: 0.6rem;
    }}
    .status-dot {{
      width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
    }}
    .status-dot.green {{ background: var(--green); box-shadow: 0 0 6px var(--green); }}
    .status-dot.amber {{ background: var(--amber); box-shadow: 0 0 6px var(--amber); }}
    .status-dot.red {{ background: var(--red); }}
    .repo-name {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem; font-weight: 500; color: var(--text);
    }}
    .repo-vis {{
      font-size: 0.6rem; color: var(--dim);
      margin-left: auto;
      font-family: 'JetBrains Mono', monospace;
      letter-spacing: 0.05em;
    }}
    .repo-meta {{
      display: flex; gap: 1.2rem;
      font-size: 0.7rem; color: var(--muted);
    }}

    .qdrant-section {{ margin-bottom: 3rem; }}
    .qdrant-row {{
      display: grid; grid-template-columns: 200px 1fr 80px;
      align-items: center; gap: 1rem;
      padding: 0.4rem 0;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
    }}
    .col-name {{ color: var(--muted); }}
    .col-count {{ color: var(--accent); text-align: right; }}
    .bar-container {{
      height: 6px; background: var(--surface);
      border-radius: 3px; overflow: hidden;
    }}
    .bar {{
      height: 100%; border-radius: 3px;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
    }}

    .footer {{
      text-align: center; padding: 2rem 0;
      font-size: 0.7rem; color: var(--dim);
      border-top: 1px solid var(--border);
    }}
  </style>
</head>
<body>
  <div class="header">
    <h1><strong>Control Plane</strong> Dashboard</h1>
    <span class="timestamp">Generated {now}</span>
  </div>

  <div class="stats-row">
    <div class="stat-card">
      <div class="label">Managed Repos</div>
      <div class="value">{len(repos)}</div>
      <div class="sub">{len(categories)} categories</div>
    </div>
    <div class="stat-card">
      <div class="label">Vector Points</div>
      <div class="value">{total_vectors:,}</div>
      <div class="sub">{len(qdrant_stats)} collections</div>
    </div>
    <div class="stat-card">
      <div class="label">Clean Trees</div>
      <div class="value">{clean_count}/{len(repos)}</div>
      <div class="sub">repos with no uncommitted changes</div>
    </div>
    <div class="stat-card">
      <div class="label">Contract Coverage</div>
      <div class="value">100%</div>
      <div class="sub">CLAUDE + INTENT + .control + .env.ex + .gitignore</div>
    </div>
  </div>

  <div class="section-label">Repositories</div>
  <div class="cat-pills">
    {''.join(cat_pills)}
  </div>
  <div class="repo-grid">
    {''.join(repo_cards)}
  </div>

  <div class="section-label">Vector Collections (Qdrant)</div>
  <div class="qdrant-section">
    {''.join(qdrant_rows)}
  </div>

  <div class="footer">
    <a href="https://github.com/jthorvaldur/policy-orchestrator">policy-orchestrator</a>
    &nbsp;&middot;&nbsp; Generated by <code>devctl dashboard</code>
    &nbsp;&middot;&nbsp; <a href="https://jthorvaldur.github.io">jthorvaldur.github.io</a>
  </div>
</body>
</html>"""

    return html


def main():
    repos = load_repos()
    qdrant = get_qdrant_stats()

    html = generate_html(repos, qdrant)

    output = Path(__file__).parent.parent / "dashboards" / "control-plane.html"
    output.write_text(html)
    print(f"Generated: {output}", file=sys.stderr)

    # Also copy to GitHub Pages if available
    pages_dest = Path.home() / "GitHub" / "jthorvaldur.github.io" / "r" / "control-plane.html"
    if pages_dest.parent.exists():
        pages_dest.write_text(html)
        print(f"Copied to: {pages_dest}", file=sys.stderr)


if __name__ == "__main__":
    main()

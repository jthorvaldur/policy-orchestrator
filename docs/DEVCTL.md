# devctl Command Reference

> `devctl` -- multi-repo development control plane.
> Run with no arguments for a live dashboard. Run `devctl <command> --help` for full option details.

---

## Repos

| Command | Description |
|---------|-------------|
| `status` | Show git status of all registered repos |
| `list` | List all registered repos with metadata |
| `audit` | Audit repos for policy compliance |
| `discover` | Discover and classify all git repos on the filesystem |
| `inventory` | Query the saved inventory from last discovery run |

### status

Show git status (clean/dirty) across all registered repos.

```
devctl status [--category CATEGORY] [--dirty]
```

| Option | Description |
|--------|-------------|
| `--category` | Filter by repo category |
| `--dirty` | Show only repos with uncommitted changes |

```
$ devctl status --dirty
  vpin          ● 2 modified
  div_legal     ● 1 untracked
```

### list

List all registered repos from `registries/repos.yaml`.

```
devctl list [--category CATEGORY]
```

```
$ devctl list --category=legal
Name                           Category           Language        Visibility   Priority
-----------------------------------------------------------------------------------------------
div_legal                      legal              python          private      1
```

### audit

Check repos for structural compliance (INTENT.md present, .control/repo.yaml, etc).

```
devctl audit [--repo REPO] [--all]
```

| Option | Description |
|--------|-------------|
| `--repo` | Audit a specific repo by name |
| `--all` | Audit all repos (default: true) |

```
$ devctl audit --repo=vpin
  vpin: PASS  INTENT.md OK  .control/repo.yaml OK
```

### discover

Scan the filesystem for git repos, classify lifecycle and risk, detect duplicates.

```
devctl discover [--lifecycle LIFECYCLE] [--risk RISK] [--duplicates-only]
                [--unregistered-only] [--save] [--format {table,json,yaml}]
```

| Option | Description |
|--------|-------------|
| `--lifecycle` | Filter: active, work-org, reference, duplicate, backup, orphan, empty, dependency, stale |
| `--risk` | Filter by minimum risk: critical, high, medium, low |
| `--duplicates-only` | Show only duplicate groups |
| `--unregistered-only` | Show only repos not in the registry |
| `--save` | Write results to `registries/inventory.yaml` |
| `--format` | Output format: table (default), json, yaml |

```
$ devctl discover --unregistered-only --format=table
Name                           Location       Lifecycle    Risk       Registered
--------------------------------------------------------------------------------
old-experiment                 ~/Projects     orphan       medium
```

### inventory

Query the cached inventory from the last `devctl discover --save`.

```
devctl inventory [--lifecycle LIFECYCLE] [--risk RISK]
```

```
$ devctl inventory --risk=high
Name                           Location       Lifecycle    Risk       Registered
--------------------------------------------------------------------------------
legacy-secrets                 ~/old          stale        high
```

---

## Data

| Command | Description |
|---------|-------------|
| `db-status` | Show database status: repos, collections, live counts |
| `search` | Unified semantic search across all vector collections |
| `embed` | Trigger embedding for a repo's vector collection |
| `audit-vectors` | Audit vector collection health across Qdrant instances |

### db-status

Show Qdrant collection status, point counts, and data source info.

```
devctl db-status [--repo REPO] [--port PORT]
```

| Option | Description |
|--------|-------------|
| `--repo` | Show only this repo's collections |
| `--port` | Show only this Qdrant port (e.g. 6333, 7333) |

```
$ devctl db-status --repo=div_legal
  div_legal_chunks   :6333   12,847 vectors   dim=384
```

### search

Unified semantic search across vector collections.

**Default scope excludes AI-assistant chats** (`claude_code_sessions`,
`claude_chats_ai`, `openai_chats`) — those carry the user's questions and
assertions, not ground truth, and they crowd out source documents. The
default search covers ingested docs, court files, facts, and algorithms.

```
devctl search QUERY [-n LIMIT] [-c COLLECTION] [--collections COLS]
                    [--claude] [--algos] [--facts] [--all] [--rerank]
```

| Option | Description |
|--------|-------------|
| `-n`, `--limit` | Number of results (default: 20) |
| `-c`, `--collection` | Search a specific collection |
| `--collections` | Comma-separated collection names |
| `--claude` | AI-assistant chats only (Claude Code, Claude.ai, ChatGPT) |
| `--algos` | Algorithms collection only |
| `--facts` | Fact collections only (fact_registry, case_facts, case_facts_semantic) |
| `--all` | Include AI chats alongside the default scope |
| `--rerank/--no-rerank` | Cross-encoder reranking (default: on) |

Scope flags combine: `--facts --algos` searches both groups.

```
$ devctl search "custody modification timeline" -n 5        # docs/court files/facts
$ devctl search "deemed admissions" --facts                 # litigation playbook
$ devctl search "vector ingest pipeline" --claude           # past AI sessions
```

### embed

Trigger embedding pipeline for a repo's vector collection.

```
devctl embed --repo REPO [--full] [--gpu] [--collection COLLECTION]
```

| Option | Description |
|--------|-------------|
| `--repo` | **(required)** Repo name from registry |
| `--full` | Full re-embed, clearing previous state |
| `--gpu` | Offload to Vast.ai GPU |
| `--collection` | Target a specific collection |

```
$ devctl embed --repo=div_legal --full
  Clearing state... embedding 847 documents...
  Done: 12,847 vectors in div_legal_chunks
```

### audit-vectors

Audit vector collection health: orphaned points, dimension mismatches, stale data.

```
devctl audit-vectors [--repo REPO]
```

```
$ devctl audit-vectors
  div_legal_chunks     :6333   OK    12,847 pts   dim=384
  contacts_vectors     :6333   OK     3,201 pts   dim=384
  session_chunks       :7333   WARN   stale (14d)
```

---

## Pages

| Command | Description |
|---------|-------------|
| `deploy-pages` | Deploy encrypted HTML pages to jthorvaldur.github.io |
| `audit-pages` | Audit GitHub Pages for encryption and security compliance |
| `verify-pages` | Live-verify deployed pages decrypt correctly via HTTPS |

### deploy-pages

Build and deploy encrypted HTML pages to the GitHub Pages hub repo.

```
devctl deploy-pages [--section SECTION] [--pending] [--dry-run]
                    [--push] [--verify] [--auto]
```

| Option | Description |
|--------|-------------|
| `--section` | Deploy a specific section only |
| `--pending` | Include sections not yet deployed |
| `--dry-run` | Show what would be deployed |
| `--push` | Commit and push the hub repo after deploy |
| `--verify` | Verify encrypted pages decrypt correctly |
| `--auto` | Auto-detect section from current directory |

```
$ devctl deploy-pages --section=legal --verify --push
  Deploying legal... 23 pages encrypted
  Verify: all pages decrypt OK
  Pushed to jthorvaldur.github.io
```

### audit-pages

Audit all GitHub Pages for encryption policy compliance (no plaintext sensitive data).

```
devctl audit-pages
```

```
$ devctl audit-pages
  legal/         23 files   all encrypted   PASS
  financial/     12 files   all encrypted   PASS
```

### verify-pages

Fetch deployed pages over HTTPS and verify they decrypt correctly.

```
devctl verify-pages [--section SECTION] [--quick]
```

| Option | Description |
|--------|-------------|
| `--section` | Verify a specific section only |
| `--quick` | Test one page per section instead of all |

```
$ devctl verify-pages --quick
  legal/index.html       200   decrypts OK
  financial/index.html   200   decrypts OK
```

---

## Secrets

| Command | Description |
|---------|-------------|
| `secrets` | Check repos for secret hygiene violations |
| `validate-secrets` | Validate repos have the API keys their profiles require |

### secrets

Scan repos for leaked secrets, .env files in git, and hygiene violations.

```
devctl secrets [--repo REPO]
```

```
$ devctl secrets --repo=vpin
  vpin: PASS  no secrets detected  .env in .gitignore
```

### validate-secrets

Validate that each repo has the API keys its configuration requires.

```
devctl validate-secrets [--repo REPO] [--live] [--keys-only]
```

| Option | Description |
|--------|-------------|
| `--repo` | Validate a specific repo |
| `--live` | Ping endpoints to verify keys actually work |
| `--keys-only` | Just show key inventory without validation |

```
$ devctl validate-secrets --repo=div_legal --live
  OPENAI_API_KEY       present   live: OK
  QDRANT_API_KEY       present   live: OK
```

---

## Facts

| Command | Description |
|---------|-------------|
| `log-fact` | Log a classified fact with provenance and confidence |
| `query-facts` | Query the fact registry with filtering |
| `log-feedback` | Log a calibration event to the feedback collection |
| `query-feedback` | Query feedback events for calibration notes |

### log-fact

Log a fact with source type, confidence level, and domain classification.

```
devctl log-fact --fact TEXT --source-type TYPE --confidence LEVEL --domain DOMAIN
               [--source-ref REF] [--source-date DATE] [--claimed-by WHO]
               [--contradicts TEXT] [--repo REPO] [--notes TEXT]
```

| Option | Values |
|--------|--------|
| `--fact` | **(required)** The factual claim |
| `--source-type` | **(required)** financial_download, court_document, tax_document, email, text_message, conversation, medical_record, legal_filing, calculation, public_record, photograph, other |
| `--confidence` | **(required)** verified, documented, asserted, disputed, inferred, unknown |
| `--domain` | **(required)** financial, legal, medical, personal, technical, property, employment |
| `--source-ref` | File path or document reference |
| `--source-date` | Date the fact pertains to (YYYY-MM-DD) |
| `--claimed-by` | Who made this claim |
| `--contradicts` | What this fact contradicts |
| `--repo` | Originating repo |
| `--notes` | Additional context |

```
$ devctl log-fact \
    --fact "Property appraised at $425,000" \
    --source-type court_document \
    --confidence documented \
    --domain property \
    --source-date 2024-06-15
```

### query-facts

Semantic search and filtered queries against the fact registry.

```
devctl query-facts [QUERY] [--domain DOMAIN] [--confidence LEVEL]
                   [--min-confidence LEVEL] [--source-type TYPE]
                   [--repo REPO] [--limit N] [--all]
```

| Option | Description |
|--------|-------------|
| `QUERY` | Optional semantic search query |
| `--domain` | Filter: financial, legal, medical, personal, technical, property, employment |
| `--confidence` | Exact confidence match |
| `--min-confidence` | Show facts at this confidence or higher |
| `--source-type` | Filter by source type |
| `--repo` | Filter by originating repo |
| `--limit` | Number of results (default: 10) |
| `--all` | Show all fields including notes |

```
$ devctl query-facts "property valuation" --domain=property --min-confidence=documented
  0.93  [documented]  Property appraised at $425,000  (2024-06-15)
  0.87  [verified]    Tax assessed value $398,000      (2024-01-01)
```

### log-feedback

Log a calibration event (correction, confirmation, mode shift, or observation).

```
devctl log-feedback --type TYPE --signal TEXT [--action TEXT] [--delta TEXT]
                    [--rule TEXT] [--repo REPO] [--scope {all_sessions,repo_specific}]
```

| Option | Description |
|--------|-------------|
| `--type` | **(required)** correction, confirmation, mode_shift, observation |
| `--signal` | **(required)** What the user said/did |
| `--action` | What the agent did |
| `--delta` | What was wrong / what changed |
| `--rule` | The learned calibration rule |
| `--repo` | Which repo this applies to |
| `--scope` | all_sessions (default) or repo_specific |

```
$ devctl log-feedback \
    --type correction \
    --signal "Don't create markdown files unless asked" \
    --delta "Agent was proactively creating summary docs" \
    --rule "Never create .md files without explicit request"
```

### query-feedback

Query feedback events, optionally with semantic search.

```
devctl query-feedback [QUERY] [--repo REPO] [--type TYPE] [--limit N]
```

| Option | Description |
|--------|-------------|
| `QUERY` | Optional semantic search query |
| `--repo` | Filter to a specific repo |
| `--type` | Filter: correction, confirmation, mode_shift, observation |
| `--limit` | Number of results (default: 5) |

```
$ devctl query-feedback "file creation" --type=correction
  [correction]  "Don't create markdown files unless asked"
                rule: Never create .md files without explicit request
```

---

## Build

| Command | Description |
|---------|-------------|
| `provenance` | Track build provenance -- what generated each output |
| `benchmark` | Benchmark system operations (embed, upsert, query, encrypt) |
| `health` | System health check -- services, data, repos, pages, disk |

### provenance

Track what generated each output file and how to recreate it.

```
devctl provenance {show,stale,rebuild,list} [PATH] [--repo REPO]
```

| Action | Description |
|--------|-------------|
| `show PATH` | Show provenance for a specific output file |
| `stale` | List outputs whose inputs have changed |
| `rebuild` | Rebuild the provenance index |
| `list` | List all tracked outputs (optionally filtered by `--repo`) |

```
$ devctl provenance stale
  div_legal/output/timeline.html   stale (input modified 2d ago)

$ devctl provenance show div_legal/output/timeline.html
  generator: scripts/build_timeline.py
  inputs:    sdata/md/timeline_*.md (3 files)
  last_built: 2024-06-10T14:22:00
```

### benchmark

Run performance benchmarks for system operations.

```
devctl benchmark [--category CATEGORY] [--compare] [--project N]
```

| Option | Description |
|--------|-------------|
| `--category` | Only run: embed, db_upsert, db_query, generate |
| `--compare` | Compare against historical results |
| `--project` | Project time at this scale (number of items) |

```
$ devctl benchmark --category=db_query --compare
  db_query   p50=12ms  p99=45ms  (prev: p50=14ms  -14%)
```

### health

Comprehensive system health check: Docker, Ollama, Qdrant, Postgres, repos, pages, disk.

```
devctl health
```

```
$ devctl health
  Services
  ● Docker       3 containers  infra-qdrant-1, infra-postgres-1, infra-qdrant-sensitive-1
  ● Ollama       2 models  nomic-embed-text:latest, llama3:latest

  Data
  ● Qdrant :6333  4 collections  16,048 vectors
  ● Qdrant :7333  2 collections   8,421 vectors
  ● Postgres     :5433  12 tables  caseledger

  Repos
  ● Repos        21 registered  23 on disk  20 clean  3 dirty

  Pages
  ● GitHub Pages  3 deployed  1 pending  35 HTML files  35 encrypted

  Build
  ● Provenance   47 builds tracked  8 repos
  ● Benchmarks   23 measurements on file

  Disk
  ● Storage      142GB free (65%)  ~/GitHub = 4.2G
```

---

## Tools

| Command | Description |
|---------|-------------|
| `sync` | Sync control plane templates to managed repos |
| `dashboard` | Generate HTML dashboard and deploy to GitHub Pages |
| `readme` | Generate or augment README.md for a managed repo |
| `policy` | Lint repos against hard and soft policies |
| `ingest-sessions` | Ingest Claude Code sessions into Qdrant |
| `search-sessions` | Semantic search across Claude Code sessions |

### sync

Push control plane templates (INTENT.md, .env.example, .gitignore) to managed repos.

```
devctl sync [--files FILES] [--repo REPO] [--force] [--dry-run] [--all-templates]
```

| Option | Description |
|--------|-------------|
| `--files` | Comma-separated template files to sync |
| `--repo` | Sync to a specific repo only |
| `--force` | Overwrite existing files |
| `--dry-run` | Show what would be synced |
| `--all-templates` | Sync INTENT.md, .env.example, .gitignore |

```
$ devctl sync --all-templates --dry-run
  Would sync INTENT.md -> vpin/INTENT.md
  Would sync INTENT.md -> div_legal/INTENT.md
  Would sync .env.example -> vpin/.env.example
```

### dashboard

Generate the HTML dashboard and deploy to GitHub Pages.

```
devctl dashboard
```

```
$ devctl dashboard
  Generated dashboard.html with 21 repos, 6 categories
  Deployed to jthorvaldur.github.io
```

### readme

Generate or update README.md for a managed repo using CLAUDE.md, CLI help, and directory structure.

```
devctl readme --repo REPO [--init] [--update] [--dry-run]
```

| Option | Description |
|--------|-------------|
| `--repo` | **(required)** Repo name from registry |
| `--init` | Generate from scratch even if README exists |
| `--update` | Only refresh auto-generated sections |
| `--dry-run` | Print to stdout, don't write |

```
$ devctl readme --repo=vpin --update
  Updated: Commands, Architecture, Status Badge sections
  Wrote: ~/GitHub/vpin/README.md
```

### policy

Lint repos against hard policies (ERROR) and soft policies (WARN).

```
devctl policy [--repo REPO]
```

```
$ devctl policy --repo=div_legal
  [PASS]  no-secrets: no .env files committed
  [PASS]  git-main: default branch is main
  [WARN]  docs-coverage: README.md missing Commands section
```

### ingest-sessions

Ingest Claude Code chat sessions into Qdrant for later semantic search.

```
devctl ingest-sessions [--repo REPO] [--all] [--dry-run]
```

| Option | Description |
|--------|-------------|
| `--repo` | Only ingest sessions from this repo |
| `--all` | Re-ingest all sessions, ignoring previous state |
| `--dry-run` | Count what would be ingested without doing it |

```
$ devctl ingest-sessions --repo=div_legal
  Found 14 new sessions for div_legal
  Ingested 14 sessions -> 1,247 chunks
```

### search-sessions

Semantic search across ingested Claude Code sessions.

```
devctl search-sessions QUERY [--repo REPO] [--role {user,assistant}] [--limit N] [--full]
```

| Option | Description |
|--------|-------------|
| `QUERY` | **(required)** Search query |
| `--repo` | Filter to a specific repo |
| `--role` | Filter by message role: user or assistant |
| `--limit` | Number of results (default: 10) |
| `--full` | Show full chunk text |

```
$ devctl search-sessions "vector embedding pipeline" --repo=div_legal --limit=3
  0.92  div_legal  assistant  "The embedding pipeline uses nomic-embed..."
  0.88  div_legal  user       "How do I re-embed the legal documents?"
  0.85  div_legal  assistant  "Run devctl embed --repo=div_legal --full..."
```

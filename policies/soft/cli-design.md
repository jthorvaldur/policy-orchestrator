# Preference: CLI Design (SOFT)

> **Type:** Soft policy (advisory)
> **Scope:** All CLI commands in devctl and managed repos (sovereign, rights, embed, etc.)
> **Rationale:** Consistent, scannable CLI output across 60+ repos and 30+ commands

## 1. Output Format

### Header

Every command prints a header with command name and scope:

```
  devctl <command>  <count> <units>
```

Bold command name, dim gray for the unit count. Leading two-space indent. Blank line after.

### Body

- **Colored dots** for item-level status: `●` green (pass), `●` yellow (warn), `●` red (error)
- **Inline icons** for individual findings: `✓` pass, `✗` fail, `!` warning, `–` skipped
- **Clean items hidden by default** in summary views — shown with `--verbose` or `--repo=X`
- **Sort by severity**: errors first, then warnings, then clean
- **Dim gray** (`\033[90m`) for metadata, categories, labels, and secondary information
- **Bold** (`\033[1m`) for repo names and primary identifiers
- **Indentation**: 2 spaces for items, 6 spaces for sub-findings

```
  ● repo-name  category · visibility
      ✗ missing README.md
      ! dirty git tree (3 files)
```

### Summary bar

Every command ends with a horizontal rule and counts:

```
  ──────────────────────────────────────────────────
  <count> <units>  ● N clean  ● N warnings  ● N errors
```

Omit zero categories (don't print `● 0 errors`). Parts are colored to match their dot.

## 2. Color Scheme (ANSI)

All scripts share a single `C` dict. These are the canonical codes:

```python
C = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "dim":    "\033[90m",     # gray — metadata, labels, secondary text
    "green":  "\033[32m",     # pass, healthy, clean
    "yellow": "\033[33m",     # warning, dirty, drift
    "red":    "\033[31m",     # error, failure, missing
    "cyan":   "\033[36m",     # info, links, badges, policy tags
    "mag":    "\033[35m",     # accent (rarely used)
    "white":  "\033[37m",     # neutral emphasis
    "blue":   "\033[34m",     # rarely used — reserved for links in rich terminals
}
```

Rules:
- Never use raw escape codes inline — always reference the `C` dict
- Respect `NO_COLOR` env var (if set, disable all color)
- JSON/YAML output modes (`--format json`) must never include ANSI codes

## 3. Command Conventions

### Flags

| Flag | Purpose | Notes |
|------|---------|-------|
| `--repo=X` | Single-repo focus | Shows details hidden in summary view |
| `--format json\|yaml\|table` | Machine-readable output | Default is `table` (human) |
| `--dry-run` | Non-destructive preview | Required for any write/deploy command |
| `--verbose` / `-v` | Detailed output | Shows clean items, chunk details, etc. |
| `--limit N` / `-n N` | Result count | For search and query commands |
| `--all` | Override incremental behavior | Re-process everything, ignore state |

### Naming

- Subcommands are `kebab-case`: `db-status`, `audit-vectors`, `deploy-pages`
- Flags are `--kebab-case`: `--dry-run`, `--keys-only`
- Positional arguments only for natural-language input (search queries, file paths)

### Exit codes

- `0` — clean / success
- `1` — errors found (hard policy violations, failures)
- Non-zero propagates — if a script exits 1, the CLI exits 1

## 4. Output Width

- Target 80 columns for primary content (dots, names, findings)
- Allow up to 120 for tables (`devctl list`, `devctl status`)
- Horizontal rules are 50 chars (`'─' * 50`) for summary bars, 60-65 for section dividers
- No hard wrapping — let the terminal handle reflow

## 5. Performance

- **Parallelize repo checks** with `concurrent.futures.ThreadPoolExecutor` (8 workers)
- **Deduplicate** `repos.yaml` entries before iteration (seen-set on `name`)
- **Timeout all subprocess calls** — 10s default for git, 5s for network, 60s for gitleaks
- **Fail open on network** — if Qdrant or Docker is unreachable, report and continue

## 6. Error Handling

- **Never crash on a single repo failure** — catch, report, continue to the next
- **Three severity levels** used consistently across all commands:
  - `ERROR` — must fix, blocks compliance (hard policy violation, tracked secret, missing required file)
  - `WARN` — should fix, advisory (dirty tree, missing optional file, drift)
  - `INFO` — notice only (tool not installed, recommendation)
- **Fix hints in dim gray** after error messages where actionable: `fix: docker start qdrant`
- `--repo=X` that matches nothing should print a message, not silently exit

## 7. The `C` Dict Pattern

Every script that produces colored output should start with this block:

```python
# ANSI
C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[90m",
    "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m",
    "cyan": "\033[36m",
}
```

Extend with `"mag"`, `"white"`, `"blue"` only when the command uses them. Keep unused entries out.

## 8. Examples

### devctl audit (summary view)

```
  devctl audit  61 repos

  ● stale-experiment  research · private
      ✗ missing README.md
      ! no .control/repo.yaml
  ● my-tool  infrastructure · private
      ! dirty git tree (2 files)

  ──────────────────────────────────────────────────
  61 repos  ● 59 clean  ● 1 warnings  ● 1 errors
```

### devctl policy --repo=vpin

```
  devctl policy  1 repos

  ● vpin  quant-finance
      ✗ [secrets] .gitignore missing .env exclusion
      ! [docs] README.md too short (< 50 chars)

  ──────────────────────────────────────────────────
  1 repos  ● 1 warnings  ● 1 errors
```

### devctl health (section-based)

```
  System Health
  ────────────────────────────────────────────────────────────────

  Services
  ● Docker       3 containers  qdrant, postgres, redis
  ● Ollama       2 models  llama3.2, nomic-embed-text

  Data
  ● Qdrant :6333  7 collections  312,000 vectors
  ● Qdrant :7333  1 collections  1,700,000 vectors

  Repos
  ● Repos        61 registered  45 on disk  43 clean  2 dirty
```

## Enforcement

- `devctl audit` does not currently check CLI output style
- This is an advisory reference for contributors and agents writing new commands
- When adding a new `devctl` subcommand, follow this template and copy the `C` dict

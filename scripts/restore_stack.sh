#!/usr/bin/env bash
# ============================================================================
# Full Stack Restore Script
# Run after reboot to bring everything back up in the correct order.
#
# Usage:  ./restore_stack.sh          # full restore
#         ./restore_stack.sh status    # check what's running
#         ./restore_stack.sh stop      # graceful shutdown (pre-reboot)
# ============================================================================
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }
hdr()  { echo -e "\n${BOLD}── $* ──${NC}"; }

wait_for_port() {
    local port=$1 name=$2 max=${3:-30}
    for i in $(seq 1 "$max"); do
        if curl -sf "http://localhost:$port" >/dev/null 2>&1 || \
           curl -sf "http://localhost:$port/health" >/dev/null 2>&1 || \
           pg_isready -h localhost -p "$port" >/dev/null 2>&1; then
            log "$name ready on :$port"
            return 0
        fi
        sleep 1
    done
    err "$name not ready on :$port after ${max}s"
    return 1
}

# ============================================================================
# INVENTORY — Everything that runs on this machine
# ============================================================================
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  LAYER 1: macOS Apps (auto-start on login)                            │
# ├─────────────────────────────────────────────────────────────────────────┤
# │  Docker Desktop    — manages all containers         (login item)      │
# │  Postgres.app      — native PG 18 on :5432          (login item)      │
# │  Ollama.app        — local LLM inference on :11434   (login item)     │
# │  NordVPN           — VPN                             (login item)     │
# │  WhatsApp          — needed for live chat DB access  (login item)     │
# ├─────────────────────────────────────────────────────────────────────────┤
# │  LAYER 2: LaunchAgents (auto-start via launchd)                       │
# ├─────────────────────────────────────────────────────────────────────────┤
# │  Caddy             — reverse proxy :443→:3100        (KeepAlive)      │
# │    Config: /opt/homebrew/etc/Caddyfile                                │
# │    Domains: twilight.ghostwright.dev, joel.ghostwright.dev             │
# │  Docvec            — embedding/reranking :8100       (KeepAlive)      │
# │    Plist: ~/Library/LaunchAgents/com.jthor.docvec-service.plist       │
# │  Qdrant Backup     — daily 3AM snapshot + B2 upload  (cron)          │
# │    Plist: ~/Library/LaunchAgents/com.jthor.backup-qdrant.plist        │
# │  Session Ingest    — every 6h Claude Code ingest     (interval)       │
# │    Plist: ~/Library/LaunchAgents/com.jthor.ingest-sessions.plist      │
# ├─────────────────────────────────────────────────────────────────────────┤
# │  LAYER 3: Docker Compose stacks (restart: unless-stopped)             │
# ├─────────────────────────────────────────────────────────────────────────┤
# │  "legal" stack — ~/legal/docker-compose.yml                           │
# │    qdrant (container: qdrant)     — :6333/:6334  main vector DB       │
# │      Volume: legal_qdrant_data (12 collections, 984K vectors)         │
# │    ruvector                       — :5432 (CONFLICTS w/ Postgres.app) │
# │      Volume: ruvector_data (unused)                                   │
# │                                                                       │
# │  "infra" stack — policy-orchestrator + caseledger compose merged      │
# │    Compose files (both contribute to "infra" project):                │
# │      ~/GitHub/policy-orchestrator/infra/docker-compose.yml            │
# │      ~/GitHub/caseledger/infra/docker-compose.yml                     │
# │    infra-qdrant-1    — :7333/:7334  caseledger vectors                │
# │      Volume: infra_qdrant_data (case_docs 1.7M, case_facts 107K)     │
# │    infra-postgres-1  — :5433       caseledger fact store (13 tables)  │
# │      Volume: infra_pg_data                                            │
# │    infra-neo4j-1     — :7474/:7687 knowledge graph (108K nodes)       │
# │      Volume: infra_neo4j_data                                         │
# │    infra-timescaledb-1 — :5434     trade timeseries                   │
# │      Volume: infra_tsdb_data                                          │
# │                                                                       │
# │  "daylight" stack — ~/GitHub/daylight/infra/docker-compose.yml        │
# │    daylight-api-1    — :9000       Daylight API (FastAPI in Docker)   │
# │    daylight-qdrant-1 — :9333/:9334 tenant vector DB                   │
# │      Volume: daylight_daylight_qdrant                                 │
# │    daylight-postgres-1 — :9432     tenant fact store                  │
# │      Volume: daylight_daylight_pg                                     │
# │    daylight-neo4j-1  — :9474/:9687 tenant graph                      │
# │      Volume: daylight_daylight_neo4j                                  │
# ├─────────────────────────────────────────────────────────────────────────┤
# │  LAYER 4: Native FastAPI services (managed by devctl / launchd)       │
# ├─────────────────────────────────────────────────────────────────────────┤
# │  Daylight (native)  — :8000  ~/GitHub/daylight                        │
# │    Start: cd ~/GitHub/daylight && uv run uvicorn src.api.main:app     │
# │           --host 127.0.0.1 --port 8000                                │
# │    OR:    cd ~/GitHub/policy-orchestrator && uv run devctl services    │
# │           start daylight                                              │
# │  Docvec             — :8100  ~/GitHub/docvec  (launchd auto-starts)   │
# │    Start: launchctl kickstart gui/$(id -u)/com.jthor.docvec-service   │
# ├─────────────────────────────────────────────────────────────────────────┤
# │  LAYER 5: Cloud / Subscription Services                              │
# ├─────────────────────────────────────────────────────────────────────────┤
# │  Railway            — daylight production deployment                  │
# │    URL: daylight-production-f4d1.up.railway.app                       │
# │    Services: daylight app + 2× Postgres                              │
# │    Token: $RAILWAY_TOKEN                                              │
# │  Neon.tech          — hosted Postgres (13 tables, CaseLedger mirror) │
# │    Connection: $NEON_CONNECTION_STRING                                │
# │  Qdrant Cloud       — AWS us-east-1 (currently empty, standby)       │
# │    URL: $QDRANT_CLOUD_URL, Key: $QDRANT_CLOUD_API_KEY                │
# │  Backblaze B2       — object storage for backups                     │
# │    Buckets: jthor-trade-data, jthor-qdrant-backups, jthor-personal   │
# │    B2 has 37GB of Qdrant snapshots (multi-day history)               │
# │  GitHub Pages       — 12 deployed sites (147 encrypted HTML files)   │
# │  Docker Hub         — thorvaldurian (image registry)                 │
# │  2captcha           — CAPTCHA solving API                            │
# │  OpenRouter         — LLM gateway (DeepSeek/Llama/Mistral)          │
# │  Anthropic API      — Claude API                                     │
# │  OpenAI API         — ChatGPT/embeddings                            │
# └─────────────────────────────────────────────────────────────────────────┘
#
# PORT MAP:
#   5432  — Postgres.app (native, macOS)
#   5433  — infra-postgres-1 (caseledger, Docker)
#   5434  — infra-timescaledb-1 (Docker)
#   6333  — qdrant (legal stack, Docker) ← main vector DB
#   6334  — qdrant gRPC
#   7333  — infra-qdrant-1 (caseledger, Docker)
#   7334  — infra-qdrant-1 gRPC
#   7474  — infra-neo4j-1 HTTP browser
#   7687  — infra-neo4j-1 Bolt
#   8000  — Daylight API (native uvicorn)
#   8100  — Docvec (native uvicorn, launchd)
#   9000  — daylight-api-1 (Docker)
#   9333  — daylight-qdrant-1 (Docker)
#   9432  — daylight-postgres-1 (Docker)
#   9474  — daylight-neo4j-1 HTTP
#   9687  — daylight-neo4j-1 Bolt
#   11434 — Ollama

# ============================================================================
# COMMANDS
# ============================================================================

cmd_status() {
    hdr "macOS Apps"
    pgrep -q "com.docker.backend" && log "Docker Desktop running" || warn "Docker Desktop NOT running"
    pgrep -qf "Postgres.app" && log "Postgres.app running (:5432)" || warn "Postgres.app NOT running"
    pgrep -qf "ollama" && log "Ollama running (:11434)" || warn "Ollama NOT running"

    hdr "LaunchAgents"
    launchctl print "gui/$(id -u)/com.jthor.docvec-service" >/dev/null 2>&1 && log "Docvec agent loaded" || warn "Docvec agent not loaded"
    launchctl print "gui/$(id -u)/com.jthor.backup-qdrant" >/dev/null 2>&1 && log "Qdrant backup agent loaded" || warn "Qdrant backup agent not loaded"
    launchctl print "gui/$(id -u)/com.jthor.ingest-sessions" >/dev/null 2>&1 && log "Session ingest agent loaded" || warn "Session ingest agent not loaded"
    launchctl print "gui/$(id -u)/homebrew.mxcl.caddy" >/dev/null 2>&1 && log "Caddy agent loaded" || warn "Caddy agent not loaded"

    hdr "Docker Containers"
    docker ps --format '  {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || warn "Docker not reachable"

    hdr "Native Services"
    curl -sf http://localhost:8000/health >/dev/null 2>&1 && log "Daylight :8000" || warn "Daylight :8000 down"
    curl -sf http://localhost:8100/health >/dev/null 2>&1 && log "Docvec :8100" || warn "Docvec :8100 down"

    hdr "Port Check"
    for port in 5432 5433 5434 6333 7333 7474 7687 8000 8100 9000 9333 9432 9474 11434; do
        if lsof -i ":$port" -sTCP:LISTEN >/dev/null 2>&1; then
            log ":$port listening"
        else
            warn ":$port not listening"
        fi
    done
}

cmd_stop() {
    hdr "Graceful Shutdown (pre-reboot)"

    warn "Stopping native Daylight..."
    pkill -f "uvicorn src.api.main:app.*--port 8000" 2>/dev/null && log "Daylight stopped" || warn "Daylight was not running"

    warn "Stopping Docker stacks..."
    docker compose -f ~/GitHub/daylight/infra/docker-compose.yml down 2>/dev/null && log "daylight stack down" || true
    docker compose -f ~/GitHub/caseledger/infra/docker-compose.yml -f ~/GitHub/policy-orchestrator/infra/docker-compose.yml down 2>/dev/null && log "infra stack down" || true
    docker compose -f ~/legal/docker-compose.yml down 2>/dev/null && log "legal stack down" || true

    warn "Docvec will stop automatically (launchd KeepAlive stops at logout)"
    warn "Ollama/Docker/Postgres.app will stop at shutdown"
    log "Safe to reboot."
}

cmd_restore() {
    hdr "Stack Restore — Post-Reboot"
    echo "Expecting: Docker Desktop, Postgres.app, Ollama auto-started at login."
    echo ""

    # --- Wait for Docker ---
    hdr "Waiting for Docker"
    for i in $(seq 1 60); do
        if docker info >/dev/null 2>&1; then
            log "Docker ready"
            break
        fi
        if [ "$i" -eq 60 ]; then
            err "Docker not ready after 60s — open Docker Desktop manually"
            exit 1
        fi
        sleep 1
    done

    # --- Docker stacks (order: legal first — main Qdrant, then infra, then daylight) ---
    hdr "Starting Docker stacks"

    warn "Starting legal stack (main Qdrant :6333)..."
    docker compose -f ~/legal/docker-compose.yml up -d
    wait_for_port 6333 "Qdrant :6333" 30

    warn "Starting infra stack (caseledger Qdrant :7333, Postgres :5433, Neo4j :7474, TimescaleDB :5434)..."
    docker compose -f ~/GitHub/caseledger/infra/docker-compose.yml \
                   -f ~/GitHub/policy-orchestrator/infra/docker-compose.yml up -d
    wait_for_port 7333 "Qdrant :7333" 30
    wait_for_port 5433 "Postgres :5433" 15
    wait_for_port 7474 "Neo4j :7474" 30
    wait_for_port 5434 "TimescaleDB :5434" 15

    warn "Starting daylight stack (:9000, :9333, :9432, :9474)..."
    docker compose -f ~/GitHub/daylight/infra/docker-compose.yml up -d
    wait_for_port 9000 "Daylight Docker :9000" 60
    wait_for_port 9333 "Daylight Qdrant :9333" 30

    # --- Native services ---
    hdr "Starting native services"

    # Docvec — launchd should auto-restart it, but kick it if not
    if ! curl -sf http://localhost:8100/health >/dev/null 2>&1; then
        warn "Kicking Docvec..."
        launchctl kickstart "gui/$(id -u)/com.jthor.docvec-service" 2>/dev/null || \
            launchctl load ~/Library/LaunchAgents/com.jthor.docvec-service.plist 2>/dev/null
        wait_for_port 8100 "Docvec :8100" 30
    else
        log "Docvec already running"
    fi

    # Daylight native — start if not already up
    if ! curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        warn "Starting Daylight (native :8000)..."
        cd ~/GitHub/daylight
        nohup uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000 \
            > /tmp/daylight-native.log 2>&1 &
        cd - >/dev/null
        wait_for_port 8000 "Daylight :8000" 30
    else
        log "Daylight already running"
    fi

    # --- Wait for Postgres.app ---
    hdr "Checking Postgres.app"
    wait_for_port 5432 "Postgres.app :5432" 15 || \
        warn "Postgres.app may need to be opened manually"

    # --- Wait for Ollama ---
    hdr "Checking Ollama"
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        log "Ollama ready (:11434)"
    else
        warn "Ollama not responding — open Ollama.app manually"
    fi

    # --- Verify LaunchAgents ---
    hdr "Verifying scheduled agents"
    launchctl print "gui/$(id -u)/com.jthor.backup-qdrant" >/dev/null 2>&1 && \
        log "Qdrant backup cron loaded (daily 3AM)" || \
        { warn "Loading backup agent..."; launchctl load ~/Library/LaunchAgents/com.jthor.backup-qdrant.plist 2>/dev/null; }

    launchctl print "gui/$(id -u)/com.jthor.ingest-sessions" >/dev/null 2>&1 && \
        log "Session ingest loaded (every 6h)" || \
        { warn "Loading ingest agent..."; launchctl load ~/Library/LaunchAgents/com.jthor.ingest-sessions.plist 2>/dev/null; }

    # --- Final health check ---
    hdr "Final Health Check"
    cd ~/GitHub/policy-orchestrator
    uv run devctl health 2>/dev/null || warn "devctl health had issues"

    echo ""
    log "Stack restore complete."
}

# ============================================================================
# MAIN
# ============================================================================
case "${1:-restore}" in
    status)  cmd_status ;;
    stop)    cmd_stop ;;
    restore) cmd_restore ;;
    *)       echo "Usage: $0 {restore|status|stop}"; exit 1 ;;
esac

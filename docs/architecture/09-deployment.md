# Deployment

## Local Stack (Current — M4 MacBook Pro)

### Services (Always Running)

| Service | Port | How | Restart |
|---------|------|-----|---------|
| Qdrant (main) | 6333 | Docker Desktop | Auto-restart |
| Qdrant (caseledger) | 7333 | docker-compose | `docker compose up -d` |
| PostgreSQL (caseledger) | 5433 | docker-compose | `docker compose up -d` |
| TimescaleDB | 5434 | docker-compose | `docker compose up -d` |
| docvec service | 8100 | LaunchAgent | KeepAlive=true |
| Ollama | 11434 | Desktop app | Auto-start |

### LaunchAgents (Scheduled)

| Agent | Schedule | Task |
|-------|----------|------|
| `com.jthor.docvec-service` | RunAtLoad + KeepAlive | Embedding service (warm) |
| `com.jthor.ingest-sessions` | Every 6 hours | Ingest Claude Code sessions |
| `com.jthor.backup-qdrant` | Daily 3:00 AM | Snapshot + upload to B2 |

### Docker Compose Files

**policy-orchestrator/infra/docker-compose.yml:**
```yaml
services:
  timescaledb:
    image: timescale/timescaledb:latest-pg16
    ports: ["5434:5432"]
    environment:
      POSTGRES_DB: orchestrator
      POSTGRES_USER: orchestrator
      POSTGRES_PASSWORD: orchestrator_dev
    volumes:
      - tsdb_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
```

**caseledger/infra/docker-compose.yml:**
```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["7333:6333", "7334:6334"]
    volumes:
      - qdrant_data:/qdrant/storage

  postgres:
    image: postgres:16
    ports: ["5433:5432"]
    environment:
      POSTGRES_DB: caseledger
      POSTGRES_USER: caseledger
      POSTGRES_PASSWORD: caseledger_dev
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
```

### Backup Strategy

```bash
# Daily at 3 AM (LaunchAgent)
~/GitHub/policy-orchestrator/scripts/backup_qdrant.sh
# → Snapshots all collections (both ports)
# → Uploads to Backblaze B2 via rclone
# → Keeps 7 days locally, unlimited in B2
```

## AWS Lambda Scaling Path

### Architecture on AWS

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer                              │
├─────────────────────────────────────────────────────────┤
│  API Gateway + Lambda (Python)                           │
│  ├── /search → embed query + Qdrant Cloud search        │
│  ├── /facts → Aurora PostgreSQL                         │
│  ├── /cycles → graph analysis (Lambda, 15min timeout)   │
│  ├── /chain → chain engine (Lambda)                     │
│  └── /ingest → Step Function (multi-step pipeline)      │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────┼─────────────────────────────────┐
│                    Compute                                │
├───────────────────────┼─────────────────────────────────┤
│  Lambda (256MB-3GB)   │  SageMaker Endpoints             │
│  - Search queries     │  - BGE embedding (warm)          │
│  - Fact CRUD          │  - SPLADE++ sparse               │
│  - Graph algorithms   │  - Cross-encoder rerank          │
│  - Chain building     │  - LLM inference (Bedrock)       │
└───────────────────────┼─────────────────────────────────┘
                        │
┌───────────────────────┼─────────────────────────────────┐
│                    Storage                                │
├───────────────────────┼─────────────────────────────────┤
│  Qdrant Cloud         │  Aurora PostgreSQL               │
│  - All collections    │  - Facts, graph, parties         │
│  - Managed scaling    │  - TimescaleDB extension         │
│  - API-compatible     │                                  │
│                       │  S3                              │
│  DynamoDB             │  - Raw documents                 │
│  - Provenance index   │  - Processed markdown            │
│  - Session state      │  - Backups                       │
└───────────────────────┴─────────────────────────────────┘
```

### Migration Steps

1. **Qdrant → Qdrant Cloud**
   - Export snapshots (already have backup script)
   - Import to Qdrant Cloud (same API, just change URL)
   - Update `EmbedConfig.qdrant_host` to cloud endpoint

2. **PostgreSQL → Aurora**
   - pg_dump from local → restore to Aurora
   - Enable TimescaleDB extension (or use separate RDS TimescaleDB)
   - Update connection strings

3. **docvec service → Lambda + EFS**
   - Package models on EFS (shared filesystem)
   - Lambda loads from EFS (cold start ~30s, warm ~100ms)
   - Or: SageMaker endpoint (always warm, $0.05/hr)

4. **Ollama → Bedrock**
   - Replace llama3.1:8b calls with Claude Haiku (Bedrock)
   - Same prompt patterns, just different API
   - Or: SageMaker with vLLM for self-hosted

5. **Ingestion → Step Functions**
   - Each pipeline step = Lambda function
   - Step Function orchestrates: extract → chunk → embed → store
   - S3 triggers for new document arrival
   - SQS for batch processing

6. **Scheduled tasks → EventBridge**
   - Session ingestion: EventBridge rule → Lambda
   - Backups: EventBridge → Lambda → S3
   - Health checks: EventBridge → Lambda → SNS alerts

### Cost Estimate (Moderate Usage)

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| Qdrant Cloud (2M vectors) | ~$50 | Managed, auto-scaling |
| Aurora PostgreSQL (db.t3.medium) | ~$60 | Multi-AZ optional |
| Lambda (10K invocations/day) | ~$5 | Most are fast searches |
| SageMaker (BGE endpoint, ml.g4dn.xlarge) | ~$150 | Always-warm embedding |
| S3 (100GB documents) | ~$3 | Infrequent access tier |
| API Gateway | ~$5 | Per-request pricing |
| **Total** | **~$275/mo** | Without SageMaker: ~$125/mo |

### Key Decisions for Lambda

1. **Embedding warm vs cold:** SageMaker endpoint ($150/mo) vs Lambda+EFS (free when idle, 30s cold start)
2. **LLM:** Bedrock (pay per token, no infra) vs SageMaker (fixed cost, full control)
3. **Qdrant:** Cloud managed ($50/mo) vs self-hosted on EC2 ($30/mo but ops burden)
4. **Graph analysis:** Lambda has 15min timeout — enough for most cases, but large graphs may need Fargate

## Secrets Management

### Local (Current)
```bash
# All keys in one file, sourced by shell
~/.oh-my-zsh/custom/keys.zsh
# Contains: ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY,
#           VAST_API_KEY, HF_TOKEN, GOOGLE_CLIENT_ID/SECRET,
#           page passwords, database credentials
```

### AWS (Recommended)
```
AWS Secrets Manager
├── /legal-intel/api-keys (Anthropic, OpenRouter, HF)
├── /legal-intel/database (Aurora credentials)
├── /legal-intel/qdrant (Qdrant Cloud API key)
└── /legal-intel/pages (encryption passwords)

Lambda reads via IAM role → Secrets Manager SDK
```

### Key Validation Patterns
```
ANTHROPIC_API_KEY: sk-ant-*
OPENROUTER_API_KEY: sk-or-v1-*
OPENAI_API_KEY: sk-*
HF_TOKEN: hf_*
GITHUB_TOKEN: ghp_*
VAST_API_KEY: [64-char hex]
```

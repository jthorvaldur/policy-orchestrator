# Key Acquisition Spec

What you have, what you need, where to get it, and what's not worth getting yet.

## Current Inventory

**9 keys active** — covers the core workflow: local models, Anthropic, OpenRouter, Vast GPU, embeddings.

| Key | Status | Covers |
|-----|--------|--------|
| `ANTHROPIC_API_KEY` | HAVE | Claude Sonnet/Haiku/Opus — primary reasoning engine |
| `OPENROUTER_API_KEY` | HAVE | 100+ models via single key — cheap classification, fallback |
| `OPENAI_API_KEY` | HAVE | GPT-4.1, o3, Codex — currently unused in code but available |
| `VAST_API_KEY` | HAVE | GPU instance provisioning — batch embedding offload |
| `HF_TOKEN` | HAVE | HuggingFace model downloads (gated models like Llama) |
| `GEMINI_API_KEY` | HAVE | Google Gemini — currently unused in code |
| `OLLAMA_BASE_URL` | HAVE | Local Ollama — primary for legal, embedding, cheap tasks |
| `QDRANT_URL` | HAVE | Local Qdrant — all vector collections |
| `PLAID_*` | HAVE | Banking API — caseledger financial data |

## Priority Ranking

### Tier 1 — GET NOW (real code references, immediate value)

#### `GITHUB_TOKEN`
- **Used by:** puffin (GitHub Q&A bot — GraphQL API for discussions/comments)
- **Where:** https://github.com/settings/tokens
- **Type:** Fine-grained PAT
- **Scopes needed:** `repo` (read), `discussions` (read/write)
- **Cost:** Free
- **Add to keys.zsh:**
  ```bash
  export GITHUB_TOKEN="github_pat_..."
  ```

#### `VAST_ENDPOINT`
- **Used by:** llm_router.py — routes inference to remote GPU
- **Where:** Dynamic per-instance. Set after `vast_up.sh` creates an instance.
- **Not a persistent key** — set it when a Vast instance is running, unset when done:
  ```bash
  export VAST_ENDPOINT="http://<IP>:<PORT>/v1"
  ```
- **Note:** Don't add to keys.zsh permanently. The deploy scripts handle this per-session.

### Tier 2 — GET WHEN NEEDED (code exists but optional, or unlocks new capability)

#### `MISTRAL_API_KEY`
- **Used by:** puffin (Mistral Vibe CLI agent — optional per-call)
- **Where:** https://console.mistral.ai/api-keys
- **Cost:** Free tier available (limited), paid starts at ~$0.15/M tokens
- **Worth it?** Only if actively using puffin's Vibe feature. OpenRouter already gives you Mistral models without a separate key.
- **Priority:** Low — OpenRouter covers this.

#### `QDRANT_API_KEY`
- **Used by:** caseledger (optional auth for Qdrant)
- **Where:** Only needed for Qdrant Cloud. Local Qdrant (what you run) doesn't require auth.
- **Where to get:** https://cloud.qdrant.io → create cluster → API keys
- **Cost:** Free tier (1GB), then $0.025/GB/month
- **Worth it?** Only when you move from local Docker Qdrant to cloud. Not needed now.
- **Priority:** Low — local Qdrant works fine.

#### `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`
- **Used by:** gmail_tools profile (not yet implemented in code)
- **Where:** https://console.cloud.google.com → APIs & Services → Credentials → OAuth 2.0
- **Steps:**
  1. Create project (or use existing)
  2. Enable Gmail API + Calendar API
  3. Create OAuth 2.0 Client ID (Desktop app type)
  4. Download credentials → extract client_id + client_secret
- **Cost:** Free (API usage limits apply)
- **Worth it?** When you build email/calendar integration for div_legal or caseledger. The MCP Gmail tools you already have use a different auth flow (Claude.ai managed).
- **Priority:** Medium — useful for automated email parsing in legal workflows.

### Tier 3 — DON'T GET YET (zero code references, purely scaffolding)

These are listed in `secrets.schema.yaml` as optional keys in the `base_llm` profile. None have actual code calling them. **OpenRouter already gives you access to all these models** without separate keys.

| Key | Provider | Why skip | OpenRouter equivalent |
|-----|----------|----------|----------------------|
| `DEEPSEEK_API_KEY` | https://platform.deepseek.com | No code uses it | `deepseek/deepseek-chat` via OpenRouter |
| `GROQ_API_KEY` | https://console.groq.com | No code uses it | Groq models available via OpenRouter |
| `TOGETHER_API_KEY` | https://api.together.ai | No code uses it | Together models available via OpenRouter |
| `GOOGLE_API_KEY` | https://aistudio.google.com/apikey | You already have `GEMINI_API_KEY` which is the same thing | Already covered |

### Tier 4 — SKIP (wrong category for your stack)

| Key | Why skip |
|-----|----------|
| `NETLIFY_TOKEN` | You use GitHub Pages, not Netlify |
| `VERCEL_TOKEN` | caseledger GOAL.md says Railway for deploy, not Vercel |

## Coverage Analysis

```
What you can do today (with current keys):
  Reasoning/Analysis    ██████████ Anthropic Claude (direct + via OpenRouter)
  Cheap classification  ██████████ Ollama local + OpenRouter (Llama, Mistral)
  Embedding             ██████████ Ollama local (nomic) + Vast.ai GPU (bge/nomic)
  Vector search         ██████████ Local Qdrant (10 collections, 180K points)
  Model downloads       ██████████ HuggingFace (gated models)
  GPU offload           ██████████ Vast.ai (4090/A100)

What you're missing:
  GitHub API            ████░░░░░░ Need GITHUB_TOKEN for puffin bot
  Gmail/Calendar API    ░░░░░░░░░░ Need Google OAuth for email automation
  Direct Mistral        ░░░░░░░░░░ Optional — OpenRouter covers this

What's overkill to get:
  DeepSeek direct       ░░░░░░░░░░ OpenRouter covers this
  Groq direct           ░░░░░░░░░░ OpenRouter covers this
  Together direct       ░░░░░░░░░░ OpenRouter covers this
  Vercel/Netlify        ░░░░░░░░░░ Not your deploy stack
```

## Action Items

1. **Now (2 minutes):** Generate a GitHub PAT at https://github.com/settings/tokens, add to keys.zsh as `GITHUB_TOKEN`
2. **When needed:** Set `VAST_ENDPOINT` per-session when running GPU jobs (deploy scripts handle this)
3. **When building email automation:** Set up Google Cloud OAuth for `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`
4. **Never:** Don't bother with DeepSeek/Groq/Together/Netlify/Vercel direct keys — OpenRouter is your multi-model gateway

## Cleanup Suggestion

Consider removing these from `secrets.schema.yaml` optional lists to reduce noise in `gai secrets` output:
- `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `TOGETHER_API_KEY` — fully redundant with OpenRouter
- `NETLIFY_TOKEN`, `VERCEL_TOKEN` — not your deploy stack
- `GOOGLE_API_KEY` — duplicate of `GEMINI_API_KEY` you already have

This would bring the "optional keys not set" warnings from 5-6 per repo down to 1-2.

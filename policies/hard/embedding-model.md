# Policy: Embedding Model Standard (HARD)

**Severity:** ERROR — flags non-compliant collections

## Rules

1. **Dense model: BAAI/bge-base-en-v1.5** (768-dim). Single model ensures cross-collection score comparability. BGE-base chosen for best size/quality tradeoff on M4 Mac.
2. **Sparse model: prithivida/Splade_PP_en_v1**. SPLADE++ enables literal matching (names, numbers, account IDs) alongside semantic search. Required for financial/legal data.
3. **Quantization: INT8** for collections >10K points. 4x memory reduction with ~99% recall.
4. **Named vectors** for hybrid collections: `dense` + `sparse` vector names in Qdrant.

## Exceptions

Collections may use non-standard models if declared in `registries/vector-collections.yaml` with a `migration_note` and deadline.

Current exceptions:
- `claude_code_sessions` — nomic-embed-text (migration deadline: 2026-06-01)
- `feedback_events`, `fact_registry` — nomic-embed-text (small, migrate with sessions)
- `claude_chats_ai`, `concepts`, `directives`, `patents` — nomic-embed-text (contacts-owned, low priority)

## Enforcement

- `devctl audit-vectors` checks model compliance
- `devctl sync-vectors` triggers re-embed for non-compliant collections

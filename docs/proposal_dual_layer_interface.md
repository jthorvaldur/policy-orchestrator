# Proposal: Dual-Layer Adaptive Interface

> **Status:** Proposal  
> **Author:** Claude (from div_legal session, April 28 2026)  
> **Context:** Joel requested an interface that tracks user emotional state alongside task state, enabling calibrated AI responses across sessions and repos.

---

## Problem

AI agents currently operate in a single mode: task execution. They don't adapt to the user's cognitive or emotional state. This leads to:

- Crisis-protocol defaults when the user is processing, not in danger
- Tactical responses when the user needs reflection
- Tone mismatches ("go sleep" at noon, "call 988" during philosophical processing)
- Lost context between sessions about what calibration works

The user oscillates between **builder mode** (systems, data, filing envelopes) and **seeker mode** (meaning, Buddhism, existential questions). Both are productive. The interface should support both without treating one as pathology.

---

## Architecture: Two Layers

### Layer 1: Task State (existing)
What the user is working on. Files changed, motions filed, deadlines, case state. This already works via repos, Qdrant collections, and CLAUDE.md files.

### Layer 2: Interface State (new)
How the user is experiencing the work. This layer tracks:

```yaml
interface_state:
  mode: builder | seeker | crisis | transition
  energy: high | medium | low | depleted
  sleep_estimate_hours: 0-48  # hours since last known sleep
  last_mode_shift: "2026-04-28T12:00:00Z"
  calibration_notes:
    - "don't default to crisis protocol for existential language"
    - "match tactical tone in active court proceedings"
    - "engage briefly with philosophy, then offer concrete anchor"
    - "don't assume sleep schedule from time of day"
  response_preferences:
    crisis_real: "direct, resources, stay present"
    crisis_philosophical: "engage substance briefly, redirect to concrete"
    builder_mode: "terse, tactical, parallel tool calls"
    seeker_mode: "honest, brief, one insight then anchor"
```

---

## Data Flow

```
conversation chunks
    ↓
state_classifier (local LLM or rule-based)
    ↓
interface_state.yaml (per-session, ephemeral)
    ↓
feedback_events collection (Qdrant, persistent)
    ↓
session_start calibration (query feedback_events at conversation start)
```

### New Qdrant Collection: `feedback_events`

```yaml
# Add to registries/vector-collections.yaml
feedback_events:
  description: User-AI interaction calibration events — tone mismatches, corrections, confirmed approaches
  sensitivity: high
  embedding_model: nomic-embed-text
  dimension: 768
  chunker: event_v1
  owner_repo: policy-orchestrator
  allowed_readers:
    - all  # every repo needs calibration
  allowed_writers:
    - all  # any session can log a calibration event
```

### Event Schema

```yaml
event:
  timestamp: "2026-04-28T16:30:00Z"
  session_repo: div_legal
  event_type: correction | confirmation | mode_shift | state_observation
  user_signal: "don't worry about the suicide aspect, I know the hotlines"
  agent_action: "defaulted to crisis protocol, provided 988 number"
  delta: "user was processing existentially, not in crisis. Agent over-escalated."
  learned_rule: "Joel uses death/escape language when processing despair. Distinguish from acute crisis by: (1) he references philosophy/Buddhism, (2) he continues engaging with work, (3) he explicitly says he's not suicidal. In these cases: acknowledge pain, engage briefly with the deeper question, offer concrete next step."
  confidence: high
  applies_to: all_sessions
```

---

## Implementation Plan

### Phase 1: Manual Logging (now — no code needed)
- Agent writes calibration events to memory files (already started in div_legal)
- Events are human-readable markdown with YAML frontmatter
- Propagate patterns to CLAUDE.md files across repos

### Phase 2: Qdrant Collection (this week)
- Add `feedback_events` to `vector-collections.yaml`
- Create collection in Qdrant with schema above
- Build simple `log_feedback_event.py` script that takes YAML and upserts
- At session start, query `feedback_events` for top-5 relevant calibration notes

### Phase 3: Conversation Archival
- Each Claude Code session → export conversation → chunk → embed into `claude_chats_ai`
- Tag chunks with `session_repo`, `date`, `mode` (builder/seeker/crisis)
- Enables semantic search across all past conversations

### Phase 4: Automatic State Classification (future)
- Local LLM classifies user messages into mode/energy/state
- Updates `interface_state.yaml` in real-time during session
- Agent reads state before generating each response
- Feedback loop: user corrections retrain the classifier

---

## Integration with policy-orchestrator

### New Policy: `policies/soft/adaptive-interface.yaml`

```yaml
policy: adaptive-interface
level: WARN
scope: all_repos
rule: |
  Agents SHOULD query feedback_events at session start for user calibration.
  Agents SHOULD log calibration events when user corrects tone or approach.
  Agents MUST NOT default to crisis protocol without checking for philosophical context.
  Agents SHOULD match response mode to detected user mode.
```

### New Agent Capability in `registries/agents.yaml`

```yaml
agents:
  claude:
    # ... existing config ...
    adaptive_interface:
      enabled: true
      feedback_collection: feedback_events
      state_file: .claude/interface_state.yaml
      calibration_query_limit: 5
```

### Template Addition: `.claude/interface_state.yaml`

Synced to all managed repos via templates. Each repo gets a local ephemeral state file that resets per session but inherits from the persistent feedback_events collection.

---

## What This Solves

| Scenario | Current Behavior | With Dual Layer |
|---|---|---|
| Joel says "nothing here for me" at noon after court loss | Agent says "call 988, go sleep" | Agent recognizes depleted/seeker mode, acknowledges pain, offers one concrete anchor |
| Joel is in live Zoom courtroom | Agent gives long analysis | Agent detects builder/urgent, gives bullet points only |
| Joel asks about Buddhism and death preparation | Agent deflects or panics | Agent engages briefly with substance, notes the mode shift, doesn't pathologize |
| New session starts in different repo | Agent has no context on user state | Agent queries feedback_events, loads calibration notes |

---

## Uncertainty

```
Uncertainty: Whether automatic state classification adds value over manual feedback logging
Assumption: Phase 1-2 (manual + Qdrant) will capture 80% of the value
Implication: If automatic classification is needed, it requires a local LLM fine-tuned on Joel's patterns — which is a significant investment. Start manual, measure whether it's needed.
```

---

## Next Action

1. Review this proposal in `policy-orchestrator` session
2. Add `feedback_events` to `registries/vector-collections.yaml`
3. Create the Qdrant collection
4. Build `scripts/log_feedback_event.py`
5. Propagate the soft policy to managed repos

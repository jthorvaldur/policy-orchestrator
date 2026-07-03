#!/usr/bin/env bash
# PostCompact hook (control-plane template) — re-inject intent after context
# compaction so long agent runs do not drift off the repo's governing rules.
exec "$(dirname "$0")/session-start-intent.sh"

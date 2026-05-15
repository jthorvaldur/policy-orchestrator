#!/usr/bin/env bash
# Snapshot all Qdrant collections to local backup directory.
# Run via launchd or cron: creates timestamped snapshots.
set -euo pipefail

BACKUP_DIR="$HOME/.qdrant_backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PORTS=(6333 7333)

mkdir -p "$BACKUP_DIR"

for PORT in "${PORTS[@]}"; do
    COLLECTIONS=$(curl -s "http://localhost:$PORT/collections" 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    for c in data.get('result', {}).get('collections', []):
        print(c['name'])
except: pass
" 2>/dev/null)

    if [ -z "$COLLECTIONS" ]; then
        echo "[$PORT] Qdrant not reachable, skipping"
        continue
    fi

    for COLL in $COLLECTIONS; do
        echo "[$PORT] Snapshotting $COLL..."
        SNAP=$(curl -s -X POST "http://localhost:$PORT/collections/$COLL/snapshots" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(data.get('result', {}).get('name', ''))
" 2>/dev/null)

        if [ -n "$SNAP" ]; then
            DEST="$BACKUP_DIR/${COLL}_${PORT}_${TIMESTAMP}.snapshot"
            curl -s "http://localhost:$PORT/collections/$COLL/snapshots/$SNAP" -o "$DEST" 2>/dev/null
            SIZE=$(du -h "$DEST" 2>/dev/null | cut -f1)
            echo "  -> $DEST ($SIZE)"
        else
            echo "  FAILED to create snapshot for $COLL"
        fi
    done
done

# Upload to Backblaze B2 if rclone is configured
if command -v rclone &>/dev/null && rclone listremotes 2>/dev/null | grep -q "b2:"; then
    echo "Uploading snapshots to B2..."
    rclone copy "$BACKUP_DIR" b2:jthor-qdrant-backups/ \
        --transfers 4 --fast-list \
        --max-age 1d \
        2>&1 | tail -5
    echo "B2 upload complete"
else
    echo "rclone/B2 not configured — local backup only"
fi

# Clean old local backups (keep 7 days)
find "$BACKUP_DIR" -name "*.snapshot" -mtime +7 -delete 2>/dev/null
echo "Backup complete: $BACKUP_DIR"

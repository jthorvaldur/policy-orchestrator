# Qdrant Backups — Verification & Monitoring

**Status: Fixed 2026-05-25 (PATH issue resolved)**
**Gap: May 17-25 (8 days of offsite backups missed)**
**Local backups: Running nightly at 3am, ~16GB/run, 2-day local retention**
**Offsite: Backblaze B2 jthor-qdrant-backups bucket**

## What Was Fixed

The backup script `~/GitHub/policy-orchestrator/scripts/backup_qdrant.sh` runs via launchd at 3am daily. It was creating local snapshots successfully but failing to upload to B2 because launchd's PATH didn't include `/opt/homebrew/bin/rclone`.

Fix: Added `export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"` to the script.

## Verification Steps

### Step 1: Check tonight's backup ran and uploaded (run after 4am tomorrow)
```bash
# Check logs
cat /tmp/backup-qdrant.log | tail -20

# Verify B2 has today's files
rclone ls b2:jthor-qdrant-backups/ --max-age 1d
```

### Step 2: Monitor ongoing
```bash
# Quick health check — should show recent files
rclone ls b2:jthor-qdrant-backups/ --max-age 2d | wc -l
# Should be 14+ (14 collections x 1 day, plus maybe 2 days)
```

### Step 3: Add to devctl health check
The backup status should be part of `devctl health`. Check:
- Last local backup timestamp
- Last B2 upload timestamp
- Size sanity (legal_docs_v2 should be ~4.7GB, case_docs ~10GB)

## Current Backup Inventory

| Collection | Port | Snapshot Size | Frequency |
|-----------|------|--------------|-----------|
| legal_docs_v2 | 6333 | 4.7 GB | Daily |
| claude_code_sessions | 6333 | 724 MB | Daily |
| case_docs | 7333 | 10 GB | Daily |
| case_facts | 7333 | 578 MB | Daily |
| whatsapp_chats | 6333 | 137 MB | Daily |
| contacts | 6333 | 27 MB | Daily |
| openai_chats | 6333 | 49 MB | Daily |
| Others (7 small) | 6333 | <25 MB each | Daily |

Total per run: ~16 GB
Monthly B2 storage: ~16 GB x 30 = ~480 GB (with retention)
B2 cost at $6/TB/mo: ~$3/mo for backups

## Local Disk Usage
- 65 GB in ~/.qdrant_backups/ (2-day retention)
- Auto-cleaned by backup script (files older than 2 days deleted)

## The 1.49 TB in jthor-personal
This is the Andrew Zachary backup data. Separate from Qdrant backups. B2 cost ~$9/mo. Keep as long as needed.

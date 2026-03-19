# Quick Reference: Rolling Logs

## What Changed?

Rolling (rotating) log files have been implemented to prevent logs from growing too large.

## Log Rotation Details

| Component | Location | Max Size | Backups | Rotation |
|-----------|----------|----------|---------|----------|
| **App** | `logs/app.log` | 10 MB | 10 files | Auto (Python) |
| **Process** | `logs/process_logs/*.log` | 50 MB | 10 files | Auto (Python) |
| **Bash Scripts** | Script stdout | 50 MB | 10 files | At script start |

## File Naming After Rotation

```
logs/app.log
logs/app.log.1      ← Previous log
logs/app.log.2      ← Older log
logs/app.log.10     ← Oldest log
```

## Automatic Cleanup

- **When:** Every 24 hours (automatic background thread)
- **What:** Deletes rotated files (`.log.1`, `.log.2`, etc.) older than 30 days
- **Where:** `logs/` and `logs/process_logs/` directories

## Maximum Disk Usage

- **Before:** Unlimited (could grow to GBs)
- **After:** ~1.2 GB maximum
  - App logs: ~110 MB
  - Process logs: ~550 MB (preproc + postproc)

## No Action Required

✅ Logs rotate automatically
✅ Old logs clean up automatically  
✅ Works transparently with existing code
✅ No configuration needed

## If You Want to Adjust Settings

Edit these values:

### App logs (in `common/common.py`, line ~40)
```python
maxBytes=10485760,  # Change this (bytes)
backupCount=10,     # Or this
```

### Process logs (in `app.py`, ProcessTracker.__init__)
```python
self._max_log_size = 50 * 1024 * 1024  # Change this
self._max_backups = 10                 # Or this
```

### Old log cleanup (in `app.py`, cleanup_old_logs method)
```python
max_age_seconds = 30 * 24 * 60 * 60  # Change this (seconds)
```

## Monitoring Commands

```bash
# Check current log sizes
du -sh logs/
ls -lh logs/*.log*

# Watch rotation in real-time
tail -f logs/app.log | grep "rotated\|cleanup"

# Find all log files
find logs -name "*.log*" -type f | sort

# Check disk usage trend
watch -n5 'du -sh logs/'
```

## Files Changed

- `app.py` - Log rotation & cleanup in ProcessTracker
- `install/postproc.sh` - Added rotate_log_if_needed() function
- `install/preproc.sh` - Added rotate_log_if_needed() function
- `config/preproc.sh` - Added rotate_log_if_needed() function

## Detailed Docs

See:
- `ROLLING_LOGS_IMPLEMENTATION.md` - Complete technical details
- `ROLLING_LOGS_SUMMARY.md` - Implementation summary

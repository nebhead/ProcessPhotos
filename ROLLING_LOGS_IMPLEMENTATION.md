# Rolling Logs Implementation

## Overview
Rolling logs have been implemented across all logging systems to prevent log files from growing indefinitely. This prevents disk space issues and improves performance.

## Log Rotation Policies

### Main Application Logs (`logs/app.log`)
- **Max Size:** 10 MB per file
- **Backup Count:** 10 files
- **Location:** `logs/` directory
- **Implementation:** Python `RotatingFileHandler` (already existed in `common.py`)
- **Format:** `app.log`, `app.log.1`, `app.log.2`, ... `app.log.10`

When `app.log` reaches 10 MB:
1. `app.log` is renamed to `app.log.1`
2. `app.log.1` becomes `app.log.2` (if it exists)
3. `app.log.2` becomes `app.log.3` (if it exists), etc.
4. New `app.log` is created
5. Oldest file (`app.log.10` or higher) is deleted

### Process Logs (`logs/process_logs/*.log`)
- **Max Size:** 50 MB per log file
- **Backup Count:** 10 files per script
- **Location:** `logs/process_logs/` directory
- **Implementation:** Manual rotation in `ProcessTracker` class
- **Format:** `postproc_<uuid>.log`, `postproc_<uuid>.log.1`, etc.

Each process script gets its own log file with UUID naming. Rotation happens:
1. When a new process starts (if previous log for same type exists and is > 50 MB)
2. Automatically before writing to the log

### Shell Script Logs (if run standalone)
- **Max Size:** 50 MB per log file
- **Backup Count:** 10 files
- **Implementation:** Bash `rotate_log_if_needed()` function
- **Called:** At the start of each script execution

The bash scripts (`preproc.sh` and `postproc.sh`) include a `rotate_log_if_needed()` function that:
- Checks if the current log exceeds 50 MB
- Rotates existing backups (renaming each incrementally)
- Renames current log to `.1` suffix
- Keeps up to 10 backup files

## File Cleanup

### Old Log Cleanup (> 30 days)
- **Frequency:** Every 24 hours (automatic background thread)
- **Age Threshold:** 30 days
- **Targets:** Rotated log files (those with numeric suffixes like `.1`, `.2`, etc.)
- **Scope:** `logs/process_logs/` directory

The `cleanup_logs_periodically()` function runs as a daemon thread and:
1. Sleeps for 24 hours
2. Calls `process_tracker.cleanup_old_logs()`
3. Removes any `.logN` files older than 30 days
4. Logs actions for audit trail

## Current Log Files

### Active (Not Rotated)
- `logs/app.log` - Main Flask application logs
- `logs/process_logs/preproc_<uuid>.log` - Current preprocessing session
- `logs/process_logs/postproc_<uuid>.log` - Current postprocessing session

### Rotated/Archived
- `logs/app.log.1` through `logs/app.log.10` - Previous app.log files
- `logs/process_logs/preproc_<uuid>.log.1` through `.10` - Previous preproc sessions
- `logs/process_logs/postproc_<uuid>.log.1` through `.10` - Previous postproc sessions

## Disk Space Impact

### Worst Case Scenario
With the current settings:

| Log Type | Max Per File | Max Backups | Total Space |
|----------|-------------|----------|-------------|
| app.log | 10 MB | 10 | ~110 MB |
| preproc logs | 50 MB | 10 | ~550 MB |
| postproc logs | 50 MB | 10 | ~550 MB |
| **Total** | - | - | **~1.2 GB** |

### Before (Original Problem)
- Single log files could grow to multiple GBs
- No automatic cleanup
- Disk space could be completely consumed
- Log reads/writes became very slow

## Configuration

### To Adjust Log Rotation Settings

#### Main App Logs (in `common/common.py`)
```python
file_handler = RotatingFileHandler(
    filename,
    maxBytes=10485760,  # 10MB - Change this value
    backupCount=10,     # 10 backups - Change this value
)
```

#### Process Logs (in `app.py`, ProcessTracker class)
```python
self._max_log_size = 50 * 1024 * 1024  # 50MB - Adjust here
self._max_backups = 10                 # 10 backups - Adjust here
```

#### Bash Scripts (in `postproc.sh` and `preproc.sh`)
```bash
rotate_log_if_needed() {
    local max_size=$((50 * 1024 * 1024))  # 50MB - Adjust here
    local max_backups=10                   # 10 backups - Adjust here
```

#### Old Log Cleanup (in `app.py`, ProcessTracker class)
```python
def cleanup_old_logs(self):
    max_age_seconds = 30 * 24 * 60 * 60  # 30 days - Adjust here
```

## Monitoring Log Rotation

### Check Current Log Sizes
```bash
# View all logs with their sizes
du -sh logs/ logs/process_logs/
ls -lh logs/app.log*
ls -lh logs/process_logs/*.log*

# Find largest log files
find logs -name "*.log*" -type f -exec ls -lh {} \; | sort -k5 -h -r | head -20
```

### Check Log Rotation in Action
```bash
# Monitor app logs in real-time
tail -f logs/app.log

# Watch for rotation messages
grep "Log rotated" logs/app.log

# See oldest log files (candidates for cleanup)
find logs/process_logs -name "*.log.[0-9]*" -type f -printf '%T@ %p\n' | sort -n | head -10
```

### Manually Trigger Old Log Cleanup
```bash
# This happens automatically, but you can monitor it
grep "Deleted old log file\|log cleanup" logs/app.log

# Or trigger manually in Python:
# python -c "from app import process_tracker; process_tracker.cleanup_old_logs()"
```

## Benefits

1. **Prevents Disk Space Issues** - Logs never exceed configured size limits
2. **Improves Performance** - Smaller log files are faster to read/write
3. **Enables Long-term Operation** - Application can run indefinitely
4. **Maintains History** - Keeps 10 backups for troubleshooting
5. **Automatic Cleanup** - Old backups removed after 30 days
6. **Consistent Across Systems** - Same approach for app, process, and shell logs

## Troubleshooting

### Logs Still Growing Too Large
1. Check if rotation thresholds are too high
2. Verify log rotation is working: `grep "Log rotated" logs/app.log`
3. Check disk space: `df -h`
4. Monitor process output: `tail -f logs/process_logs/*.log`

### Missing Recent Log Entries
1. This is normal - look at `.log.1`, `.log.2` files for older entries
2. Use command: `ls -lt logs/process_logs/*.log* | head`

### Log Cleanup Not Working
1. Verify cleanup thread is running: `grep "log cleanup thread started" logs/app.log`
2. Check for cleanup errors: `grep "Error in log cleanup" logs/app.log`
3. Restart the application

### File Permissions Issues
1. Ensure app has write permissions to `logs/` directory
2. Check: `ls -la logs/` and `ls -la logs/process_logs/`
3. Fix: `chmod -R 755 logs/`

## Files Modified

- `app.py` - Added log rotation to ProcessTracker class, cleanup thread
- `install/postproc.sh` - Added rotate_log_if_needed() function
- `config/preproc.sh` - Added rotate_log_if_needed() function
- `install/preproc.sh` - Added rotate_log_if_needed() function
- `common/common.py` - Already had RotatingFileHandler (no changes needed)

## References

- Python RotatingFileHandler: https://docs.python.org/3/library/logging.handlers.html#rotatingfilehandler
- Bash log rotation examples: https://wiki.archlinux.org/title/Logrotate

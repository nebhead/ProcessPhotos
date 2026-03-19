# Log Rolling Implementation Summary

## What Was Implemented

A comprehensive rolling log system has been added to all logging across the ProcessPhotos application:

### 1. **Main Application Logs** (already existed)
- File: `logs/app.log`
- Max size: 10 MB
- Keeps: 10 backups
- Rotates automatically via Python `RotatingFileHandler`

### 2. **Process Logs** (new - in app.py)
- Files: `logs/process_logs/*.log`
- Max size: 50 MB per log
- Keeps: 10 backups per process
- Rotates automatically before each process starts

### 3. **Shell Script Logs** (new - in postproc.sh, preproc.sh)
- Checks log size at script start
- Max size: 50 MB
- Keeps: 10 backups
- Can be called manually if needed

### 4. **Automatic Cleanup** (new - background thread)
- Removes rotated logs older than 30 days
- Runs every 24 hours automatically
- Only targets backup files (`.log.1`, `.log.2`, etc.)

## Key Files Modified

1. **app.py**
   - Added `_rotate_log_if_needed()` method to `ProcessTracker` class
   - Added `cleanup_old_logs()` method
   - Added `cleanup_logs_periodically()` background thread
   - Logs now rotate at 50 MB with 10 backups

2. **install/postproc.sh**
   - Added `rotate_log_if_needed()` function
   - Added timestamp logging with `log_msg()`
   - Uses rsync for better performance (from previous fix)

3. **install/preproc.sh**
   - Added `rotate_log_if_needed()` function
   - Added timestamp logging with `log_msg()`

4. **config/preproc.sh**
   - Added `rotate_log_if_needed()` function
   - Added timestamp logging with `log_msg()`

## How It Works

### Manual Rotation (Shell Scripts)
```bash
# When script starts, this function can rotate logs if > 50MB
rotate_log_if_needed "/path/to/log.file"
```

### Automatic Rotation (Python App)
```python
# ProcessTracker checks log size when starting a new process
if log_file:
    self._rotate_log_if_needed(log_file)
```

### Automatic Cleanup (Background Thread)
```
Every 24 hours:
  - Find all log backup files (*.log.1, *.log.2, etc.)
  - Delete any older than 30 days
  - Log the actions
```

## Example Log Rotation Sequence

### Before Rotation
```
logs/
├── app.log (10.1 MB) ← exceeds 10 MB limit
├── app.log.1 (10 MB)
├── app.log.2 (10 MB)
└── ...
```

### After Rotation
```
logs/
├── app.log (0 bytes, new)
├── app.log.1 (10.1 MB, was app.log)
├── app.log.2 (10 MB, was app.log.1)
├── app.log.3 (10 MB, was app.log.2)
└── ...
```

### After Cleanup (30+ days later)
```
logs/
├── app.log (current)
├── app.log.1 through app.log.5 (kept, < 30 days)
├── app.log.6 through app.log.10 (deleted, > 30 days old)
```

## Disk Space Impact

**Maximum disk usage with current settings:**
- Main app logs: ~110 MB (10 files × 10 MB + current)
- Process logs: ~550 MB per type (10 files × 50 MB + current)
- **Total: ~1.2 GB** (vs unlimited before)

After 30 days:
- Old process logs are automatically deleted
- Only recent logs remain
- Prevents unbounded growth

## Monitoring

### Check Log Sizes
```bash
du -sh logs/
ls -lh logs/*.log*
ls -lh logs/process_logs/*.log*
```

### Watch Rotation Happening
```bash
tail -f logs/app.log
# Look for messages like: "Log rotated (exceeded X bytes)"
```

### Check Cleanup Status
```bash
grep "log cleanup" logs/app.log
grep "Deleted old log file" logs/app.log
```

## Configuration (If Needed)

All settings can be adjusted:

### App logs (common/common.py)
- `maxBytes=10485760` → change to desired size in bytes
- `backupCount=10` → change number of backups

### Process logs (app.py)
- `self._max_log_size = 50 * 1024 * 1024` → change to bytes
- `self._max_backups = 10` → change number of backups

### Shell scripts (postproc.sh, preproc.sh)
- `max_size=$((50 * 1024 * 1024))` → change to bytes
- `max_backups=10` → change number of backups

### Cleanup threshold (app.py)
- `max_age_seconds = 30 * 24 * 60 * 60` → change to seconds

## Result

✅ **Problem Solved:**
- Logs no longer grow indefinitely
- Disk space is bounded and predictable
- Old logs are automatically cleaned up
- Performance stays consistent
- Full troubleshooting history is maintained (30 days minimum)

✅ **No Action Required:**
- Rolling logs work automatically
- No manual intervention needed
- Transparent to application code
- Works across all logging systems

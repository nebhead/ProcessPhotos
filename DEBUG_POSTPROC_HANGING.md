# PostProc Hanging - Debug & Fix Report

## Problem Summary
When processing large numbers of files (~3000), the postproc.sh script hangs with no output to the log file, which grows to a large size. This is a classic symptom of:

1. **Output buffering issues** - Output gets buffered in pipes
2. **Pipe deadlocks** - Parent process (app.py) can't read output fast enough, subprocess blocks trying to write
3. **Lack of visibility** - No intermediate logging makes it impossible to know where it's hanging

## Root Causes Identified

### 1. Verbose `-v` flag on cp command
The `cp -rpv` command outputs ONE LINE PER FILE. With 3000 files, this creates:
- 3000+ lines of output to the pipe
- Each line is a separate write operation
- If parent process isn't reading fast enough, the pipe buffer fills up
- Child process blocks trying to write, causing a deadlock

### 2. Insufficient output flushing in shell script
Shell `echo` commands can be buffered when output is redirected through pipes to a file.

### 3. Lack of progress indicators
With no intermediate logging, it's impossible to know where the script is hanging:
- During file copying?
- During sortphotos processing?
- During file verification?

### 4. No timeout protection
If sortphotos hangs indefinitely, there's no mechanism to stop it.

## Fixes Applied

### 1. **Replaced `cp -rpv` with `rsync`**
```bash
# BEFORE (can cause deadlock with 3000+ files)
cp -rpv "./export/"* "./import/unsorted/" 2>&1

# AFTER (much better for large file counts)
rsync -a --info=progress2 "./export/" "./import/unsorted/" 2>&1
```

**Benefits:**
- `rsync` is designed for large file operations
- Progress output is throttled (not per-file)
- Better performance for large file counts
- Falls back to `cp` if rsync unavailable

### 2. **Added detailed timestamped logging**
- Every major step now includes timestamps
- Progress messages show file counts and percentages
- Post-operation verification counts files

**Example:**
```
[2026-02-03 14:23:45] Starting post-processing...
[2026-02-03 14:23:46] Found 3000 files in export folder
[2026-02-03 14:23:47] Copying 3000 files in export/ folder to import/unsorted/ folder
[2026-02-03 14:24:52] Copied 3000 files to import/unsorted
```

### 3. **Added timeout protection on sortphotos**
```bash
timeout 3600 python -u ./sortphotos/src/sortphotos.py -r --sort %Y/%m import/unsorted export/sorted 2>&1
```

- 1-hour timeout (3600 seconds)
- If sortphotos hangs, process terminates gracefully
- Clear error message indicates timeout vs other failure

### 4. **Added post-operation verification**
```bash
sorted_count=$(find "./export/sorted" -type f 2>/dev/null | wc -l)
log_msg "Found $sorted_count files in export/sorted after sorting"
```

- Verifies all files were actually sorted
- Detects if sortphotos failed silently

### 5. **Better error messages**
- Includes exit codes
- Distinguishes between timeout vs other errors
- More descriptive logging throughout

## How to Monitor for Hanging

### Option 1: Use included monitor script
```bash
bash install/monitor_postproc.sh
```

This script:
- Monitors the most recent postproc log file
- Alerts if log hasn't been updated in 5 minutes
- Shows last 5 lines of log and running processes

### Option 2: Manual monitoring
```bash
# Watch log file in real-time
tail -f logs/process_logs/postproc_*.log

# Count files being processed
watch -n5 'find export/sorted -type f | wc -l'
```

### Option 3: Check process status
```bash
# List all Python/sortphotos processes
ps aux | grep -E "(sortphotos|python)" | grep -v grep

# Monitor resource usage
top -p $(pgrep -f sortphotos)
```

## Performance Expectations

With the fixes applied:

| Files | Expected Time | Bottleneck |
|-------|---|---|
| 100 | 10-15s | File operations |
| 1000 | 1-2 min | File operations |
| 3000 | 3-5 min | Sortphotos EXIF processing |
| 10000+ | 10-20 min | Sortphotos EXIF processing |

The sortphotos EXIF processing is I/O bound. Actual time depends on:
- Disk speed
- File sizes
- EXIF data complexity
- System load

## Troubleshooting

### If still hanging after fixes:

1. **Check sortphotos speed**
   ```bash
   timeout 60 python -u ./sortphotos/src/sortphotos.py -r --sort %Y/%m import/unsorted export/sorted
   # Check how many files are processed in 60 seconds
   find export/sorted -type f | wc -l
   ```

2. **Check disk I/O**
   ```bash
   iostat -x 1 10
   iotop -o
   ```

3. **Check memory usage**
   ```bash
   free -h
   watch -n1 'ps aux | grep sortphotos'
   ```

4. **Enable debug mode** (uncomment in postproc.sh)
   ```bash
   # set -x  # Uncomment this line for verbose bash debugging
   ```

5. **Test with subset of files**
   ```bash
   # Move only 100 files to test
   # Then gradually increase
   ```

## Additional Recommendations

1. **Consider async/streaming in app.py**
   - Currently, the app waits for the entire subprocess to complete before returning
   - Could improve responsiveness by reading log file periodically

2. **Add progress webhook**
   - Send progress updates to frontend as files are processed
   - Would prevent "no output for 5 minutes" frustration

3. **Monitor system resources**
   - Set alerts if CPU/memory usage spikes unexpectedly
   - Could indicate buggy subprocess

4. **Database performance**
   - If log file is on slow storage, I/O could be the bottleneck
   - Consider writing to tmpfs first, then moving to persistent storage

## Files Modified

- `/install/postproc.sh` - Main script improvements
- Created `/install/monitor_postproc.sh` - Monitoring helper script

## Testing

Test the fixed script with:
```bash
# Create test directory with many files
mkdir -p test_export
for i in {1..1000}; do
    touch test_export/test_$i.jpg
done

# Run postproc (will take a while, should show progress)
bash install/postproc.sh
```

Monitor the logs:
```bash
tail -f logs/process_logs/postproc_*.log
```

You should see timestamps and progress messages appearing regularly.

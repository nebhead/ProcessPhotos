#!/bin/bash
# Monitor script to diagnose hanging postproc processes

TIMEOUT_SECONDS=300  # Alert if no output for 5 minutes
LOG_DIR="logs/process_logs"
PATTERN="postproc_*.log"

echo "Monitoring postproc processes..."
echo "Looking for logs matching: $LOG_DIR/$PATTERN"

# Find the most recent postproc log file
LATEST_LOG=$(ls -t $LOG_DIR/$PATTERN 2>/dev/null | head -1)

if [ -z "$LATEST_LOG" ]; then
    echo "No postproc log files found in $LOG_DIR"
    exit 1
fi

echo "Monitoring log file: $LATEST_LOG"
echo "---"

# Track last modification time
LAST_MOD=$(stat -c%Y "$LATEST_LOG")

while true; do
    CURRENT_MOD=$(stat -c%Y "$LATEST_LOG")
    CURRENT_TIME=$(date +%s)
    TIME_DIFF=$((CURRENT_TIME - CURRENT_MOD))
    
    # Show last 5 lines of log
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Last 5 lines of log (No update for ${TIME_DIFF}s):"
    tail -5 "$LATEST_LOG"
    echo "---"
    
    # Check if file hasn't been updated
    if [ $TIME_DIFF -gt $TIMEOUT_SECONDS ]; then
        echo "WARNING: Log file has not been updated for ${TIME_DIFF} seconds!"
        echo "Possible hanging process. File status:"
        stat "$LATEST_LOG"
        
        # Try to find the actual process
        echo ""
        echo "Looking for sortphotos or Python processes..."
        ps aux | grep -E "(sortphotos|python|postproc)" | grep -v grep
    fi
    
    sleep 30
done

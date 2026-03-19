#!/bin/bash
# Disable buffering and enable error output
set -o pipefail
exec 2>&1  # Redirect stderr to stdout

# Enable debug output to diagnose hanging
# Uncomment next line for verbose output during troubleshooting
# set -x

# Function to rotate log file if it exceeds max size
rotate_log_if_needed() {
    local log_file=$1
    local max_size=$((50 * 1024 * 1024))  # 50MB max size
    local max_backups=10
    
    if [ -f "$log_file" ]; then
        local file_size=$(stat -f%z "$log_file" 2>/dev/null || stat -c%s "$log_file" 2>/dev/null || echo 0)
        
        if [ "$file_size" -gt "$max_size" ]; then
            # Rotate existing backups
            for ((i=max_backups-1; i>=1; i--)); do
                if [ -f "${log_file}.$i" ]; then
                    mv "${log_file}.$i" "${log_file}.$((i+1))"
                fi
            done
            # Rename current log to .1
            mv "$log_file" "${log_file}.1"
            
            echo "[$(date +'%Y-%m-%d %H:%M:%S')] Log rotated (exceeded ${max_size} bytes)"
        fi
    fi
}

# Function to log with timestamp
log_msg() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

# Function to log progress with file count
log_progress() {
    local current=$1
    local total=$2
    local percent=$((current * 100 / total))
    log_msg "Progress: $current/$total files ($percent%) - $*"
}

log_msg "Starting post-processing..."
log_msg "Current working directory: $(pwd)"

# Check if export folder has content
log_msg "Checking export folder contents..."
if [ ! -d "./export" ]; then
    log_msg "ERROR: ./export folder does not exist!"
    exit 1
fi

file_count=$(find "./export" -type f 2>/dev/null | wc -l)
log_msg "Found $file_count files in export folder"

if [ "$file_count" -eq 0 ]; then
    log_msg "WARNING: No files found in export folder. Nothing to process."
    log_msg "Script complete (nothing to do)!"
    exit 0
fi

# Delete all files in import/ folder
log_msg "Deleting all files in import/ folder"
find "./import/" -mindepth 1 -delete 2>&1 || log_msg "Warning: Error deleting import folder contents"

# Copy with -p flag to preserve attributes all files and folders in export/ folder to import/unsorted/ folder (create if it doesn't exist)
log_msg "Copying $file_count files in export/ folder to import/unsorted/ folder"
mkdir -p "./import/unsorted"

# Use rsync instead of cp for better progress reporting and performance with large numbers of files
if command -v rsync &> /dev/null; then
    log_msg "Using rsync for copy operation (better for large file counts)"
    rsync -a --info=progress2 "./export/" "./import/unsorted/" 2>&1 || {
        log_msg "ERROR: Failed to copy files from export to import/unsorted"
        exit 1
    }
else
    log_msg "Using cp for copy operation (rsync not available)"
    cp -rp "./export/"* "./import/unsorted/" 2>&1 || {
        log_msg "ERROR: Failed to copy files from export to import/unsorted"
        exit 1
    }
fi

log_msg "Verifying copy operation..."
import_count=$(find "./import/unsorted" -type f 2>/dev/null | wc -l)
log_msg "Copied $import_count files to import/unsorted"

if [ "$import_count" -ne "$file_count" ]; then
    log_msg "WARNING: File count mismatch! Expected $file_count but got $import_count"
fi

# Delete all files and folders in export/ folder
log_msg "Deleting all files in export/ folder"
find "./export/" -mindepth 1 -delete 2>&1 || log_msg "Warning: Error deleting export folder contents"

log_msg "Creating /export/sorted folder"
# Create /export/sorted and ensure it's empty
mkdir -p "./export/sorted" || {
    log_msg "ERROR: Failed to create export/sorted folder"
    exit 1
}

# Run sortphotos with unbuffered output
log_msg "Running sortphotos to organize files..."
log_msg "Command: python -u ./sortphotos/src/sortphotos.py -r --sort %Y/%m import/unsorted export/sorted"

# Run sortphotos with timeout protection and better output handling
timeout 3600 python -u ./sortphotos/src/sortphotos.py -r --sort %Y/%m import/unsorted export/sorted 2>&1 || {
    exit_code=$?
    if [ $exit_code -eq 124 ]; then
        log_msg "ERROR: sortphotos timed out after 3600 seconds"
    else
        log_msg "ERROR: sortphotos failed with exit code $exit_code"
    fi
    exit 1
}

log_msg "Verifying sortphotos output..."
sorted_count=$(find "./export/sorted" -type f 2>/dev/null | wc -l)
log_msg "Found $sorted_count files in export/sorted after sorting"

# Optionally, run Python script to export to Immich.  Uncomment below if you want to use this feature
# log_msg "Running export to Immich script"
# python -u ./immich/immich.py -c ./config/secrets.yaml -r export/sorted

log_msg "Script complete!"
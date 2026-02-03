#!/bin/bash
# Disable buffering and enable error output
set -o pipefail
exec 2>&1  # Redirect stderr to stdout

echo "Starting post-processing..."
echo " - Current working directory: $(pwd)"

# Check if export folder has content
echo " - Checking export folder contents..."
if [ ! -d "./export" ]; then
    echo "ERROR: ./export folder does not exist!"
    exit 1
fi

file_count=$(find "./export" -type f 2>/dev/null | wc -l)
echo " - Found $file_count files in export folder"

if [ "$file_count" -eq 0 ]; then
    echo "WARNING: No files found in export folder. Nothing to process."
    echo " - Script complete (nothing to do)!"
    exit 0
fi

# delete all files in import/ folder
echo " - Deleting all files in import/ folder"
find "./import/" -mindepth 1 -delete 2>&1 || echo "Warning: Error deleting import folder contents"

# copy with -p flag to preserve attributes all files and folders in export/ folder to import/unsorted/ folder (create if it doesn't exist)
echo " - Copying all files in export/ folder to import/unsorted/ folder"
mkdir -p "./import/unsorted"
cp -rpv "./export/"* "./import/unsorted/" 2>&1 || {
    echo "ERROR: Failed to copy files from export to import/unsorted"
    exit 1
}

# delete all files and folders in export/ folder
echo " - Deleting all files in export/ folder"
find "./export/" -mindepth 1 -delete 2>&1 || echo "Warning: Error deleting export folder contents"

echo " - Creating /export/sorted folder"
# Create /export/sorted and ensure it's empty
mkdir -p "./export/sorted" || {
    echo "ERROR: Failed to create export/sorted folder"
    exit 1
}

# Run sortphotos
echo " - Running sortphotos"
python -u ./sortphotos/src/sortphotos.py -r --sort %Y/%m import/unsorted export/sorted 2>&1 || {
    echo "ERROR: sortphotos failed with exit code $?"
    exit 1
}

# Optionally, run Python script to export to Immich.  Uncomment below if you want to use this feature
# echo " - Running export to Immich script"
# python ./immich/immich.py -c ./config/secrets.yaml -r export/sorted

echo " - Script complete!"
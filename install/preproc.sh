#!/bin/bash
# Disable buffering and enable error output
set -o pipefail
exec 2>&1  # Redirect stderr to stdout

echo "Starting pre-processing..."

# Check if a source directory was provided as argument
if [ $# -ne 1 ]; then
    echo "Error: Please provide the source directory path as an argument"
    echo "Usage: $0 <source_directory_path>"
    exit 1
fi

# Source directory from command line argument
SOURCE_DIR="$1"
# Destination directory
ROOT_DIR="./import"
IMPORT_DIR="./import/unsorted"
SORTED_DIR="./import/presorted"

# Check if source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    echo "Error: Source directory '$SOURCE_DIR' does not exist"
    exit 1
fi

# Delete all files in import/ folder
echo " - Deleting all files in import/ folder"
find "$ROOT_DIR" -mindepth 1 -delete 2>&1 || echo "Warning: Error deleting import folder contents"

# Create import/unsorted directory if it doesn't exist
if [ ! -d "$IMPORT_DIR" ]; then
    echo " - Creating import/unsorted directory..."
    mkdir -p "$IMPORT_DIR" || {
        echo "ERROR: Failed to create import/unsorted directory"
        exit 1
    }
fi

# Create import/sorted directory if it doesn't exist
if [ ! -d "$SORTED_DIR" ]; then
    echo " - Creating import/presorted directory..."
    mkdir -p "$SORTED_DIR" || {
        echo "ERROR: Failed to create import/presorted directory"
        exit 1
    }
fi

# Copy contents
echo " - Copying contents from '$SOURCE_DIR' to '$IMPORT_DIR'..."
cp -prv "$SOURCE_DIR"/* "$IMPORT_DIR" 2>&1 || {
    echo "ERROR: Copy operation failed with exit code $?"
    exit 1
}

# Check if copy was successful
if [ $? -eq 0 ]; then
    echo " - Copy completed successfully"
else
    echo "Error: Copy operation failed"
    exit 1
fi

# Run sortphotos
echo " - Running sortphotos"
python -u ./sortphotos/src/sortphotos.py -r --sort %Y/%m "$IMPORT_DIR" "$SORTED_DIR" 2>&1 || {
    echo "ERROR: sortphotos failed with exit code $?"
    exit 1
}

echo " - Pre-processing Script complete!"
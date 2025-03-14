#!/bin/bash
echo "Starting post-processing..."

echo " - Current working directory: $(pwd)"

# delete all files in import/ folder
echo " - Deleting all files in import/ folder"
find "./import/" -mindepth 1 -delete

# copy with -p flag to preserve attributes all files and folders in export/ folder to import/unsorted/ folder (create if it doesn't exist)
echo " - Copying all files in export/ folder to import/unsorted/ folder"
cp -rp "./export/" "./import/unsorted"
# delete all files and folders in export/ folder
echo " - Deleting all files in export/ folder"
find "./export/" -mindepth 1 -delete

echo " - Creating /export/sorted folder"
# Create /export/sorted and ensure it's empty
mkdir -p "./export/sorted"

# Run sortphotos
echo " - Running sortphotos"
python ./sortphotos/src/sortphotos.py -r --sort %Y/%m import/unsorted export/sorted

# Optionally, run Python script to export to Immich.  Uncomment below if you want to use this feature
# echo " - Running export to Immich script"
# python ./immich/immich.py -c ./config/secrets.yaml -r export/sorted

echo " - Script complete!"
#!/bin/bash

# Check if a file argument is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <doi_file>"
    echo "Example: $0 dois.txt"
    exit 1
fi

# Check if the file exists
if [ ! -f "$1" ]; then
    echo "Error: File '$1' not found"
    exit 1
fi

# Check if obsidian-templater.py exists
if [ ! -f "obsidian-templater.py" ]; then
    echo "Error: obsidian-templater.py not found in current directory"
    exit 1
fi

# Read each line from the file and process it
while IFS= read -r doi || [ -n "$doi" ]; do
    # Skip empty lines
    if [ -z "$doi" ]; then
        continue
    fi
    
    # Remove any whitespace and 'doi' prefix if present
    doi=$(echo "$doi" | tr -d '[:space:]' | sed 's/^[Dd][Oo][Ii][[:space:]]*//')
    
    echo "Processing DOI: $doi"
    python3 obsidian-templater.py -doi "$doi"
    echo "----------------------------------------"
done < "$1"

echo "All DOIs processed!" 
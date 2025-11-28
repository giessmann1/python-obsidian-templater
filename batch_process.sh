#!/bin/bash

# Script to batch process DOIs and AIS eLibrary papers
# Automatically detects whether each line is a DOI or AIS URL

# Display usage information
usage() {
    echo "Usage: $0 <paper_file> [--related-projects \"<projects>\"]"
    echo ""
    echo "Arguments:"
    echo "  <paper_file>              File containing DOIs or AIS URLs (one per line)"
    echo "  --related-projects        Optional: Related projects to add to each note"
    echo ""
    echo "Examples:"
    echo "  $0 papers.txt"
    echo "  $0 papers.txt --related-projects \"[[My Project]]\""
    echo "  $0 papers.txt --related-projects \"[[Project A]], [[Project B]]\""
    echo ""
    echo "The input file can contain:"
    echo "  - DOIs (e.g., 10.1007/978-3-031-68211-7_10)"
    echo "  - AIS URLs (e.g., https://aisel.aisnet.org/icis2023/blockchain/7)"
    echo "  - AIS paths (e.g., icis2023/blockchain/7)"
    exit 1
}

# Check if a file argument is provided
if [ $# -eq 0 ]; then
    usage
fi

# Parse arguments
PAPER_FILE=""
RELATED_PROJECTS=""

while [ $# -gt 0 ]; do
    case "$1" in
        --related-projects)
            if [ -z "$2" ]; then
                echo "Error: --related-projects requires a value"
                exit 1
            fi
            RELATED_PROJECTS="$2"
            shift 2
            ;;
        --help|-h)
            usage
            ;;
        *)
            if [ -z "$PAPER_FILE" ]; then
                PAPER_FILE="$1"
            else
                echo "Error: Unknown argument '$1'"
                usage
            fi
            shift
            ;;
    esac
done

# Check if the file exists
if [ ! -f "$PAPER_FILE" ]; then
    echo "Error: File '$PAPER_FILE' not found"
    exit 1
fi

# Check if obsidian-templater.py exists
if [ ! -f "obsidian-templater.py" ]; then
    echo "Error: obsidian-templater.py not found in current directory"
    exit 1
fi

# Function to determine if a line is a DOI or AIS paper
is_ais_paper() {
    local line="$1"
    # Check if it's an AIS URL or path
    if [[ "$line" == *"aisel.aisnet.org"* ]] || \
       [[ "$line" =~ ^(icis|amcis|ecis|pacis|hicss|misqe|jais|cais|misq)[0-9]* ]]; then
        return 0  # true - is AIS paper
    fi
    return 1  # false - is DOI
}

# Build the related projects argument if provided
RELATED_PROJECTS_ARG=""
if [ -n "$RELATED_PROJECTS" ]; then
    RELATED_PROJECTS_ARG="--related-projects \"$RELATED_PROJECTS\""
fi

# Counters for summary
total=0
dois=0
ais=0

# Read each line from the file and process it
while IFS= read -r line || [ -n "$line" ]; do
    # Skip empty lines and comments
    if [ -z "$line" ] || [[ "$line" == \#* ]]; then
        continue
    fi
    
    # Remove any leading/trailing whitespace
    line=$(echo "$line" | xargs)
    
    ((total++))
    
    if is_ais_paper "$line"; then
        # Process as AIS paper
        echo "Processing AIS paper: $line"
        if [ -n "$RELATED_PROJECTS" ]; then
            python3 obsidian-templater.py -ais "$line" --related-projects "$RELATED_PROJECTS"
        else
            python3 obsidian-templater.py -ais "$line"
        fi
        ((ais++))
    else
        # Process as DOI - remove any "doi" prefix and extra whitespace
        doi=$(echo "$line" | sed 's/^[Dd][Oo][Ii][[:space:]:]*//;s/^https:\/\/doi.org\///')
        echo "Processing DOI: $doi"
        if [ -n "$RELATED_PROJECTS" ]; then
            python3 obsidian-templater.py -doi "$doi" --related-projects "$RELATED_PROJECTS"
        else
            python3 obsidian-templater.py -doi "$doi"
        fi
        ((dois++))
    fi
    echo "----------------------------------------"
done < "$PAPER_FILE"

echo ""
echo "All papers processed!"
echo "Summary: $total total ($dois DOIs, $ais AIS papers)"

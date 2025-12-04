#!/bin/bash

# Script to batch process DOIs and AIS eLibrary papers
# Automatically detects whether each line is a DOI or AIS URL

# Ensure script continues even if individual commands fail
set +e

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

# Count total valid lines in file (excluding empty lines and comments)
count_valid_lines() {
    local count=0
    while IFS= read -r line || [ -n "$line" ]; do
        if [ -n "$line" ] && [[ "$line" != \#* ]]; then
            ((count++))
        fi
    done < "$1"
    echo "$count"
}

# Function to display progress bar
show_progress() {
    local current=$1
    local total=$2
    local width=40
    local percentage=$((current * 100 / total))
    local filled=$((current * width / total))
    local empty=$((width - filled))
    
    printf "\r\033[K["
    printf "%${filled}s" | tr ' ' '█'
    printf "%${empty}s" | tr ' ' '░'
    printf "] %d/%d (%d%%)" "$current" "$total" "$percentage"
}

# Counters for summary
current=0
retrieved=0
failed=0
skipped=0

# Get total count first
total_papers=$(count_valid_lines "$PAPER_FILE")

echo "Starting batch processing of $total_papers papers..."
echo ""

# Read each line from the file and process it
while IFS= read -r line || [ -n "$line" ]; do
    # Skip empty lines and comments
    if [ -z "$line" ] || [[ "$line" == \#* ]]; then
        continue
    fi
    
    # Remove any leading/trailing whitespace
    line=$(echo "$line" | xargs)
    
    ((current++))
    
    # Initialize output and exit_code for this iteration
    output=""
    exit_code=1
    
    if is_ais_paper "$line"; then
        # Process as AIS paper (silently, with error handling)
        if [ -n "$RELATED_PROJECTS" ]; then
            output=$(python3 obsidian-templater.py -ais "$line" --related-projects "$RELATED_PROJECTS" 2>&1)
            exit_code=$?
        else
            output=$(python3 obsidian-templater.py -ais "$line" 2>&1)
            exit_code=$?
        fi
    else
        # Process as DOI - remove any "doi" prefix and extra whitespace (silently, with error handling)
        doi=$(echo "$line" | sed 's/^[Dd][Oo][Ii][[:space:]:]*//;s/^https:\/\/doi.org\///')
        if [ -n "$RELATED_PROJECTS" ]; then
            output=$(python3 obsidian-templater.py -doi "$doi" --related-projects "$RELATED_PROJECTS" 2>&1)
            exit_code=$?
        else
            output=$(python3 obsidian-templater.py -doi "$doi" 2>&1)
            exit_code=$?
        fi
    fi
    
    # Track success/failure based on output and exit code
    if [[ "$output" == *"Paper already exists"* ]]; then
        ((skipped++))
    elif [ $exit_code -eq 0 ] && [[ "$output" == *"Note created"* ]]; then
        ((retrieved++))
    else
        ((failed++))
    fi
    
    # Show progress bar (updates in place)
    show_progress "$current" "$total_papers"
    
    # Add 5 second delay before next retrieval (except for the last paper)
    if [ "$current" -lt "$total_papers" ]; then
        sleep 5
    fi
    
done < "$PAPER_FILE"

# Move to new line after progress bar and show final stats
echo ""
echo ""
echo "========================================"
echo "           BATCH PROCESSING COMPLETE"
echo "========================================"
echo ""
echo "Total papers processed: $total_papers"
echo ""
echo "  ✓ Papers retrieved:   $retrieved"
echo "  ✗ Papers failed:      $failed"
echo "  ○ Papers skipped:     $skipped (already existed)"
echo ""
echo "========================================"

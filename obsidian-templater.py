"""
Obsidian Templater: A tool to generate Obsidian literature notes from DOIs.
Automatically fetches metadata, downloads PDFs, and creates formatted notes.
"""

import os
import json
import shutil
import subprocess
import glob
import argparse
import html
import re
from datetime import datetime
from urllib.parse import urlparse, urljoin
from habanero import cn
import pandas as pd
from difflib import SequenceMatcher
import csv
import requests
from bs4 import BeautifulSoup
TEMPLATE_DIR = "templates"

# Cache for SJR data to avoid reloading on every journal article
_sjr_data_cache = None

# Cache for AIS journal URLs
_ais_journals_cache = None

def load_ais_journal_urls():
    """
    Load AIS journal URLs from ais_journals.txt file.
    
    Returns:
        set: Set of journal path prefixes (e.g., 'misqe', 'jais', 'cais')
    """
    global _ais_journals_cache
    if _ais_journals_cache is not None:
        return _ais_journals_cache
    
    journals_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ais_journals.txt')
    journal_prefixes = set()
    
    if os.path.exists(journals_file):
        with open(journals_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and 'aisel.aisnet.org' in line:
                    # Extract the journal path (e.g., 'misqe' from 'https://aisel.aisnet.org/misqe/')
                    parts = line.rstrip('/').split('/')
                    if parts:
                        journal_prefix = parts[-1]
                        if journal_prefix:
                            journal_prefixes.add(journal_prefix.lower())
    
    _ais_journals_cache = journal_prefixes
    return journal_prefixes

def is_ais_journal_url(url):
    """
    Check if an AIS eLibrary URL is from a journal (vs conference proceedings).
    
    Args:
        url (str): The AIS eLibrary URL
        
    Returns:
        bool: True if the URL is from a journal, False otherwise
    """
    journal_prefixes = load_ais_journal_urls()
    
    if not journal_prefixes:
        return False
    
    # Parse the URL and check if any segment matches a journal prefix
    # URLs like: https://aisel.aisnet.org/misqe/vol15/iss4/5/
    parsed = urlparse(url)
    path_parts = [p.lower() for p in parsed.path.strip('/').split('/') if p]
    
    for part in path_parts:
        if part in journal_prefixes:
            return True
    
    return False

# Maps BibTeX fields to their corresponding metadata fields
type_fields = {
    "conference": {
        "booktitle": "container-title",
        "month": "issued.date-parts",
        "volume": "volume",
        "number": "issue",
        "pages": "page",
        "series": "collection-title",
        "editor": "editor",
        "publisher": "publisher",
        "address": "publisher-location",
        "organization": "event.name"
    },
    "journal": {
        "journal": "container-title",
        "volume": "volume",
        "number": "issue",
        "pages": "page",
        "issn": "ISSN"
    },
    "book": {
        "booktitle": "title",
        "publisher": "publisher",
        "address": "publisher-location",
        "isbn": "ISBN",
        "edition": "edition",
        "editor": "editor",
        "pages": "page",
        "series": "container-title"
    },
    "chapter": {
        "booktitle": "collection-title",
        "publisher": "publisher",
        "address": "publisher-location",
        "pages": "page",
        "editor": "editor",
        "isbn": "ISBN",
        "series": "container-title",
        "edition": "edition",
        "chapter": "chapter"
    }
}

def get_metadata_from_doi(doi):
    """
    Fetch metadata for a given DOI using CrossRef API.
    
    Args:
        doi (str): The DOI to fetch metadata for
        
    Returns:
        tuple: (metadata dict, publication type) or (None, None) if failed
    """
    try:
        metadata_str = cn.content_negotiation(ids=doi, format="citeproc-json")
        metadata = json.loads(metadata_str)
        
        # Safely get container-title as a string (it can be a list or string)
        container_title = metadata.get("container-title", "")
        if isinstance(container_title, list):
            container_title = container_title[0] if container_title else ""
        container_title_lower = container_title.lower() if container_title else ""
        
        # Determine publication type based on metadata
        pub_type = "Misc"  # default type
        
        if metadata.get("type") == "proceedings-article" or \
           "conference" in container_title_lower or \
           "proceedings" in container_title_lower:
            pub_type = "conference"
            metadata["type"] = "Conference Proceedings"
        elif metadata.get("type") == "book-chapter":
            pub_type = "chapter"
            metadata["type"] = "Book Chapter"
        elif metadata.get("type") in ("book", "edited-book", "monograph"):
            pub_type = "book"
            metadata["type"] = "Book"
        elif metadata.get("type") == "journal-article":
            pub_type = "journal"
            metadata["type"] = "Journal Article"
        
        print("Successfully retrieved metadata")
        return metadata, pub_type
    except Exception:
        print("Failed to retrieve metadata for this DOI")
        return None, None

def download_pdf_with_pypaperbot(doi, save_dir):
    """
    Download PDF for a given DOI using PyPaperBot.
    
    Args:
        doi (str): The DOI to download PDF for
        save_dir (str): Directory to save the PDF
        
    Returns:
        str: Path to downloaded PDF or None if failed
    """
    try:
        os.makedirs(save_dir, exist_ok=True)
        
        # Clean up any existing PDFs in the save directory
        for pdf in glob.glob(os.path.join(save_dir, "*.pdf")):
            try:
                os.remove(pdf)
            except OSError:
                pass  # Ignore errors if file can't be removed
        
        # Create a unique temporary directory for this download
        temp_dir = os.path.join(save_dir, f"temp_{doi.replace('/', '_')}")
        os.makedirs(temp_dir, exist_ok=True)
        
        cmd = ["python3", "-m", "PyPaperBot", "--doi", doi, "--dwn-dir", temp_dir]
        # Run subprocess with output redirected to devnull and timeout
        print(f"Running PyPaperBot (this may take a while)...")
        with open(os.devnull, 'w') as devnull:
            subprocess.run(cmd, stdout=devnull, stderr=devnull, check=True, timeout=300)  # 5 minute timeout

        # Find the downloaded PDF in the temporary directory
        pdfs = sorted(glob.glob(os.path.join(temp_dir, "*.pdf")), key=os.path.getmtime, reverse=True)
        if pdfs:
            # Move the PDF to the main save directory
            final_pdf = os.path.join(save_dir, os.path.basename(pdfs[0]))
            shutil.move(pdfs[0], final_pdf)
            # Clean up the temporary directory
            shutil.rmtree(temp_dir)
            print("PDF was found and downloaded successfully")
            return final_pdf
        else:
            # Clean up the temporary directory if no PDF was found
            shutil.rmtree(temp_dir)
            print("No PDF was found for this DOI")
            return None
    except subprocess.TimeoutExpired:
        # Clean up the temporary directory on timeout
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        print("PDF download timed out after 5 minutes")
        return None
    except subprocess.CalledProcessError:
        # Clean up the temporary directory on error
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        print("No PDF was found for this DOI")
        return None
    except Exception as e:
        # Clean up the temporary directory on any other error
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        print(f"Error downloading PDF: {str(e)}")
        return None

def create_bibtex_string(metadata, alias):
    """
    Create a BibTeX string from metadata.
    
    Args:
        metadata (dict): Publication metadata
        alias (str): Citation key
        
    Returns:
        str: Formatted BibTeX entry
    """
    # Format author list with cleaned names
    authors = metadata.get("author", [])
    valid_authors = []
    for author in authors:
        cleaned_name = clean_author_name(author)
        if cleaned_name:
            valid_authors.append(author)
    
    # For books, use editors as authors if no authors are present
    if metadata.get("type") == "Book" and not valid_authors:
        editors = metadata.get("editor", [])
        valid_editors = []
        for editor in editors:
            cleaned_name = clean_author_name(editor)
            if cleaned_name:
                valid_editors.append(editor)
        if valid_editors:
            valid_authors = valid_editors
            # Clear the editors list since we're using them as authors
            editors = []
    
    author_entries = " and ".join(
        f"{clean_lastname_for_alias(a.get('family', ''))}, {a.get('given', '').strip()}" for a in valid_authors
    )
    
    # Format editor list with cleaned names (only if we haven't used them as authors)
    editors = metadata.get("editor", [])
    valid_editors = []
    for editor in editors:
        cleaned_name = clean_author_name(editor)
        if cleaned_name:
            valid_editors.append(editor)
    
    editor_entries = " and ".join(
        f"{clean_lastname_for_alias(e.get('family', ''))}, {e.get('given', '').strip()}" for e in valid_editors
    )
    
    # Extract year and month
    year = metadata.get("issued", {}).get("date-parts", [[None]])[0][0]
    month = metadata.get("issued", {}).get("date-parts", [[None]])[0][1] if len(metadata.get("issued", {}).get("date-parts", [[None]])[0]) > 1 else None

    # Helper function to safely get and format metadata values for BibTeX
    def get_metadata_value(key, default=""):
        value = metadata.get(key, default)
        if isinstance(value, list):
            value = value[0] if value else default
        # First deescape any HTML entities
        value = html.unescape(str(value))
        # Then escape for BibTeX
        return value.replace("&", "\\&")

    # Common fields for all types
    common_fields = {
        "author": author_entries,
        "title": get_metadata_value("title"),
        "year": year or "",
        "doi": metadata.get("DOI", ""),
        "type": metadata.get("type", "")
    }

    # Determine entry type and fields based on publication type
    pub_type = metadata.get("type", "").lower().replace(" ", "")
    if "conference" in pub_type:
        entry_type = "inproceedings"
        fields = {**common_fields, **{k: get_metadata_value(v) for k, v in type_fields["conference"].items()}}
        if editor_entries:
            fields["editor"] = editor_entries
        # Add howpublished (AIS URL) if no DOI is present
        if not fields.get("doi") or not fields["doi"].strip():
            url = metadata.get("URL", "")
            if url:
                fields["howpublished"] = get_metadata_value("URL")
        # Add paper_type as note if available
        paper_type = metadata.get("paper_type", "")
        if paper_type:
            # Check if there's already a note field and append to it, or create new one
            existing_note = fields.get("note", "")
            if existing_note:
                fields["note"] = f"{existing_note}, Paper Type: {paper_type}"
            else:
                fields["note"] = f"Paper Type: {paper_type}"
    elif "journal" in pub_type:
        entry_type = "article"
        fields = {**common_fields, **{k: get_metadata_value(v) for k, v in type_fields["journal"].items()}}
        # Take first ISSN if multiple exist
        if isinstance(metadata.get("ISSN"), list):
            fields["issn"] = metadata.get("ISSN", [""])[0]
    elif "book" in pub_type and "chapter" not in pub_type:
        entry_type = "book"
        fields = {**common_fields, **{k: get_metadata_value(v) for k, v in type_fields["book"].items()}}
        # Take first ISBN if multiple exist
        if isinstance(metadata.get("ISBN"), list):
            fields["isbn"] = metadata.get("ISBN", [""])[0]
        if editor_entries:
            fields["editor"] = editor_entries
    elif "chapter" in pub_type:
        entry_type = "inbook"
        fields = {**common_fields, **{k: get_metadata_value(v) for k, v in type_fields["chapter"].items()}}
        # Take first ISBN if multiple exist
        if isinstance(metadata.get("ISBN"), list):
            fields["isbn"] = metadata.get("ISBN", [""])[0]
        if editor_entries:
            fields["editor"] = editor_entries
    else:
        entry_type = "misc"
        fields = common_fields

    # Handle page ranges in BibTeX
    if "pages" in fields:
        # If there's already a double hyphen, keep it
        if "--" not in fields["pages"]:
            fields["pages"] = fields["pages"].replace("-", "--")
    
    # Remove empty DOI field from BibTeX
    if "doi" in fields and (not fields["doi"] or not fields["doi"].strip()):
        del fields["doi"]

    # Format BibTeX string
    bibtex = f"@{entry_type}{{{alias},\n"
    for key, val in fields.items():
        bibtex += f"\t{key}={{{val}}},\n"
    bibtex = bibtex.rstrip(",\n") + "\n}"
    return bibtex

def load_sjr_data():
    """
    Load SCImago Journal Rankings data from CSV.
    Uses a module-level cache to avoid reloading on every call.
    
    Returns:
        pd.DataFrame: DataFrame containing SJR data
    """
    global _sjr_data_cache
    if _sjr_data_cache is not None:
        return _sjr_data_cache
    
    try:
        # Try with different CSV parsing options
        _sjr_data_cache = pd.read_csv('scimagojr_2024.csv', sep=';', quoting=csv.QUOTE_ALL)
        return _sjr_data_cache
    except Exception as e:
        print(f"Warning: Could not load SJR data: {str(e)}")
        return None

def normalize_journal_name(name):
    """
    Normalize journal name for comparison.
    
    Args:
        name (str): Journal name to normalize
        
    Returns:
        str: Normalized journal name
    """
    if not name:
        return ""
    # Convert to lowercase
    name = name.lower()
    # Replace common variations
    name = name.replace(" & ", " and ")
    name = name.replace("&", " and ")
    # Remove common words
    name = name.replace("the ", "")
    # Remove punctuation
    name = ''.join(c for c in name if c.isalnum() or c.isspace())
    return name.strip()

def find_journal_metrics(journal_name, sjr_data):
    """
    Find journal metrics using fuzzy matching.
    
    Args:
        journal_name (str): Name of the journal to find
        sjr_data (pd.DataFrame): SJR data
        
    Returns:
        dict: Journal metrics or None if not found
    """
    if sjr_data is None or not journal_name:
        return None
        
    normalized_search = normalize_journal_name(journal_name)
    
    # Try exact match first - use iloc for better performance than iterrows
    print("Searching for exact match...")
    exact_match = None
    # Limit search to first 5000 rows for performance (most journals should be in top results)
    max_search_rows = min(5000, len(sjr_data))
    for idx in range(max_search_rows):
        row = sjr_data.iloc[idx]
        normalized_title = normalize_journal_name(row['Title'])
        if normalized_title == normalized_search:
            exact_match = row
            break
    
    if exact_match is not None:
        # Split areas by semicolon and create a list
        areas = exact_match['Areas']
        areas_list = [area.strip() for area in areas.split(';')] if pd.notna(areas) else []
        
        return {
            'SJR Best Quartile': exact_match['SJR Best Quartile'],
            'H index': exact_match['H index'],
            'Citations / Doc. (2years)': exact_match['Citations / Doc. (2years)'],
            'Publisher': exact_match['Publisher'],
            'Areas': areas_list
        }
    
    # Try fuzzy matching if no exact match
    print("No exact match found, trying fuzzy matching...")
    best_ratio = 0
    best_match = None
    
    # Limit fuzzy matching to first 10000 rows to prevent hanging on very large datasets
    max_rows = min(10000, len(sjr_data))
    for idx in range(max_rows):
        row = sjr_data.iloc[idx]
        normalized_title = normalize_journal_name(row['Title'])
        ratio = SequenceMatcher(None, normalized_search, normalized_title).ratio()
        if ratio > 0.9 and ratio > best_ratio:
            best_ratio = ratio
            best_match = row
    
    if best_match is not None:
        # Split areas by semicolon and create a list
        areas = best_match['Areas']
        areas_list = [area.strip() for area in areas.split(';')] if pd.notna(areas) else []
        
        return {
            'SJR Best Quartile': best_match['SJR Best Quartile'],
            'H index': best_match['H index'],
            'Citations / Doc. (2years)': best_match['Citations / Doc. (2years)'],
            'Publisher': best_match['Publisher'],
            'Areas': areas_list
        }
    
    return None

def clean_author_name(author):
    """
    Clean and validate an author name.
    
    Args:
        author (dict or str): Author information
        
    Returns:
        str: Cleaned name or None if invalid
    """
    if isinstance(author, dict):
        given = author.get('given', '').strip()
        family = author.get('family', '').strip()
        if given or family:  # If either given or family name exists
            return f"{given} {family}".strip()
    elif isinstance(author, str):
        name = author.strip()
        if name:  # If string is not empty or just whitespace
            return name
    return None

def clean_lastname_for_alias(lastname):
    """
    Clean lastname for use in alias and filenames.
    
    Args:
        lastname (str): Lastname to clean
        
    Returns:
        str: Cleaned lastname with underscores
    """
    if not lastname:
        return "Unknown"
    # Trim whitespace and replace internal spaces with underscores
    return lastname.strip().replace(' ', '_')

def get_first_valid_author(authors):
    """
    Get the first valid author from the list.
    
    Args:
        authors (list): List of author dictionaries or strings
        
    Returns:
        str: First valid author's family name or "Unknown"
    """
    if not authors:
        return "Unknown"
    
    for author in authors:
        if isinstance(author, dict):
            family = author.get('family', '').strip()
            if family:
                return clean_lastname_for_alias(family)
        elif isinstance(author, str):
            name = author.strip()
            if name:
                # Try to extract family name (last word)
                parts = name.split()
                if parts:
                    return clean_lastname_for_alias(parts[-1])
    return "Unknown"

def fill_template(template_path, metadata, pdf_filename, pdf_output_dir, related_projects=None):
    """
    Fill template with metadata and return formatted content.
    
    Args:
        template_path (str): Path to template file
        metadata (dict): Publication metadata
        pdf_filename (str): Name of PDF file
        pdf_output_dir (str): Directory containing PDF
        related_projects (str): Related projects to add to the note (optional)
        
    Returns:
        tuple: (formatted content, citation key)
    """
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Helper function to escape double quotes for YAML strings
    def escape_yaml_quotes(value):
        if isinstance(value, str):
            # Escape double quotes by doubling them or using backslash
            return value.replace('"', '\\"')
        return value
    
    # Helper function to safely get and format metadata values for markdown
    def get_metadata_value(key, default="", escape_quotes=True):
        value = metadata.get(key, default)
        if isinstance(value, list):
            value = value[0] if value else default
        # Deescape any HTML entities
        value = html.unescape(str(value))
        # Escape double quotes for YAML if requested
        if escape_quotes:
            value = escape_yaml_quotes(value)
        return value

    # Extract basic metadata
    year = metadata.get("issued", {}).get("date-parts", [[None]])[0][0]
    month = metadata.get("issued", {}).get("date-parts", [[None]])[0][1] if len(metadata.get("issued", {}).get("date-parts", [[None]])[0]) > 1 else None
    
    # Clean and filter authors
    authors = metadata.get("author", [])
    valid_authors = []
    for author in authors:
        cleaned_name = clean_author_name(author)
        if cleaned_name:
            valid_authors.append(author)
    
    # For books, use editors as authors if no authors are present
    if metadata.get("type") == "Book" and not valid_authors:
        editors = metadata.get("editor", [])
        valid_editors = []
        for editor in editors:
            cleaned_name = clean_author_name(editor)
            if cleaned_name:
                valid_editors.append(editor)
        if valid_editors:
            valid_authors = valid_editors
    
    # Get first valid author for alias
    first_author = get_first_valid_author(valid_authors)
    alias = f"{first_author}{year}"
    imported_date = datetime.today().strftime("%Y-%m-%d")
    status = "Imported" if pdf_filename else "NoPDF"

    # Format author and editor lists with newline only if there are items
    author_list = "".join(f"  - \"{escape_yaml_quotes(clean_author_name(a))}\"\n" for a in valid_authors)
    author_list = f"\n{author_list}" if author_list else "No authors found"
    
    # Clean and filter editors (only if we haven't used them as authors)
    editors = metadata.get("editor", [])
    valid_editors = []
    for editor in editors:
        cleaned_name = clean_author_name(editor)
        if cleaned_name:
            valid_editors.append(editor)
    
    editor_list = "".join(f"  - \"{escape_yaml_quotes(clean_author_name(e))}\"\n" for e in valid_editors)
    editor_list = f"\n{editor_list}" if editor_list else ""

    # Common placeholders for all types
    placeholders = {
        "alias": alias,
        "imported_date": imported_date,
        "status": status,
        "author_list": author_list.rstrip(),
        "title": get_metadata_value("title"),
        "year": year or "",
        "doi": metadata.get("DOI", "") or "",
        "pdf_link": pdf_filename if pdf_filename else "PDF not available",
        "bibtex": create_bibtex_string(metadata, alias),
        "related_projects": related_projects or ""
    }

    # Add journal metrics if this is a journal article
    if metadata.get("type") == "Journal Article":
        # Load SJR data
        print("Loading SJR data...")
        sjr_data = load_sjr_data()
        journal_name = get_metadata_value("container-title")
        print(f"Searching for journal metrics for: {journal_name}")
        journal_metrics = find_journal_metrics(journal_name, sjr_data)
        print("Journal metrics lookup completed.")
        
        # Format institutions list for journals
        institutions_list = ""
        institutions = metadata.get("institutions", [])
        if institutions:
            institutions_list = "".join(f"  - \"{escape_yaml_quotes(inst)}\"\n" for inst in institutions)
            institutions_list = f"\n{institutions_list}" if institutions_list else ""
        
        # Get howpublished (AIS URL) - only if there's no DOI
        howpublished = ""
        doi_value = metadata.get("DOI", "") or ""
        if not doi_value:
            url = metadata.get("URL", "")
            if url:
                howpublished = url
        
        # Add journal-specific placeholders
        placeholders.update({
            "journal": journal_name,
            "volume": get_metadata_value("volume"),
            "number": get_metadata_value("issue"),
            "pages": get_metadata_value("page"),
            "issn": metadata.get("ISSN", [""])[0] if isinstance(metadata.get("ISSN"), list) else metadata.get("ISSN", ""),
            "institutions_list": institutions_list.rstrip(),
            "howpublished": howpublished
        })
        
        if journal_metrics:
            # Format areas as a markdown list with quotes around each area
            areas_list = journal_metrics['Areas']
            areas_markdown = "\n".join([f"  - \"{area}\"" for area in areas_list]) if areas_list else "No areas found"
            areas_markdown = f"\n{areas_markdown}" if areas_list else areas_markdown
            
            # Convert numeric values to string and replace comma with dot
            h_index = str(journal_metrics['H index']).replace(',', '.')
            citations_per_doc = str(journal_metrics['Citations / Doc. (2years)']).replace(',', '.')
            
            placeholders.update({
                "sjr_quartile": journal_metrics['SJR Best Quartile'],
                "h_index": h_index,
                "citations_per_doc": citations_per_doc,
                "sjr_publisher": journal_metrics['Publisher'],
                "sjr_areas": areas_markdown,
                "sjr_year": "2024"  # Add hardcoded SJR year
            })
        else:
            placeholders.update({
                "sjr_quartile": "Not found in SJR",
                "h_index": "Not found in SJR",
                "citations_per_doc": "Not found in SJR",
                "sjr_publisher": "Not found in SJR",
                "sjr_areas": "Not found in SJR",
                "sjr_year": "Not found in SJR"
            })

    # Add type-specific placeholders
    if metadata.get("type") == "Conference Proceedings":
        # Format institutions list
        institutions_list = ""
        institutions = metadata.get("institutions", [])
        if institutions:
            institutions_list = "".join(f"  - \"{escape_yaml_quotes(inst)}\"\n" for inst in institutions)
            institutions_list = f"\n{institutions_list}" if institutions_list else ""
        
        # Get abstract (can come from CrossRef or HTML extraction)
        abstract = metadata.get("abstract", "")
        # If abstract is a list, take the first element
        if isinstance(abstract, list) and abstract:
            abstract = abstract[0]
        if not abstract:
            abstract = ""
        # Escape double quotes for YAML
        abstract = escape_yaml_quotes(abstract)
        
        # Get howpublished (AIS URL) - only if there's no DOI
        howpublished = ""
        doi_value = metadata.get("DOI", "") or ""
        if not doi_value:
            # No DOI, so add the AIS URL if available
            url = metadata.get("URL", "")
            if url:
                howpublished = url
        
        # Get note (paper_type if available)
        note = ""
        paper_type = metadata.get("paper_type", "")
        if paper_type:
            note = f"Paper Type: {paper_type}"
        
        # Get track and comments info if available (escape quotes for YAML)
        track = escape_yaml_quotes(metadata.get("track", ""))
        comments = escape_yaml_quotes(metadata.get("comments", ""))
        
        placeholders.update({
            "booktitle": get_metadata_value("container-title"),
            "month": month or "",
            "volume": get_metadata_value("volume"),
            "number": get_metadata_value("issue"),
            "pages": get_metadata_value("page").replace("--", "-"),
            "series": get_metadata_value("collection-title"),
            "editor_list": editor_list.rstrip(),
            "publisher": get_metadata_value("publisher"),
            "address": get_metadata_value("publisher-location"),
            "organization": get_metadata_value("event.name"),
            "abstract": abstract,
            "institutions_list": institutions_list.rstrip(),
            "howpublished": howpublished,
            "note": note,
            "track": track,
            "comments": comments
        })
    elif metadata.get("type") == "Book":
        placeholders.update({
            "booktitle": get_metadata_value("title"),
            "publisher": get_metadata_value("publisher"),
            "address": get_metadata_value("publisher-location"),
            "isbn": metadata.get("ISBN", [""])[0] or "",  # Take first ISBN if multiple exist
            "edition": get_metadata_value("edition"),
            "editor_list": editor_list.rstrip(),
            "pages": get_metadata_value("page").replace("--", "-"),
            "series": get_metadata_value("container-title")
        })
    elif metadata.get("type") == "Book Chapter":
        placeholders.update({
            "booktitle": get_metadata_value("collection-title"),
            "publisher": get_metadata_value("publisher"),
            "address": get_metadata_value("publisher-location"),
            "pages": get_metadata_value("page").replace("--", "-"),
            "editor_list": editor_list.rstrip(),
            "isbn": metadata.get("ISBN", [""])[0] or "",  # Take first ISBN if mu exist
            "series": get_metadata_value("container-title"),
            "edition": get_metadata_value("edition"),
            "chapter": get_metadata_value("chapter")
        })

    # Replace all placeholders in template
    for key, val in placeholders.items():
        content = content.replace(f"{{{{{key}}}}}", str(val))
    
    # Handle empty DOI - remove the entire DOI line if DOI is empty
    doi_value = placeholders.get("doi", "")
    if not doi_value or doi_value.strip() == "":
        # Remove the DOI line (handles different formats)
        # Match lines like "doi: "[...](...)" or "doi: ..." with optional whitespace
        content = re.sub(r'^doi:\s*.*$', '', content, flags=re.MULTILINE)
        # Clean up any double newlines that might result
        content = re.sub(r'\n\n\n+', '\n\n', content)
    
    # Handle empty note - remove the entire note line if note is empty
    note_value = placeholders.get("note", "")
    if not note_value or note_value.strip() == "":
        # Remove the note line
        content = re.sub(r'^note:\s*.*$', '', content, flags=re.MULTILINE)
        # Clean up any double newlines that might result
        content = re.sub(r'\n\n\n+', '\n\n', content)

    return content, alias

def clean_title_for_filename(title):
    """
    Clean title for use in filename.
    
    Args:
        title (str): Title to clean
        
    Returns:
        str: Cleaned title
    """
    return ''.join(c for c in title if c.isalnum() or c.isspace()).replace(' ', '_')

def check_paper_exists(markdown_output_dir, alias, title):
    """
    Check if a paper with the given alias and similar title already exists in any subdirectory.
    Searches recursively through all year/quarter folders.
    
    Args:
        markdown_output_dir (str): Base directory for markdown files
        alias (str): Citation key (e.g., "Smith2024")
        title (str): Publication title
        
    Returns:
        str: Path to existing file if found, None otherwise
    """
    # Clean the title for filename matching
    cleaned_title = clean_title_for_filename(title)
    filename = f"{alias}_{cleaned_title}.md"
    
    # Search recursively in all subdirectories
    for root, dirs, files in os.walk(markdown_output_dir):
        for file in files:
            # Exact match on full filename (alias + title)
            if file == filename:
                return os.path.join(root, file)
            
            # Also check for similar titles with same alias (handles minor title differences)
            # Only match if the file has the same alias AND similar title
            if file.startswith(f"{alias}_") and file.endswith(".md"):
                # Extract the title part from the existing filename
                existing_title = file[len(alias)+1:-3]  # Remove "alias_" prefix and ".md" suffix
                # Use fuzzy matching to detect similar titles (threshold 0.85)
                similarity = SequenceMatcher(None, cleaned_title.lower(), existing_title.lower()).ratio()
                if similarity > 0.85:
                    return os.path.join(root, file)
    
    return None

def save_markdown(content, alias, output_dir, title):
    """
    Save markdown content to file.
    
    Args:
        content (str): Content to save
        alias (str): Citation key
        output_dir (str): Output directory
        title (str): Publication title
        
    Returns:
        str: Path to saved file, or None if file already exists
    """
    # Check if file already exists anywhere in the output directory
    existing_file = check_paper_exists(output_dir, alias, title)
    if existing_file:
        print(f"Paper already exists at: {existing_file}")
        return None
    
    # Create year and quarter directories
    current_date = datetime.today()
    year = current_date.year
    quarter = f"Q{(current_date.month-1)//3 + 1}"
    
    year_dir = os.path.join(output_dir, str(year))
    quarter_dir = os.path.join(year_dir, quarter)
    os.makedirs(quarter_dir, exist_ok=True)
    
    filename = f"{alias}_{clean_title_for_filename(title)}.md"
    filepath = os.path.join(quarter_dir, filename)
    
    # Ensure we're not double-escaping ampersands
    content = content.replace("\\&amp;", "\\&")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath

def rename_and_copy_pdf(pdf_path, alias, pdf_output_dir, title):
    """
    Copy PDF to output directory with new name.
    
    Args:
        pdf_path (str): Path to source PDF
        alias (str): Citation key
        pdf_output_dir (str): PDF directory
        title (str): Publication title
        
    Returns:
        str: Path to copied PDF
    """
    if not pdf_path:
        return None

    # Create PDF output directory if it doesn't exist
    os.makedirs(pdf_output_dir, exist_ok=True)

    # Extract year from alias (last 4 characters)
    year = alias[-4:]
    # Clean the alias (in case it wasn't cleaned before)
    cleaned_alias = clean_lastname_for_alias(alias[:-4]) + year

    # Copy PDF to output directory
    new_pdf_path = os.path.join(pdf_output_dir, f"{cleaned_alias}_{clean_title_for_filename(title)}.pdf")
    shutil.copy(pdf_path, new_pdf_path)
    
    return f"{cleaned_alias}_{clean_title_for_filename(title)}.pdf"

def check_required_fields(metadata, pub_type):
    """
    Check for missing required fields based on publication type.
    
    Args:
        metadata (dict): Publication metadata
        pub_type (str): Publication type
        
    Returns:
        list: List of missing fields
    """
    if pub_type in type_fields:
        missing_fields = []
        for field, metadata_field in type_fields[pub_type].items():
            if not metadata.get(metadata_field):
                missing_fields.append(field)
        
        if missing_fields:
            print(f"\033[91mWarning: Missing fields for: {', '.join(missing_fields)}\033[0m")
        return missing_fields
    return []

def normalize_ais_url(ais_input):
    """
    Normalize AIS eLibrary URL or path to a consistent format.
    
    Handles both:
    - Full URLs: "https://aisel.aisnet.org/icis2024/general_is/general_is/11/"
    - Shortened paths: "icis2024/general_is/general_is/11/"
    
    Args:
        ais_input (str): AIS eLibrary URL or path
        
    Returns:
        tuple: (normalized_path, full_url)
            - normalized_path: Path without domain (e.g., "icis2024/general_is/general_is/11/")
            - full_url: Complete URL (e.g., "https://aisel.aisnet.org/icis2024/general_is/general_is/11/")
    """
    # Remove leading/trailing whitespace
    ais_input = ais_input.strip()
    
    # Base URL for AIS eLibrary
    base_url = "https://aisel.aisnet.org"
    
    # If it's a full URL, extract the path
    if ais_input.startswith("http://") or ais_input.startswith("https://"):
        # Parse URL to extract path
        parsed = urlparse(ais_input)
        # Get path and remove leading/trailing slashes
        path = parsed.path.strip("/")
        # Reconstruct full URL
        full_url = f"{parsed.scheme}://{parsed.netloc}/{path}/"
        return path, full_url
    
    # If it's already a shortened path, construct full URL
    path = ais_input.strip("/")
    full_url = f"{base_url}/{path}/"
    return path, full_url

def fetch_ais_html(ais_url):
    """
    Fetch HTML content from AIS eLibrary URL.
    
    Args:
        ais_url (str): Full AIS eLibrary URL
        
    Returns:
        BeautifulSoup: Parsed HTML content or None if failed
    """
    try:
        response = requests.get(ais_url, timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        print(f"Error fetching HTML from {ais_url}: {str(e)}")
        return None

def extract_doi_from_html(soup):
    """
    Extract DOI from a div with ID "doi" in the HTML.
    
    Args:
        soup (BeautifulSoup): Parsed HTML content
        
    Returns:
        str: DOI string if found and valid, None otherwise
    """
    if soup is None:
        return None
    
    doi_div = soup.find('div', id='doi')
    if doi_div:
        p_tag = doi_div.find('p')
        if p_tag:
            doi_text = p_tag.get_text().strip()
            # Only return if we have actual content that looks like a DOI
            # A valid DOI typically starts with "10." (DOI prefix)
            if doi_text and len(doi_text) > 0:
                # Check if it looks like a DOI (contains "10." prefix)
                if '10.' in doi_text or doi_text.startswith('10.'):
                    return doi_text
                # If the div exists but doesn't contain a valid DOI, return None
                # This handles cases where the div exists but is empty or has placeholder text
    return None

def extract_paper_number_from_html(soup):
    """
    Extract paper number from a div with ID "paper_no" in the HTML.
    
    Args:
        soup (BeautifulSoup): Parsed HTML content
        
    Returns:
        str: Paper number string if found, None otherwise
    """
    if soup is None:
        return None
    
    paper_no_div = soup.find('div', id='paper_no')
    if paper_no_div:
        p_tag = paper_no_div.find('p')
        if p_tag:
            paper_no_text = p_tag.get_text().strip()
            if paper_no_text and len(paper_no_text) > 0:
                return paper_no_text
    return None

def extract_paper_type_from_html(soup):
    """
    Extract paper type from a div with ID "paper_type" in the HTML.
    
    Args:
        soup (BeautifulSoup): Parsed HTML content
        
    Returns:
        str: Paper type string if found, None otherwise
    """
    if soup is None:
        return None
    
    paper_type_div = soup.find('div', id='paper_type')
    if paper_type_div:
        p_tag = paper_type_div.find('p')
        if p_tag:
            paper_type_text = p_tag.get_text().strip()
            if paper_type_text and len(paper_type_text) > 0:
                return paper_type_text
    return None

def extract_ais_pdf_url(soup, base_url):
    """
    Extract PDF download URL from AIS eLibrary page.
    
    Args:
        soup (BeautifulSoup): Parsed HTML content
        base_url (str): Base URL of the AIS page
        
    Returns:
        str: PDF download URL if found, None otherwise
    """
    if soup is None:
        print("Error: Cannot extract PDF URL - HTML content is None")
        return None
    
    # Look for link with id="pdf"
    pdf_link = soup.find('a', id='pdf', href=True)
    if pdf_link:
        href = pdf_link.get('href', '')
        # Clean up HTML entities in URL (e.g., &amp; -> &)
        href = html.unescape(href)
        # Make URL absolute if it's relative
        if href.startswith('http'):
            return href
        else:
            return urljoin(base_url, href)
    else:
        print("Error: PDF download link with id='pdf' not found on AIS page")
        return None

def download_pdf_from_url(pdf_url, save_dir):
    """
    Download PDF from a direct URL.
    
    Args:
        pdf_url (str): URL to the PDF file
        save_dir (str): Directory to save the PDF
        
    Returns:
        str: Path to downloaded PDF or None if failed
    """
    try:
        os.makedirs(save_dir, exist_ok=True)
        
        # Get the PDF filename from URL or generate one
        from urllib.parse import urlparse
        parsed_url = urlparse(pdf_url)
        filename = os.path.basename(parsed_url.path)
        if not filename or not filename.endswith('.pdf'):
            filename = f"downloaded_{hash(pdf_url) % 10000}.pdf"
        
        pdf_path = os.path.join(save_dir, filename)
        
        # Prepare cookies for AIS eLibrary authentication
        cookies = {}
        if 'aisel.aisnet.org' in pdf_url:
            # AIS eLibrary requires authentication cookie for PDF downloads
            # Read cookie from .secrets.txt JSON file in the script's directory
            secrets_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.secrets.txt')
            ais_cookie = ''
            if os.path.exists(secrets_file):
                with open(secrets_file, 'r') as f:
                    secrets = json.load(f)
                    ais_cookie = secrets.get('ais_auth_cookie', '')
            cookies['BPAuth201311'] = ais_cookie
        
        # Download the PDF
        print(f"Downloading PDF from: {pdf_url}")
        response = requests.get(pdf_url, timeout=30, stream=True, cookies=cookies if cookies else None)
        response.raise_for_status()
        
        # Check if it's actually a PDF
        content_type = response.headers.get('content-type', '').lower()
        if 'pdf' not in content_type and not pdf_url.endswith('.pdf'):
            print("Warning: URL does not appear to be a PDF")
        
        # Save the PDF
        with open(pdf_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"PDF downloaded successfully from AIS")
        return pdf_path
    except Exception as e:
        print(f"Error downloading PDF from URL: {str(e)}")
        return None

def extract_citation_metadata(soup):
    """
    Extract volume, issue, pages, and journal name from the recommended citation div.
    
    Args:
        soup (BeautifulSoup): Parsed HTML content
        
    Returns:
        dict: Dictionary with 'volume', 'issue', 'pages', 'journal' keys (values may be empty)
    """
    result = {'volume': '', 'issue': '', 'pages': '', 'journal': ''}
    
    citation_div = soup.find('div', id='recommended_citation')
    if not citation_div:
        return result
    
    # Extract journal name from <em> tag
    em_tag = citation_div.find('em')
    if em_tag:
        result['journal'] = em_tag.get_text(strip=True)
    
    # Get the full text content for parsing
    citation_text = citation_div.get_text()
    
    # Try to extract volume and issue
    # Pattern 1: "(49: 3)" format (volume: issue)
    vol_iss_match = re.search(r'\((\d+):\s*(\d+)\)', citation_text)
    if vol_iss_match:
        result['volume'] = vol_iss_match.group(1)
        result['issue'] = vol_iss_match.group(2)
    else:
        # Pattern 2: "Vol. 16 : Iss. 1" format
        vol_match = re.search(r'Vol\.?\s*(\d+)', citation_text)
        if vol_match:
            result['volume'] = vol_match.group(1)
        iss_match = re.search(r'Iss\.?\s*(\d+)', citation_text)
        if iss_match:
            result['issue'] = iss_match.group(1)
    
    # Try to extract pages
    # Pattern 1: "pp.917-952" or "pp.iii-xi"
    pages_match = re.search(r'pp\.?\s*([ivxlcdm\d]+-[ivxlcdm\d]+)', citation_text, re.IGNORECASE)
    if pages_match:
        result['pages'] = pages_match.group(1)
    else:
        # Pattern 2: Just page numbers like "917-952"
        pages_match = re.search(r'(\d+-\d+)', citation_text)
        if pages_match:
            result['pages'] = pages_match.group(1)
    
    return result

def extract_ais_metadata_from_html(soup, full_url):
    """
    Extract metadata from AIS eLibrary HTML page.
    
    Args:
        soup (BeautifulSoup): Parsed HTML content
        full_url (str): Full URL of the AIS page
        
    Returns:
        tuple: (metadata dict, publication type) or (None, None) if failed
    """
    if soup is None:
        return None, None
    
    metadata = {}
    
    # Extract title (usually in h1 or h2)
    title_elem = soup.find('h1') or soup.find('h2')
    if title_elem:
        metadata['title'] = title_elem.get_text(strip=True)
    
    # Extract authors from "Presenter Information" or "Authors" section
    authors = []
    institutions = []
    # Look for "Presenter Information" or "Authors" heading
    presenter_heading = soup.find(string=lambda text: text and 'Presenter Information' in text)
    if not presenter_heading:
        # Also try "Authors" heading (used on some AIS pages)
        presenter_heading = soup.find(string=lambda text: text and text.strip() == 'Authors')
    if presenter_heading:
        # Find the parent element (usually a heading tag)
        parent = presenter_heading.find_parent(['h2', 'h3', 'h4', 'div', 'section'])
        if parent:
            # Look for all bold/strong elements after the heading (these contain author names)
            for bold in parent.find_all_next(['b', 'strong'], limit=20):
                author_text = bold.get_text(strip=True)
                # Skip common non-author text
                skip_texts = ['Presenter Information', 'Authors', 'Follow', 'Paper Number', 'Paper Type', 
                              'Abstract', 'Comments', 'Recommended Citation', 'Download', 
                              'Author Connect Link', 'DOWNLOADS', 'Share', 'COinS', 'Paper',
                              'Additional Files', 'Additional files']
                if author_text and author_text not in skip_texts:
                    # Remove "Follow" if present
                    author_text = author_text.replace('Follow', '').strip()
                    if author_text:
                        # Try to find institution in the next sibling (often in italics or after comma)
                        institution = ""
                        # Check if there's italic text or em tag next to the bold tag
                        next_sibling = bold.find_next_sibling(['em', 'i'])
                        if next_sibling:
                            institution = next_sibling.get_text(strip=True).replace('Follow', '').strip()
                        else:
                            # Check if institution is in the same text after a comma
                            if ',' in author_text:
                                parts = author_text.split(',')
                                author_text = parts[0].strip()
                                institution = parts[1].strip() if len(parts) > 1 else ""
                        
                        # Split name into given and family
                        name_parts = author_text.split()
                        if len(name_parts) >= 2:
                            given = ' '.join(name_parts[:-1])
                            family = name_parts[-1]
                            authors.append({'given': given, 'family': family})
                            if institution:
                                institutions.append(institution)
                        elif len(name_parts) == 1 and len(name_parts[0]) > 2:
                            # Single name - might be last name only
                            authors.append({'given': '', 'family': name_parts[0]})
                            if institution:
                                institutions.append(institution)
                        # Stop if we've found reasonable number of authors
                        if len(authors) >= 10:
                            break
            # Stop searching after we've processed the presenter section
            if authors:
                pass  # Already found authors
    
    # Alternative: look for patterns like "Name, Institution_Follow" in the page
    if not authors:
        # Look for text patterns that match author format
        for elem in soup.find_all(['p', 'div', 'span']):
            text = elem.get_text(strip=True)
            # Pattern: "Name, Institution" followed by "Follow" or similar
            if text and '_' in text and any(x in text.lower() for x in ['university', 'college', 'school']):
                # Try to extract author names
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and ',' in line:
                        parts = line.split(',')
                        name_part = parts[0].strip()
                        institution = parts[1].strip() if len(parts) > 1 else ""
                        name_parts = name_part.split()
                        if len(name_parts) >= 2:
                            given = ' '.join(name_parts[:-1])
                            family = name_parts[-1]
                            authors.append({'given': given, 'family': family})
                            if institution:
                                institutions.append(institution)
                            if len(authors) >= 10:
                                break
                if authors:
                    break
    
    metadata['author'] = authors if authors else []
    metadata['institutions'] = institutions if institutions else []
    
    # Extract paper number (maps to "number" field in templates)
    paper_number = extract_paper_number_from_html(soup)
    if paper_number:
        metadata['issue'] = paper_number  # "issue" maps to "number" in templates
    
    # Extract paper type
    paper_type = extract_paper_type_from_html(soup)
    if paper_type:
        metadata['paper_type'] = paper_type
    
    # Extract track info (if available)
    track_div = soup.find('div', id='track')
    if track_div:
        track_p = track_div.find('p')
        if track_p:
            track_text = track_p.get_text(strip=True)
            if track_text:
                metadata['track'] = track_text
    
    # Extract comments (if available)
    comments_div = soup.find('div', id='comments')
    if comments_div:
        comments_p = comments_div.find('p')
        if comments_p:
            comments_text = comments_p.get_text(strip=True)
            if comments_text:
                metadata['comments'] = comments_text
    
    # Extract abstract
    abstract_heading = soup.find(string=lambda text: text and 'Abstract' in text)
    if abstract_heading:
        parent = abstract_heading.find_parent(['h2', 'h3', 'h4', 'div', 'section'])
        if parent:
            # Find the next paragraph or div containing abstract text
            # Try to get all paragraphs until we hit another heading or section
            abstract_parts = []
            current = parent.find_next(['p', 'div'])
            while current:
                # Stop if we hit another heading
                if current.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    break
                text = current.get_text(strip=True)
                # Skip if it's too short or looks like a heading
                if text and len(text) > 10 and text not in ['Abstract', 'Paper Number', 'Paper Type']:
                    abstract_parts.append(text)
                # Move to next sibling
                current = current.find_next_sibling(['p', 'div'])
                # Limit to prevent going too far
                if len(abstract_parts) >= 5:
                    break
            
            if abstract_parts:
                # Join all abstract parts
                abstract_text = ' '.join(abstract_parts)
                # Clean up abstract text (remove extra whitespace)
                abstract_text = ' '.join(abstract_text.split())
                if abstract_text and len(abstract_text) > 20:  # Reasonable minimum length
                    metadata['abstract'] = abstract_text
            else:
                # Fallback: just get the first paragraph/div
                next_elem = parent.find_next(['p', 'div'])
                if next_elem:
                    abstract_text = next_elem.get_text(strip=True)
                    # Clean up abstract text (remove extra whitespace)
                    abstract_text = ' '.join(abstract_text.split())
                    if abstract_text and len(abstract_text) > 20:  # Reasonable minimum length
                        metadata['abstract'] = abstract_text
    
    # Extract year from URL or page
    # AIS URLs often contain year: e.g., amcis2025, icis2024
    year = None
    if full_url:
        year_match = re.search(r'(\d{4})', full_url)
        if year_match:
            year = int(year_match.group(1))
    
    # If not found in URL, try to extract from page
    if not year:
        year_elem = soup.find(string=lambda text: text and re.search(r'\b(19|20)\d{2}\b', text) if text else False)
        if year_elem:
            year_match = re.search(r'\b(19|20)\d{2}\b', year_elem)
            if year_match:
                year = int(year_match.group())
    
    # Extract conference/proceedings name (booktitle)
    booktitle = None
    # Look for conference name in breadcrumbs or headings
    breadcrumb = soup.find('nav', class_=lambda x: x and 'breadcrumb' in x.lower()) or \
                 soup.find(string=lambda text: text and ('Proceedings' in text or 'Conference' in text))
    if breadcrumb:
        if isinstance(breadcrumb, str):
            # Extract conference name
            if 'AMCIS' in breadcrumb:
                booktitle = 'AMCIS Proceedings'
            elif 'ICIS' in breadcrumb:
                booktitle = 'ICIS Proceedings'
            elif 'ECIS' in breadcrumb:
                booktitle = 'ECIS Proceedings'
            else:
                # Try to extract from breadcrumb text
                parts = breadcrumb.split()
                for i, part in enumerate(parts):
                    if 'Proceedings' in part and i > 0:
                        booktitle = ' '.join(parts[max(0, i-2):i+1])
                        break
        else:
            text = breadcrumb.get_text()
            if 'AMCIS' in text:
                booktitle = 'AMCIS Proceedings'
            elif 'ICIS' in text:
                booktitle = 'ICIS Proceedings'
            elif 'ECIS' in text:
                booktitle = 'ECIS Proceedings'
    
    # Set issued date
    if year:
        metadata['issued'] = {'date-parts': [[year]]}
    
    # Set container-title (booktitle for conferences)
    if booktitle:
        # Clean up booktitle - remove trailing colons
        booktitle = booktitle.rstrip(':').strip()
        metadata['container-title'] = booktitle
    
    # Determine if this is a journal or conference based on URL
    if is_ais_journal_url(full_url):
        metadata['type'] = 'Journal Article'
        pub_type = 'journal'
        
        # Extract volume, issue, pages, and journal name from recommended citation
        citation_data = extract_citation_metadata(soup)
        
        # Set journal name (container-title)
        if citation_data['journal']:
            metadata['container-title'] = citation_data['journal']
        elif not metadata.get('container-title'):
            # Fallback: try to extract journal name from the page
            journal_name_elem = soup.find('div', id='series-title') or soup.find('h1', class_='series-title')
            if journal_name_elem:
                metadata['container-title'] = journal_name_elem.get_text(strip=True)
        
        # Set volume, issue, and pages from citation
        if citation_data['volume']:
            metadata['volume'] = citation_data['volume']
        if citation_data['issue']:
            metadata['issue'] = citation_data['issue']
        if citation_data['pages']:
            metadata['page'] = citation_data['pages']
    else:
        metadata['type'] = 'Conference Proceedings'
        pub_type = 'conference'
    
    # Set URL
    metadata['URL'] = full_url
    
    # Extract DOI if available (though this function is for non-DOI cases)
    doi = extract_doi_from_html(soup)
    if doi:
        metadata['DOI'] = doi
    
    return metadata, pub_type

def process_ais_paper(ais_id, template_dir, markdown_output_dir, pdf_output_dir, skip_pdf=False, local_pdf=None, related_projects=None):
    """
    Process an AIS eLibrary paper: fetch metadata, download PDF, create note.
    
    Args:
        ais_id (str): AIS eLibrary paper ID, URL, or path
        template_dir (str): Directory containing templates
        markdown_output_dir (str): Directory for markdown output
        pdf_output_dir (str): Directory for PDF output
        skip_pdf (bool): Whether to skip PDF download
        local_pdf (str): Path to local PDF file
        related_projects (str): Related projects to add to the note
    """
    # Normalize the AIS input (handle both full URLs and shortened paths)
    normalized_path, full_url = normalize_ais_url(ais_id)
    
    print(f"Processing AIS eLibrary paper: {ais_id}")
    print(f"Normalized path: {normalized_path}")
    print(f"Full URL: {full_url}")
    
    # Fetch HTML from the AIS URL
    print("Fetching HTML from AIS eLibrary...")
    soup = fetch_ais_html(full_url)
    
    if soup is None:
        print("Failed to fetch HTML from AIS eLibrary")
        return
    
    # Try to download PDF from AIS website first (for both DOI and non-DOI cases)
    pdf_path = None
    if not skip_pdf and not local_pdf:
        print("Attempting to download PDF from AIS website...")
        pdf_url = extract_ais_pdf_url(soup, full_url)
        if pdf_url:
            pdf_path = download_pdf_from_url(pdf_url, "/tmp")
            if pdf_path:
                print(f"PDF downloaded from AIS website: {pdf_url}")
            else:
                print("Failed to download PDF from AIS website")
        else:
            print("No PDF download link found on AIS page")
    
    # Extract DOI from HTML
    doi = extract_doi_from_html(soup)
    
    if doi:
        print(f"Found DOI in AIS page: {doi}")
        # Use the same CrossRef API approach as with regular DOI processing
        metadata, pub_type = get_metadata_from_doi(doi)
        if metadata:
            # Successfully retrieved metadata from CrossRef
            print("Successfully retrieved metadata from CrossRef")
            # If we have a PDF from AIS, use it; otherwise try DOI-based download
            if pdf_path:
                # Use the AIS PDF we already downloaded
                process_metadata(metadata, pub_type, template_dir, markdown_output_dir, pdf_output_dir,
                                 None, True, pdf_path, doi, related_projects)  # skip_pdf=True, local_pdf=pdf_path
            else:
                # Process with DOI-based PDF download
                process_metadata(metadata, pub_type, template_dir, markdown_output_dir, pdf_output_dir,
                                 None, skip_pdf, local_pdf, doi, related_projects)
            return
        else:
            # DOI lookup failed, fall back to HTML extraction
            print("DOI lookup failed, falling back to HTML extraction...")
    else:
        print("No DOI found in AIS page.")
    
    # No DOI found or DOI lookup failed - extract metadata from HTML
    print("Extracting metadata from HTML...")
    metadata, pub_type = extract_ais_metadata_from_html(soup, full_url)
    
    if not metadata or not metadata.get('title'):
        print("Failed to extract sufficient metadata from AIS page")
        return
    
    print(f"Extracted metadata: {metadata.get('title', 'Unknown title')}")
    
    # Process metadata using the shared function
    # If we have a PDF from AIS, use it
    if pdf_path:
        process_metadata(metadata, pub_type, template_dir, markdown_output_dir, pdf_output_dir,
                         None, True, pdf_path, None, related_projects)  # skip_pdf=True, local_pdf=pdf_path
    else:
        process_metadata(metadata, pub_type, template_dir, markdown_output_dir, pdf_output_dir,
                         None, skip_pdf, local_pdf, None, related_projects)

def process_metadata(metadata, pub_type, template_dir, markdown_output_dir, pdf_output_dir, 
                     force_type=None, skip_pdf=False, local_pdf=None, doi=None, related_projects=None):
    """
    Process metadata to create Obsidian note: select template, handle PDF, create markdown.
    This is the core processing function that can be used by both DOI and AIS processing.
    
    Args:
        metadata (dict): Publication metadata
        pub_type (str): Publication type
        template_dir (str): Directory containing templates
        markdown_output_dir (str): Directory for markdown output
        pdf_output_dir (str): Directory for PDF output
        force_type (str): Force publication type (optional)
        skip_pdf (bool): Whether to skip PDF download
        local_pdf (str): Path to local PDF file (optional)
        doi (str): DOI string for PDF download (optional)
        related_projects (str): Related projects to add to the note (optional)
    """
    # Override publication type if forced
    if force_type:
        pub_type = force_type
        # Format the type consistently
        type_mapping = {
            "conference": "Conference Proceedings",
            "journal": "Journal Article",
            "book": "Book",
            "chapter": "Book Chapter",
            "misc": "Misc"
        }
        metadata["type"] = type_mapping.get(force_type, force_type.capitalize())
        print(f"Using type: {metadata['type']}")
    else:
        print(f"Using type: {metadata['type']}")

    # Check for required fields
    check_required_fields(metadata, pub_type)

    # Select template based on publication type
    template_mapping = {
        "conference": "conference_template.md",
        "journal": "journal_template.md",
        "book": "book_template.md",
        "chapter": "chapter_template.md",
        "misc": "misc_template.md"
    }
    template_path = os.path.join(template_dir, template_mapping.get(pub_type, "misc_template.md"))

    # Extract publication year from metadata
    pub_year = metadata.get("issued", {}).get("date-parts", [[None]])[0][0]

    # Clean and filter authors
    authors = metadata.get("author", [])
    valid_authors = []
    for author in authors:
        cleaned_name = clean_author_name(author)
        if cleaned_name:
            valid_authors.append(author)
    
    # For books, use editors as authors if no authors are present
    if metadata.get("type") == "Book" and not valid_authors:
        editors = metadata.get("editor", [])
        valid_editors = []
        for editor in editors:
            cleaned_name = clean_author_name(editor)
            if cleaned_name:
                valid_editors.append(editor)
        if valid_editors:
            valid_authors = valid_editors
    
    # Get first valid author for alias
    first_author = get_first_valid_author(valid_authors)
    alias = f"{first_author}{pub_year}"
    title = metadata.get("title", "")

    # Check if markdown file already exists anywhere in the output directory
    existing_file = check_paper_exists(markdown_output_dir, alias, title)
    if existing_file:
        print(f"Paper already exists at: {existing_file}")
        return

    # Handle PDF
    pdf_filename = None
    if local_pdf:
        # Use local PDF (always process if provided, regardless of skip_pdf)
        if os.path.exists(local_pdf):
            pdf_filename = rename_and_copy_pdf(local_pdf, alias, pdf_output_dir, title)
            print(f"PDF moved to {pdf_output_dir}/{pdf_filename}")
        else:
            print(f"Warning: Local PDF not found at {local_pdf}")
    elif not skip_pdf and doi:
        # Download PDF using DOI
        print(f"Attempting to download PDF for DOI: {doi}")
        pdf_path = download_pdf_with_pypaperbot(doi, "/tmp")
        if pdf_path:
            pdf_filename = rename_and_copy_pdf(pdf_path, alias, pdf_output_dir, title)
            print(f"PDF moved to {pdf_output_dir}/{pdf_filename}")
        else:
            print("PDF not downloaded.")

    # Create and save markdown
    content, _ = fill_template(template_path, metadata, pdf_filename, pdf_output_dir, related_projects)
    saved_path = save_markdown(content, alias, markdown_output_dir, title)
    if saved_path:
        print(f"Note created and saved to {saved_path}")

    # Print BibTeX entry
    print("BibTeX entry:")
    bibtex = create_bibtex_string(metadata, alias)
    # Ensure proper ampersand handling in printed BibTeX
    bibtex = bibtex.replace("\\&amp;", "\\&")
    print(bibtex)

def process_doi(doi, template_dir, markdown_output_dir, pdf_output_dir, force_type=None, skip_pdf=False, local_pdf=None, related_projects=None):
    """
    Process a DOI: fetch metadata, download PDF, create note.
    """
    # Fetch metadata
    metadata, pub_type = get_metadata_from_doi(doi)
    if not metadata:
        print("Exiting: Cannot proceed without metadata")
        exit(1)

    # Process metadata using the shared function
    process_metadata(metadata, pub_type, template_dir, markdown_output_dir, pdf_output_dir,
                     force_type, skip_pdf, local_pdf, doi, related_projects)

def read_directories():
    """
    Read directory paths from directories.txt.
    
    Returns:
        dict: Dictionary of directory paths
        
    Raises:
        SystemExit: If directories.txt is missing or required paths are not found
    """
    required_dirs = ['markdown_dir', 'pdf_dir']
    directories = {}
    
    try:
        with open('directories.txt', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    directories[key] = value
    except FileNotFoundError:
        print("Error: directories.txt not found")
        print("Please create a directories.txt file with the following format:")
        print("markdown_dir=/path/to/your/obsidian/notes/")
        print("pdf_dir=/path/to/your/papers/")
        exit(1)
    
    # Check for missing required directories
    missing_dirs = [dir for dir in required_dirs if dir not in directories]
    if missing_dirs:
        print(f"Error: Missing required directories in directories.txt: {', '.join(missing_dirs)}")
        print("Please ensure directories.txt contains all required paths:")
        print("markdown_dir=/path/to/your/obsidian/notes/")
        print("pdf_dir=/path/to/your/papers/")
        exit(1)
    
    return directories

def main():
    """Main function to parse arguments and process DOI."""
    # Read directories from file
    directories = read_directories()
    
    parser = argparse.ArgumentParser(description='Process a DOI and create Obsidian notes with optional PDF download.')
    parser.add_argument('-doi', help='The DOI to process')
    parser.add_argument('-ais', help='AIS eLibrary paper ID or URL to process')
    parser.add_argument('--markdown-dir', default=directories['markdown_dir'],
                      help=f'Directory for markdown output (default: {directories["markdown_dir"]})')
    parser.add_argument('--pdf-dir', default=directories['pdf_dir'],
                      help=f'Directory for PDF output (default: {directories["pdf_dir"]})')
    parser.add_argument('--force-type', choices=['conference', 'journal', 'book', 'chapter', 'misc'],
                      help='Force the DOI to be treated as a specific type')
    parser.add_argument('--skip-pdf', action='store_true', help='Skip PDF download and only create markdown')
    parser.add_argument('--local-pdf', help='Path to a local PDF file to use instead of downloading')
    parser.add_argument('--related-projects', help='Related projects to add to the note (e.g., "[[Project A]], [[Project B]]")')

    args = parser.parse_args()

    # Process AIS eLibrary paper if -ais flag is provided
    if args.ais:
        process_ais_paper(
            args.ais,
            TEMPLATE_DIR,  # Use hard-coded template directory
            args.markdown_dir,
            args.pdf_dir,
            args.skip_pdf,
            args.local_pdf,
            args.related_projects
        )
    # Process DOI if -doi flag is provided
    elif args.doi:
        process_doi(
        args.doi,
        TEMPLATE_DIR,  # Use hard-coded template directory
        args.markdown_dir,
        args.pdf_dir,
        args.force_type,
        args.skip_pdf,
        args.local_pdf,
        args.related_projects
    )
    else:
        parser.error('Either -doi or -ais must be provided')

if __name__ == "__main__":
    main()
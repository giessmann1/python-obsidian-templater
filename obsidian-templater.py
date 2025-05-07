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
from datetime import datetime
from habanero import cn

TEMPLATE_DIR = "templates"

# Maps BibTeX fields to their corresponding metadata fields
type_fields = {
    "conference": {
        "booktitle": "collection-title",
        "month": "issued.date-parts",
        "volume": "volume",
        "number": "issue",
        "pages": "page",
        "series": "container-title",
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
        "booktitle": "container-title",
        "publisher": "publisher",
        "address": "publisher-location",
        "pages": "page",
        "editor": "editor",
        "isbn": "ISBN",
        "series": "collection-title",
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
        
        # Determine publication type based on metadata
        pub_type = "Misc"  # default type
        
        if metadata.get("type") == "paper-conference" or \
           "conference" in metadata.get("container-title", "").lower() or \
           "proceedings" in metadata.get("container-title", "").lower():
            pub_type = "conference"
            metadata["type"] = "Conference Proceedings"
        elif metadata.get("type") == "book-chapter":
            pub_type = "chapter"
            metadata["type"] = "Book Chapter"
        elif metadata.get("type") == "book":
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
        # Run subprocess with output redirected to devnull
        with open(os.devnull, 'w') as devnull:
            subprocess.run(cmd, stdout=devnull, stderr=devnull, check=True)

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
    except subprocess.CalledProcessError:
        # Clean up the temporary directory on error
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        print("No PDF was found for this DOI")
        return None
    except Exception as e:
        # Clean up the temporary directory on any other error
        if os.path.exists(temp_dir):
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
    # Format author list
    authors = metadata.get("author", [])
    author_entries = " and ".join(
        f"{a.get('family', '')}, {a.get('given', '')}" for a in authors
    )
    
    # Format editor list
    editors = metadata.get("editor", [])
    editor_entries = " and ".join(
        f"{e.get('family', '')}, {e.get('given', '')}" for e in editors
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

    # Format BibTeX string
    bibtex = f"@{entry_type}{{{alias},\n"
    for key, val in fields.items():
        bibtex += f"\t{key}={{{val}}},\n"
    bibtex = bibtex.rstrip(",\n") + "\n}"
    return bibtex

def fill_template(template_path, metadata, pdf_filename, pdf_output_dir):
    """
    Fill template with metadata and return formatted content.
    
    Args:
        template_path (str): Path to template file
        metadata (dict): Publication metadata
        pdf_filename (str): Name of PDF file
        pdf_output_dir (str): Directory containing PDF
        
    Returns:
        tuple: (formatted content, citation key)
    """
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Helper function to safely get and format metadata values for markdown
    def get_metadata_value(key, default=""):
        value = metadata.get(key, default)
        if isinstance(value, list):
            value = value[0] if value else default
        # Deescape any HTML entities
        return html.unescape(str(value))

    # Extract basic metadata
    year = metadata.get("issued", {}).get("date-parts", [[None]])[0][0]
    month = metadata.get("issued", {}).get("date-parts", [[None]])[0][1] if len(metadata.get("issued", {}).get("date-parts", [[None]])[0]) > 1 else None
    authors = metadata.get("author", [])
    first_author = authors[0].get("family", "Unknown") if authors else "Unknown"
    alias = f"{first_author}{year}"
    imported_date = datetime.today().strftime("%Y-%m-%d")
    status = "Imported" if pdf_filename else "NoPDF"

    # Format author and editor lists
    author_list = "".join(f"  - \"{a.get('given', '')} {a.get('family', '')}\"\n" for a in authors)
    editor_list = "".join(f"  - \"{e.get('given', '')} {e.get('family', '')}\"\n" for e in metadata.get("editor", []))

    # Common placeholders for all types
    placeholders = {
        "alias": alias,
        "imported_date": imported_date,
        "status": status,
        "author_list": author_list.rstrip(),
        "title": get_metadata_value("title"),
        "year": year or "",
        "doi": metadata.get("DOI", "") or "",
        "pdf_link": pdf_output_dir + pdf_filename if pdf_filename else "PDF not available",
        "bibtex": create_bibtex_string(metadata, alias)
    }

    # Add type-specific placeholders
    if metadata.get("type") == "Conference Proceedings":
        placeholders.update({
            "booktitle": get_metadata_value("collection-title"),
            "month": month or "",
            "volume": get_metadata_value("volume"),
            "number": get_metadata_value("issue"),
            "pages": get_metadata_value("page").replace("--", "-"),
            "series": get_metadata_value("container-title"),
            "editor_list": editor_list.rstrip(),
            "publisher": get_metadata_value("publisher"),
            "address": get_metadata_value("publisher-location"),
            "organization": get_metadata_value("event.name")
        })
    elif metadata.get("type") == "Journal Article":
        placeholders.update({
            "journal": get_metadata_value("container-title"),
            "volume": get_metadata_value("volume"),
            "number": get_metadata_value("issue"),
            "pages": get_metadata_value("page").replace("--", "-"),
            "issn": metadata.get("ISSN", [""])[0] or ""  # Take first ISSN if multiple exist
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
            "booktitle": get_metadata_value("container-title"),
            "publisher": get_metadata_value("publisher"),
            "address": get_metadata_value("publisher-location"),
            "pages": get_metadata_value("page").replace("--", "-"),
            "editor_list": editor_list.rstrip(),
            "isbn": metadata.get("ISBN", [""])[0] or "",  # Take first ISBN if multiple exist
            "series": get_metadata_value("collection-title"),
            "edition": get_metadata_value("edition"),
            "chapter": get_metadata_value("chapter")
        })

    # Replace all placeholders in template
    for key, val in placeholders.items():
        content = content.replace(f"{{{{{key}}}}}", str(val))

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

def save_markdown(content, alias, output_dir, title):
    """
    Save markdown content to file.
    
    Args:
        content (str): Content to save
        alias (str): Citation key
        output_dir (str): Output directory
        title (str): Publication title
        
    Returns:
        str: Path to saved file
    """
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

    # Copy PDF to output directory
    new_pdf_path = os.path.join(pdf_output_dir, f"{alias}_{clean_title_for_filename(title)}.pdf")
    shutil.copy(pdf_path, new_pdf_path)
    
    return f"{alias}_{clean_title_for_filename(title)}.pdf"

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
            print(f"Warning: Missing fields for: {', '.join(missing_fields)}")
        return missing_fields
    return []

def process_doi(doi, template_dir, markdown_output_dir, pdf_output_dir, force_type=None, skip_pdf=False, local_pdf=None):
    """
    Process a DOI: fetch metadata, download PDF, create note.
    
    Args:
        doi (str): DOI to process
        template_dir (str): Directory containing templates
        markdown_output_dir (str): Directory for markdown output
        pdf_output_dir (str): Directory for PDF output
        force_type (str, optional): Force publication type
        skip_pdf (bool, optional): Skip PDF download
        local_pdf (str, optional): Path to local PDF file
    """
    # Fetch metadata
    metadata, pub_type = get_metadata_from_doi(doi)
    if not metadata:
        print("Exiting: Cannot proceed without metadata")
        exit(1)

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

    # Compute alias and title
    year = metadata.get("issued", {}).get("date-parts", [[None]])[0][0]
    authors = metadata.get("author", [])
    first_author = authors[0].get("family", "Unknown") if authors else "Unknown"
    alias = f"{first_author}{year}"
    title = metadata.get("title", "")

    # Handle PDF
    pdf_filename = None
    if not skip_pdf:
        if local_pdf:
            # Use local PDF
            if os.path.exists(local_pdf):
                pdf_filename = rename_and_copy_pdf(local_pdf, alias, pdf_output_dir, title)
                print(f"PDF moved to {pdf_output_dir}/{pdf_filename}")
            else:
                print(f"Warning: Local PDF not found at {local_pdf}")
        else:
            # Download PDF
            pdf_path = download_pdf_with_pypaperbot(doi, "/tmp")
            if pdf_path:
                pdf_filename = rename_and_copy_pdf(pdf_path, alias, pdf_output_dir, title)
                print(f"PDF moved to {pdf_output_dir}/{pdf_filename}")
            else:
                print("PDF not downloaded.")

    # Create and save markdown
    content, _ = fill_template(template_path, metadata, pdf_filename, pdf_output_dir)
    filepath = save_markdown(content, alias, markdown_output_dir, title)
    print(f"Note created and moved to {filepath}")

    # Print BibTeX entry
    print("BibTeX entry:")
    bibtex = create_bibtex_string(metadata, alias)
    # Ensure proper ampersand handling in printed BibTeX
    bibtex = bibtex.replace("\\&amp;", "\\&")
    print(bibtex)

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
    parser.add_argument('--markdown-dir', default=directories['markdown_dir'],
                      help=f'Directory for markdown output (default: {directories["markdown_dir"]})')
    parser.add_argument('--pdf-dir', default=directories['pdf_dir'],
                      help=f'Directory for PDF output (default: {directories["pdf_dir"]})')
    parser.add_argument('--force-type', choices=['conference', 'journal', 'book', 'chapter', 'misc'],
                      help='Force the DOI to be treated as a specific type')
    parser.add_argument('--skip-pdf', action='store_true', help='Skip PDF download and only create markdown')
    parser.add_argument('--local-pdf', help='Path to a local PDF file to use instead of downloading')

    args = parser.parse_args()

    process_doi(
        args.doi,
        TEMPLATE_DIR,  # Use hard-coded template directory
        args.markdown_dir,
        args.pdf_dir,
        args.force_type,
        args.skip_pdf,
        args.local_pdf
    )

if __name__ == "__main__":
    main()
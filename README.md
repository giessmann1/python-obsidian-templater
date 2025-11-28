# Obsidian Templater

Just a small vibe coding project that automatically generates Obsidian literature notes following templates and organizes PDFs from DOIs.

❗ This is an actively maintained repository for scholarly purposes only. If you have suggestions for further improvement or find bugs: [Email me](mailto:nico.giessmann@uni-luebeck.de)

## Features

- Fetches metadata from DOIs using CrossRef API
- **AIS eLibrary support**: Process papers directly from AIS eLibrary URLs
- Automatically detects publication type (journal, conference, book, chapter, misc)
- Downloads PDFs using PyPaperBot (if available)
- Creates Obsidian literature notes using templates
- Organizes literature notes into year/quarter folders
- Generates BibTeX entries
- Configurable paths through directories.txt

## Requirements

- Python 3.x
- Required Python packages (install using requirements.txt):
  ```bash
  python3 -m venv .env
  source .env/bin/activate
  pip install -r requirements.txt
  ```

## Setup

1. Create `directories.txt` with the following format:
```txt
markdown_dir=/path/to/your/obsidian/notes
pdf_dir=/path/to/your/papers
```

2. (Optional) For AIS eLibrary PDF downloads, create `.secrets.txt` with your authentication cookie:
```json
{
    "ais_auth_cookie": "YOUR_BPAUTH201311_COOKIE_VALUE_HERE"
}
```
See [AIS eLibrary Authentication](#ais-elibrary-authentication) for details on obtaining the cookie.

3. Update the `templates` directory if needed:
   - `journal_template.md`
   - `conference_template.md`
   - `book_template.md`
   - `chapter_template.md`
   - `misc_template.md`

## Usage

### Command Line Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `-doi` | DOI to process | Required (or `-ais`) |
| `-ais` | AIS eLibrary paper URL or ID to process | Required (or `-doi`) |
| `--markdown-dir` | Override markdown output directory | From directories.txt |
| `--pdf-dir` | Override PDF output directory | From directories.txt |
| `--force-type` | Force publication type | Auto-detected |
| `--skip-pdf` | Skip PDF download | False |
| `--local-pdf` | Use local PDF file instead of downloading | None |
| `--related-projects` | Related projects to add to the note (e.g., `"[[Project A]]"`) | None |

### Examples

1. Basic usage with a DOI:
```bash
python obsidian-templater.py -doi 10.1007/978-3-031-68211-7_10
```

2. Skip PDF download:
```bash
python obsidian-templater.py -doi 10.1007/978-3-031-68211-7_10 --skip-pdf
```

3. Use a local PDF file:
```bash
python obsidian-templater.py -doi 10.1007/978-3-031-68211-7_10 --local-pdf "/path/to/paper.pdf"
```

4. Force publication type:
```bash
python obsidian-templater.py -doi 10.1007/978-3-031-68211-7_10 --force-type conference
```
Hint: If the metadata type is incorrect, simply run the command again with the correct type and the note and PDF will be overwritten.

5. Override output directories:
```bash
python obsidian-templater.py -doi 10.1007/978-3-031-68211-7_10 \
    --markdown-dir "/path/to/notes" \
    --pdf-dir "/path/to/papers"
```

6. Add related projects to a note:
```bash
python obsidian-templater.py -doi 10.1007/978-3-031-68211-7_10 --related-projects "[[My Dissertation]]"
```

7. Multiple related projects:
```bash
python obsidian-templater.py -doi 10.1007/978-3-031-68211-7_10 --related-projects "[[Project A]], [[Project B]]"
```

### Batch Processing

You can process multiple papers at once using the provided shell script. Create a text file with one DOI or AIS URL per line (e.g., `papers.txt`):

```txt
# DOIs
10.1007/978-3-031-68211-7_10
10.1007/978-3-658-46151-5

# AIS eLibrary papers
https://aisel.aisnet.org/icis2023/blockchain/blockchain/7
icis2024/general_is/general_is/11
```

Then run:
```bash
./batch_process.sh papers.txt
```

With related projects:
```bash
./batch_process.sh papers.txt --related-projects "[[My Research Project]]"
```

Multiple related projects:
```bash
./batch_process.sh papers.txt --related-projects "[[Project A]], [[Project B]]"
```

The script will:
- Automatically detect whether each line is a DOI or AIS paper
- Process each paper sequentially
- Skip empty lines and comments (lines starting with `#`)
- Remove any "doi" prefix, `https://doi.org/` prefix, and extra whitespace
- Apply the `--related-projects` parameter to all processed papers
- Show progress and summary statistics

### AIS eLibrary Papers

Process papers directly from AIS eLibrary:

```bash
python obsidian-templater.py -ais "https://aisel.aisnet.org/icis2023/blockchain/blockchain/7"
```

Or using just the path:
```bash
python obsidian-templater.py -ais "icis2023/blockchain/blockchain/7"
```

With related projects:
```bash
python obsidian-templater.py -ais "icis2023/blockchain/blockchain/7" --related-projects "[[Blockchain Research]]"
```

## AIS eLibrary Authentication

To download PDFs from AIS eLibrary, you need to provide an authentication cookie. This requires membership access to AIS eLibrary.

### Obtaining the Authentication Cookie

1. Log in to [AIS eLibrary](https://aisel.aisnet.org/)
2. Open your browser's Developer Tools
3. Go to the **Network** tab
4. Navigate to any paper page on AIS eLibrary
5. Click on any request and look at the **Cookies** in the request headers
6. Find the cookie named `BPAuth201311` and copy its value

### Setting Up the Cookie

1. Copy `.secrets.txt.example` to `.secrets.txt`:
   ```bash
   cp .secrets.txt.example .secrets.txt
   ```

2. Edit `.secrets.txt` and replace the placeholder with your cookie value:
   ```json
   {
       "ais_auth_cookie": "YOUR_ACTUAL_COOKIE_VALUE"
   }
   ```

> ⚠️ **Note**: The authentication cookie may expire periodically. If PDF downloads stop working, obtain a fresh cookie by logging in again.

> 🔒 **Security**: The `.secrets.txt` file is excluded from version control via `.gitignore`. Never commit your authentication cookies.

## License
This project is licensed under the MIT License.

## Contributions
Pull requests and suggestions are welcome! Feel free to submit issues or feature requests. Please note that I am not a professional software developer, just a researcher trying automate parts of his workflow.
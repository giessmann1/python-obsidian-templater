# Obsidian Templater

Just a small vibe coding project that automatically generates Obsidian literature notes following templates and organizes PDFs from DOIs.

❗ This is an actively maintained repository for scholarly purposes only. If you have suggestions for further improvement or find bugs: [Email me](mailto:nico.giessmann@uni-luebeck.de)

## Features

- Fetches metadata from DOIs using CrossRef API
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

1. Update the `directories.txt` with the following format:
```txt
markdown_dir=/path/to/your/obsidian/notes
pdf_dir=/path/to/your/papers
```

2. Update the `templates` directory if needed:
   - `journal_template.md`
   - `conference_template.md`
   - `book_template.md`
   - `chapter_template.md`
   - `misc_template.md`

## Usage

### Command Line Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `-doi` | DOI to process | Required |
| `--markdown-dir` | Override markdown output directory | From directories.txt |
| `--pdf-dir` | Override PDF output directory | From directories.txt |
| `--force-type` | Force publication type | Auto-detected |
| `--skip-pdf` | Skip PDF download | False |
| `--local-pdf` | Use local PDF file instead of downloading | None |

### Examples

1. Basic usage with a DOI:
```bash
python obsidian-templater.py -doi 10.1038/s41586-020-2649-2
```

2. Skip PDF download:
```bash
python obsidian-templater.py -doi 10.1038/s41586-020-2649-2 --skip-pdf
```

3. Use a local PDF file:
```bash
python obsidian-templater.py -doi 10.1038/s41586-020-2649-2 --local-pdf "/path/to/paper.pdf"
```

4. Force publication type:
```bash
python obsidian-templater.py -doi 10.1038/s41586-020-2649-2 --force-type conference
```
Hint: If the metadata type is incorrect, simply run the command again with the correct type and the note and PDF will be overwritten.

5. Override output directories:
```bash
python obsidian-templater.py -doi 10.1038/s41586-020-2649-2 \
    --markdown-dir "/path/to/notes" \
    --pdf-dir "/path/to/papers"
```

## License
This project is licensed under the MIT License.

## Contributions
Pull requests and suggestions are welcome! Feel free to submit issues or feature requests. Please note that I am not a professional software developer, just a researcher trying automate parts of his workflow.
---
name: archi-scraper
description: Extract ArchiMate architecture models from Archi HTML reports. Converts published HTML reports back into editable ArchiMate Open Exchange Format XML, JSON, or Markdown. Use when working with ArchiMate models, architecture documentation, enterprise architecture reports, or when you need to reverse-engineer Archi HTML exports into structured data.
---

# ArchiScraper

Reverse-engineer Archi HTML reports into editable ArchiMate models.

## Quick Start (CLI)

```bash
# Install
pip install "git+https://github.com/gonzalopezgil/archi-scraper.git"

# List all views in a report
python scripts/html_to_archimate_xml.py --url URL --list-views

# Download all views as master XML
python scripts/html_to_archimate_xml.py --url URL --download-all -o master.xml

# Full export: XML + JSON + Markdown + images + validation
python scripts/html_to_archimate_xml.py --url URL --download-all \
  --connections --images --markdown --validate --format both -o master.xml

# Local files
python scripts/html_to_archimate_xml.py --model model.html --views view1.html view2.html -o output.xml

# Convert XML to Markdown docs
python scripts/archiscraper_to_markdown.py --input master.xml --output-dir docs/
```

## Key CLI Flags

| Flag | Description |
|---|---|
| `--url URL` | Remote Archi HTML report URL |
| `--model FILE` | Local model.html path |
| `--views FILE...` | Local view HTML files |
| `--download-all` | Download all views |
| `--list-views` | List views without downloading |
| `--select-views ID...` | Download specific view IDs |
| `-o FILE` | Output filename (default: `master_model.xml`) |
| `--format xml\|json\|both` | Output format |
| `--connections` | Include relationship elements |
| `--images` | Download PNG images per view |
| `--markdown` | Generate .md alongside output |
| `--validate` | Validate XML integrity |

## GUI Application

```bash
python scripts/ArchiScraperApp.py
```

4-step wizard: Source → Review → Options → Done. Includes embedded browser with network sniffer for auto-detecting `model.html` URLs.

## Output Formats

- **XML**: ArchiMate Open Exchange Format (`.xml`) — importable into Archi, ADOIT, etc.
- **JSON**: Structured dict with elements, relationships, views
- **Markdown**: LLM-friendly structured docs by ArchiMate layer

## Architecture

Both GUI and CLI share `archiscraper_core.py` (parser + XML generator + retry logic + validation). The `archiscraper_to_markdown.py` module converts XML output to structured Markdown.

## Requirements

- Python 3.10+
- `requests`, `beautifulsoup4`, `lxml`
- GUI additionally needs `PyQt6`, `PyQt6-WebEngine`

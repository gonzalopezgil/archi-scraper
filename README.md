# Archi Scraper

### An ArchiMate Web Report to XML Converter

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/gonzalopezgil/archi-scraper)](https://github.com/gonzalopezgil/archi-scraper/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/gonzalopezgil/archi-scraper/total)](https://github.com/gonzalopezgil/archi-scraper/releases)
[![Platform](https://img.shields.io/badge/platform-windows%20%7C%20macos-lightgrey)](https://github.com/gonzalopezgil/archi-scraper)
[![License](https://img.shields.io/github/license/gonzalopezgil/archi-scraper)](https://github.com/gonzalopezgil/archi-scraper)

**Reverse-engineer Archi HTML reports back into editable ArchiMate models**

ArchiScraper is a Python-based tool that extracts architecture data from published Archi HTML reports and converts them back into standard ArchiMate Open Exchange Format (`.xml`) files. This allows architects to recover lost models, extract data from shared websites, or migrate content between modeling tools.

![ArchiScraper Screenshot](icon.png)

![Demo of my app](https://github.com/user-attachments/assets/0f0a302b-96b3-4da6-87bd-60af018bb9ac)

---

## Key Features

- GUI application with a PyQt6 embedded browser and network sniffer to auto-discover `model.html`
- One-click export of the active view or all views as a master ArchiMate XML
- Batch mode to collect multiple views and export as a single master model
- Download ALL Views with optional connection overlays and view images
- CLI tool for remote reports and local files, including list/select view workflows
- Clean Views: connections are hidden by default to avoid spiderweb clutter while preserving the underlying relationships
- XML-to-Markdown converter that creates layer-based docs for AI/LLM consumption and semantic search
- Shared core parser/generator module used by both GUI and CLI (no UI dependencies)

---

## Installation & Usage

### Option A: Portable Executable (Recommended)

**For Windows:**
1. Download `ArchiScraper_v1.0_Windows.zip` from [Releases](https://github.com/gonzalopezgil/archi-scraper/releases).
2. Unzip the file.
3. Double-click `ArchiScraper.exe`.
   *(Note: If Windows SmartScreen prompts you, click "More Info" -> "Run Anyway").*

**For macOS (Apple Silicon M1/M2/M3):**
1. Download `ArchiScraper_v1.0_macOS_Silicon.zip` from [Releases](https://github.com/gonzalopezgil/archi-scraper/releases).
2. Unzip the file.
3. Move `ArchiScraper.app` to your Applications folder.
4. **Important:** Right-click (or Control+Click) the app and select **Open**.
   *(Required for the first run to bypass the "Unidentified Developer" check).*

### Option B: Running from Source

```bash
# Clone the repository
git clone https://github.com/gonzalopezgil/archi-scraper.git
cd archi-scraper

# Create virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run the GUI application
python scripts/ArchiScraperApp.py
```

### Option C: CLI Usage (html_to_archimate_xml.py)

Remote URL mode:

```bash
python3 scripts/html_to_archimate_xml.py --url URL [--download-all] [--list-views] \
  [--select-views VIEW_ID [VIEW_ID ...]] [--connections] [--images] \
  [--images-dir DIR] [--output FILE] [--user-agent STR]
```

Local file mode:

```bash
python3 scripts/html_to_archimate_xml.py --model FILE --views FILE [FILE ...] --output FILE
```

Key CLI flags:

- `--url URL`: Archi HTML report URL (auto-discovers `model.html` GUID)
- `--download-all`: Download all views and export as master XML
- `--list-views`: List all views (name + ID) without downloading
- `--select-views VIEW_ID [VIEW_ID ...]`: Download specific views only
- `--connections`: Include connection elements in views (default: off for clean diagrams)
- `--images`: Download PNG images for each view (URL mode only)
- `--images-dir DIR`: Directory for downloaded images (default: `images/`)
- `--output FILE`: Output XML filename (default: `master_model.xml`)
- `--user-agent STR`: Custom User-Agent header
- `--model FILE`: Path to local `model.html`
- `--views FILE [FILE ...]`: Paths to local view HTML files

### Option D: XML-to-Markdown Converter (archiscraper_to_markdown.py)

```bash
python3 scripts/archiscraper_to_markdown.py --input FILE --output-dir DIR
```

Outputs a structured documentation set organized by ArchiMate layer:

- `README.md` (overview)
- `elements/strategy.md`, `business.md`, `application.md`, `technology.md`, `motivation.md`, `implementation.md`, `other.md`
- `relationships.md` (full relationship table)
- `views/index.md` (all views with elements)

Relationship directions are represented with arrows:

- `A -> B` for outgoing relationships
- `A <- B` for incoming relationships

---

## Development

```bash
pip install -e .[dev]
pytest
```

---

## Examples

```bash
# List all views in a remote report
python3 scripts/html_to_archimate_xml.py --url https://example.com/report/index.html --list-views

# Download all views as master XML
python3 scripts/html_to_archimate_xml.py --url https://example.com/report/index.html --download-all --output master.xml

# Download with images and connections
python3 scripts/html_to_archimate_xml.py --url https://example.com/report/index.html --download-all --connections --images --output master.xml

# Convert XML to Markdown
python3 scripts/archiscraper_to_markdown.py --input master.xml --output-dir model-docs/
```

---

## Architecture

Shared core module design (single source of truth):

```text
ArchiScraperApp.py (GUI)
        |\
        | \
        |  v
        |  archiscraper_core.py
        |  (ModelDataParser, ViewParser, ArchiMateXMLGenerator)
        |
        v
html_to_archimate_xml.py (CLI) ----> archiscraper_to_markdown.py (Docs)
```

---

## Notes / Limitations

- Only works with Archi HTML Report exports (standard Archi HTML export format).
- Remote URL mode requires network access to the report URL.
- Some complex nested element relationships may need manual adjustment after import.
- Connection bendpoints are not preserved; connections are hidden in views by default (Clean Views).
- View images are only available when using `--url` + `--images`.

---

## Status/Roadmap

Actively maintained. Recent additions: User-Agent rotation, image export, XML-to-Markdown converter.

---

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

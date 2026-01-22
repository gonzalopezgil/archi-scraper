# Archi Scraper

### An ArchiMate Web Report to XML Converter

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/your-username/archi-scraper)](https://github.com/your-username/archi-scraper/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/your-username/archi-scraper/total)](https://github.com/your-username/archi-scraper/releases)
[![Platform](https://img.shields.io/badge/platform-windows-blue)](https://github.com/your-username/archi-scraper)
[![License](https://img.shields.io/github/license/your-username/archi-scraper)](https://github.com/your-username/archi-scraper)

**Reverse-engineer Archi HTML reports back into editable ArchiMate models**

ArchiScraper is a Python-based tool that extracts architecture data from published Archi HTML reports and converts them back into standard ArchiMate Open Exchange Format (`.xml`) files. This allows architects to recover lost models, extract data from shared websites, or migrate content between modeling tools.

![ArchiScraper Screenshot](icon.png)

---

## ✨ Key Features

### 🚀 One-Click Site Export
Download **every view** in a report automatically with a single button click. No need to manually navigate to each diagram.

### 🔍 Smart Network Sniffer
Automatically detects `model.html` data even in complex URL structures with randomized GUIDs (common in SharePoint, corporate intranets). No manual configuration required.

### 🎨 Clean Views
Generates diagrams with a **flattened layout** and hidden connection lines to avoid "spiderweb" visual clutter—while preserving all model relationships in the underlying data.

### 📁 Full Data Recovery
Replicates the original:
- **Folder Structure** (`<organizations>` section)
- **Element Documentation**
- **Properties and Types**

### 📦 Batch Mode
Select specific views to merge into a single **Master Model XML**, or use Download All to get everything at once.

---

## 📥 Installation & Usage

### Option A: Portable Executable (Recommended)

1. Download `ArchiScraper_v1.0_Portable.zip` from [Releases](https://github.com/your-username/archi-scraper/releases)
2. Unzip the file.
3. Run `ArchiScraper.exe` (no installation required).

### Option B: Running from Source

```bash
# Clone the repository
git clone [https://github.com/your-username/archi-scraper.git](https://github.com/your-username/archi-scraper.git)
cd archi-scraper

# Create virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Run the application
python scripts/ArchiScraperApp.py

# ArchiScraper

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

1. Download `ArchiScraper.exe` from [Releases](../../releases)
2. Run `ArchiScraper.exe` (no installation required)

### Option B: Running from Source

```bash
# Clone the repository
git clone https://github.com/your-username/argic-archi.git
cd argic-archi

# Create virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Run the application
python scripts/ArchiScraperApp.py
```

---

## 🖥️ How to Use

1. **Enter URL**: Paste the Archi HTML report URL in the address bar and click **Go**
2. **Wait for Model**: The status bar will show "Model Loaded" when ready (with element/folder/view counts)
3. **Choose Export Method**:
   - **Download Active View**: Export the currently visible view
   - **Add to Batch**: Collect multiple views, then export together
   - **Download ALL Views**: Automatically fetch and merge every view in the model

4. **Import to Archi**: 
   - Open Archi
   - Go to `File → Import → Model from Open Exchange File`
   - Select your exported `.xml` file

---

## 🔧 Building the Executable

For contributors who want to create a distributable `.exe`:

### Prerequisites
```bash
pip install pyinstaller pillow
```

### Build Command
```bash
python build_app.py
```

### Output
Find the standalone executable at:
```
dist/ArchiScraper.exe
```

The build script automatically:
- Installs PyInstaller if missing
- Bundles the application icon
- Creates a single-file executable with no console window

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.x |
| GUI Framework | PyQt6 |
| Embedded Browser | PyQt6-WebEngine (Chromium) |
| HTML Parsing | BeautifulSoup4 |
| HTTP Requests | Requests |
| Build Tool | PyInstaller |

---

## 📄 Output Format

ArchiScraper generates standard **ArchiMate Open Exchange Format** XML files compatible with:
- [Archi](https://www.archimatetool.com/) (primary target)
- Other ArchiMate modeling tools that support the Open Exchange format

---

## ⚠️ Limitations

- Only works with **Archi HTML Report** exports (standard Archi HTML export format)
- Requires network access to the report URL
- Some complex nested element relationships may need manual adjustment after import
- Connection bendpoints are not preserved (connections are hidden in views)

---

## 📝 License

This project is provided as-is for architectural recovery and research purposes.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

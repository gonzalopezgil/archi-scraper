"""
ArchiScraper - Archi HTML Report Browser and XML Exporter

A PyQt6-based GUI application that:
1. Browses Archi HTML reports via QWebEngineView
2. Auto-fetches model.html to cache element/relationship/folder data
3. Extracts the current view from the iframe and converts it to ArchiMate XML

Prerequisites:
    python -m pip install PyQt6 PyQt6-WebEngine requests beautifulsoup4
"""

import sys
import re
import uuid
import urllib.parse
from pathlib import Path
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
from xml.dom import minidom

import requests
from bs4 import BeautifulSoup

from PyQt6.QtCore import QUrl, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QStatusBar
)
from PyQt6.QtWebEngineWidgets import QWebEngineView


# ============================================================================
# XML Namespaces (preserved from CLI script)
# ============================================================================
ARCHIMATE_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = "http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.1/archimate3_Diagram.xsd"

ET.register_namespace('', ARCHIMATE_NS)
ET.register_namespace('xsi', XSI_NS)


# ============================================================================
# Utility Functions (preserved from CLI script)
# ============================================================================
def gen_id(prefix="id"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def decode_url(s):
    """Decode URL-encoded strings."""
    if s:
        return urllib.parse.unquote_plus(s)
    return s


def fix_relationship_type(rel_type):
    """Convert HTML relationship types to ArchiMate schema types.
    
    e.g., 'AggregationRelationship' -> 'Aggregation'
    """
    if rel_type.endswith('Relationship'):
        return rel_type[:-12]  # Remove 'Relationship' suffix
    return rel_type


def extract_id_from_href(href):
    """Extract element/view ID from href path."""
    if not href:
        return None
    # ../elements/id-xxx.html -> id-xxx
    # ../views/id-xxx.html -> id-xxx
    match = re.search(r'(id-[a-f0-9-]+)\.html', href)
    if match:
        return match.group(1)
    return None


# ============================================================================
# Model Data Parser (preserved from CLI script)
# ============================================================================
class ModelDataParser:
    """Parses and caches data from model.html."""
    
    def __init__(self):
        self.elements = {}
        self.relationships = {}
        self.folders = {}
        self.folder_contents = []
        self.loaded = False
    
    def load_from_url(self, model_url):
        """Download and parse model.html from URL."""
        try:
            print(f"Fetching model data from: {model_url}")
            response = requests.get(model_url, timeout=30)
            response.raise_for_status()
            content = response.text
            self._parse_content(content)
            self.loaded = True
            return True
        except Exception as e:
            print(f"Error loading model.html: {e}")
            return False
    
    def _parse_content(self, content):
        """Parse JavaScript data structures from model.html."""
        # Reset
        self.elements = {}
        self.relationships = {}
        self.folders = {}
        self.folder_contents = []
        
        # Extract dataElements
        pattern = r'dataElements\.push\(\s*\{([^}]+)\}\s*\);'
        matches = re.findall(pattern, content)
        
        for match in matches:
            elem_data = {}
            
            id_match = re.search(r'id:\s*"([^"]+)"', match)
            if id_match:
                elem_data['id'] = id_match.group(1)
            
            name_match = re.search(r'name:\s*(?:decodeURL\()?"([^"]+)"', match)
            if name_match:
                elem_data['name'] = decode_url(name_match.group(1))
            
            type_match = re.search(r'type:\s*"([^"]+)"', match)
            if type_match:
                elem_data['type'] = type_match.group(1)
            
            doc_match = re.search(r'documentation:\s*(?:decodeURL\()?"([^"]+)"', match)
            if doc_match:
                elem_data['documentation'] = decode_url(doc_match.group(1))
            
            if 'id' in elem_data:
                self.elements[elem_data['id']] = elem_data
        
        print(f"  Loaded {len(self.elements)} elements from model.html")
        
        # Extract dataFolders
        folder_pattern = r'dataFolders\.push\(\s*\{([^}]+)\}\s*\);'
        folder_matches = re.findall(folder_pattern, content)
        
        for match in folder_matches:
            folder_data = {}
            
            id_match = re.search(r'id:\s*"([^"]+)"', match)
            if id_match:
                folder_data['id'] = id_match.group(1)
            
            type_match = re.search(r'type:\s*"([^"]+)"', match)
            if type_match:
                folder_data['type'] = type_match.group(1)
            
            name_match = re.search(r'name:\s*(?:decodeURL\()?"([^"]+)"', match)
            if name_match:
                folder_data['name'] = decode_url(name_match.group(1))
            
            if 'id' in folder_data:
                self.folders[folder_data['id']] = folder_data
        
        print(f"  Loaded {len(self.folders)} folders from model.html")
        
        # Extract dataFoldersContent (parent-child relationships)
        content_pattern = r'dataFoldersContent\.push\(\s*\{([^}]+)\}\s*\);'
        content_matches = re.findall(content_pattern, content)
        
        for match in content_matches:
            folder_id_match = re.search(r'folderid:\s*"([^"]+)"', match)
            content_id_match = re.search(r'contentid:\s*"([^"]+)"', match)
            content_type_match = re.search(r'contenttype:\s*"([^"]+)"', match)
            
            if folder_id_match and content_id_match:
                self.folder_contents.append({
                    'folder_id': folder_id_match.group(1),
                    'content_id': content_id_match.group(1),
                    'content_type': content_type_match.group(1) if content_type_match else 'Unknown'
                })
        
        print(f"  Loaded {len(self.folder_contents)} folder-content mappings")
    
    def get_element_documentation(self, elem_id):
        """Get documentation for an element."""
        if elem_id in self.elements:
            return self.elements[elem_id].get('documentation', '')
        return ''


# ============================================================================
# View HTML Parser (preserved from CLI script)
# ============================================================================
class ViewParser:
    """Parses a single view HTML file."""
    
    @staticmethod
    def extract_elements(soup):
        """Parse the #elements table to get element IDs, names, and types."""
        elements = {}
        
        elements_div = soup.find('div', id='elements')
        if not elements_div:
            return elements
        
        table = elements_div.find('table')
        if not table:
            return elements
        
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 2:
                name_link = cells[0].find('a')
                type_link = cells[1].find('a')
                
                if name_link:
                    href = name_link.get('href', '')
                    name = name_link.get_text(strip=True)
                    elem_id = extract_id_from_href(href)
                    
                    elem_type = 'Unknown'
                    if type_link:
                        classes = type_link.get('class', [])
                        for cls in classes:
                            if cls.startswith('i18n-elementtype-'):
                                elem_type = cls.replace('i18n-elementtype-', '')
                                break
                    
                    if elem_id and name:
                        elements[elem_id] = {
                            'id': elem_id,
                            'name': name,
                            'type': elem_type
                        }
        
        return elements
    
    @staticmethod
    def extract_coordinates(soup):
        """Parse <map>/<area> tags to get coordinates for each element."""
        coordinates = {}
        
        map_elem = soup.find('map')
        if not map_elem:
            return coordinates
        
        areas = map_elem.find_all('area')
        
        for area in areas:
            if area.get('shape') != 'rect':
                continue
            
            coords_str = area.get('coords', '')
            href = area.get('href', '')
            target = area.get('target', '')
            
            # Skip view references (we only want elements)
            if target == 'view':
                continue
            
            elem_id = extract_id_from_href(href)
            if not elem_id or not coords_str:
                continue
            
            try:
                parts = [int(x.strip()) for x in coords_str.split(',')]
                if len(parts) >= 4:
                    x1, y1, x2, y2 = parts[:4]
                    coordinates[elem_id] = {
                        'x': x1,
                        'y': y1,
                        'w': x2 - x1,
                        'h': y2 - y1,
                        'x2': x2,
                        'y2': y2
                    }
            except ValueError:
                continue
        
        return coordinates
    
    @staticmethod
    def extract_relationships(soup):
        """Parse the #relationships table to get relationships."""
        relationships = []
        
        rel_div = soup.find('div', id='relationships')
        if not rel_div:
            return relationships
        
        table = rel_div.find('table')
        if not table:
            return relationships
        
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 4:
                rel_link = cells[0].find('a')
                type_link = cells[1].find('a')
                source_link = cells[2].find('a')
                target_link = cells[3].find('a')
                
                if rel_link and type_link and source_link and target_link:
                    rel_id = extract_id_from_href(rel_link.get('href', ''))
                    source_id = extract_id_from_href(source_link.get('href', ''))
                    target_id = extract_id_from_href(target_link.get('href', ''))
                    
                    rel_type = 'Association'
                    classes = type_link.get('class', [])
                    for cls in classes:
                        if cls.startswith('i18n-elementtype-'):
                            raw_type = cls.replace('i18n-elementtype-', '')
                            rel_type = fix_relationship_type(raw_type)
                            break
                    
                    if rel_id and source_id and target_id:
                        relationships.append({
                            'id': rel_id,
                            'type': rel_type,
                            'source': source_id,
                            'target': target_id,
                            'name': rel_link.get_text(strip=True)
                        })
        
        return relationships
    
    @staticmethod
    def parse(html_content):
        """Parse view HTML and return extracted data."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Get view name from title
        title = soup.find('title')
        view_name = title.get_text(strip=True) if title else 'Unknown View'
        
        # Get view ID from map name
        view_id = None
        map_elem = soup.find('map')
        if map_elem and map_elem.get('name'):
            map_name = map_elem.get('name')
            if map_name.endswith('map'):
                view_id = map_name[:-3]  # Remove 'map' suffix
        
        if not view_id:
            view_id = gen_id("view")
        
        elements = ViewParser.extract_elements(soup)
        coordinates = ViewParser.extract_coordinates(soup)
        relationships = ViewParser.extract_relationships(soup)
        
        if not coordinates:
            return None
        
        return {
            'view_name': view_name,
            'view_id': view_id,
            'elements': elements,
            'relationships': relationships,
            'coordinates': coordinates
        }


# ============================================================================
# XML Generator (preserved from CLI script)
# ============================================================================
class ArchiMateXMLGenerator:
    """Generates ArchiMate Model Exchange Format XML."""
    
    def __init__(self, model_data: ModelDataParser):
        self.model_data = model_data
    
    def create_single_view_xml(self, view_data):
        """Create ArchiMate XML for a single view with folder structure."""
        
        model_id = gen_id("model")
        
        # Root
        root = ET.Element("model", {
            "xmlns": ARCHIMATE_NS,
            "xmlns:xsi": XSI_NS,
            "xsi:schemaLocation": SCHEMA_LOCATION,
            "identifier": model_id
        })
        
        ET.SubElement(root, "name", {"xml:lang": "en"}).text = view_data['view_name']
        
        elements = view_data['elements']
        coordinates = view_data['coordinates']
        relationships = view_data['relationships']
        view_id = view_data['view_id']
        
        # Collect only elements that are in this view
        all_elements = {}
        for elem_id, elem in elements.items():
            if elem_id in coordinates:
                elem_type = elem['type']
                if elem_type not in ('DiagramModelNote', 'DiagramModelReference', 'Unknown'):
                    all_elements[elem_id] = elem
        
        # Collect relationships (keyed by ID)
        all_relationships = {}
        for rel in relationships:
            all_relationships[rel['id']] = rel
        
        # --- Elements section ---
        elements_section = ET.SubElement(root, "elements")
        for elem_id, elem in all_elements.items():
            element = ET.SubElement(elements_section, "element", {
                "identifier": elem_id,
                "xsi:type": elem['type']
            })
            ET.SubElement(element, "name", {"xml:lang": "en"}).text = elem['name']
            
            # Add documentation from model.html
            doc = self.model_data.get_element_documentation(elem_id)
            if doc:
                ET.SubElement(element, "documentation", {"xml:lang": "en"}).text = doc
        
        # --- Relationships section ---
        if all_relationships:
            rels_section = ET.SubElement(root, "relationships")
            for rel_id, rel in all_relationships.items():
                rel_elem = ET.SubElement(rels_section, "relationship", {
                    "identifier": rel_id,
                    "xsi:type": rel['type'],
                    "source": rel['source'],
                    "target": rel['target']
                })
                if rel.get('name'):
                    ET.SubElement(rel_elem, "name", {"xml:lang": "en"}).text = rel['name']
        
        # --- Organizations section (folder structure with whitelisting) ---
        if self.model_data.folders and self.model_data.folder_contents:
            self._add_organizations(root, all_elements, all_relationships, [view_data])
        
        # --- Views section (FLAT nodes with Z-order sorting) ---
        views_section = ET.SubElement(root, "views")
        diagrams = ET.SubElement(views_section, "diagrams")
        view = ET.SubElement(diagrams, "view", {"identifier": view_id, "xsi:type": "Diagram"})
        ET.SubElement(view, "name", {"xml:lang": "en"}).text = view_data['view_name']
        
        # Collect nodes with coordinates for z-order sorting
        nodes_to_add = []
        for elem_id, elem in elements.items():
            if elem_id not in coordinates:
                continue
            
            elem_type = elem['type']
            if elem_type in ('DiagramModelNote', 'DiagramModelReference', 'Unknown'):
                continue
            
            coords = coordinates[elem_id]
            area = coords['w'] * coords['h']
            
            nodes_to_add.append({
                'elem_id': elem_id,
                'coords': coords,
                'area': area
            })
        
        # Sort by area DESCENDING (largest first for z-order)
        nodes_to_add.sort(key=lambda n: n['area'], reverse=True)
        
        # Add flat nodes with absolute coordinates (NO nesting, NO connections)
        for node_data in nodes_to_add:
            elem_id = node_data['elem_id']
            coords = node_data['coords']
            
            ET.SubElement(view, "node", {
                "identifier": gen_id("node"),
                "elementRef": elem_id,
                "xsi:type": "Element",
                "x": str(coords['x']),
                "y": str(coords['y']),
                "w": str(coords['w']),
                "h": str(coords['h'])
            })
        
        return root
    
    def _add_organizations(self, root, all_elements, all_relationships, views_data):
        """Add organizations section with folder whitelisting."""
        print("  Building folder structure with referential integrity...")
        
        # Build set of valid IDs (Elements + Relationships + Views)
        valid_ids = set(all_elements.keys())
        valid_ids.update(all_relationships.keys())
        for v_data in views_data:
            if v_data.get('view_id'):
                valid_ids.add(v_data['view_id'])
        
        print(f"    Valid IDs for folder structure: {len(valid_ids)}")
        
        # Build parent->children mapping
        folder_children = {}
        for fc in self.model_data.folder_contents:
            parent_id = fc['folder_id']
            if parent_id not in folder_children:
                folder_children[parent_id] = []
            folder_children[parent_id].append((fc['content_id'], fc['content_type']))
        
        # Recursive function to determine if a folder has valid content
        def folder_has_valid_content(folder_id, visited=None):
            if visited is None:
                visited = set()
            if folder_id in visited:
                return False
            visited.add(folder_id)
            
            children = folder_children.get(folder_id, [])
            for content_id, content_type in children:
                if content_id in valid_ids:
                    return True
                if content_type == 'Folder' or content_id in self.model_data.folders:
                    if folder_has_valid_content(content_id, visited):
                        return True
            return False
        
        # Identify all folders that should be included
        included_folders = set()
        for folder_id in self.model_data.folders:
            if folder_has_valid_content(folder_id):
                included_folders.add(folder_id)
        
        # Ensure ancestors are included
        def get_parent_folder(folder_id):
            for fc in self.model_data.folder_contents:
                if fc['content_id'] == folder_id and fc['content_type'] == 'Folder':
                    return fc['folder_id']
            return None
        
        folders_to_check = list(included_folders)
        while folders_to_check:
            folder_id = folders_to_check.pop()
            parent_id = get_parent_folder(folder_id)
            if parent_id and parent_id not in included_folders:
                included_folders.add(parent_id)
                folders_to_check.append(parent_id)
        
        print(f"    Including {len(included_folders)} folders (filtered from {len(self.model_data.folders)})")
        
        # Find root folders
        root_folder_ids = []
        for folder_id in included_folders:
            folder = self.model_data.folders.get(folder_id)
            if folder and folder.get('type') == 'Folder':
                parent = get_parent_folder(folder_id)
                if parent is None or self.model_data.folders.get(parent, {}).get('type') == 'ArchimateModel':
                    root_folder_ids.append(folder_id)
        
        # Generate XML
        orgs_section = ET.SubElement(root, "organizations")
        
        def add_folder_items(parent_xml, folder_id):
            folder = self.model_data.folders.get(folder_id)
            if not folder or folder_id not in included_folders:
                return
            
            folder_item = ET.SubElement(parent_xml, "item")
            ET.SubElement(folder_item, "label", {"xml:lang": "en"}).text = folder.get('name', 'Unnamed')
            
            children = folder_children.get(folder_id, [])
            for content_id, content_type in children:
                if content_type == 'Folder' and content_id in included_folders:
                    add_folder_items(folder_item, content_id)
                elif content_id in valid_ids:
                    ET.SubElement(folder_item, "item", {"identifierRef": content_id})
        
        for folder_id in root_folder_ids:
            add_folder_items(orgs_section, folder_id)
        
        print(f"    Added organizations structure with {len(root_folder_ids)} root folders")
    
    @staticmethod
    def prettify_xml(elem):
        rough = ET.tostring(elem, encoding='unicode')
        return minidom.parseString(rough).toprettyxml(indent="  ")
    
    @staticmethod
    def save_xml(root, output_path):
        xml_string = ArchiMateXMLGenerator.prettify_xml(root)
        lines = xml_string.split('\n')
        if lines[0].startswith('<?xml'):
            lines = lines[1:]
        final = '<?xml version="1.0" encoding="UTF-8"?>\n' + '\n'.join(lines).strip()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final)
        print(f"  Created: {output_path}")


# ============================================================================
# Main GUI Application
# ============================================================================
class ArchiScraperApp(QMainWindow):
    """Main application window for ArchiScraper."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ArchiScraper - Archi HTML Report Browser")
        self.setMinimumSize(1200, 800)
        
        # Model data cache
        self.model_data = ModelDataParser()
        self.base_url = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the user interface."""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # === Top bar: Address bar + Go button ===
        top_bar = QHBoxLayout()
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter Archi HTML report URL (e.g., http://server/report/index.html)")
        self.url_input.returnPressed.connect(self._on_go_clicked)
        top_bar.addWidget(self.url_input)
        
        self.go_button = QPushButton("Go")
        self.go_button.setFixedWidth(80)
        self.go_button.clicked.connect(self._on_go_clicked)
        top_bar.addWidget(self.go_button)
        
        layout.addLayout(top_bar)
        
        # === Main area: Web view ===
        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl("about:blank"))
        layout.addWidget(self.web_view, 1)  # stretch factor = 1
        
        # === Bottom bar: Download button ===
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()
        
        self.download_button = QPushButton("Download Active View as XML")
        self.download_button.setFixedHeight(40)
        self.download_button.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
                padding: 8px 24px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.download_button.clicked.connect(self._on_download_clicked)
        bottom_bar.addWidget(self.download_button)
        
        bottom_bar.addStretch()
        layout.addLayout(bottom_bar)
        
        # === Status bar ===
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Enter a URL to begin.")
    
    def _on_go_clicked(self):
        """Handle Go button click."""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a URL.")
            return
        
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
            self.url_input.setText(url)
        
        # Determine base URL
        parsed = urlparse(url)
        path_parts = parsed.path.rsplit('/', 1)
        if len(path_parts) > 1:
            base_path = path_parts[0] + '/'
        else:
            base_path = '/'
        self.base_url = f"{parsed.scheme}://{parsed.netloc}{base_path}"
        
        print(f"Base URL: {self.base_url}")
        self.status_bar.showMessage(f"Loading: {url}")
        
        # Load the page
        self.web_view.setUrl(QUrl(url))
        
        # Auto-fetch model.html in background
        model_url = urljoin(self.base_url, "model.html")
        self.status_bar.showMessage(f"Fetching model data from {model_url}...")
        
        if self.model_data.load_from_url(model_url):
            self.status_bar.showMessage(
                f"Model data loaded: {len(self.model_data.elements)} elements, "
                f"{len(self.model_data.folders)} folders"
            )
        else:
            self.status_bar.showMessage("Warning: Could not load model.html. Documentation will be limited.")
    
    def _on_download_clicked(self):
        """Handle Download button click."""
        if not self.base_url:
            QMessageBox.warning(self, "Error", "Please load a report first by entering a URL and clicking Go.")
            return
        
        self.status_bar.showMessage("Extracting view from iframe...")
        
        # JavaScript to get the iframe src
        js_code = """
        (function() {
            var iframe = document.querySelector('iframe[name="view"]');
            if (!iframe) {
                iframe = document.querySelector('iframe');
            }
            if (iframe && iframe.src) {
                return iframe.src;
            }
            return null;
        })();
        """
        
        self.web_view.page().runJavaScript(js_code, self._on_iframe_src_received)
    
    @pyqtSlot("QVariant")
    def _on_iframe_src_received(self, iframe_src):
        """Callback when iframe src is received from JavaScript."""
        if not iframe_src:
            QMessageBox.warning(
                self, "Error", 
                "Could not find the view iframe. Make sure you're viewing an Archi HTML report."
            )
            return
        
        print(f"Iframe src: {iframe_src}")
        self.status_bar.showMessage(f"Downloading view: {iframe_src}")
        
        try:
            # Download the view HTML
            response = requests.get(iframe_src, timeout=30)
            response.raise_for_status()
            view_html = response.text
            
            # Parse the view
            view_data = ViewParser.parse(view_html)
            if not view_data:
                QMessageBox.warning(self, "Error", "Failed to parse the view HTML. No coordinates found.")
                return
            
            print(f"View: {view_data['view_name']}")
            print(f"  Elements: {len(view_data['elements'])}")
            print(f"  Coordinates: {len(view_data['coordinates'])}")
            print(f"  Relationships: {len(view_data['relationships'])}")
            
            # Generate XML
            generator = ArchiMateXMLGenerator(self.model_data)
            xml_root = generator.create_single_view_xml(view_data)
            
            # Ask user where to save
            default_name = f"{view_data['view_name'].replace(' ', '_')}.xml"
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save ArchiMate XML",
                default_name,
                "ArchiMate XML Files (*.xml);;All Files (*)"
            )
            
            if file_path:
                ArchiMateXMLGenerator.save_xml(xml_root, file_path)
                self.status_bar.showMessage(f"Saved: {file_path}")
                QMessageBox.information(
                    self, "Success",
                    f"ArchiMate XML saved to:\n{file_path}\n\n"
                    f"Elements: {len(view_data['elements'])}\n"
                    f"Relationships: {len(view_data['relationships'])}\n\n"
                    "Import into Archi: File → Import → Model from Open Exchange File"
                )
            else:
                self.status_bar.showMessage("Save cancelled.")
        
        except requests.RequestException as e:
            QMessageBox.critical(self, "Error", f"Failed to download view:\n{e}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to convert view:\n{e}")
            import traceback
            traceback.print_exc()


# ============================================================================
# Entry Point
# ============================================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = ArchiScraperApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

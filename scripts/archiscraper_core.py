"""
Shared core parsing and XML generation for ArchiScraper.

This module contains model parsing, view parsing, and ArchiMate XML
export logic used by both the GUI and CLI.
"""

from __future__ import annotations

import random
import re
import uuid
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


# ============================================================================
# XML Namespaces
# ============================================================================
_FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

try:
    from fake_useragent import UserAgent
    _ua = UserAgent()

    def get_random_user_agent() -> str:
        """Return a random User-Agent from real browser statistics (via fake-useragent)."""
        return _ua.random
except ImportError:
    _ua = None

    def get_random_user_agent() -> str:
        """Return a random User-Agent from hardcoded fallback list."""
        return random.choice(_FALLBACK_USER_AGENTS)


DEFAULT_USER_AGENT = get_random_user_agent()

ARCHIMATE_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = (
    "http://www.opengroup.org/xsd/archimate/3.0/ "
    "http://www.opengroup.org/xsd/archimate/3.1/archimate3_Diagram.xsd"
)

ET.register_namespace('', ARCHIMATE_NS)
ET.register_namespace('xsi', XSI_NS)


# ============================================================================
# Utility Functions
# ============================================================================

def gen_id(prefix: str = "id") -> str:
    """Generate a short unique identifier with a prefix."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def decode_url(s: Optional[str]) -> Optional[str]:
    """Decode URL-encoded strings."""
    if s:
        return urllib.parse.unquote_plus(s)
    return s


def fix_relationship_type(rel_type: str) -> str:
    """Convert HTML relationship types to ArchiMate schema types.

    Example: 'AggregationRelationship' -> 'Aggregation'
    """
    if rel_type.endswith('Relationship'):
        return rel_type[:-12]
    return rel_type


# Types that should be skipped entirely (visual-only, not ArchiMate elements)
SKIP_ELEMENT_TYPES = {
    'DiagramModelNote',       # Notes/annotations (visual only)
    'DiagramModelReference',  # References to other diagrams (visual only)
    'SketchModelSticky',      # Sketch sticky notes (visual only)
    'Unknown',                # Unknown types
}

# Type mappings for ArchiMate schema compliance
ELEMENT_TYPE_MAPPINGS = {
    'DiagramModelGroup': 'Grouping',     # Visual group -> ArchiMate Grouping element
    'Junction': 'AndJunction',           # Generic Junction -> AndJunction (safest default)
    'OrJunction': 'OrJunction',          # Explicit OrJunction stays as is
    'AndJunction': 'AndJunction',        # Explicit AndJunction stays as is
    'SketchModelActor': 'BusinessActor', # Sketch actor -> real ArchiMate actor
}


def clean_element_type(type_str: Optional[str]) -> Optional[str]:
    """Clean and validate element type for ArchiMate XML export."""
    if not type_str:
        return None

    clean_type = type_str.strip()

    if clean_type in SKIP_ELEMENT_TYPES:
        return None

    if clean_type in ELEMENT_TYPE_MAPPINGS:
        return ELEMENT_TYPE_MAPPINGS[clean_type]

    return clean_type


def extract_id_from_href(href: Optional[str]) -> Optional[str]:
    """Extract element/view ID from href path."""
    if not href:
        return None
    match = re.search(r'(id-[a-f0-9-]+)\.html', href, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be safe for use as a filename."""
    illegal_chars = r'[\\/:*?"<>|]'
    sanitized = re.sub(illegal_chars, '_', name)
    sanitized = sanitized.strip(' .')
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized if sanitized else 'unnamed'


def download_view_images(
    base_url: str,
    guid: str,
    views: List[Dict[str, object]],
    output_dir: str,
    user_agent: Optional[str] = None,
    timeout: int = 30,
) -> tuple[int, int]:
    """Download PNG images for each view in a report."""
    if not base_url.endswith('/'):
        base_url = f"{base_url}/"

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    headers = {"User-Agent": user_agent or DEFAULT_USER_AGENT}
    total = len(views)
    downloaded = 0
    skipped = 0

    for index, view_data in enumerate(views, start=1):
        view_id = view_data.get('view_id')
        view_name = view_data.get('view_name') or view_id or f"view-{index}"
        if not view_id:
            print(f"  Warning: Missing view_id for '{view_name}'. Skipping image.")
            skipped += 1
            continue

        safe_name = sanitize_filename(str(view_name))
        filename = f"{safe_name}.png"
        file_path = output_path / filename
        if file_path.exists():
            filename = f"{safe_name}_{view_id}.png"
            file_path = output_path / filename

        print(f"Downloading image {index}/{total}: {filename}...")
        image_url = f"{base_url}{guid}/images/{view_id}.png"

        try:
            response = requests.get(image_url, headers=headers, timeout=timeout)
            if response.status_code == 404:
                print(f"  Warning: Image not found for {view_id} (404). Skipping.")
                skipped += 1
                continue
            response.raise_for_status()
            with open(file_path, 'wb') as handle:
                handle.write(response.content)
            downloaded += 1
        except requests.RequestException as exc:
            print(f"  Warning: Failed to download image for {view_id} ({exc}). Skipping.")
            skipped += 1

    return downloaded, skipped


# ============================================================================
# Model Data Parser
# ============================================================================
class ModelDataParser:
    """Parses and caches data from model.html."""

    def __init__(self) -> None:
        self.elements: Dict[str, Dict[str, str]] = {}
        self.relationships: Dict[str, Dict[str, str]] = {}
        self.folders: Dict[str, Dict[str, str]] = {}
        self.folder_contents: List[Dict[str, str]] = []
        self.views: Dict[str, Dict[str, str]] = {}
        self.loaded = False

    def load_from_url(self, model_url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30) -> bool:
        """Download and parse model.html from a URL."""
        try:
            if headers is None:
                headers = {"User-Agent": DEFAULT_USER_AGENT}
            print(f"Fetching model data from: {model_url}")
            response = requests.get(model_url, headers=headers, timeout=timeout)
            response.raise_for_status()
            self._parse_content(response.text)
            self.loaded = True
            print(
                f"Model data loaded successfully: {len(self.elements)} elements, "
                f"{len(self.folders)} folders"
            )
            return True
        except Exception as exc:
            print(f"Error loading model.html: {exc}")
            self.loaded = False
            return False

    def load_from_file(self, model_html_path: str) -> bool:
        """Load and parse model.html from a local file path."""
        try:
            print(f"Loading model data from: {model_html_path}")
            with open(model_html_path, 'r', encoding='utf-8') as handle:
                content = handle.read()
            self._parse_content(content)
            self.loaded = True
            print(
                f"Model data loaded successfully: {len(self.elements)} elements, "
                f"{len(self.folders)} folders"
            )
            return True
        except Exception as exc:
            print(f"Error loading model.html: {exc}")
            self.loaded = False
            return False

    def _parse_content(self, content: str) -> None:
        """Parse JavaScript data structures from model.html."""
        self.elements = {}
        self.relationships = {}
        self.folders = {}
        self.folder_contents = []
        self.views = {}

        pattern = r'dataElements\.push\(\s*\{([^}]+)\}\s*\);'
        matches = re.findall(pattern, content)

        for match in matches:
            elem_data: Dict[str, str] = {}

            id_match = re.search(r'id:\s*"([^"]+)"', match)
            if id_match:
                elem_data['id'] = id_match.group(1)

            name_match = re.search(r'name:\s*(?:decodeURL\()?"([^"]+)"', match)
            if name_match:
                elem_data['name'] = decode_url(name_match.group(1)) or ''

            type_match = re.search(r'type:\s*"([^"]+)"', match)
            if type_match:
                elem_data['type'] = type_match.group(1)

            doc_match = re.search(r'documentation:\s*(?:decodeURL\()?"([^"]+)"', match)
            if doc_match:
                elem_data['documentation'] = decode_url(doc_match.group(1)) or ''

            if 'id' in elem_data:
                self.elements[elem_data['id']] = elem_data

        print(f"  Parsed {len(self.elements)} elements from model.html")

        folder_pattern = r'dataFolders\.push\(\s*\{([^}]+)\}\s*\);'
        folder_matches = re.findall(folder_pattern, content)

        for match in folder_matches:
            folder_data: Dict[str, str] = {}

            id_match = re.search(r'id:\s*"([^"]+)"', match)
            if id_match:
                folder_data['id'] = id_match.group(1)

            type_match = re.search(r'type:\s*"([^"]+)"', match)
            if type_match:
                folder_data['type'] = type_match.group(1)

            name_match = re.search(r'name:\s*(?:decodeURL\()?"([^"]+)"', match)
            if name_match:
                folder_data['name'] = decode_url(name_match.group(1)) or ''

            if 'id' in folder_data:
                self.folders[folder_data['id']] = folder_data

        print(f"  Parsed {len(self.folders)} folders from model.html")

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
                    'content_type': content_type_match.group(1) if content_type_match else 'Unknown',
                })

        print(f"  Parsed {len(self.folder_contents)} folder-content mappings")

        views_pattern = r'dataViews\.push\(\s*\{([^}]+)\}\s*\);'
        views_matches = re.findall(views_pattern, content)

        for match in views_matches:
            view_data: Dict[str, str] = {}

            id_match = re.search(r'id:\s*"([^"]+)"', match)
            if id_match:
                view_data['id'] = id_match.group(1)

            name_match = re.search(r'name:\s*(?:decodeURL\()?"([^"]+)"', match)
            if name_match:
                view_data['name'] = decode_url(name_match.group(1)) or ''

            type_match = re.search(r'type:\s*"([^"]+)"', match)
            if type_match:
                view_data['type'] = type_match.group(1)

            if 'id' in view_data:
                self.views[view_data['id']] = view_data

        print(f"  Parsed {len(self.views)} views from model.html")

    def get_element_documentation(self, elem_id: str) -> str:
        """Get documentation for an element."""
        if elem_id in self.elements:
            return self.elements[elem_id].get('documentation', '')
        return ''


# ============================================================================
# View HTML Parser
# ============================================================================
class ViewParser:
    """Parses a single view HTML file."""

    @staticmethod
    def _extract_type_from_cell(cell: BeautifulSoup, prefix: str) -> Optional[str]:
        """Extract i18n-* type from a table cell's class or child elements."""
        candidates = [cell]
        candidates.extend(cell.find_all(True))
        for candidate in candidates:
            classes = candidate.get('class', [])
            for cls in classes:
                if cls.startswith(prefix):
                    return cls.replace(prefix, '')
        return None

    @staticmethod
    def extract_elements(soup: BeautifulSoup) -> Dict[str, Dict[str, str]]:
        """Parse the #elements table to get element IDs, names, and types."""
        elements: Dict[str, Dict[str, str]] = {}

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

                if name_link:
                    href = name_link.get('href', '')
                    name = name_link.get_text(strip=True)
                    elem_id = extract_id_from_href(href)

                    elem_type = 'Unknown'
                    raw_type = ViewParser._extract_type_from_cell(cells[1], 'i18n-elementtype-')
                    if raw_type:
                        elem_type = raw_type

                    if elem_id and name:
                        elements[elem_id] = {
                            'id': elem_id,
                            'name': name,
                            'type': elem_type,
                        }

        return elements

    @staticmethod
    def extract_coordinates(soup: BeautifulSoup) -> Dict[str, Dict[str, int]]:
        """Parse <map>/<area> tags to get coordinates for each element."""
        coordinates: Dict[str, Dict[str, int]] = {}

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
                        'y2': y2,
                    }
            except ValueError:
                continue

        return coordinates

    @staticmethod
    def extract_relationships(soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Parse the #relationships table to get relationships."""
        relationships: List[Dict[str, str]] = []

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
                source_link = cells[2].find('a')
                target_link = cells[3].find('a')

                if rel_link and source_link and target_link:
                    rel_id = extract_id_from_href(rel_link.get('href', ''))
                    source_id = extract_id_from_href(source_link.get('href', ''))
                    target_id = extract_id_from_href(target_link.get('href', ''))

                    rel_type = 'Association'
                    raw_type = ViewParser._extract_type_from_cell(cells[1], 'i18n-relationshiptype-')
                    if raw_type is None:
                        raw_type = ViewParser._extract_type_from_cell(cells[1], 'i18n-elementtype-')
                    if raw_type:
                        rel_type = fix_relationship_type(raw_type)

                    if rel_id and source_id and target_id:
                        relationships.append({
                            'id': rel_id,
                            'type': rel_type,
                            'source': source_id,
                            'target': target_id,
                            'name': rel_link.get_text(strip=True),
                        })

        return relationships

    @staticmethod
    def parse(html_content: str) -> Optional[Dict[str, object]]:
        """Parse view HTML and return extracted data."""
        soup = BeautifulSoup(html_content, 'html.parser')

        title = soup.find('title')
        view_name = title.get_text(strip=True) if title else 'Unknown View'

        view_id = None
        map_elem = soup.find('map')
        if map_elem and map_elem.get('name'):
            map_name = map_elem.get('name')
            if map_name.endswith('map'):
                view_id = map_name[:-3]

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
            'coordinates': coordinates,
        }


# ============================================================================
# XML Generator
# ============================================================================
class ArchiMateXMLGenerator:
    """Generates ArchiMate Model Exchange Format XML."""

    def __init__(self, model_data: ModelDataParser) -> None:
        self.model_data = model_data

    def create_single_view_xml(
        self,
        view_data: Dict[str, object],
        include_connections: bool = False,
    ) -> ET.Element:
        """Create ArchiMate XML for a single view with folder structure."""
        model_id = gen_id("model")

        root = ET.Element("model", {
            "xmlns": ARCHIMATE_NS,
            "xmlns:xsi": XSI_NS,
            "xsi:schemaLocation": SCHEMA_LOCATION,
            "identifier": model_id,
        })

        ET.SubElement(root, "name", {"xml:lang": "en"}).text = view_data['view_name']

        elements = view_data['elements']
        coordinates = view_data['coordinates']
        relationships = view_data['relationships']
        view_id = view_data['view_id']

        all_elements: Dict[str, Dict[str, str]] = {}
        for elem_id, elem in elements.items():
            if elem_id in coordinates:
                cleaned_type = clean_element_type(elem['type'])
                if cleaned_type is not None:
                    elem_copy = elem.copy()
                    elem_copy['type'] = cleaned_type
                    all_elements[elem_id] = elem_copy

        filtered_relationships = [
            rel for rel in relationships
            if rel['source'] in all_elements and rel['target'] in all_elements
        ]

        all_relationships: Dict[str, Dict[str, str]] = {}
        for rel in filtered_relationships:
            all_relationships[rel['id']] = rel

        elements_section = ET.SubElement(root, "elements")
        for elem_id, elem in all_elements.items():
            element = ET.SubElement(elements_section, "element", {
                "identifier": elem_id,
                "xsi:type": elem['type'],
            })
            ET.SubElement(element, "name", {"xml:lang": "en"}).text = elem['name']

            doc = self.model_data.get_element_documentation(elem_id)
            if doc:
                ET.SubElement(element, "documentation", {"xml:lang": "en"}).text = doc

        if all_relationships:
            rels_section = ET.SubElement(root, "relationships")
            for rel_id, rel in all_relationships.items():
                rel_elem = ET.SubElement(rels_section, "relationship", {
                    "identifier": rel_id,
                    "xsi:type": rel['type'],
                    "source": rel['source'],
                    "target": rel['target'],
                })
                if rel.get('name'):
                    ET.SubElement(rel_elem, "name", {"xml:lang": "en"}).text = rel['name']

        if self.model_data.loaded and self.model_data.folders and self.model_data.folder_contents:
            self._add_organizations(root, all_elements, all_relationships, [view_data])

        views_section = ET.SubElement(root, "views")
        diagrams = ET.SubElement(views_section, "diagrams")
        view = ET.SubElement(diagrams, "view", {"identifier": view_id, "xsi:type": "Diagram"})
        ET.SubElement(view, "name", {"xml:lang": "en"}).text = view_data['view_name']

        nodes_to_add = []
        for elem_id, elem in elements.items():
            if elem_id not in coordinates:
                continue

            elem_type = elem['type']
            if clean_element_type(elem_type) is None:
                continue

            coords = coordinates[elem_id]
            area = coords['w'] * coords['h']

            nodes_to_add.append({
                'elem_id': elem_id,
                'coords': coords,
                'area': area,
            })

        nodes_to_add.sort(key=lambda n: n['area'], reverse=True)

        element_node_map: Dict[str, List[str]] = {}
        for node_data in nodes_to_add:
            elem_id = node_data['elem_id']
            coords = node_data['coords']

            node_id = gen_id("node")
            ET.SubElement(view, "node", {
                "identifier": node_id,
                "elementRef": elem_id,
                "xsi:type": "Element",
                "x": str(coords['x']),
                "y": str(coords['y']),
                "w": str(coords['w']),
                "h": str(coords['h']),
            })
            element_node_map.setdefault(elem_id, []).append(node_id)

        if include_connections:
            for rel in filtered_relationships:
                source_nodes = element_node_map.get(rel['source'], [])
                target_nodes = element_node_map.get(rel['target'], [])
                if not source_nodes or not target_nodes:
                    continue
                for source_node in source_nodes:
                    for target_node in target_nodes:
                        ET.SubElement(view, "connection", {
                            "identifier": gen_id("conn"),
                            "relationshipRef": rel['id'],
                            "xsi:type": "Relationship",
                            "source": source_node,
                            "target": target_node,
                        })

        return root

    def create_merged_xml(
        self,
        views_data_list: List[Dict[str, object]],
        include_connections: bool = False,
    ) -> ET.Element:
        """Create a single ArchiMate XML with all elements, relationships, and views."""
        model_id = gen_id("model")

        root = ET.Element("model", {
            "xmlns": ARCHIMATE_NS,
            "xmlns:xsi": XSI_NS,
            "xsi:schemaLocation": SCHEMA_LOCATION,
            "identifier": model_id,
        })

        ET.SubElement(root, "name", {"xml:lang": "en"}).text = "Master Architecture Model"

        all_elements: Dict[str, Dict[str, str]] = {}
        all_relationships: Dict[str, Dict[str, str]] = {}

        for view_data in views_data_list:
            elements = view_data['elements']
            coordinates = view_data['coordinates']

            for elem_id, elem in elements.items():
                if elem_id in coordinates:
                    cleaned_type = clean_element_type(elem['type'])
                    if cleaned_type is not None and elem_id not in all_elements:
                        elem_copy = elem.copy()
                        elem_copy['type'] = cleaned_type
                        all_elements[elem_id] = elem_copy

        for view_data in views_data_list:
            relationships = view_data['relationships']
            for rel in relationships:
                if rel['source'] not in all_elements or rel['target'] not in all_elements:
                    continue
                rel_id = rel['id']
                if rel_id not in all_relationships:
                    all_relationships[rel_id] = rel

        print(
            f"Merged: {len(all_elements)} unique elements, "
            f"{len(all_relationships)} unique relationships"
        )

        elements_section = ET.SubElement(root, "elements")
        for elem_id, elem in all_elements.items():
            element = ET.SubElement(elements_section, "element", {
                "identifier": elem_id,
                "xsi:type": elem['type'],
            })
            ET.SubElement(element, "name", {"xml:lang": "en"}).text = elem['name']

            doc = self.model_data.get_element_documentation(elem_id)
            if doc:
                ET.SubElement(element, "documentation", {"xml:lang": "en"}).text = doc

        if all_relationships:
            rels_section = ET.SubElement(root, "relationships")
            for rel_id, rel in all_relationships.items():
                rel_elem = ET.SubElement(rels_section, "relationship", {
                    "identifier": rel_id,
                    "xsi:type": rel['type'],
                    "source": rel['source'],
                    "target": rel['target'],
                })
                if rel.get('name'):
                    ET.SubElement(rel_elem, "name", {"xml:lang": "en"}).text = rel['name']

        if self.model_data.loaded and self.model_data.folders and self.model_data.folder_contents:
            self._add_organizations(root, all_elements, all_relationships, views_data_list)

        views_section = ET.SubElement(root, "views")
        diagrams = ET.SubElement(views_section, "diagrams")

        for view_data in views_data_list:
            view_id = view_data.get('view_id') or gen_id("view")
            view = ET.SubElement(diagrams, "view", {"identifier": view_id, "xsi:type": "Diagram"})
            ET.SubElement(view, "name", {"xml:lang": "en"}).text = view_data['view_name']

            elements = view_data['elements']
            coordinates = view_data['coordinates']
            relationships = view_data['relationships']

            nodes_to_add = []
            for elem_id, elem in elements.items():
                if elem_id not in coordinates:
                    continue

                elem_type = elem['type']
                if clean_element_type(elem_type) is None:
                    continue

                coords = coordinates[elem_id]
                area = coords['w'] * coords['h']

                nodes_to_add.append({
                    'elem_id': elem_id,
                    'coords': coords,
                    'area': area,
                })

            nodes_to_add.sort(key=lambda n: n['area'], reverse=True)

            element_node_map: Dict[str, List[str]] = {}
            for node_data in nodes_to_add:
                elem_id = node_data['elem_id']
                coords = node_data['coords']

                node_id = gen_id("node")
                ET.SubElement(view, "node", {
                    "identifier": node_id,
                    "elementRef": elem_id,
                    "xsi:type": "Element",
                    "x": str(coords['x']),
                    "y": str(coords['y']),
                    "w": str(coords['w']),
                    "h": str(coords['h']),
                })
                element_node_map.setdefault(elem_id, []).append(node_id)

            if include_connections:
                for rel in relationships:
                    if rel['source'] not in all_elements or rel['target'] not in all_elements:
                        continue
                    source_nodes = element_node_map.get(rel['source'], [])
                    target_nodes = element_node_map.get(rel['target'], [])
                    if not source_nodes or not target_nodes:
                        continue
                    for source_node in source_nodes:
                        for target_node in target_nodes:
                            ET.SubElement(view, "connection", {
                                "identifier": gen_id("conn"),
                                "relationshipRef": rel['id'],
                                "xsi:type": "Relationship",
                                "source": source_node,
                                "target": target_node,
                            })

            print(f"  Added view '{view_data['view_name']}' with {len(nodes_to_add)} nodes")

        return root

    def _add_organizations(
        self,
        root: ET.Element,
        all_elements: Dict[str, Dict[str, str]],
        all_relationships: Dict[str, Dict[str, str]],
        views_data: List[Dict[str, object]],
    ) -> None:
        """Add organizations section with folder whitelisting."""
        print("  Building folder structure with referential integrity...")

        valid_ids = set(all_elements.keys())
        valid_ids.update(all_relationships.keys())
        for v_data in views_data:
            if v_data.get('view_id'):
                valid_ids.add(v_data['view_id'])

        print(f"    Valid IDs for folder structure: {len(valid_ids)}")

        folder_children: Dict[str, List[tuple]] = {}
        for fc in self.model_data.folder_contents:
            parent_id = fc['folder_id']
            if parent_id not in folder_children:
                folder_children[parent_id] = []
            folder_children[parent_id].append((fc['content_id'], fc['content_type']))

        def folder_has_valid_content(folder_id: str, visited: Optional[set] = None) -> bool:
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

        included_folders = set()
        for folder_id in self.model_data.folders:
            if folder_has_valid_content(folder_id):
                included_folders.add(folder_id)

        def get_parent_folder(folder_id: str) -> Optional[str]:
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

        print(
            f"    Including {len(included_folders)} folders "
            f"(filtered from {len(self.model_data.folders)})"
        )

        root_folder_ids = []
        for folder_id in included_folders:
            folder = self.model_data.folders.get(folder_id)
            if folder and folder.get('type') == 'Folder':
                parent = get_parent_folder(folder_id)
                if parent is None or self.model_data.folders.get(parent, {}).get('type') == 'ArchimateModel':
                    root_folder_ids.append(folder_id)

        orgs_section = ET.SubElement(root, "organizations")

        def add_folder_items(parent_xml: ET.Element, folder_id: str) -> None:
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
    def prettify_xml(elem: ET.Element) -> str:
        """Pretty-print an XML element."""
        rough = ET.tostring(elem, encoding='unicode')
        return minidom.parseString(rough).toprettyxml(indent="  ")

    @staticmethod
    def save_xml(root: ET.Element, output_path: str) -> None:
        """Write XML to disk with ArchiMate header."""
        xml_string = ArchiMateXMLGenerator.prettify_xml(root)
        lines = xml_string.split('\n')
        if lines[0].startswith('<?xml'):
            lines = lines[1:]
        final = '<?xml version="1.0" encoding="UTF-8"?>\n' + '\n'.join(lines).strip()

        with open(output_path, 'w', encoding='utf-8') as handle:
            handle.write(final)
        print(f"  Saved: {output_path}")

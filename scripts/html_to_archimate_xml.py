"""
Archi HTML View to ArchiMate Model Exchange Format XML Converter

Parses Archi HTML report view files containing:
- <map>/<area> tags with coordinates
- Elements table with element types
- Relationships table with source/target

Also merges documentation from model.html (main Archi HTML report).

Outputs valid ArchiMate Open Exchange Format XML with proper nesting.
"""

import re
import uuid
import urllib.parse
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("ERROR: BeautifulSoup4 required. Install with: pip install beautifulsoup4")
    exit(1)

# Global cache for model.html data
MODEL_DATA = None

# ============================================================================
# XML Namespaces
# ============================================================================
ARCHIMATE_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = "http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.1/archimate3_Diagram.xsd"

ET.register_namespace('', ARCHIMATE_NS)
ET.register_namespace('xsi', XSI_NS)

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

# ============================================================================
# Load Documentation from model.html
# ============================================================================
def load_model_data(model_html_path):
    """Load element documentation from model.html."""
    global MODEL_DATA
    
    if MODEL_DATA is not None:
        return MODEL_DATA
    
    MODEL_DATA = {'elements': {}, 'relationships': {}}
    
    if not Path(model_html_path).exists():
        print(f"  Warning: {model_html_path} not found. Skipping documentation.")
        return MODEL_DATA
    
    print(f"  Loading documentation from {model_html_path}...")
    
    with open(model_html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract dataElements
    pattern = r'dataElements\.push\(\s*\{([^}]+)\}\s*\);'
    matches = re.findall(pattern, content)
    
    for match in matches:
        # Parse each field
        elem_data = {}
        
        # Extract id
        id_match = re.search(r'id:\s*"([^"]+)"', match)
        if id_match:
            elem_data['id'] = id_match.group(1)
        
        # Extract name
        name_match = re.search(r'name:\s*(?:decodeURL\()?"([^"]+)"', match)
        if name_match:
            elem_data['name'] = decode_url(name_match.group(1))
        
        # Extract type
        type_match = re.search(r'type:\s*"([^"]+)"', match)
        if type_match:
            elem_data['type'] = type_match.group(1)
        
        # Extract documentation
        doc_match = re.search(r'documentation:\s*(?:decodeURL\()?"([^"]+)"', match)
        if doc_match:
            elem_data['documentation'] = decode_url(doc_match.group(1))
        
        if 'id' in elem_data:
            MODEL_DATA['elements'][elem_data['id']] = elem_data
    
    print(f"    Loaded {len(MODEL_DATA['elements'])} elements from model.html")
    
    return MODEL_DATA

def get_element_documentation(elem_id):
    """Get documentation for an element from model.html."""
    if MODEL_DATA and elem_id in MODEL_DATA.get('elements', {}):
        return MODEL_DATA['elements'][elem_id].get('documentation', '')
    return ''

# ============================================================================
# Step A: Extract Elements from the Elements Table
# ============================================================================
def extract_elements(soup):
    """Parse the #elements table to get element IDs, names, and types."""
    elements = {}
    
    elements_div = soup.find('div', id='elements')
    if not elements_div:
        print("  Warning: No #elements div found")
        return elements
    
    table = elements_div.find('table')
    if not table:
        return elements
    
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 2:
            # First cell: name and link
            name_link = cells[0].find('a')
            # Second cell: type
            type_link = cells[1].find('a')
            
            if name_link:
                href = name_link.get('href', '')
                name = name_link.get_text(strip=True)
                
                # Extract ID from href (../elements/id-xxx.html -> id-xxx)
                elem_id = extract_id_from_href(href)
                
                # Extract type from class (i18n-elementtype-Capability -> Capability)
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
# Step B: Extract Visual Coordinates from Image Map
# ============================================================================
def extract_coordinates(soup):
    """Parse <map>/<area> tags to get coordinates for each element."""
    coordinates = {}
    
    map_elem = soup.find('map')
    if not map_elem:
        print("  Warning: No <map> element found")
        return coordinates
    
    areas = map_elem.find_all('area')
    print(f"  Found {len(areas)} <area> elements")
    
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

# ============================================================================
# Step C: Extract Relationships from Relationships Table
# ============================================================================
def extract_relationships(soup):
    """Parse the #relationships table to get relationships."""
    relationships = []
    
    rel_div = soup.find('div', id='relationships')
    if not rel_div:
        print("  Warning: No #relationships div found")
        return relationships
    
    table = rel_div.find('table')
    if not table:
        return relationships
    
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 4:
            # Cell 0: relationship name/link (contains rel ID)
            # Cell 1: type
            # Cell 2: source
            # Cell 3: target
            
            rel_link = cells[0].find('a')
            type_link = cells[1].find('a')
            source_link = cells[2].find('a')
            target_link = cells[3].find('a')
            
            if rel_link and type_link and source_link and target_link:
                rel_id = extract_id_from_href(rel_link.get('href', ''))
                source_id = extract_id_from_href(source_link.get('href', ''))
                target_id = extract_id_from_href(target_link.get('href', ''))
                
                # Extract type and fix for ArchiMate schema
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

# ============================================================================
# Nesting Logic: Determine Parent-Child Relationships by Coordinates
# ============================================================================
def build_nesting_tree(coordinates):
    """
    Determine nesting by checking if one box is completely inside another.
    Returns a dict mapping element_id -> parent_id (or None for top-level).
    """
    parent_map = {}
    items = list(coordinates.items())
    
    for elem_id, coords in items:
        parent_map[elem_id] = None
        best_parent = None
        best_parent_area = float('inf')
        
        for other_id, other_coords in items:
            if elem_id == other_id:
                continue
            
            # Check if elem is inside other
            if is_inside(coords, other_coords):
                other_area = other_coords['w'] * other_coords['h']
                # Choose the smallest containing parent (most direct parent)
                if other_area < best_parent_area:
                    best_parent = other_id
                    best_parent_area = other_area
        
        parent_map[elem_id] = best_parent
    
    return parent_map

def is_inside(inner, outer):
    """Check if inner box is completely inside outer box."""
    return (inner['x'] >= outer['x'] and
            inner['y'] >= outer['y'] and
            inner['x2'] <= outer['x2'] and
            inner['y2'] <= outer['y2'])

def get_children(parent_map, parent_id):
    """Get all direct children of a parent."""
    return [eid for eid, pid in parent_map.items() if pid == parent_id]

# ============================================================================
# Build XML with Nested Nodes
# ============================================================================
def create_archimate_xml(elements, coordinates, relationships, view_name):
    """Create ArchiMate Model Exchange Format XML with nested nodes."""
    
    model_id = gen_id("model")
    view_id = gen_id("view")
    
    # Root
    root = ET.Element("model", {
        "xmlns": ARCHIMATE_NS,
        "xmlns:xsi": XSI_NS,
        "xsi:schemaLocation": SCHEMA_LOCATION,
        "identifier": model_id
    })
    
    ET.SubElement(root, "name", {"xml:lang": "en"}).text = view_name
    
    # --- Elements section ---
    elements_section = ET.SubElement(root, "elements")
    for elem_id, elem in elements.items():
        if elem_id in coordinates:  # Only include elements that are in the view
            elem_type = elem['type']
            # Skip non-ArchiMate types
            if elem_type in ('DiagramModelNote', 'DiagramModelReference', 'Unknown'):
                continue
            
            element = ET.SubElement(elements_section, "element", {
                "identifier": elem_id,
                "xsi:type": elem_type
            })
            ET.SubElement(element, "name", {"xml:lang": "en"}).text = elem['name']
            
            # Add documentation from model.html
            doc = get_element_documentation(elem_id)
            if doc:
                ET.SubElement(element, "documentation", {"xml:lang": "en"}).text = doc
    
    # --- Relationships section ---
    if relationships:
        rels_section = ET.SubElement(root, "relationships")
        for rel in relationships:
            rel_elem = ET.SubElement(rels_section, "relationship", {
                "identifier": rel['id'],
                "xsi:type": rel['type'],
                "source": rel['source'],
                "target": rel['target']
            })
            if rel.get('name'):
                ET.SubElement(rel_elem, "name", {"xml:lang": "en"}).text = rel['name']
    
    # --- Views section with FLAT nodes (no nesting) ---
    views_section = ET.SubElement(root, "views")
    diagrams = ET.SubElement(views_section, "diagrams")
    view = ET.SubElement(diagrams, "view", {"identifier": view_id, "xsi:type": "Diagram"})
    ET.SubElement(view, "name", {"xml:lang": "en"}).text = view_name
    
    # Track node IDs for connections
    node_ids = {}
    
    # Collect all nodes with their coordinates
    nodes_to_add = []
    for elem_id, elem in elements.items():
        if elem_id not in coordinates:
            continue
        
        elem_type = elem['type']
        # Skip non-ArchiMate types
        if elem_type in ('DiagramModelNote', 'DiagramModelReference', 'Unknown'):
            continue
        
        coords = coordinates[elem_id]
        area = coords['w'] * coords['h']
        
        nodes_to_add.append({
            'elem_id': elem_id,
            'elem': elem,
            'coords': coords,
            'area': area
        })
    
    # Sort by area DESCENDING (largest first for proper z-order)
    # This ensures containers/groups are drawn behind smaller elements
    nodes_to_add.sort(key=lambda n: n['area'], reverse=True)
    
    print(f"  Z-Order: {len(nodes_to_add)} nodes sorted by area (largest first)")
    
    # Add ALL nodes as FLAT siblings (direct children of view)
    # Using ABSOLUTE coordinates from HTML - no subtraction!
    for node_data in nodes_to_add:
        elem_id = node_data['elem_id']
        coords = node_data['coords']
        
        node_id = gen_id("node")
        node_ids[elem_id] = node_id
        
        # Use ABSOLUTE coordinates directly from the HTML
        ET.SubElement(view, "node", {
            "identifier": node_id,
            "elementRef": elem_id,
            "xsi:type": "Element",
            "x": str(coords['x']),
            "y": str(coords['y']),
            "w": str(coords['w']),
            "h": str(coords['h'])
        })
    
    # NOTE: Connections are SKIPPED to create a clean diagram without spiderweb lines
    # The relationships still exist in the <relationships> section of the model
    # They will appear in Archi's Model Tree, just not drawn on this view canvas
    
    return root

# ============================================================================
# Pretty Print and Save
# ============================================================================
def prettify_xml(elem):
    rough = ET.tostring(elem, encoding='unicode')
    return minidom.parseString(rough).toprettyxml(indent="  ")

def save_xml(root, output_path):
    xml_string = prettify_xml(root)
    lines = xml_string.split('\n')
    if lines[0].startswith('<?xml'):
        lines = lines[1:]
    final = '<?xml version="1.0" encoding="UTF-8"?>\n' + '\n'.join(lines).strip()
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final)
    print(f"  Created: {output_path}")

# ============================================================================
# Process Single HTML File
# ============================================================================
def process_html_file(html_path):
    """Process a single Archi HTML view file."""
    print(f"\nProcessing: {html_path}")
    
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    
    # Get view name from title
    title = soup.find('title')
    view_name = title.get_text(strip=True) if title else html_path.stem
    print(f"  View: {view_name}")
    
    # Load model.html for documentation
    load_model_data("model.html")
    
    # Step A: Extract elements
    elements = extract_elements(soup)
    print(f"  Elements: {len(elements)}")
    
    # Step B: Extract coordinates
    coordinates = extract_coordinates(soup)
    print(f"  Coordinates: {len(coordinates)}")
    
    # Step C: Extract relationships
    relationships = extract_relationships(soup)
    print(f"  Relationships: {len(relationships)}")
    
    if not coordinates:
        print("  ERROR: No coordinates found. Skipping.")
        return None
    
    # Create XML
    root = create_archimate_xml(elements, coordinates, relationships, view_name)
    
    # Save
    output_path = html_path.with_suffix('.xml')
    save_xml(root, output_path)
    
    return output_path

# ============================================================================
# Main
# ============================================================================
def main():
    # Files to process
    html_files = [
        Path("capabilities.html"),
        Path("data-architecting.html"),
        Path("data-quality.html"),
    ]
    
    print("=" * 60)
    print("Archi HTML View to ArchiMate XML Converter")
    print("=" * 60)
    
    for html_path in html_files:
        if html_path.exists():
            process_html_file(html_path)
        else:
            print(f"\nSkipping (not found): {html_path}")
    
    print("\n" + "=" * 60)
    print("Conversion Complete")
    print("=" * 60)

if __name__ == "__main__":
    main()

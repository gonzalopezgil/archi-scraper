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
import argparse
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
# Load Documentation and Folder Structure from model.html
# ============================================================================
def load_model_data(model_html_path):
    """Load element documentation and folder structure from model.html."""
    global MODEL_DATA
    
    if MODEL_DATA is not None:
        return MODEL_DATA
    
    MODEL_DATA = {'elements': {}, 'relationships': {}, 'folders': {}, 'folder_contents': []}
    
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
            MODEL_DATA['elements'][elem_data['id']] = elem_data
    
    print(f"    Loaded {len(MODEL_DATA['elements'])} elements from model.html")
    
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
            MODEL_DATA['folders'][folder_data['id']] = folder_data
    
    print(f"    Loaded {len(MODEL_DATA['folders'])} folders from model.html")
    
    # Extract dataFoldersContent (parent-child relationships)
    content_pattern = r'dataFoldersContent\.push\(\s*\{([^}]+)\}\s*\);'
    content_matches = re.findall(content_pattern, content)
    
    for match in content_matches:
        folder_id_match = re.search(r'folderid:\s*"([^"]+)"', match)
        content_id_match = re.search(r'contentid:\s*"([^"]+)"', match)
        content_type_match = re.search(r'contenttype:\s*"([^"]+)"', match)
        
        if folder_id_match and content_id_match:
            MODEL_DATA['folder_contents'].append({
                'folder_id': folder_id_match.group(1),
                'content_id': content_id_match.group(1),
                'content_type': content_type_match.group(1) if content_type_match else 'Unknown'
            })
    
    print(f"    Loaded {len(MODEL_DATA['folder_contents'])} folder-content mappings")
    
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
# Process Single HTML File - Returns data for merging
# ============================================================================
def extract_view_data(html_path):
    """Extract elements, relationships, coordinates and view info from HTML."""
    print(f"\nProcessing: {html_path}")
    
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    
    # Get view name from title
    title = soup.find('title')
    view_name = title.get_text(strip=True) if title else html_path.stem
    print(f"  View: {view_name}")
    
    # Get view ID from map name
    view_id = None
    map_elem = soup.find('map')
    if map_elem and map_elem.get('name'):
        map_name = map_elem.get('name')
        if map_name.endswith('map'):
            view_id = map_name[:-3] # Remove 'map' suffix
    
    if not view_id:
        view_id = gen_id("view")
    print(f"  View ID: {view_id}")
    
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
        print("  WARNING: No coordinates found.")
        return None
    
    return {
        'view_name': view_name,
        'view_id': view_id,
        'elements': elements,
        'relationships': relationships,
        'coordinates': coordinates
    }

# ============================================================================
# Create Merged ArchiMate XML
# ============================================================================
def create_merged_xml(all_elements, all_relationships, views_data):
    """Create a single ArchiMate XML with all elements, relationships, and views."""
    
    model_id = gen_id("model")
    
    # Root
    root = ET.Element("model", {
        "xmlns": ARCHIMATE_NS,
        "xmlns:xsi": XSI_NS,
        "xsi:schemaLocation": SCHEMA_LOCATION,
        "identifier": model_id
    })
    
    ET.SubElement(root, "name", {"xml:lang": "en"}).text = "Data Centric Reference Architecture"
    
    # --- Elements section (all unique elements) ---
    elements_section = ET.SubElement(root, "elements")
    for elem_id, elem in all_elements.items():
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
    
    # --- Relationships section (all unique relationships) ---
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
    
    # --- Organizations section (folder structure) ---
    # Must come BEFORE Views per ArchiMate schema
    if MODEL_DATA and MODEL_DATA.get('folders') and MODEL_DATA.get('folder_contents'):
        print("\n  Building folder structure with referential integrity...")
        
        # Build set of valid IDs (Elements + Relationships + PROCESSED Views)
        valid_ids = set()
        
        # Add only Elements that will actually be written (skip excluded types)
        for elem_id, elem in all_elements.items():
            elem_type = elem['type']
            if elem_type not in ('DiagramModelNote', 'DiagramModelReference', 'Unknown'):
                valid_ids.add(elem_id)
                
        valid_ids.update(all_relationships.keys())
        for v_data in views_data:
            if v_data.get('view_id'):
                valid_ids.add(v_data['view_id'])
        
        print(f"    Valid IDs for folder structure: {len(valid_ids)}")
        
        # Build parent->children mapping
        folder_children = {}  # folder_id -> list of (content_id, content_type)
        for fc in MODEL_DATA['folder_contents']:
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
                # If content is a valid ID (element/relation/view)
                if content_id in valid_ids:
                    return True
                
                # If content is a sub-folder, check if it has valid content
                if content_type == 'Folder' or content_id in MODEL_DATA['folders']:
                    if folder_has_valid_content(content_id, visited):
                        return True
            return False
        
        # Identify all folders that should be included
        included_folders = set()
        for folder_id in MODEL_DATA['folders']:
            if folder_has_valid_content(folder_id):
                included_folders.add(folder_id)
        
        # Ensure ancestors are included for all included folders
        def get_parent_folder(folder_id):
            for fc in MODEL_DATA['folder_contents']:
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
        
        print(f"    Including {len(included_folders)} folders (filtered from {len(MODEL_DATA['folders'])})")
        
        # Find root folders
        root_folder_ids = []
        for folder_id in included_folders:
            folder = MODEL_DATA['folders'].get(folder_id)
            if folder and folder.get('type') == 'Folder':
                parent = get_parent_folder(folder_id)
                if parent is None or MODEL_DATA['folders'].get(parent, {}).get('type') == 'ArchimateModel':
                    root_folder_ids.append(folder_id)
        
        # Generate XML
        orgs_section = ET.SubElement(root, "organizations")
        
        def add_folder_items(parent_xml, folder_id):
            folder = MODEL_DATA['folders'].get(folder_id)
            if not folder or folder_id not in included_folders:
                return
            
            folder_item = ET.SubElement(parent_xml, "item")
            ET.SubElement(folder_item, "label", {"xml:lang": "en"}).text = folder.get('name', 'Unnamed')
            
            children = folder_children.get(folder_id, [])
            for content_id, content_type in children:
                # Add sub-folder if included
                if content_type == 'Folder' and content_id in included_folders:
                    add_folder_items(folder_item, content_id)
                # Add content only if it maps to a VALID ID
                elif content_id in valid_ids:
                    ET.SubElement(folder_item, "item", {"identifierRef": content_id})
        
        for folder_id in root_folder_ids:
            add_folder_items(orgs_section, folder_id)
            
        print(f"    Added organizations structure with {len(root_folder_ids)} root folders")
    
    # --- Views section (multiple views) ---
    # Must come LAST (after organizations)
    views_section = ET.SubElement(root, "views")
    diagrams = ET.SubElement(views_section, "diagrams")
    
    for view_data in views_data:
        # Use extracted view_id if available to match folder references
        view_id = view_data.get('view_id') or gen_id("view")
        view = ET.SubElement(diagrams, "view", {"identifier": view_id, "xsi:type": "Diagram"})
        ET.SubElement(view, "name", {"xml:lang": "en"}).text = view_data['view_name']
        
        elements = view_data['elements']
        coordinates = view_data['coordinates']
        
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
        
        # Add flat nodes with absolute coordinates
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
        
        print(f"  Added view '{view_data['view_name']}' (ID: {view_id}) with {len(nodes_to_add)} nodes")
    
    return root

# ============================================================================
# Main - Merge all views into single master_model.xml
# ============================================================================
def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Archi HTML View to ArchiMate Model Exchange Format XML Converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  python html_to_archimate_xml.py --model model.html --views view1.html view2.html --output my_architecture.xml
        """
    )
    parser.add_argument(
        "--model", "-m",
        required=True,
        type=str,
        help="Path to the main model.html file (Required)"
    )
    parser.add_argument(
        "--views", "-v",
        required=True,
        nargs="+",
        type=str,
        help="Paths to the specific view HTML files to process (Required, supports multiple files)"
    )
    parser.add_argument(
        "--output", "-o",
        default="master_model.xml",
        type=str,
        help="Output XML filename (Optional, default: master_model.xml)"
    )
    
    args = parser.parse_args()
    
    # Convert paths
    model_path = Path(args.model)
    view_files = [Path(v) for v in args.views]
    output_path = Path(args.output)
    
    print("=" * 60)
    print("Archi HTML Views to Single Master Model Converter")
    print("=" * 60)
    print(f"  Model: {model_path}")
    print(f"  Views: {[str(v) for v in view_files]}")
    print(f"  Output: {output_path}")
    
    # Load model.html documentation ONCE at start
    load_model_data(str(model_path))
    
    # Global accumulators (keyed by ID for deduplication)
    all_elements = {}      # {elem_id: elem_data}
    all_relationships = {} # {rel_id: rel_data}
    views_data = []        # List of view data dicts
    
    # Process each HTML file
    for html_path in view_files:
        if not html_path.exists():
            print(f"\nSkipping (not found): {html_path}")
            continue
        
        data = extract_view_data(html_path)
        if not data:
            continue
        
        # Accumulate elements (deduplicate by ID)
        for elem_id, elem in data['elements'].items():
            if elem_id not in all_elements:
                all_elements[elem_id] = elem
        
        # Accumulate relationships (deduplicate by ID)
        for rel in data['relationships']:
            rel_id = rel['id']
            if rel_id not in all_relationships:
                all_relationships[rel_id] = rel
        
        # Add view data
        views_data.append(data)
    
    print(f"\n--- Summary ---")
    print(f"Total unique elements: {len(all_elements)}")
    print(f"Total unique relationships: {len(all_relationships)}")
    print(f"Total views: {len(views_data)}")
    
    if not views_data:
        print("\nERROR: No valid views found. Exiting.")
        return
    
    # Create merged XML
    print(f"\nGenerating {output_path}...")
    root = create_merged_xml(all_elements, all_relationships, views_data)
    
    # Save
    save_xml(root, output_path)
    
    print("\n" + "=" * 60)
    print(f"SUCCESS: Created {output_path}")
    print("=" * 60)
    print(f"  Elements: {len(all_elements)}")
    print(f"  Relationships: {len(all_relationships)}")
    print(f"  Views: {len(views_data)}")
    print(f"\nImport into Archi: File → Import → Model from Open Exchange File")

if __name__ == "__main__":
    main()


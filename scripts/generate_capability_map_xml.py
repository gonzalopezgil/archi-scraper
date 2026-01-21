"""
Python Script: Generate ArchiMate Model Exchange Format XML
Creates a valid ArchiMate Open Exchange file matching the complex capability map diagram.
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
import uuid

# ============================================================================
# 1. Define Namespaces (ArchiMate Open Exchange Format)
# ============================================================================
ARCHIMATE_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = "http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.1/archimate3_Diagram.xsd"

# Register namespaces
ET.register_namespace('', ARCHIMATE_NS)
ET.register_namespace('xsi', XSI_NS)

# ============================================================================
# 2. Helper to generate unique IDs
# ============================================================================
def gen_id(prefix="id"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

# ============================================================================
# 3. Define All Elements
# ============================================================================

# Goals (Motivation elements - left side)
goals = [
    {"id": gen_id("goal"), "name": "Establish a data governance operating model for the Alliance", "type": "Goal"},
    {"id": gen_id("goal"), "name": "Establish Data Architecting capability", "type": "Goal"},
    {"id": gen_id("goal"), "name": "Establish a Data Quality Framework for the Alliance", "type": "Goal"},
    {"id": gen_id("goal"), "name": "Establish Master- and Reference Data Management", "type": "Goal"},
    {"id": gen_id("goal"), "name": "Establish automated Data Preservation", "type": "Goal"},
]

# Main Capability (container)
main_capability = {"id": gen_id("cap"), "name": "Data Centric Governance", "type": "Capability"}

# Nested Capabilities (inside Data Centric Governance)
nested_capabilities = [
    {"id": gen_id("cap"), "name": "Data Architecting", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Data Quality Management", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Master- and Reference Data Management", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Data Archiving", "type": "Capability"},
]

# Right side Capabilities
right_capabilities = [
    {"id": gen_id("cap"), "name": "Data Analytics", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Data Space", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Data Mesh", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Data Modelling & Design", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Data Labelling", "type": "Capability"},
]

# Bottom Capability
bottom_capability = {"id": gen_id("cap"), "name": "Data Standardization", "type": "Capability"}

# Collect all elements
all_elements = goals + [main_capability] + nested_capabilities + right_capabilities + [bottom_capability]

# ============================================================================
# 4. Define Relationships
# ============================================================================
relationships = []

# "realizes" relationships: Goals -> Nested Capabilities
# Goal 0 -> main capability (governance model)
relationships.append({
    "id": gen_id("rel"),
    "type": "Realization",
    "source": goals[0]["id"],
    "target": main_capability["id"]
})
# Goal 1 -> Data Architecting
relationships.append({
    "id": gen_id("rel"),
    "type": "Realization",
    "source": goals[1]["id"],
    "target": nested_capabilities[0]["id"]
})
# Goal 2 -> Data Quality Management
relationships.append({
    "id": gen_id("rel"),
    "type": "Realization",
    "source": goals[2]["id"],
    "target": nested_capabilities[1]["id"]
})
# Goal 3 -> Master- and Reference Data Management
relationships.append({
    "id": gen_id("rel"),
    "type": "Realization",
    "source": goals[3]["id"],
    "target": nested_capabilities[2]["id"]
})
# Goal 4 -> Data Archiving
relationships.append({
    "id": gen_id("rel"),
    "type": "Realization",
    "source": goals[4]["id"],
    "target": nested_capabilities[3]["id"]
})

# "regulates" relationships: Data Centric Governance -> Right Capabilities
# Note: In ArchiMate, "regulates" is typically an Influence relationship
for right_cap in right_capabilities:
    relationships.append({
        "id": gen_id("rel"),
        "type": "Influence",
        "source": main_capability["id"],
        "target": right_cap["id"]
    })

# "supports" relationship: Data Standardization -> Data Centric Governance
# Note: In ArchiMate, this would be a Serving relationship (supports)
relationships.append({
    "id": gen_id("rel"),
    "type": "Serving",
    "source": bottom_capability["id"],
    "target": main_capability["id"]
})

# ============================================================================
# 5. Layout Dimensions and Positions
# ============================================================================
gap = 10
small_box_w = 150
small_box_h = 55
goal_box_w = 170
goal_box_h = 55

# Starting positions
start_x = 30
start_y = 30

# Calculate positions
layout = {}

# --- Left Column: Goals ---
goal_x = start_x
goal_y = start_y
for goal in goals:
    layout[goal["id"]] = {"x": goal_x, "y": goal_y, "w": goal_box_w, "h": goal_box_h}
    goal_y += goal_box_h + gap

# --- Center: Main Capability with nested ---
center_x = goal_x + goal_box_w + 80  # extra space for "realizes" label
center_y = start_y

# Main capability container - size to fit nested elements
nested_area_h = (small_box_h * 4) + (gap * 5)  # 4 nested + padding
main_cap_w = 200
main_cap_h = nested_area_h + 40  # extra for title

layout[main_capability["id"]] = {
    "x": center_x, 
    "y": center_y, 
    "w": main_cap_w, 
    "h": main_cap_h,
    "nested": []  # Will contain nested node positions
}

# Nested capabilities inside main
nested_x = center_x + 15
nested_y = center_y + 45  # offset for title
for nested_cap in nested_capabilities:
    layout[nested_cap["id"]] = {
        "x": nested_x, 
        "y": nested_y, 
        "w": main_cap_w - 30, 
        "h": small_box_h,
        "parent": main_capability["id"]
    }
    layout[main_capability["id"]]["nested"].append(nested_cap["id"])
    nested_y += small_box_h + gap

# --- Right Column: Capabilities ---
right_x = center_x + main_cap_w + 80  # extra space for "regulates" label
right_y = start_y
for right_cap in right_capabilities:
    layout[right_cap["id"]] = {"x": right_x, "y": right_y, "w": small_box_w, "h": small_box_h}
    right_y += small_box_h + gap

# --- Bottom: Data Standardization ---
# Center it under the main capability
bottom_x = center_x + (main_cap_w - small_box_w) // 2
bottom_y = center_y + main_cap_h + 60  # space for "supports" label
layout[bottom_capability["id"]] = {"x": bottom_x, "y": bottom_y, "w": small_box_w, "h": small_box_h}

# ============================================================================
# 6. Build XML Structure
# ============================================================================
def create_archimate_xml():
    """Create the ArchiMate Model Exchange Format XML structure."""
    
    model_id = gen_id("model")
    view_id = gen_id("view")
    
    # Root element
    root = ET.Element("model", {
        "xmlns": ARCHIMATE_NS,
        "xmlns:xsi": XSI_NS,
        "xsi:schemaLocation": SCHEMA_LOCATION,
        "identifier": model_id
    })
    
    # Model name
    name_elem = ET.SubElement(root, "name", {"xml:lang": "en"})
    name_elem.text = "Data Governance Capability Map"
    
    # --- Elements section ---
    elements_section = ET.SubElement(root, "elements")
    for elem in all_elements:
        element = ET.SubElement(elements_section, "element", {
            "identifier": elem["id"],
            "xsi:type": elem["type"]
        })
        elem_name = ET.SubElement(element, "name", {"xml:lang": "en"})
        elem_name.text = elem["name"]
    
    # --- Relationships section ---
    relationships_section = ET.SubElement(root, "relationships")
    for rel in relationships:
        relationship = ET.SubElement(relationships_section, "relationship", {
            "identifier": rel["id"],
            "xsi:type": rel["type"],
            "source": rel["source"],
            "target": rel["target"]
        })
    
    # --- Views section ---
    views_section = ET.SubElement(root, "views")
    diagrams = ET.SubElement(views_section, "diagrams")
    
    view = ET.SubElement(diagrams, "view", {
        "identifier": view_id,
        "xsi:type": "Diagram"
    })
    view_name = ET.SubElement(view, "name", {"xml:lang": "en"})
    view_name.text = "Data Governance Capability Map"
    
    # Add nodes - handle nested structure
    node_ids = {}  # Map element id to node id
    
    for elem in all_elements:
        pos = layout[elem["id"]]
        node_id = gen_id("node")
        node_ids[elem["id"]] = node_id
        
        # Check if this is nested inside another element
        if "parent" in pos:
            # Skip for now, will add as child
            continue
        
        node = ET.SubElement(view, "node", {
            "identifier": node_id,
            "elementRef": elem["id"],
            "xsi:type": "Element",
            "x": str(pos["x"]),
            "y": str(pos["y"]),
            "w": str(pos["w"]),
            "h": str(pos["h"])
        })
        
        # Add nested nodes as children
        if "nested" in pos:
            for nested_id in pos["nested"]:
                nested_elem = next(e for e in all_elements if e["id"] == nested_id)
                nested_pos = layout[nested_id]
                nested_node_id = gen_id("node")
                node_ids[nested_id] = nested_node_id
                
                # Nested positions are relative to parent in some viewers
                nested_node = ET.SubElement(node, "node", {
                    "identifier": nested_node_id,
                    "elementRef": nested_id,
                    "xsi:type": "Element",
                    "x": str(nested_pos["x"]),
                    "y": str(nested_pos["y"]),
                    "w": str(nested_pos["w"]),
                    "h": str(nested_pos["h"])
                })
    
    # Add relationship connections
    for rel in relationships:
        conn_id = gen_id("conn")
        source_node = node_ids.get(rel["source"])
        target_node = node_ids.get(rel["target"])
        
        if source_node and target_node:
            connection = ET.SubElement(view, "connection", {
                "identifier": conn_id,
                "relationshipRef": rel["id"],
                "xsi:type": "Relationship",
                "source": source_node,
                "target": target_node
            })
    
    return root

# ============================================================================
# 7. Pretty Print and Save
# ============================================================================
def prettify_xml(elem):
    rough_string = ET.tostring(elem, encoding='unicode')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")

def main():
    print("Generating ArchiMate Model Exchange Format XML...")
    print()
    
    root = create_archimate_xml()
    xml_string = prettify_xml(root)
    
    lines = xml_string.split('\n')
    if lines[0].startswith('<?xml'):
        lines = lines[1:]
    xml_content = '\n'.join(lines)
    
    final_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_content.strip()
    
    output_file = "capability_map.xml"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_xml)
    
    print(f"Created: {output_file}")
    print()
    print("Elements created:")
    print(f"  - Goals: {len(goals)}")
    print(f"  - Capabilities: {len([main_capability] + nested_capabilities + right_capabilities + [bottom_capability])}")
    print(f"  - Relationships: {len(relationships)}")
    print()
    print("Structure:")
    print("  LEFT: Goals (realizes ->)")
    print("  CENTER: Data Centric Governance (contains nested capabilities)")
    print("  RIGHT: Capabilities (<- regulates)")
    print("  BOTTOM: Data Standardization (supports ->)")

if __name__ == "__main__":
    main()

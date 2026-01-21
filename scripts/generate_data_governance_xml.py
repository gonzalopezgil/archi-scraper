"""
Python Script: Generate ArchiMate Model Exchange Format XML
Creates a valid ArchiMate Open Exchange file for Data Governance Architecture.
Reproduces the diagram with nested containers, relationships, and visual layout.
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
import uuid

# ============================================================================
# 1. XML Namespaces
# ============================================================================
ARCHIMATE_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = "http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.1/archimate3_Diagram.xsd"

ET.register_namespace('', ARCHIMATE_NS)
ET.register_namespace('xsi', XSI_NS)

# ============================================================================
# 2. Helper Functions
# ============================================================================
def gen_id(prefix="id"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

# ============================================================================
# 3. Define Model Elements
# ============================================================================

# --- Group A: Courses of Action (individual stacked elements, NOT nested) ---
courses_of_action = [
    {"id": gen_id("coa"), "name": "Establish a data governance operating model for the Alliance", "type": "CourseOfAction"},
    {"id": gen_id("coa"), "name": "Establish Data Architecting capability", "type": "CourseOfAction"},
    {"id": gen_id("coa"), "name": "Establish a Data Quality Framework for the Alliance", "type": "CourseOfAction"},
    {"id": gen_id("coa"), "name": "Establish Master- and Reference Data Management", "type": "CourseOfAction"},
    {"id": gen_id("coa"), "name": "Establish automated Data Preservation", "type": "CourseOfAction"},
]

# --- Group B: Governance Capabilities (nested under Data Centric Governance) ---
cap_parent = {
    "id": gen_id("cap"), 
    "name": "Data Centric Governance", 
    "type": "Capability"
}
cap_children = [
    {"id": gen_id("cap"), "name": "Data Architecting", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Data Quality Management", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Master- and Reference Data Management", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Data Archiving", "type": "Capability"},
]

# --- Group C: Independent Capabilities (right side stack) ---
independent_caps = [
    {"id": gen_id("cap"), "name": "Data Analytics", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Data Space", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Data Mesh", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Data Modelling & Design", "type": "Capability"},
    {"id": gen_id("cap"), "name": "Data Labelling", "type": "Capability"},
]

# --- Bottom element ---
bottom_cap = {
    "id": gen_id("cap"), 
    "name": "Data Standardization", 
    "type": "Capability"
}

# Collect all elements
all_elements = (
    courses_of_action + 
    [cap_parent] + cap_children + 
    independent_caps + 
    [bottom_cap]
)

# ============================================================================
# 4. Define Relationships
# ============================================================================
relationships = []

# --- Realization Relationships (Capability realizes CourseOfAction) ---
# Data Architecting -> Establish Data Architecting capability
relationships.append({
    "id": gen_id("rel"),
    "type": "Realization",
    "source": cap_children[0]["id"],  # Data Architecting
    "target": courses_of_action[1]["id"],  # Establish Data Architecting capability (index 1)
    "name": None
})

# Data Quality Management -> Establish a Data Quality Framework
relationships.append({
    "id": gen_id("rel"),
    "type": "Realization",
    "source": cap_children[1]["id"],
    "target": courses_of_action[2]["id"],
    "name": None
})

# Master- and Reference Data Management (Cap) -> Establish Master- and Reference Data Management (CoA)
relationships.append({
    "id": gen_id("rel"),
    "type": "Realization",
    "source": cap_children[2]["id"],
    "target": courses_of_action[3]["id"],
    "name": None
})

# Data Archiving -> Establish automated Data Preservation
relationships.append({
    "id": gen_id("rel"),
    "type": "Realization",
    "source": cap_children[3]["id"],
    "target": courses_of_action[4]["id"],
    "name": None
})

# --- Association Relationships (Data Centric Governance -> Independent Caps) ---
# With "regulates" label for all
relationships.append({
    "id": gen_id("rel"),
    "type": "Association",
    "source": cap_parent["id"],
    "target": independent_caps[0]["id"],  # Data Analytics
    "name": "regulates"
})

relationships.append({
    "id": gen_id("rel"),
    "type": "Association",
    "source": cap_parent["id"],
    "target": independent_caps[1]["id"],  # Data Space
    "name": "regulates"
})

relationships.append({
    "id": gen_id("rel"),
    "type": "Association",
    "source": cap_parent["id"],
    "target": independent_caps[2]["id"],  # Data Mesh
    "name": "regulates"
})

relationships.append({
    "id": gen_id("rel"),
    "type": "Association",
    "source": cap_parent["id"],
    "target": independent_caps[3]["id"],  # Data Modelling & Design
    "name": "regulates"
})

relationships.append({
    "id": gen_id("rel"),
    "type": "Association",
    "source": cap_parent["id"],
    "target": independent_caps[4]["id"],  # Data Labelling
    "name": "regulates"
})

# Data Standardization -> Data Centric Governance (supports)
relationships.append({
    "id": gen_id("rel"),
    "type": "Association",
    "source": bottom_cap["id"],
    "target": cap_parent["id"],
    "name": "supports"
})

# ============================================================================
# 5. Visual Layout Calculations
# ============================================================================

# Standard dimensions
coa_w = 150  # Course of Action box width
coa_h = 60   # Course of Action box height
child_w = 160  # Capability child width
child_h = 55   # Capability child height
gap = 10     # Gap between boxes

# Container padding
container_pad_top = 35  # Space for title
container_pad_sides = 15
container_pad_bottom = 15

# Starting positions
start_x = 50
start_y = 50

# --- LEFT: Courses of Action (individual stacked boxes) ---
coa_positions = []
coa_x = start_x
coa_y = start_y
for i in range(5):
    coa_positions.append({
        "x": coa_x,
        "y": coa_y,
        "w": coa_w,
        "h": coa_h
    })
    coa_y += coa_h + gap

# --- CENTER: Data Centric Governance Container with nested children ---
# Calculate container size based on 4 children
num_cap_children = 4
cap_container_inner_h = (child_h * num_cap_children) + (gap * (num_cap_children - 1))
cap_container_h = cap_container_inner_h + container_pad_top + container_pad_bottom
cap_container_w = child_w + (container_pad_sides * 2)

center_container_x = coa_x + coa_w + 80  # Gap between left and center
center_container_y = start_y

# Children positions (relative within container)
cap_child_positions = []
child_y = container_pad_top
for i in range(num_cap_children):
    cap_child_positions.append({
        "x": container_pad_sides,
        "y": child_y,
        "w": child_w,
        "h": child_h
    })
    child_y += child_h + gap

# --- RIGHT: Independent Capabilities Stack ---
right_stack_x = center_container_x + cap_container_w + 80
right_stack_y = start_y

independent_positions = []
current_y = right_stack_y
for i in range(5):
    independent_positions.append({
        "x": right_stack_x,
        "y": current_y,
        "w": child_w,
        "h": child_h
    })
    current_y += child_h + gap

# --- BOTTOM: Data Standardization ---
# Center it under the main capability container
bottom_x = center_container_x + (cap_container_w - child_w) // 2
bottom_y = center_container_y + cap_container_h + 50

bottom_position = {
    "x": bottom_x,
    "y": bottom_y,
    "w": child_w,
    "h": child_h
}

# ============================================================================
# 6. Build XML Structure
# ============================================================================
def create_archimate_xml():
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
    name_elem.text = "Data Governance Architecture Model"
    
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
        rel_attrs = {
            "identifier": rel["id"],
            "xsi:type": rel["type"],
            "source": rel["source"],
            "target": rel["target"]
        }
        relationship = ET.SubElement(relationships_section, "relationship", rel_attrs)
        if rel["name"]:
            rel_name = ET.SubElement(relationship, "name", {"xml:lang": "en"})
            rel_name.text = rel["name"]
    
    # --- Views section ---
    views_section = ET.SubElement(root, "views")
    diagrams = ET.SubElement(views_section, "diagrams")
    
    view = ET.SubElement(diagrams, "view", {
        "identifier": view_id,
        "xsi:type": "Diagram"
    })
    view_name = ET.SubElement(view, "name", {"xml:lang": "en"})
    view_name.text = "Data Governance Architecture"
    
    # Track node IDs for connections
    node_ids = {}
    
    # --- LEFT: Courses of Action (individual separate nodes) ---
    for i, coa in enumerate(courses_of_action):
        coa_node_id = gen_id("node")
        node_ids[coa["id"]] = coa_node_id
        pos = coa_positions[i]
        
        ET.SubElement(view, "node", {
            "identifier": coa_node_id,
            "elementRef": coa["id"],
            "xsi:type": "Element",
            "x": str(pos["x"]),
            "y": str(pos["y"]),
            "w": str(pos["w"]),
            "h": str(pos["h"])
        })
    
    # --- CENTER: Data Centric Governance Container with nested children ---
    center_container_node_id = gen_id("node")
    node_ids[cap_parent["id"]] = center_container_node_id
    
    center_container_node = ET.SubElement(view, "node", {
        "identifier": center_container_node_id,
        "elementRef": cap_parent["id"],
        "xsi:type": "Element",
        "x": str(center_container_x),
        "y": str(center_container_y),
        "w": str(cap_container_w),
        "h": str(cap_container_h)
    })
    
    # Add Capability children as nested nodes (positions relative to parent)
    for i, cap_child in enumerate(cap_children):
        child_node_id = gen_id("node")
        node_ids[cap_child["id"]] = child_node_id
        pos = cap_child_positions[i]
        
        ET.SubElement(center_container_node, "node", {
            "identifier": child_node_id,
            "elementRef": cap_child["id"],
            "xsi:type": "Element",
            "x": str(pos["x"]),
            "y": str(pos["y"]),
            "w": str(pos["w"]),
            "h": str(pos["h"])
        })
    
    # --- RIGHT: Independent Capabilities Stack ---
    for i, indep_cap in enumerate(independent_caps):
        node_id = gen_id("node")
        node_ids[indep_cap["id"]] = node_id
        pos = independent_positions[i]
        
        ET.SubElement(view, "node", {
            "identifier": node_id,
            "elementRef": indep_cap["id"],
            "xsi:type": "Element",
            "x": str(pos["x"]),
            "y": str(pos["y"]),
            "w": str(pos["w"]),
            "h": str(pos["h"])
        })
    
    # --- BOTTOM: Data Standardization ---
    bottom_node_id = gen_id("node")
    node_ids[bottom_cap["id"]] = bottom_node_id
    
    ET.SubElement(view, "node", {
        "identifier": bottom_node_id,
        "elementRef": bottom_cap["id"],
        "xsi:type": "Element",
        "x": str(bottom_position["x"]),
        "y": str(bottom_position["y"]),
        "w": str(bottom_position["w"]),
        "h": str(bottom_position["h"])
    })
    
    # --- Connections (Visual Relationships) ---
    for rel in relationships:
        source_node = node_ids.get(rel["source"])
        target_node = node_ids.get(rel["target"])
        
        if source_node and target_node:
            conn_id = gen_id("conn")
            ET.SubElement(view, "connection", {
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
    
    output_file = "data_governance.xml"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_xml)
    
    print(f"Created: {output_file}")
    print()
    print("Summary:")
    print(f"  - Courses of Action: {len(courses_of_action)} (individual stacked boxes)")
    print(f"  - Governance Capabilities: {len([cap_parent] + cap_children)} (1 container + 4 nested)")
    print(f"  - Independent Capabilities: {len(independent_caps) + 1} (5 right + 1 bottom)")
    print(f"  - Relationships: {len(relationships)}")
    print()
    print("Layout:")
    print("  [LEFT]   Courses of Action (5 individual stacked boxes)")
    print("  [CENTER] Data Centric Governance (container with 4 nested capabilities)")
    print("  [RIGHT]  Independent Capabilities (5 stacked boxes)")
    print("  [BOTTOM] Data Standardization")

if __name__ == "__main__":
    main()

"""
ArchiMate Open Exchange Format XML to Markdown converter.

Outputs a structured Markdown directory for LLM-friendly navigation.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple

ARCHIMATE_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
logger = logging.getLogger(__name__)

LAYER_FILES = {
    "strategy": "strategy.md",
    "business": "business.md",
    "application": "application.md",
    "technology": "technology.md",
    "motivation": "motivation.md",
    "implementation": "implementation.md",
    "other": "other.md",
}

LAYER_TYPE_MAP = {
    "strategy": {
        "Capability", "CourseOfAction", "Resource", "ValueStream",
    },
    "business": {
        "BusinessActor", "BusinessRole", "BusinessProcess", "BusinessService",
        "BusinessObject", "BusinessFunction", "BusinessInteraction",
        "BusinessCollaboration", "BusinessInterface", "BusinessEvent",
        "Contract", "Representation", "Product",
    },
    "application": {
        "ApplicationComponent", "ApplicationService", "ApplicationFunction",
        "ApplicationInteraction", "ApplicationCollaboration", "ApplicationInterface",
        "ApplicationProcess", "ApplicationEvent", "DataObject",
    },
    "technology": {
        "TechnologyService", "TechnologyFunction", "TechnologyProcess",
        "TechnologyInteraction", "TechnologyCollaboration", "TechnologyInterface",
        "TechnologyEvent", "Node", "Device", "SystemSoftware", "Path",
        "CommunicationNetwork", "Artifact", "DistributionNetwork", "Equipment",
        "Facility", "Material",
    },
    "motivation": {
        "Stakeholder", "Driver", "Assessment", "Goal", "Outcome", "Principle",
        "Requirement", "Constraint", "Meaning", "Value",
    },
    "implementation": {
        "WorkPackage", "Deliverable", "ImplementationEvent", "Plateau", "Gap",
    },
    "other": {
        "Grouping", "Junction", "AndJunction", "OrJunction", "Location",
    },
}


def classify_layer(type_name: str) -> str:
    for layer, types in LAYER_TYPE_MAP.items():
        if type_name in types:
            return layer
    return "other"


def get_xsi_type(elem: ET.Element) -> str:
    return elem.get(f"{{{XSI_NS}}}type", "Unknown")


def parse_model(xml_path: Path) -> Tuple[str, Dict[str, Dict[str, str]], List[Dict[str, str]], List[Dict[str, object]]]:
    try:
        tree = ET.parse(xml_path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"File not found: {xml_path}") from exc
    except ET.ParseError as exc:
        raise ValueError(f"Malformed XML in {xml_path}: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Unable to parse {xml_path}: {exc}") from exc
    root = tree.getroot()
    ns = {"a": ARCHIMATE_NS}

    model_name = root.findtext("a:name", default="Unnamed Model", namespaces=ns)

    elements: Dict[str, Dict[str, str]] = {}
    for elem in root.findall("a:elements/a:element", ns):
        elem_id = elem.get("identifier")
        if not elem_id:
            continue
        elem_type = get_xsi_type(elem)
        name = elem.findtext("a:name", default=elem_id, namespaces=ns)
        doc = elem.findtext("a:documentation", default="", namespaces=ns).strip()
        elements[elem_id] = {
            "id": elem_id,
            "name": name,
            "type": elem_type,
            "documentation": doc,
        }

    relationships: List[Dict[str, str]] = []
    for rel in root.findall("a:relationships/a:relationship", ns):
        rel_id = rel.get("identifier")
        if not rel_id:
            continue
        rel_type = get_xsi_type(rel)
        source = rel.get("source")
        target = rel.get("target")
        relationships.append({
            "id": rel_id,
            "type": rel_type,
            "source": source or "",
            "target": target or "",
        })

    views: List[Dict[str, object]] = []
    for view in root.findall("a:views/a:diagrams/a:view", ns):
        view_id = view.get("identifier")
        view_name = view.findtext("a:name", default=view_id or "Unnamed View", namespaces=ns)
        element_refs = set()
        for node in view.findall("a:node", ns):
            elem_ref = node.get("elementRef")
            if elem_ref:
                element_refs.add(elem_ref)
        views.append({
            "id": view_id or "",
            "name": view_name,
            "elements": element_refs,
        })

    return model_name, elements, relationships, views


def build_relationship_index(
    elements: Dict[str, Dict[str, str]],
    relationships: List[Dict[str, str]],
) -> Dict[str, List[Tuple[str, str, str]]]:
    rel_index: Dict[str, List[Tuple[str, str, str]]] = {elem_id: [] for elem_id in elements}

    for rel in relationships:
        rel_type = rel.get("type", "Unknown")
        source = rel.get("source")
        target = rel.get("target")
        if source in elements and target in elements:
            rel_index[source].append(("out", rel_type, target))
            rel_index[target].append(("in", rel_type, source))
        # Skip relationships where one endpoint is missing (filtered element types)

    return rel_index


def write_readme(output_dir: Path, model_name: str, elements_count: int, rel_count: int, view_count: int) -> None:
    content = (
        f"# {model_name}\n\n"
        f"- **Element count:** {elements_count}\n"
        f"- **Relationship count:** {rel_count}\n"
        f"- **View count:** {view_count}\n"
    )
    (output_dir / "README.md").write_text(content, encoding="utf-8")


def write_elements_files(
    elements: Dict[str, Dict[str, str]],
    rel_index: Dict[str, List[Tuple[str, str, str]]],
    output_dir: Path,
) -> None:
    elements_dir = output_dir / "elements"
    elements_dir.mkdir(parents=True, exist_ok=True)

    layer_buckets: Dict[str, List[Dict[str, str]]] = {layer: [] for layer in LAYER_FILES}
    for elem in elements.values():
        layer = classify_layer(elem["type"])
        layer_buckets[layer].append(elem)

    for layer, filename in LAYER_FILES.items():
        elems = sorted(layer_buckets[layer], key=lambda e: e["name"].lower())
        lines: List[str] = []
        for elem in elems:
            elem_id = elem["id"]
            elem_name = elem["name"]
            elem_type = elem["type"]
            documentation = elem.get("documentation", "").strip()

            lines.append(f"### {elem_name}")
            lines.append(f"- **Type:** {elem_type}")
            lines.append(f"- **ID:** {elem_id}")
            if documentation:
                lines.append(f"- **Documentation:** {documentation}")

            rel_lines: List[str] = []
            for direction, rel_type, other_id in rel_index.get(elem_id, []):
                other = elements.get(other_id)
                other_name = other.get("name") if other else (other_id or "Unknown")
                other_type = other.get("type") if other else "Unknown"
                if direction == "out":
                    rel_lines.append(f"  - →{rel_type}→ {other_name} ({other_type})")
                else:
                    rel_lines.append(f"  - ←{rel_type}← {other_name} ({other_type})")

            if rel_lines:
                rel_lines_sorted = sorted(rel_lines, key=lambda line: line.lower())
                lines.append("- **Relationships:**")
                lines.extend(rel_lines_sorted)

            lines.append("")

        content = "\n".join(lines).strip() + "\n"
        (elements_dir / filename).write_text(content, encoding="utf-8")


def write_relationships(relationships: List[Dict[str, str]], elements: Dict[str, Dict[str, str]], output_dir: Path) -> None:
    lines = [
        "| Source | Source Type | Relationship | Target | Target Type |",
        "|--------|-----------|--------------|--------|-------------|",
    ]

    def display_name(elem_id: str) -> str:
        if elem_id in elements:
            return elements[elem_id]["name"]
        return elem_id or "Unknown"

    def display_type(elem_id: str) -> str:
        if elem_id in elements:
            return elements[elem_id]["type"]
        return "Unknown"

    sorted_rels = sorted(
        relationships,
        key=lambda r: (
            display_name(r.get("source", "")).lower(),
            display_name(r.get("target", "")).lower(),
            r.get("type", ""),
        ),
    )

    for rel in sorted_rels:
        source = rel.get("source", "")
        target = rel.get("target", "")
        # Skip relationships with missing endpoints
        if source not in elements or target not in elements:
            continue
        lines.append(
            f"| {display_name(source)} | {display_type(source)} | {rel.get('type', 'Unknown')} | "
            f"{display_name(target)} | {display_type(target)} |"
        )

    (output_dir / "relationships.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_views(views: List[Dict[str, object]], elements: Dict[str, Dict[str, str]], output_dir: Path) -> None:
    views_dir = output_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []

    for view in sorted(views, key=lambda v: v["name"].lower()):
        view_id = view.get("id", "")
        view_name = view.get("name", "Unnamed View")
        element_ids = sorted(view.get("elements", []))
        element_names = [elements.get(elem_id, {"name": elem_id}).get("name", elem_id) for elem_id in element_ids]
        element_names_sorted = sorted(element_names, key=lambda name: name.lower())
        element_list = ", ".join(element_names_sorted) if element_names_sorted else "None"

        lines.append(f"## {view_name}")
        lines.append(f"- **ID:** {view_id}")
        lines.append(f"- **Elements ({len(element_names_sorted)}):** {element_list}")
        lines.append("")

    (views_dir / "index.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def render_markdown_document(
    model_name: str,
    elements: Dict[str, Dict[str, str]],
    relationships: List[Dict[str, str]],
    views: List[Dict[str, object]],
) -> str:
    rel_index = build_relationship_index(elements, relationships)

    lines: List[str] = [
        f"# {model_name}",
        "",
        f"- **Element count:** {len(elements)}",
        f"- **Relationship count:** {len(relationships)}",
        f"- **View count:** {len(views)}",
        "",
        "## Elements",
    ]

    for layer, _ in LAYER_FILES.items():
        layer_elements = [
            elem for elem in elements.values()
            if classify_layer(elem["type"]) == layer
        ]
        if not layer_elements:
            continue
        lines.append(f"### {layer.title()} Layer")
        for elem in sorted(layer_elements, key=lambda e: e["name"].lower()):
            elem_id = elem["id"]
            lines.append(f"#### {elem['name']}")
            lines.append(f"- **Type:** {elem['type']}")
            lines.append(f"- **ID:** {elem_id}")
            documentation = elem.get("documentation", "").strip()
            if documentation:
                lines.append(f"- **Documentation:** {documentation}")

            rel_lines: List[str] = []
            for direction, rel_type, other_id in rel_index.get(elem_id, []):
                other = elements.get(other_id)
                other_name = other.get("name") if other else (other_id or "Unknown")
                other_type = other.get("type") if other else "Unknown"
                if direction == "out":
                    rel_lines.append(f"  - ->{rel_type}-> {other_name} ({other_type})")
                else:
                    rel_lines.append(f"  - <-{rel_type}<- {other_name} ({other_type})")

            if rel_lines:
                rel_lines_sorted = sorted(rel_lines, key=lambda line: line.lower())
                lines.append("- **Relationships:**")
                lines.extend(rel_lines_sorted)
            lines.append("")

    lines.extend([
        "## Relationships",
        "| Source | Source Type | Relationship | Target | Target Type |",
        "|--------|-----------|--------------|--------|-------------|",
    ])

    def display_name(elem_id: str) -> str:
        if elem_id in elements:
            return elements[elem_id]["name"]
        return elem_id or "Unknown"

    def display_type(elem_id: str) -> str:
        if elem_id in elements:
            return elements[elem_id]["type"]
        return "Unknown"

    sorted_rels = sorted(
        relationships,
        key=lambda r: (
            display_name(r.get("source", "")).lower(),
            display_name(r.get("target", "")).lower(),
            r.get("type", ""),
        ),
    )

    for rel in sorted_rels:
        source = rel.get("source", "")
        target = rel.get("target", "")
        if source not in elements or target not in elements:
            continue
        lines.append(
            f"| {display_name(source)} | {display_type(source)} | {rel.get('type', 'Unknown')} | "
            f"{display_name(target)} | {display_type(target)} |"
        )

    lines.append("")
    lines.append("## Views")

    for view in sorted(views, key=lambda v: v["name"].lower()):
        view_id = view.get("id", "")
        view_name = view.get("name", "Unnamed View")
        element_ids = sorted(view.get("elements", []))
        element_names = [elements.get(elem_id, {"name": elem_id}).get("name", elem_id) for elem_id in element_ids]
        element_names_sorted = sorted(element_names, key=lambda name: name.lower())
        element_list = ", ".join(element_names_sorted) if element_names_sorted else "None"

        lines.append(f"### {view_name}")
        lines.append(f"- **ID:** {view_id}")
        lines.append(f"- **Elements ({len(element_names_sorted)}):** {element_list}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_markdown_file(xml_path: Path, output_path: Path) -> None:
    model_name, elements, relationships, views = parse_model(xml_path)
    content = render_markdown_document(model_name, elements, relationships, views)
    output_path.write_text(content, encoding="utf-8")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    parser = argparse.ArgumentParser(description="Convert ArchiMate XML to structured Markdown.")
    parser.add_argument("--input", required=True, help="Path to ArchiMate XML input")
    parser.add_argument("--output-dir", required=True, help="Directory to write Markdown files")
    args = parser.parse_args()

    xml_path = Path(args.input)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        model_name, elements, relationships, views = parse_model(xml_path)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        logger.error("Error: %s", exc)
        sys.exit(1)
    rel_index = build_relationship_index(elements, relationships)

    write_readme(output_dir, model_name, len(elements), len(relationships), len(views))
    write_elements_files(elements, rel_index, output_dir)
    write_relationships(relationships, elements, output_dir)
    write_views(views, elements, output_dir)


if __name__ == "__main__":
    main()

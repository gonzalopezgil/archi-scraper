import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import archiscraper_to_markdown as module


class TestMarkdownGeneration(unittest.TestCase):
    def test_markdown_generation_from_xml(self) -> None:
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <model xmlns="http://www.opengroup.org/xsd/archimate/3.0/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <name>Sample Model</name>
          <elements>
            <element identifier="id-abc123" xsi:type="ApplicationComponent">
              <name>App</name>
            </element>
            <element identifier="id-def456" xsi:type="ApplicationService">
              <name>Service</name>
            </element>
          </elements>
          <relationships>
            <relationship identifier="id-rel111" xsi:type="Assignment" source="id-abc123" target="id-def456" />
          </relationships>
          <views>
            <diagrams>
              <view identifier="id-view123" xsi:type="Diagram">
                <name>Main View</name>
                <node elementRef="id-abc123" />
              </view>
            </diagrams>
          </views>
        </model>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_path = Path(tmpdir) / "model.xml"
            output_dir = Path(tmpdir) / "md"
            xml_path.write_text(xml_content, encoding="utf-8")
            output_dir.mkdir(parents=True, exist_ok=True)

            model_name, elements, relationships, views = module.parse_model(xml_path)
            rel_index = module.build_relationship_index(elements, relationships)
            module.write_readme(output_dir, model_name, len(elements), len(relationships), len(views))
            module.write_elements_files(elements, rel_index, output_dir)
            module.write_relationships(relationships, elements, output_dir)
            module.write_views(views, elements, output_dir)

            readme = (output_dir / "README.md").read_text(encoding="utf-8")
            self.assertIn("Sample Model", readme)

            elements_file = output_dir / "elements" / "application.md"
            self.assertTrue(elements_file.exists())
            content = elements_file.read_text(encoding="utf-8")
            self.assertIn("### App", content)
            self.assertIn("### Service", content)

            relationships_md = (output_dir / "relationships.md").read_text(encoding="utf-8")
            self.assertIn("App", relationships_md)
            self.assertIn("Service", relationships_md)

            views_md = (output_dir / "views" / "index.md").read_text(encoding="utf-8")
            self.assertIn("Main View", views_md)


if __name__ == "__main__":
    unittest.main()

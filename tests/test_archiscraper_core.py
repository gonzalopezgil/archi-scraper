import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from bs4 import BeautifulSoup

from archiscraper_core import (
    ArchiMateXMLGenerator,
    ModelDataParser,
    ViewParser,
    clean_element_type,
    decode_url,
    download_view_images,
    extract_id_from_href,
    fetch_with_retry,
    fix_relationship_type,
    sanitize_filename,
)


class TestModelDataParser(unittest.TestCase):
    def test_html_parsing_extracts_elements(self) -> None:
        content = """
        dataElements.push({id:"id-abc123",name:decodeURL("Test%20App"),type:"ApplicationComponent",documentation:decodeURL("Doc%20Text")});
        dataElements.push({id:"id-def456",name:"Another",type:"BusinessActor",documentation:""});
        dataFolders.push({id:"id-folder1",type:"Folder",name:"Folder%201"});
        dataViews.push({id:"id-view123",name:"Main%20View",type:"DiagramModel"});
        """
        parser = ModelDataParser()
        parser._parse_content(content)

        self.assertIn("id-abc123", parser.elements)
        self.assertEqual(parser.elements["id-abc123"]["name"], "Test App")
        self.assertEqual(parser.elements["id-abc123"]["documentation"], "Doc Text")
        self.assertIn("id-folder1", parser.folders)
        self.assertIn("id-view123", parser.views)


class TestViewParser(unittest.TestCase):
    def _sample_view_html(self) -> str:
        return """
        <html>
          <head><title>View One</title></head>
          <body>
            <div id="elements">
              <table>
                <tr>
                  <td><a href="id-abc123.html">App</a></td>
                  <td><span class="i18n-elementtype-ApplicationComponent">App</span></td>
                </tr>
              </table>
            </div>
            <div id="relationships">
              <table>
                <tr>
                  <td><a href="id-abcd111.html">RelName</a></td>
                  <td class="i18n-relationshiptype-AssignmentRelationship">Assignment</td>
                  <td><a href="id-abc123.html">Source</a></td>
                  <td><a href="id-def456.html">Target</a></td>
                </tr>
              </table>
            </div>
            <map name="id-view123map">
              <area shape="rect" coords="10,20,110,220" href="id-abc123.html" />
            </map>
          </body>
        </html>
        """

    def test_relationship_extraction(self) -> None:
        html = self._sample_view_html()
        relationships = ViewParser.extract_relationships(
            BeautifulSoup(html, "html.parser")
        )
        self.assertEqual(len(relationships), 1)
        self.assertEqual(relationships[0]["id"], "id-abcd111")
        self.assertEqual(relationships[0]["type"], "Assignment")
        self.assertEqual(relationships[0]["source"], "id-abc123")
        self.assertEqual(relationships[0]["target"], "id-def456")

    def test_view_parsing(self) -> None:
        html = self._sample_view_html()
        view_data = ViewParser.parse(html)
        self.assertIsNotNone(view_data)
        assert view_data is not None
        self.assertEqual(view_data["view_name"], "View One")
        self.assertEqual(view_data["view_id"], "id-view123")
        self.assertIn("id-abc123", view_data["elements"])
        self.assertEqual(view_data["elements"]["id-abc123"]["type"], "ApplicationComponent")
        coords = view_data["coordinates"]["id-abc123"]
        self.assertEqual(coords["w"], 100)
        self.assertEqual(coords["h"], 200)

    def test_extract_type_from_cell_variants(self) -> None:
        html = """
        <table>
          <tr>
            <td class="i18n-elementtype-ApplicationComponent">App</td>
            <td><a class="i18n-elementtype-BusinessActor">Actor</a></td>
            <td><span class="i18n-relationshiptype-AssignmentRelationship">Rel</span></td>
          </tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        cells = soup.find_all("td")

        self.assertEqual(
            ViewParser._extract_type_from_cell(cells[0], "i18n-elementtype-"),
            "ApplicationComponent",
        )
        self.assertEqual(
            ViewParser._extract_type_from_cell(cells[1], "i18n-elementtype-"),
            "BusinessActor",
        )
        self.assertEqual(
            ViewParser._extract_type_from_cell(cells[2], "i18n-relationshiptype-"),
            "AssignmentRelationship",
        )


class TestDownloadViewImages(unittest.TestCase):
    def test_download_view_images_uses_session(self) -> None:
        views = [{"view_id": "id-view123", "view_name": "View 1"}]

        class DummyResponse:
            status_code = 200
            content = b"image-bytes"

            def raise_for_status(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            session = Mock()
            session.get.return_value = DummyResponse()
            with patch("archiscraper_core.requests.get") as requests_get:
                downloaded, skipped = download_view_images(
                    base_url="http://example.com/report/",
                    guid="id-guid",
                    views=views,
                    output_dir=tmpdir,
                    user_agent="UA",
                    timeout=5,
                    session=session,
                )
                requests_get.assert_not_called()

            session.get.assert_called_once()
            self.assertEqual(downloaded, 1)
            self.assertEqual(skipped, 0)
            self.assertTrue((Path(tmpdir) / "View 1.png").exists())


class TestDownloadViewImagesAdditional(unittest.TestCase):
    def test_download_skips_404(self) -> None:
        views = [{"view_id": "id-view404", "view_name": "Missing View"}]

        class DummyResponse:
            status_code = 404

            def raise_for_status(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            session = Mock()
            session.get.return_value = DummyResponse()
            downloaded, skipped = download_view_images(
                base_url="http://example.com/report/",
                guid="id-guid",
                views=views,
                output_dir=tmpdir,
                user_agent="UA",
                timeout=5,
                session=session,
            )

        self.assertEqual(downloaded, 0)
        self.assertEqual(skipped, 1)

    def test_download_handles_request_exception(self) -> None:
        views = [{"view_id": "id-view500", "view_name": "Error View"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            session = Mock()
            session.get.side_effect = requests.ConnectionError("boom")
            downloaded, skipped = download_view_images(
                base_url="http://example.com/report/",
                guid="id-guid",
                views=views,
                output_dir=tmpdir,
                user_agent="UA",
                timeout=5,
                session=session,
            )

        self.assertEqual(downloaded, 0)
        self.assertEqual(skipped, 1)


class TestCleanElementType(unittest.TestCase):
    def test_skip_types(self) -> None:
        self.assertIsNone(clean_element_type("DiagramModelNote"))
        self.assertIsNone(clean_element_type("DiagramModelReference"))
        self.assertIsNone(clean_element_type("SketchModelSticky"))
        self.assertIsNone(clean_element_type("Unknown"))

    def test_mapping_types(self) -> None:
        self.assertEqual(clean_element_type("DiagramModelGroup"), "Grouping")
        self.assertEqual(clean_element_type("Junction"), "AndJunction")
        self.assertEqual(clean_element_type("OrJunction"), "OrJunction")

    def test_passthrough(self) -> None:
        self.assertEqual(clean_element_type("ApplicationComponent"), "ApplicationComponent")


class TestSanitizeFilename(unittest.TestCase):
    def test_removes_illegal_chars(self) -> None:
        self.assertEqual(sanitize_filename("my:file*name?.xml"), "my_file_name_.xml")

    def test_empty_string(self) -> None:
        self.assertEqual(sanitize_filename(""), "unnamed")

    def test_only_dots(self) -> None:
        self.assertEqual(sanitize_filename("..."), "unnamed")

    def test_strips_spaces(self) -> None:
        self.assertEqual(sanitize_filename("  hello  "), "hello")


class TestFixRelationshipType(unittest.TestCase):
    def test_strips_suffix(self) -> None:
        self.assertEqual(fix_relationship_type("AssignmentRelationship"), "Assignment")

    def test_no_suffix(self) -> None:
        self.assertEqual(fix_relationship_type("Aggregation"), "Aggregation")


class TestDecodeUrl(unittest.TestCase):
    def test_decodes(self) -> None:
        self.assertEqual(decode_url("Hello%20World"), "Hello World")

    def test_none(self) -> None:
        self.assertIsNone(decode_url(None))

    def test_empty(self) -> None:
        self.assertIn(decode_url(""), (None, ""))


class TestExtractIdFromHref(unittest.TestCase):
    def test_valid(self) -> None:
        self.assertEqual(extract_id_from_href("id-abc123def4.html"), "id-abc123def4")

    def test_no_match(self) -> None:
        self.assertIsNone(extract_id_from_href("random.html"))

    def test_none(self) -> None:
        self.assertIsNone(extract_id_from_href(None))


class TestFetchWithRetry(unittest.TestCase):
    def test_retries_on_5xx_then_succeeds(self) -> None:
        class DummyResponse:
            def __init__(self, status_code: int) -> None:
                self.status_code = status_code
                self.headers = {}

        session = Mock()
        session.get.side_effect = [
            DummyResponse(500),
            DummyResponse(500),
            DummyResponse(200),
        ]

        with patch("archiscraper_core.time.sleep") as sleep_mock:
            response = fetch_with_retry(session, "http://example.com", {}, 5)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.get.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_no_retry_on_404(self) -> None:
        class DummyResponse:
            status_code = 404
            headers = {}

        session = Mock()
        session.get.return_value = DummyResponse()

        response = fetch_with_retry(session, "http://example.com", {}, 5)

        self.assertEqual(response.status_code, 404)
        session.get.assert_called_once()
class TestXMLGeneration(unittest.TestCase):
    def test_xml_generation_contains_elements_relationships_views(self) -> None:
        model_data = ModelDataParser()
        model_data.elements = {
            "id-abc123": {"id": "id-abc123", "name": "App", "documentation": "Doc"},
            "id-def456": {"id": "id-def456", "name": "Service", "documentation": ""},
        }

        view_data = {
            "view_name": "Main View",
            "view_id": "id-view123",
            "elements": {
                "id-abc123": {"id": "id-abc123", "name": "App", "type": "ApplicationComponent"},
                "id-def456": {"id": "id-def456", "name": "Service", "type": "ApplicationService"},
            },
            "relationships": [
                {
                    "id": "id-rel111",
                    "type": "Assignment",
                    "source": "id-abc123",
                    "target": "id-def456",
                    "name": "RelName",
                }
            ],
            "coordinates": {
                "id-abc123": {"x": 10, "y": 20, "w": 100, "h": 200, "x2": 110, "y2": 220},
                "id-def456": {"x": 30, "y": 40, "w": 80, "h": 120, "x2": 110, "y2": 160},
            },
        }

        generator = ArchiMateXMLGenerator(model_data)
        root = generator.create_single_view_xml(view_data, include_connections=True)

        elements = [elem for elem in root.iter() if elem.tag.endswith("element")]
        relationships = [elem for elem in root.iter() if elem.tag.endswith("relationship")]
        views = [elem for elem in root.iter() if elem.tag.endswith("view")]
        connections = [elem for elem in root.iter() if elem.tag.endswith("connection")]

        self.assertGreaterEqual(len(elements), 2)
        self.assertEqual(len(relationships), 1)
        self.assertEqual(len(views), 1)
        self.assertGreaterEqual(len(connections), 1)


class TestXMLValidation(unittest.TestCase):
    def test_valid_xml_returns_empty(self) -> None:
        root = ET.Element("model")
        elements = ET.SubElement(root, "elements")
        ET.SubElement(elements, "element", {"identifier": "id-1"})
        ET.SubElement(elements, "element", {"identifier": "id-2"})
        relationships = ET.SubElement(root, "relationships")
        ET.SubElement(relationships, "relationship", {"identifier": "rel-1", "source": "id-1", "target": "id-2"})
        views = ET.SubElement(root, "views")
        diagrams = ET.SubElement(views, "diagrams")
        view = ET.SubElement(diagrams, "view", {"identifier": "view-1"})
        ET.SubElement(view, "node", {"elementRef": "id-1"})
        ET.SubElement(view, "connection", {"relationshipRef": "rel-1"})

        warnings = ArchiMateXMLGenerator.validate_xml(root)

        self.assertEqual(warnings, [])

    def test_dangling_relationship_reference_warns(self) -> None:
        root = ET.Element("model")
        elements = ET.SubElement(root, "elements")
        ET.SubElement(elements, "element", {"identifier": "id-1"})
        relationships = ET.SubElement(root, "relationships")
        ET.SubElement(relationships, "relationship", {"identifier": "rel-1", "source": "missing", "target": "id-1"})

        warnings = ArchiMateXMLGenerator.validate_xml(root)

        self.assertTrue(any("Relationship source missing element" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()

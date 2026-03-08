import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from PyQt6.QtWidgets import QApplication, QWidget, QFrame, QGraphicsDropShadowEffect, QCheckBox
    HAS_PYQT6 = True
except ImportError:
    HAS_PYQT6 = False

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

if HAS_PYQT6:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import ArchiScraperApp as module

    class DummyProfile:
        def setUrlRequestInterceptor(self, interceptor):
            self.interceptor = interceptor

    class DummyPage:
        def __init__(self) -> None:
            self._profile = DummyProfile()

        def profile(self):
            return self._profile

        def runJavaScript(self, *args, **kwargs):
            return None

    class DummyWebEngineView(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self._page = DummyPage()
            self._url = None

        def setUrl(self, url):
            self._url = url

        def page(self):
            return self._page


@unittest.skipUnless(HAS_PYQT6, "PyQt6 not installed")
class TestWizardGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_wizard_structure_and_validate_button_exist(self) -> None:
        with patch.object(module, "QWebEngineView", DummyWebEngineView):
            window = module.ArchiScraperApp()
            self.assertTrue(hasattr(window, "wizard_stack"))
            self.assertEqual(window.wizard_stack.count(), 4)
            self.assertEqual(window.wizard_stack.currentIndex(), 0)
            self.assertTrue(hasattr(window, "validate_xml_button"))
            self.assertEqual(window.go_button.text(), "Load")
            self.assertEqual(window.load_local_button.text(), "Open Local Files...")
            self.assertEqual(window.title_label.text(), "ArchiScraper")
            self.assertEqual(window.settings_button.text(), "Settings")
            self.assertEqual(window.version_label.text(), "1.4.0")
            self.assertEqual(window.size().width(), 800)
            self.assertEqual(window.size().height(), 600)
            self.assertFalse(window.isMaximized())

            source_cards = [
                frame for frame in window.page_source.findChildren(QFrame)
                if frame.property("card") is True
            ]
            self.assertEqual(len(source_cards), 1)
            shadow = source_cards[0].graphicsEffect()
            self.assertIsInstance(shadow, QGraphicsDropShadowEffect)
            self.assertEqual(shadow.offset().x(), 0.0)
            self.assertEqual(shadow.offset().y(), 4.0)
            self.assertEqual(shadow.blurRadius(), 24.0)
            window.close()

    def test_review_step_inline_preview_filter_and_selection_state(self) -> None:
        with patch.object(module, "QWebEngineView", DummyWebEngineView):
            window = module.ArchiScraperApp()
            window.model_data.elements = {"e1": {}, "e2": {}}
            window.model_data.relationships = {"r1": {}}
            window.available_views = [
                {
                    "view_id": "view-1",
                    "view_name": "Application Overview",
                    "elements": {"e1": {}},
                    "preview_url": "https://example.test/views/view-1.html",
                },
                {
                    "view_id": "view-2",
                    "view_name": "Technology Landscape",
                    "elements": {"e1": {}, "e2": {}},
                    "preview_url": "https://example.test/views/view-2.html",
                },
            ]

            window._enter_review_step()

            self.assertEqual(window.status_bar.currentMessage(), "Step 2 of 4 — Review")
            self.assertEqual(window.review_header_label.text(), "Model loaded successfully")
            self.assertIn("#e6f4ea", window.review_header_label.styleSheet())
            self.assertEqual(window.review_filter_input.placeholderText(), "Filter views...")
            self.assertTrue(window.review_filter_input.isClearButtonEnabled())
            self.assertFalse(hasattr(window, "preview_button"))
            self.assertEqual(window.review_selection_label.text(), "2 of 2 views selected")
            self.assertEqual(window.review_splitter.count(), 2)
            splitter_sizes = window.review_splitter.sizes()
            self.assertEqual(len(splitter_sizes), 2)
            self.assertGreater(splitter_sizes[1], splitter_sizes[0])

            first_item = window.view_list.item(0)
            first_widget = window.view_list.itemWidget(first_item)
            self.assertIsInstance(first_widget.checkbox, QCheckBox)
            self.assertEqual(first_widget.checkbox.text(), "")
            self.assertEqual(first_widget.name_label.text(), "Application Overview")
            self.assertEqual(first_widget.count_label.text(), "1 elements")
            self.assertEqual(first_widget.toolTip(), "Application Overview - 1 elements")
            self.assertEqual(first_widget.name_label.toolTip(), "Application Overview - 1 elements")

            self.assertEqual(window.preview_stack.currentWidget(), window.review_preview)
            self.assertEqual(window.review_preview._url.toString(), "https://example.test/views/view-1.html")

            dot_styles = [dot.styleSheet() for dot in window.review_stepper._dots]
            self.assertEqual(window.review_stepper._dots[0].text(), "✓")
            self.assertIn("background: #e8601c", dot_styles[0])
            self.assertEqual(window.review_stepper._dots[1].text(), "2")
            self.assertIn("border: 2px solid #e8601c", dot_styles[1])
            self.assertEqual(window.review_stepper._dots[2].text(), "3")
            self.assertIn("background: #ededed", dot_styles[2])

            window.review_filter_input.setText("tech")
            self.assertTrue(window.view_list.item(0).isHidden())
            self.assertFalse(window.view_list.item(1).isHidden())
            self.assertEqual(window.view_list.currentItem(), window.view_list.item(1))
            self.assertEqual(window.review_preview._url.toString(), "https://example.test/views/view-2.html")

            second_widget = window.view_list.itemWidget(window.view_list.item(1))
            second_widget.checkbox.setChecked(False)
            self.assertEqual(window.review_selection_label.text(), "1 of 2 views selected")
            self.assertEqual(window.select_all_button.text(), "Select All")

            window.select_all_button.click()
            self.assertEqual(window.review_selection_label.text(), "2 of 2 views selected")
            self.assertEqual(window.select_all_button.text(), "Deselect All")

            window.view_list.setCurrentItem(None)
            self.assertEqual(window.preview_stack.currentWidget(), window.preview_placeholder)
            window.close()

    def test_version_lookup_and_done_step_styling(self) -> None:
        with patch.object(module, "QWebEngineView", DummyWebEngineView):
            with patch.object(module.metadata, "version", return_value="2.3.4"):
                window = module.ArchiScraperApp()

            self.assertEqual(window.version_label.text(), "2.3.4")
            self.assertEqual(window.export_button.text(), "Export")
            self.assertTrue(window.output_dir_button.text().startswith("Browse"))

            window.export_output_dir = str(ROOT)
            window.last_xml_path = str(ROOT / "dummy.xml")
            window._enter_done_step(True, "ok", "file.xml")
            self.assertEqual(window.done_header_label.text(), "Export complete")
            self.assertIn("#e6f4ea", window.done_header_label.styleSheet())
            self.assertTrue(window.open_folder_button.property("primary"))
            self.assertTrue(window.validate_xml_button.property("secondary"))
            self.assertTrue(window.new_export_button.property("secondary"))

            window._enter_done_step(False, "bad", "retry")
            self.assertEqual(window.done_header_label.text(), "Export failed")
            self.assertIn("#fce8e6", window.done_header_label.styleSheet())
            self.assertFalse(window.retry_export_button.isHidden())
            window.close()


if __name__ == "__main__":
    unittest.main()

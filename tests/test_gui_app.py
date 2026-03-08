import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from PyQt6.QtWidgets import QApplication, QWidget
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

        def setUrl(self, url):
            self._url = url

        def page(self):
            return self._page


@unittest.skipUnless(HAS_PYQT6, "PyQt6 not installed")
class TestGuiButtons(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_validate_xml_button_exists(self) -> None:
        with patch.object(module, "QWebEngineView", DummyWebEngineView):
            window = module.ArchiScraperApp()
            self.assertTrue(hasattr(window, "validate_xml_button"))
            window.close()


if __name__ == "__main__":
    unittest.main()

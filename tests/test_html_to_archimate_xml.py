import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import html_to_archimate_xml as module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model")
    parser.add_argument("--views", nargs="+")
    parser.add_argument("--url")
    parser.add_argument("--download-all", action="store_true")
    parser.add_argument("--list-views", action="store_true")
    parser.add_argument("--select-views", nargs="+")
    parser.add_argument("--user-agent")
    parser.add_argument("--output")
    parser.add_argument("--connections", action="store_true")
    parser.add_argument("--images", action="store_true")
    parser.add_argument("--images-dir")
    return parser


class TestCliValidation(unittest.TestCase):
    def test_validate_args_rejects_mixed_modes(self) -> None:
        parser = build_parser()
        args = argparse.Namespace(
            model="model.html",
            views=["view.html"],
            url="https://example.com/index.html",
            list_views=False,
            download_all=False,
            select_views=None,
            user_agent=None,
            output=None,
            connections=False,
            images=False,
            images_dir=None,
        )
        with self.assertRaises(SystemExit):
            module.validate_args(parser, args)

    def test_validate_args_requires_local_pair(self) -> None:
        parser = build_parser()
        args = argparse.Namespace(
            model="model.html",
            views=None,
            url=None,
            list_views=False,
            download_all=False,
            select_views=None,
            user_agent=None,
            output=None,
            connections=False,
            images=False,
            images_dir=None,
        )
        with self.assertRaises(SystemExit):
            module.validate_args(parser, args)

    def test_validate_args_requires_url_mode_flag(self) -> None:
        parser = build_parser()
        args = argparse.Namespace(
            model=None,
            views=None,
            url="https://example.com/index.html",
            list_views=False,
            download_all=False,
            select_views=None,
            user_agent=None,
            output=None,
            connections=False,
            images=False,
            images_dir=None,
        )
        with self.assertRaises(SystemExit):
            module.validate_args(parser, args)

    def test_validate_args_accepts_url_list_views(self) -> None:
        parser = build_parser()
        args = argparse.Namespace(
            model=None,
            views=None,
            url="https://example.com/index.html",
            list_views=True,
            download_all=False,
            select_views=None,
            user_agent=None,
            output=None,
            connections=False,
            images=False,
            images_dir=None,
        )
        module.validate_args(parser, args)


class TestUrlValidation(unittest.TestCase):
    def test_ensure_url_scheme_adds_http(self) -> None:
        self.assertEqual(module.ensure_url_scheme("example.com"), "http://example.com")

    def test_ensure_url_scheme_keeps_https(self) -> None:
        self.assertEqual(
            module.ensure_url_scheme("https://example.com/index.html"),
            "https://example.com/index.html",
        )


class TestBuildBaseUrl(unittest.TestCase):
    def test_with_html(self) -> None:
        self.assertEqual(
            module.build_base_url("https://example.com/report/index.html"),
            "https://example.com/report/",
        )

    def test_without_html(self) -> None:
        self.assertEqual(
            module.build_base_url("https://example.com/report"),
            "https://example.com/report/",
        )

    def test_trailing_slash(self) -> None:
        self.assertEqual(
            module.build_base_url("https://example.com/report/"),
            "https://example.com/report/",
        )


class TestDiscoverModelUrl(unittest.TestCase):
    def test_raises_on_missing_guid(self) -> None:
        class DummyResponse:
            text = "<html><body>No GUID here</body></html>"

            def raise_for_status(self) -> None:
                return None

        session = unittest.mock.Mock()
        session.get.return_value = DummyResponse()

        with self.assertRaises(ValueError):
            module.discover_model_url(
                "https://example.com/report/index.html",
                headers={},
                timeout=5,
                session=session,
            )

    def test_discovers_guid(self) -> None:
        class DummyResponse:
            text = '<a href="id-abc123/elements/model.html">model</a>'

            def raise_for_status(self) -> None:
                return None

        session = unittest.mock.Mock()
        session.get.return_value = DummyResponse()

        base_url, guid, model_url = module.discover_model_url(
            "https://example.com/report/index.html",
            headers={},
            timeout=5,
            session=session,
        )

        self.assertEqual(base_url, "https://example.com/report/")
        self.assertEqual(guid, "id-abc123")
        self.assertEqual(
            model_url,
            "https://example.com/report/id-abc123/elements/model.html",
        )


class TestCollectViewDataFromFiles(unittest.TestCase):
    def test_skips_missing_file(self) -> None:
        missing = Path("missing-view.html")
        self.assertEqual(module.collect_view_data_from_files([missing]), [])


if __name__ == "__main__":
    unittest.main()

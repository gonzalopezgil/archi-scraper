"""
Archi HTML View to ArchiMate Model Exchange Format XML Converter.

Supports local HTML files (--model + --views) and remote HTML reports via --url.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

import archiscraper_to_markdown
from archiscraper_core import (
    ArchiMateXMLGenerator,
    ModelDataParser,
    ViewParser,
    download_view_images,
    fetch_with_retry,
    get_random_user_agent,
)

DEFAULT_USER_AGENT = get_random_user_agent()
logger = logging.getLogger(__name__)


def ensure_url_scheme(url: str) -> str:
    """Ensure the URL has a scheme (default http://)."""
    if not url.startswith(('http://', 'https://')):
        return f"http://{url}"
    return url


def build_base_url(url: str) -> str:
    """Compute the base URL by removing the filename and ensuring a trailing slash."""
    parsed = urlparse(url)
    path = parsed.path

    if path.endswith('.html') or path.endswith('.htm'):
        path = path.rsplit('/', 1)[0] + '/'
    elif not path.endswith('/'):
        path = path + '/'

    return f"{parsed.scheme}://{parsed.netloc}{path}"


def discover_model_url(
    index_url: str,
    headers: Dict[str, str],
    timeout: int = 30,
    session: Optional[requests.Session] = None,
) -> Tuple[str, str, str]:
    """Download index.html and discover the model.html URL using the GUID pattern."""
    response = fetch_with_retry(session, index_url, headers, timeout)
    response.raise_for_status()

    match = re.search(r'(id-[A-Fa-f0-9-]+)/elements/model\.html', response.text)
    if not match:
        raise ValueError("Could not find model.html GUID path in index.html")

    guid = match.group(1)
    base_url = build_base_url(index_url)
    model_url = f"{base_url}{guid}/elements/model.html"

    return base_url, guid, model_url


def fetch_html(
    url: str,
    headers: Dict[str, str],
    timeout: int = 30,
    session: Optional[requests.Session] = None,
) -> str:
    """Fetch HTML content from a URL."""
    response = fetch_with_retry(session, url, headers, timeout)
    response.raise_for_status()
    return response.text


def list_views(model_data: ModelDataParser) -> None:
    """Print all views available in the model."""
    if not model_data.views:
        logger.warning("No views found in model.html.")
        return

    logger.info("Found %d views:", len(model_data.views))
    for view_id, view in model_data.views.items():
        name = view.get('name', 'Unnamed View')
        logger.info("  %s  %s", view_id, name)


def collect_view_data_from_urls(
    base_url: str,
    guid: str,
    view_ids: List[str],
    view_name_map: Dict[str, str],
    headers: Dict[str, str],
    timeout: int = 30,
    session: Optional[requests.Session] = None,
) -> List[Dict[str, object]]:
    """Download and parse multiple view HTML files from a remote report."""
    views_data: List[Dict[str, object]] = []
    total = len(view_ids)

    for index, view_id in enumerate(view_ids, start=1):
        view_name = view_name_map.get(view_id, view_id)
        logger.info("Downloading view %d/%d: %s...", index, total, view_name)

        view_url = f"{base_url}{guid}/views/{view_id}.html"
        try:
            response = fetch_with_retry(session, view_url, headers, timeout)
            response.raise_for_status()
            html_content = response.text
        except requests.RequestException as exc:
            logger.warning("  Warning: Failed to download %s (%s). Skipping.", view_id, exc)
            continue

        view_data = ViewParser.parse(html_content)
        if not view_data:
            logger.warning("  Warning: No coordinates found for %s. Skipping.", view_id)
            continue

        views_data.append(view_data)

    return views_data


def collect_view_data_from_files(view_files: List[Path]) -> List[Dict[str, object]]:
    """Load and parse local view HTML files."""
    views_data: List[Dict[str, object]] = []

    for html_path in view_files:
        if not html_path.exists():
            logger.warning("Skipping (not found): %s", html_path)
            continue

        logger.info("\nProcessing: %s", html_path)
        with open(html_path, 'r', encoding='utf-8') as handle:
            html_content = handle.read()

        view_data = ViewParser.parse(html_content)
        if not view_data:
            logger.warning("  Warning: No coordinates found. Skipping.")
            continue

        logger.info("  View: %s", view_data['view_name'])
        logger.info("  View ID: %s", view_data['view_id'])
        logger.info("  Elements: %d", len(view_data['elements']))
        logger.info("  Relationships: %d", len(view_data['relationships']))
        logger.info("  Coordinates: %d", len(view_data['coordinates']))

        views_data.append(view_data)

    return views_data


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Validate CLI args and enforce mode exclusivity."""
    url_mode = args.url is not None
    local_mode = args.model is not None or args.views is not None

    if url_mode and local_mode:
        parser.error("Use either --url or --model + --views, not both.")

    if not url_mode and not (args.model and args.views):
        parser.error("Local mode requires --model and --views.")

    if url_mode:
        mode_flags = [args.list_views, args.download_all, args.select_views]
        if sum(bool(flag) for flag in mode_flags) != 1:
            parser.error("With --url, use exactly one of --list-views, --download-all, or --select-views.")

    if local_mode and (args.list_views or args.download_all or args.select_views):
        parser.error("--list-views, --download-all, and --select-views are only valid with --url.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Archi HTML View to ArchiMate Model Exchange Format XML Converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  python html_to_archimate_xml.py --model model.html --views view1.html view2.html --output my_architecture.xml
  python html_to_archimate_xml.py --url https://example.com/report/index.html --download-all --output master.xml
        """,
    )

    parser.add_argument(
        "--model",
        "-m",
        type=str,
        help="Path to the main model.html file (local mode)",
    )
    parser.add_argument(
        "--views",
        "-v",
        nargs="+",
        type=str,
        help="Paths to the specific view HTML files to process (local mode)",
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Remote Archi HTML report URL (e.g. https://example.com/report/index.html)",
    )
    parser.add_argument(
        "--download-all",
        action="store_true",
        help="Download and process all views from the remote model",
    )
    parser.add_argument(
        "--list-views",
        action="store_true",
        help="List all views in the remote model without downloading",
    )
    parser.add_argument(
        "--select-views",
        nargs="+",
        help="Download only specific view IDs from the remote model",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        type=str,
        help="HTTP User-Agent header value",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="master_model.xml",
        type=str,
        help="Output XML filename (default: master_model.xml)",
    )
    parser.add_argument(
        "--connections",
        action="store_true",
        help="Include connection elements inside views (default: off)",
    )
    parser.add_argument(
        "--images",
        action="store_true",
        help="Download PNG images for each view (URL mode only)",
    )
    parser.add_argument(
        "--images-dir",
        default="images/",
        type=str,
        help="Directory for downloaded images (default: images/ relative to output)",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Generate a Markdown file alongside the XML output",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the generated XML and print warnings",
    )
    parser.add_argument(
        "--timeout",
        default=30,
        type=int,
        help="HTTP timeout in seconds (default: 30)",
    )

    args = parser.parse_args()
    validate_args(parser, args)
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    output_path = Path(args.output)
    model_data = ModelDataParser()
    session = requests.Session()

    if args.url:
        url = ensure_url_scheme(args.url.strip())
        headers = {"User-Agent": args.user_agent}

        print("=" * 60)
        print("Archi HTML Report (Remote) to Master Model Converter")
        print("=" * 60)
        print(f"  URL: {url}")

        try:
            base_url, guid, model_url = discover_model_url(
                url,
                headers=headers,
                timeout=args.timeout,
                session=session,
            )
        except requests.RequestException as exc:
            logger.error("ERROR: Failed to fetch index.html (%s)", exc)
            sys.exit(1)
        except ValueError as exc:
            logger.error("ERROR: %s", exc)
            sys.exit(1)

        print(f"  Base URL: {base_url}")
        print(f"  GUID: {guid}")
        print(f"  Model URL: {model_url}")

        if not model_data.load_from_url(model_url, headers=headers, timeout=args.timeout, session=session):
            logger.warning("WARNING: Failed to load model.html; documentation and folders may be missing.")

        if args.list_views:
            list_views(model_data)
            return

        if not model_data.views:
            logger.error("ERROR: No views found in model.html. Exiting.")
            sys.exit(1)

        if args.download_all:
            view_ids = list(model_data.views.keys())
        else:
            view_ids = args.select_views or []

        missing_ids = [view_id for view_id in view_ids if view_id not in model_data.views]
        if missing_ids:
            logger.warning(
                "WARNING: %d view IDs not found in model.html: %s",
                len(missing_ids),
                missing_ids,
            )

        view_ids = [view_id for view_id in view_ids if view_id in model_data.views]
        if not view_ids:
            logger.error("ERROR: No valid view IDs selected. Exiting.")
            sys.exit(1)

        view_name_map = {vid: data.get('name', vid) for vid, data in model_data.views.items()}
        views_data = collect_view_data_from_urls(
            base_url,
            guid,
            view_ids,
            view_name_map,
            headers,
            timeout=args.timeout,
            session=session,
        )
    else:
        model_path = Path(args.model)
        view_files = [Path(v) for v in args.views]

        print("=" * 60)
        print("Archi HTML Views (Local) to Master Model Converter")
        print("=" * 60)
        print(f"  Model: {model_path}")
        print(f"  Views: {[str(v) for v in view_files]}")
        print(f"  Output: {output_path}")

        if not model_data.load_from_file(str(model_path)):
            logger.warning("WARNING: Failed to load model.html; documentation and folders may be missing.")

        if args.images:
            logger.warning("WARNING: --images is only supported with --url. Skipping image download.")

        views_data = collect_view_data_from_files(view_files)

    logger.info("\n--- Summary ---")
    logger.info("Total views: %d", len(views_data))

    if not views_data:
        logger.error("\nERROR: No valid views found. Exiting.")
        return

    if args.url and args.images:
        images_dir = Path(args.images_dir)
        if not images_dir.is_absolute():
            images_dir = output_path.parent / images_dir
        downloaded, skipped = download_view_images(
            base_url=base_url,
            guid=guid,
            views=views_data,
            output_dir=str(images_dir),
            user_agent=args.user_agent,
            timeout=args.timeout,
            session=session,
        )
        logger.info("Images downloaded: %d (skipped: %d)", downloaded, skipped)

    generator = ArchiMateXMLGenerator(model_data)
    xml_root = generator.create_merged_xml(views_data, include_connections=args.connections)
    ArchiMateXMLGenerator.save_xml(xml_root, str(output_path))

    if args.markdown:
        markdown_path = output_path.with_suffix(".md")
        archiscraper_to_markdown.write_markdown_file(output_path, markdown_path)
        logger.info("  Saved: %s", markdown_path)

    if args.validate:
        warnings = generator.validate_xml(xml_root)
        if warnings:
            print("\nValidation warnings:")
            for warning in warnings:
                print(f"- {warning}")
        else:
            print("\nValidation passed: no warnings.")

    print("\n" + "=" * 60)
    print(f"SUCCESS: Created {output_path}")
    print("=" * 60)
    print(f"  Views: {len(views_data)}")
    print("\nImport into Archi: File → Import → Model from Open Exchange File")


if __name__ == "__main__":
    main()

# ArchiScraper v1.5.0 — Pre-Release Code Audit

**Date:** 2026-03-09  
**Auditor:** Thoth (automated)  
**Baseline:** 46 tests passing, 4 source modules, 4 test modules  
**Files reviewed:**

| File | Lines | Role |
|------|-------|------|
| `scripts/ArchiScraperApp.py` | 1665 | GUI (PyQt6) |
| `scripts/archiscraper_core.py` | 1181 | Shared core (parser + XML generator) |
| `scripts/html_to_archimate_xml.py` | 283 | CLI entry point |
| `scripts/archiscraper_to_markdown.py` | 286 | XML → Markdown converter |
| `tests/test_archiscraper_core.py` | 274 | Core tests (28 tests) |
| `tests/test_gui_app.py` | 166 | GUI tests (3 tests) |
| `tests/test_html_to_archimate_xml.py` | 126 | CLI tests (11 tests) |
| `tests/test_archiscraper_to_markdown.py` | 56 | Markdown tests (1 test) |

---

## 1. CLI ↔ GUI Integration Audit

### 1.1 Duplicated Logic

The README claims "Shared core: GUI and CLI use the same parser/generator (no code duplication)." This is **mostly true** for XML generation and parsing, but there are **three significant areas** of duplicated logic:

#### A. URL Normalization

| GUI | CLI |
|-----|-----|
| `ArchiScraperApp._normalize_report_url()` (line 776) | `html_to_archimate_xml.ensure_url_scheme()` + `build_base_url()` (lines 25–38) |

Both do the same: ensure `http://` scheme, strip filename from path, add trailing `/`, store as `self.base_url`.

```python
# GUI (ArchiScraperApp.py:776-785)
def _normalize_report_url(self, url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    parsed = urlparse(url)
    path = parsed.path
    if path.endswith(".html") or path.endswith(".htm"):
        path = path.rsplit("/", 1)[0] + "/"
    elif not path.endswith("/"):
        path = path + "/"
    self.base_url = f"{parsed.scheme}://{parsed.netloc}{path}"
    return url

# CLI (html_to_archimate_xml.py:25-38)
def ensure_url_scheme(url: str) -> str:
    if not url.startswith(('http://', 'https://')):
        return f"http://{url}"
    return url

def build_base_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    if path.endswith('.html') or path.endswith('.htm'):
        path = path.rsplit('/', 1)[0] + '/'
    elif not path.endswith('/'):
        path = path + '/'
    return f"{parsed.scheme}://{parsed.netloc}{path}"
```

**Recommendation:** Move `ensure_url_scheme()` and `build_base_url()` to `archiscraper_core.py`. Have both GUI and CLI import them.

#### B. Remote View Collection

| GUI | CLI |
|-----|-----|
| `ArchiScraperApp._load_remote_views()` (line 818) | `html_to_archimate_xml.collect_view_data_from_urls()` (lines 81–117) |

Both iterate view IDs, construct URL `{base}/views/{id}.html`, fetch HTML, call `ViewParser.parse()`, collect results. The GUI adds `preview_url` and `preview_html` keys but the core loop is identical.

```python
# GUI loop (ArchiScraperApp.py:831-858)
for index, view_id in enumerate(view_ids, 1):
    view_url = f"{views_base_url}{view_id}.html"
    try:
        response = self.session.get(view_url, ...)
        response.raise_for_status()
        parsed = ViewParser.parse(response.text)
        ...
    except Exception:
        pass

# CLI loop (html_to_archimate_xml.py:95-117)
for index, view_id in enumerate(view_ids, start=1):
    view_url = f"{base_url}{guid}/views/{view_id}.html"
    try:
        response = fetch_with_retry(session, view_url, headers, timeout)
        response.raise_for_status()
        ...
        view_data = ViewParser.parse(html_content)
    except requests.RequestException as exc:
        ...
```

**Key difference:** GUI uses `self.session.get()` directly (no retry), CLI uses `fetch_with_retry()`. This means the **GUI has no retry logic** for view downloads — a real bug.

**Recommendation:** Extract a `collect_views_from_remote()` function into `archiscraper_core.py` with an optional progress callback. GUI calls with progress callback; CLI calls with logger. Both get retry logic.

#### C. Local File Collection

| GUI | CLI |
|-----|-----|
| `ArchiScraperApp._load_local_files()` (line 842) | `html_to_archimate_xml.collect_view_data_from_files()` (lines 120–145) |

Both open local HTML files, call `ViewParser.parse()`, collect results.

**Recommendation:** The CLI's `collect_view_data_from_files()` could be moved to core and reused by the GUI.

### 1.2 Functions That Should Delegate to Core

| GUI Method | Should Call |
|---|---|
| `_normalize_report_url()` | `core.ensure_url_scheme()` + `core.build_base_url()` |
| `_load_remote_views()` | `core.collect_views_from_remote()` (new) |
| `_load_local_files()` file loop | `core.collect_view_data_from_files()` (moved from CLI) |
| `_load_remote_views()` network calls | `core.fetch_with_retry()` (currently only CLI uses this) |

### 1.3 Integration Inconsistencies

- **GUI lacks retry on view download:** `_load_remote_views()` (line 845) calls `self.session.get()` directly instead of `fetch_with_retry()`. The CLI properly retries. This is a real reliability bug for users with flaky connections.
- **GUID discovery differs:** GUI uses `ModelUrlSniffer` (browser interception), CLI uses `discover_model_url()` (regex on index.html). This is intentional — different UX paradigms — but worth documenting.

---

## 2. Code Quality Issues

### 2.1 Dead Code / Unused Imports

| File | Issue | Line |
|---|---|---|
| `ArchiScraperApp.py` | `QPalette` imported but never used | 30 |
| `ArchiScraperApp.py` | `_on_convert_markdown_clicked()` method exists but **no UI button is connected to it** — dead code | ~1088 |
| `ArchiScraperApp.py` | `hasattr(self, 'model_guid')` check is unnecessary — `model_guid` is set in `__init__()` | 605 |

### 2.2 Inconsistent Error Handling

| Location | Issue | Severity |
|---|---|---|
| `ArchiScraperApp.py:615` | `except Exception: pass` in `_update_preview_panel()` image loading — silently swallows all errors including `MemoryError`, `KeyboardInterrupt` (via bare Exception). Should at minimum log. | Medium |
| `ArchiScraperApp.py:854` | `except Exception: pass` in `_load_remote_views()` view loop — failed views silently disappear with no user feedback. | Medium |
| `ArchiScraperApp.py:874` | `except Exception: pass` in `_load_local_files()` — same silent swallowing. | Medium |
| `archiscraper_core.py:244` | `ModelDataParser.load_from_url()` catches all `Exception` and logs, but the caller in GUI shows a generic "Failed to load model.html" — no error detail passed through. | Low |
| `html_to_archimate_xml.py:178-182` | `discover_model_url` failure exits with `sys.exit(1)` — fine for CLI but means you can't use `main()` as a library function. | Low |
| `archiscraper_core.py` | `_parse_content()` silently produces empty dicts if regex patterns don't match — no warning if model.html format changes. | Low |

### 2.3 Performance Bottlenecks

| Location | Issue | Impact |
|---|---|---|
| `ArchiScraperApp.py:594-619` | `_update_preview_panel()` fetches image **from network on every click** — no caching. Switching between 50 views = 50 HTTP requests. | High |
| `ArchiScraperApp.py:621-658` | `_generate_view_summary()` rebuilds full HTML string on every view selection — should cache. | Low |
| `ArchiScraperApp.py:569-582` | `_filter_review_list()` does `next(entry for entry in self.available_views if entry["view_id"] == view_id)` linear search per list item — O(n²) for n views. Should use a dict lookup. | Medium |
| `archiscraper_core.py:631-635` | `_add_organizations.get_parent_folder()` does a linear scan of `self.model_data.folder_contents` for each folder — O(n·m) where n=folders, m=contents. Should build a reverse index dict once. | Medium |
| `ArchiScraperApp.py:943-1000` | `_on_export_clicked()` calls `QApplication.processEvents()` synchronously during export — blocks the event loop. Should use `QThread` or `QRunnable` for long exports. | Medium |

### 2.4 Code Style Inconsistencies

| Issue | Location |
|---|---|
| Contradictory CSS in `StepperWidget`: `"background: #ededed; background: #fff;"` — second value overwrites first, making `#ededed` dead code | `ArchiScraperApp.py:103` |
| Mixed `print()` and `logger.info()` in CLI `main()` — banner/summary uses `print()`, progress uses `logger` | `html_to_archimate_xml.py:164-245` |
| `review_header_label` style comment `/* legacy #e6f4ea */` left in production CSS | `ArchiScraperApp.py:355` |
| Some methods return `Optional[str]` without type annotation (`_get_views_base_url`) while others do — inconsistent | Various |
| `_get_version_text()` hardcodes `"1.4.0"` as fallback — should track actual version | `ArchiScraperApp.py:488` |
| Long methods: `_setup_ui` (~80 lines), `_build_review_page` (~130 lines), `_on_export_clicked` (~80 lines) would benefit from extraction | Various |

### 2.5 Potential Bugs

| Issue | Location | Severity |
|---|---|---|
| `_on_go_clicked()` doesn't disable the Load button during load — user can double-click and trigger concurrent model loads | `ArchiScraperApp.py:787-795` | Medium |
| `_load_remote_views()` constructs view URL differently from CLI: uses `_get_views_base_url()` (parses model URL path) vs CLI's `{base_url}{guid}/views/` (from discovered GUID). If model URL format changes, one may break while the other works. | `ArchiScraperApp.py:805-818` | Low |
| Version fallback `"1.4.0"` is stale — should be `"1.5.0"` or read from `pyproject.toml` | `ArchiScraperApp.py:490` | Low |
| `render_markdown_document()` uses `->` and `<-` arrows while `write_elements_files()` uses `→` and `←` — inconsistent between single-file and multi-file markdown output | `archiscraper_to_markdown.py:174 vs 106` | Low |

---

## 3. Test Coverage Gaps

### 3.1 Functions with NO Test Coverage

#### archiscraper_core.py (12 untested functions/methods)

| Function | Risk |
|---|---|
| `gen_id()` | Low — trivial, but should verify prefix format |
| `_parse_retry_after()` | Medium — handles Retry-After header parsing, edge cases matter |
| `ModelDataParser.load_from_url()` | High — network + parsing, only `_parse_content()` tested |
| `ModelDataParser.load_from_file()` | High — I/O + parsing |
| `ModelDataParser.get_element_documentation()` | Low — simple dict lookup |
| `ArchiMateXMLGenerator.create_merged_xml()` | **Critical** — this is the main export path for batch mode, only `create_single_view_xml` is tested |
| `ArchiMateXMLGenerator._add_organizations()` | High — folder structure logic, complex recursion |
| `ArchiMateXMLGenerator.prettify_xml()` | Low |
| `ArchiMateXMLGenerator.save_xml()` | Medium — file I/O, encoding header |
| `ViewParser.extract_coordinates()` | Medium — only tested indirectly via `parse()` |
| `fetch_with_retry()` with 429 + Retry-After | Medium — untested code path |
| `fetch_with_retry()` connection error retry | Medium — only tested via download_view_images indirectly |

#### ArchiScraperApp.py (18 untested methods)

| Method | Risk |
|---|---|
| `_on_go_clicked()` | High — main remote flow entry point |
| `_on_model_url_found()` | High — model load + view transition |
| `_load_remote_views()` | High — network-dependent view collection |
| `_load_local_files()` | High — local file loading |
| `_on_export_clicked()` | **Critical** — the entire export pipeline |
| `_normalize_report_url()` | Medium — URL parsing |
| `_get_views_base_url()` | Medium |
| `_get_image_base_and_guid()` | Medium |
| `_generate_view_summary()` | Low |
| `_generate_markdown()` | Medium |
| `_summarize_export()` | Low |
| `_on_validate_xml_clicked()` | Medium |
| `_on_convert_markdown_clicked()` | Low (dead code) |
| `_update_preview_panel()` | Medium |
| `_open_current_view_in_browser()` | Low |
| `ModelUrlSniffer.interceptRequest()` | High — core sniffer logic |
| `SettingsDialog` | Low |
| `PreviewDialog` | Low |

#### html_to_archimate_xml.py (4 untested functions)

| Function | Risk |
|---|---|
| `fetch_html()` | Low — thin wrapper |
| `list_views()` | Low — print function |
| `collect_view_data_from_urls()` | High — remote view collection |
| `main()` (integration) | High — no end-to-end CLI test |

#### archiscraper_to_markdown.py (4 untested functions)

| Function | Risk |
|---|---|
| `classify_layer()` | Medium — layer classification logic |
| `render_markdown_document()` | Medium — single-file markdown |
| `write_markdown_file()` | Low — thin wrapper |
| `main()` | Medium — no CLI integration test |

### 3.2 Missing Edge Cases

| Area | Missing Test |
|---|---|
| `ViewParser.parse()` | HTML with no `<map>` element → should return `None` |
| `ViewParser.parse()` | HTML with no `<title>` → "Unknown View" fallback |
| `ViewParser.parse()` | Map name without `map` suffix → generates random ID |
| `ViewParser.extract_elements()` | Table with 1 cell (< 2) → should skip row |
| `ViewParser.extract_relationships()` | Relationship with missing links → should skip |
| `ModelDataParser._parse_content()` | Empty string input |
| `ModelDataParser._parse_content()` | Content with no dataElements/dataFolders/dataViews |
| `ModelDataParser._parse_content()` | Elements with missing fields (no name, no type) |
| `create_merged_xml()` | Empty views list → should still produce valid XML skeleton |
| `create_merged_xml()` | Views with overlapping elements → deduplication |
| `create_merged_xml()` | Views with elements of skip types (DiagramModelNote) → filtered |
| `create_single_view_xml()` | View with no relationships |
| `validate_xml()` | Duplicate relationship identifiers |
| `validate_xml()` | Missing elementRef on node |
| `download_view_images()` | Duplicate filenames (same view_name different IDs) |
| `download_view_images()` | Missing view_id in view data |
| `download_view_images()` | `view_name` is None |
| `sanitize_filename()` | Unicode characters |
| `sanitize_filename()` | Very long filenames (OS limits) |
| `fetch_with_retry()` | Max retries exhausted on 5xx → returns last response |
| `fetch_with_retry()` | 429 with valid Retry-After header |
| `fetch_with_retry()` | 429 with invalid Retry-After header |
| `fetch_with_retry()` | session=None (creates own session) |
| `_parse_retry_after()` | None, valid float, invalid string, negative number |
| CLI | `--timeout 0` or `--timeout -1` |
| CLI | `--output` pointing to read-only directory |
| CLI | `--select-views` with all invalid IDs |
| Markdown | XML with no elements → should produce skeleton |
| Markdown | Elements with unknown types → "other" layer |

### 3.3 Suggested New Tests

```python
# HIGH PRIORITY — Test the batch export path (most common user flow)
class TestCreateMergedXml(unittest.TestCase):
    def test_merged_xml_deduplicates_elements(self): ...
    def test_merged_xml_with_connections(self): ...
    def test_merged_xml_empty_views_list(self): ...
    def test_merged_xml_filters_skip_types(self): ...
    def test_merged_xml_with_organizations(self): ...

# HIGH PRIORITY — Test retry logic edge cases
class TestFetchWithRetryEdgeCases(unittest.TestCase):
    def test_429_with_retry_after_header(self): ...
    def test_429_max_retries_exhausted(self): ...
    def test_connection_error_recovery(self): ...
    def test_creates_session_when_none(self): ...

class TestParseRetryAfter(unittest.TestCase):
    def test_none_returns_fallback(self): ...
    def test_valid_float(self): ...
    def test_invalid_string(self): ...
    def test_negative_returns_zero(self): ...

# MEDIUM PRIORITY — Model loading
class TestModelDataParserLoadFromUrl(unittest.TestCase):
    def test_load_success(self): ...
    def test_load_network_error(self): ...
    def test_load_invalid_html(self): ...

class TestModelDataParserLoadFromFile(unittest.TestCase):
    def test_load_success(self): ...
    def test_load_missing_file(self): ...
    def test_load_empty_file(self): ...

# MEDIUM PRIORITY — View edge cases
class TestViewParserEdgeCases(unittest.TestCase):
    def test_no_map_returns_none(self): ...
    def test_no_title_uses_fallback(self): ...
    def test_map_name_without_suffix(self): ...
    def test_single_cell_row_skipped(self): ...

# MEDIUM PRIORITY — Markdown classification
class TestClassifyLayer(unittest.TestCase):
    def test_known_types(self): ...
    def test_unknown_type_returns_other(self): ...

# MEDIUM PRIORITY — Save/load round-trip
class TestSaveXmlRoundTrip(unittest.TestCase):
    def test_save_and_reparse(self): ...

# LOW PRIORITY — GUI export flow (requires PyQt6 offscreen)
class TestGuiExportFlow(unittest.TestCase):
    def test_export_xml_produces_file(self): ...
    def test_export_json_produces_file(self): ...
    def test_export_both_produces_two_files(self): ...
```

---

## 4. CLI Functionality Audit

### 4.1 Flag-by-Flag Status

| Flag | Works | Notes |
|---|---|---|
| `--url URL` | ✅ | Auto-adds `http://` if missing |
| `--model FILE` | ✅ | |
| `--views FILE...` | ✅ | |
| `--download-all` | ✅ | |
| `--list-views` | ✅ | |
| `--select-views ID...` | ✅ | Warns on missing IDs, filters them out |
| `--output, -o FILE` | ✅ | Default: `master_model.xml` |
| `--format xml\|json\|both` | ✅ | |
| `--connections` | ✅ | |
| `--images` | ✅ | URL mode only, warns if used with local |
| `--images-dir DIR` | ✅ | Relative to output by default |
| `--markdown` | ✅ | |
| `--validate` | ✅ | |
| `--user-agent STR` | ✅ | Random default via fake-useragent |
| `--timeout SECS` | ⚠️ | No validation — accepts 0, -1, or huge values |

### 4.2 Missing Error Handling

| Issue | Location |
|---|---|
| `--timeout` accepts non-positive values (0, -1) — would cause immediate timeout or error | `html_to_archimate_xml.py:246` |
| No check that output directory is writable before starting export | `main()` |
| `--format json` with `--output master.xml` produces `master.json` — non-obvious behavior, no warning | `main():229-233` |
| `--select-views` with ALL invalid IDs exits with error, but the error message could be clearer | `main():205` |
| `--images` with `--model`/`--views` only prints warning, doesn't exit — could confuse users expecting images | `main():219` |
| No `--verbose` / `--quiet` flags despite README roadmap mention | Missing feature |

### 4.3 README vs Reality Gaps

| README Claim | Status |
|---|---|
| "41 unit tests" (badge) | ❌ **Stale** — there are now **46 tests** |
| "GUI + CLI feature parity" (roadmap ✅) | ⚠️ Partial — GUI has image preview, CLI doesn't; CLI has `--validate` as a standalone flag, GUI has it as post-export button |
| "Progress callbacks for CLI" (roadmap ☐) | ❌ Not implemented — CLI has no progress bar or verbose output |
| "GitHub Actions CI" (roadmap ☐) | ❌ Not implemented |
| "PyPI package" (roadmap ☐) | ❌ Not implemented |
| GUI table: "Convert XML → Markdown" | ⚠️ `_on_convert_markdown_clicked()` exists in code but is **not connected to any button** — dead feature |

---

## 5. Optimization Opportunities

### 5.1 Network Request Efficiency

| Issue | Impact | Fix |
|---|---|---|
| **GUI preview fetches image from network on every view click** — no caching | High (UX lag) | Add an `LRUCache` dict mapping `view_id → QPixmap`. Check cache before HTTP request. |
| **GUI `_load_remote_views()` uses `session.get()` without retry** | Medium (reliability) | Use `fetch_with_retry()` from core, same as CLI does. |
| **Sequential view downloads** — both GUI and CLI download views one-by-one | Medium (latency) | Use `concurrent.futures.ThreadPoolExecutor` with 3-5 workers for parallel downloads. |
| **GUI constructs new User-Agent per `_get_user_agent()` call** if field is empty — `get_random_user_agent()` is called per request | Low | Cache the session UA once at load time. |

### 5.2 Memory Usage

| Issue | Impact | Fix |
|---|---|---|
| `preview_html` stored for every view in `available_views` | Medium — for 100+ views with large HTML, this could be tens of MB | Store only on demand or drop after parsing. The raw HTML is only needed for preview and could be fetched lazily. |
| `ArchiMateXMLGenerator.prettify_xml()` creates a full string copy via `minidom.parseString()` then splits by newlines | Low — for very large models (10k+ elements), double memory for XML string | Could stream-write with `ET.indent()` (Python 3.9+) instead of minidom round-trip. |
| `_parse_content()` compiles regex patterns on every call | Low | Pre-compile patterns as module-level constants. |

### 5.3 CPU / Algorithmic

| Issue | Impact | Fix |
|---|---|---|
| `_filter_review_list()` linear search per item: `next(entry for entry in self.available_views if ...)` | Medium — O(n²) for n views | Build a `view_id → view_data` dict once in `_enter_review_step()`. |
| `_add_organizations.get_parent_folder()` scans all `folder_contents` per folder | Medium — O(n·m) | Build a `content_id → folder_id` reverse index dict before the loop. |
| `QApplication.processEvents()` in export loop | Medium (UI freezing) | Move export to `QThread`. Emit progress signals back to main thread. |
| `validate_xml()` iterates the entire tree 4 separate times (elements, relationships, nodes, connections) | Low | Single-pass iteration collecting all data in one loop. |

---

## Summary of Recommendations

### Must Fix Before Release

1. **GUI lacks retry on view downloads** — `_load_remote_views()` should use `fetch_with_retry()` (reliability bug)
2. **Dead code: `_on_convert_markdown_clicked()`** — either wire it to a button or remove it
3. **Stale README badge** — update "41 tests" to "46 tests"
4. **Version fallback** — update `"1.4.0"` to `"1.5.0"` in `_get_version_text()`
5. **Remove unused import** — `QPalette` in `ArchiScraperApp.py`

### Should Fix

6. **Extract shared URL/view-collection logic** into `archiscraper_core.py` — eliminates 3 instances of duplication
7. **Add `create_merged_xml()` tests** — this is the primary export path with zero coverage
8. **Add `_parse_retry_after()` tests** — handles untested edge cases
9. **Cache image previews in GUI** — biggest UX improvement for the review step
10. **Add `--timeout` validation** in CLI (reject ≤ 0)
11. **Fix contradictory CSS** — `"background: #ededed; background: #fff;"` in `StepperWidget`
12. **Fix arrow inconsistency** in markdown output (`->` vs `→`)

### Nice to Have

13. Build `view_id → view_data` index for O(1) lookup in filter
14. Build reverse `content_id → folder_id` index in `_add_organizations`
15. Move export to `QThread` to avoid UI blocking
16. Add `--verbose` / `--quiet` CLI flags
17. Parallel view downloads with `ThreadPoolExecutor`
18. Pre-compile regex patterns in `_parse_content()`

### Test Coverage Priority

| Priority | Area | Current | Target |
|---|---|---|---|
| 🔴 Critical | `create_merged_xml()` | 0 tests | 4-5 tests |
| 🔴 Critical | GUI export flow | 0 tests | 2-3 tests |
| 🟡 High | `fetch_with_retry()` edge cases | 2 tests | 5-6 tests |
| 🟡 High | `ModelDataParser` load methods | 0 tests | 3-4 tests |
| 🟡 High | `_add_organizations()` | 0 tests | 2-3 tests |
| 🟢 Medium | `ViewParser` edge cases | 3 tests | 6-7 tests |
| 🟢 Medium | Markdown `classify_layer()` | 0 tests | 2 tests |
| 🟢 Medium | CLI `main()` integration | 0 tests | 1-2 tests |

**Current coverage estimate:** ~35-40% of functions have direct tests.  
**Target for v1.5.0:** 60%+ with critical paths fully covered.

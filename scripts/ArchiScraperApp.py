"""
ArchiScraper - Archi HTML Report Browser and XML Exporter

A PyQt6-based GUI application that:
1. Browses Archi HTML reports via QWebEngineView
2. Auto-fetches model.html to cache element/relationship/folder data
3. Extracts the current view from the iframe and converts it to ArchiMate XML
4. Supports batch mode: collect multiple views and export as a single master model

Prerequisites:
    python -m pip install PyQt6 PyQt6-WebEngine requests beautifulsoup4
"""

import sys
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from typing import Optional

from PyQt6.QtCore import QUrl, pyqtSlot, pyqtSignal, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QStatusBar,
    QListWidget, QLabel, QSplitter, QGroupBox, QListWidgetItem, QCheckBox,
    QDialog, QDialogButtonBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInterceptor

import archiscraper_to_markdown as markdown_converter

from archiscraper_core import (
    ArchiMateXMLGenerator,
    ModelDataParser,
    ViewParser,
    download_view_images,
    get_random_user_agent,
    sanitize_filename,
)

DEFAULT_USER_AGENT = get_random_user_agent()


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller.
    
    When running as a compiled executable, PyInstaller creates a temp folder
    and stores bundled files there. sys._MEIPASS contains that path.
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # Running as script - use the script's directory
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, relative_path)


# ============================================================================
# Network Request Interceptor for Model URL Discovery
# ============================================================================
class ModelUrlSniffer(QWebEngineUrlRequestInterceptor):
    """Intercepts browser network requests to capture model.html URL.
    
    When the Archi HTML report loads, it naturally requests model.html
    for its search index. This interceptor captures that exact URL,
    eliminating the need to guess paths with randomized folder IDs.
    """
    
    # Custom signal emitted when model.html URL is found
    model_url_found = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._already_captured = False
    
    def interceptRequest(self, info):
        """Called for every network request made by the browser."""
        url = info.requestUrl().toString()
        
        # Check if this is a request for model.html (case-insensitive, query-safe)
        if re.search(r'model\.html(?:\?|$)', url, re.IGNORECASE) and not self._already_captured:
            self._already_captured = True
            print(f"🔍 Found Model URL via Network: {url}")
            self.model_url_found.emit(url)
    
    def reset(self):
        """Reset the capture flag when navigating to a new report."""
        self._already_captured = False
        print("Model URL Sniffer reset for new report.")


# ============================================================================
# Main GUI Application
# ============================================================================
class ArchiScraperApp(QMainWindow):
    """Main application window for ArchiScraper."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ArchiScraper - Archi HTML Report Browser")
        self.setMinimumSize(1400, 900)
        
        # Set application icon (works for both script and compiled exe)
        icon_path = resource_path('icon.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # Model data cache
        self.model_data = ModelDataParser()
        self.base_url = None
        self.model_url = None  # Store the captured model.html URL
        
        # Network interceptor to capture model.html URL automatically
        self.model_sniffer = ModelUrlSniffer(self)
        self.model_sniffer.model_url_found.connect(self._on_model_url_found)
        
        # Batch mode: list of collected view data
        self.batch_views = []  # List of view_data dicts
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the user interface."""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main horizontal layout with splitter
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # === Left side: Browser ===
        browser_widget = QWidget()
        browser_layout = QVBoxLayout(browser_widget)
        browser_layout.setContentsMargins(0, 0, 0, 0)
        browser_layout.setSpacing(8)
        
        # Top bar: Address bar + Go button
        top_bar = QHBoxLayout()

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter Archi HTML report URL (e.g., http://server/report/index.html)")
        self.url_input.returnPressed.connect(self._on_go_clicked)
        top_bar.addWidget(self.url_input)

        self.go_button = QPushButton("Go")
        self.go_button.setFixedWidth(80)
        self.go_button.clicked.connect(self._on_go_clicked)
        top_bar.addWidget(self.go_button)

        browser_layout.addLayout(top_bar)

        # User-Agent input for HTTP requests
        user_agent_bar = QHBoxLayout()
        user_agent_label = QLabel("User-Agent:")
        self.user_agent_input = QLineEdit()
        self.user_agent_input.setText(DEFAULT_USER_AGENT)
        user_agent_bar.addWidget(user_agent_label)
        user_agent_bar.addWidget(self.user_agent_input)
        browser_layout.addLayout(user_agent_bar)
        
        # Web view with network interceptor
        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl("about:blank"))
        
        # Attach the model URL sniffer to capture model.html requests
        self.web_view.page().profile().setUrlRequestInterceptor(self.model_sniffer)
        
        browser_layout.addWidget(self.web_view, 1)
        
        # Bottom bar: Download buttons
        bottom_bar = QHBoxLayout()
        
        self.download_button = QPushButton("Download Active View as XML")
        self.download_button.setFixedHeight(40)
        self.download_button.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.download_button.clicked.connect(self._on_download_clicked)
        bottom_bar.addWidget(self.download_button)
        
        self.add_to_batch_button = QPushButton("Add Active View to Batch")
        self.add_to_batch_button.setFixedHeight(40)
        self.add_to_batch_button.setStyleSheet("""
            QPushButton {
                background-color: #107c10;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0e6b0e;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.add_to_batch_button.clicked.connect(self._on_add_to_batch_clicked)
        bottom_bar.addWidget(self.add_to_batch_button)

        self.single_image_checkbox = QCheckBox("Download view image")
        self.single_image_checkbox.setChecked(False)
        bottom_bar.addWidget(self.single_image_checkbox)

        bottom_bar.addStretch()
        browser_layout.addLayout(bottom_bar)
        
        splitter.addWidget(browser_widget)
        
        # === Right side: Batch Panel ===
        batch_widget = QGroupBox("Views to Export (Batch Mode)")
        batch_layout = QVBoxLayout(batch_widget)
        
        # List of collected views
        self.batch_list = QListWidget()
        self.batch_list.setMinimumWidth(250)
        batch_layout.addWidget(self.batch_list)
        
        # Batch info label
        self.batch_info_label = QLabel("No views added yet")
        self.batch_info_label.setStyleSheet("color: #666; font-style: italic;")
        batch_layout.addWidget(self.batch_info_label)
        
        # Remove selected button
        self.remove_selected_button = QPushButton("Remove Selected")
        self.remove_selected_button.clicked.connect(self._on_remove_selected_clicked)
        batch_layout.addWidget(self.remove_selected_button)
        
        # Clear all button
        self.clear_batch_button = QPushButton("Clear All")
        self.clear_batch_button.clicked.connect(self._on_clear_batch_clicked)
        batch_layout.addWidget(self.clear_batch_button)
        
        # Export batch button
        self.export_batch_button = QPushButton("Export Batch as Master Model")
        self.export_batch_button.setFixedHeight(50)
        self.export_batch_button.setStyleSheet("""
            QPushButton {
                background-color: #5c2d91;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #4a2474;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.export_batch_button.clicked.connect(self._on_export_batch_clicked)
        batch_layout.addWidget(self.export_batch_button)

        # Connections toggle (applies to single and batch exports)
        self.include_connections_checkbox = QCheckBox("Include connections in views")
        self.include_connections_checkbox.setChecked(False)
        batch_layout.addWidget(self.include_connections_checkbox)

        # Image download toggle (applies to batch exports)
        self.download_images_checkbox = QCheckBox("Download view images")
        self.download_images_checkbox.setChecked(False)
        batch_layout.addWidget(self.download_images_checkbox)

        # List/select views controls
        self.list_views_button = QPushButton("List Views")
        self.list_views_button.clicked.connect(self._on_list_views_clicked)
        batch_layout.addWidget(self.list_views_button)

        self.select_views_button = QPushButton("Select Views...")
        self.select_views_button.clicked.connect(self._on_select_views_clicked)
        batch_layout.addWidget(self.select_views_button)

        # Download ALL views button
        self.download_all_button = QPushButton("⬇ Download ALL Views")
        self.download_all_button.setFixedHeight(50)
        self.download_all_button.setStyleSheet("""
            QPushButton {
                background-color: #d83b01;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #b83000;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.download_all_button.clicked.connect(self._on_download_all_clicked)
        batch_layout.addWidget(self.download_all_button)

        # Local report loader
        self.load_local_button = QPushButton("Load Local Views...")
        self.load_local_button.clicked.connect(self._on_load_local_clicked)
        batch_layout.addWidget(self.load_local_button)

        # XML to Markdown conversion
        self.markdown_button = QPushButton("Convert XML → Markdown")
        self.markdown_button.clicked.connect(self._on_convert_markdown_clicked)
        batch_layout.addWidget(self.markdown_button)
        
        splitter.addWidget(batch_widget)
        
        # Set splitter proportions (70% browser, 30% batch panel)
        splitter.setSizes([900, 400])
        
        # === Status bar ===
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Enter a URL to begin.")
        
        self._update_batch_ui()

    def _get_user_agent(self) -> str:
        """Return the User-Agent string for HTTP requests."""
        user_agent = self.user_agent_input.text().strip()
        return user_agent or DEFAULT_USER_AGENT

    def _get_views_base_url(self) -> Optional[str]:
        """Derive the views base URL from the captured model.html URL."""
        if not self.model_url:
            return None
        parsed = urlparse(self.model_url)
        path = parsed.path
        if not path.endswith("/elements/model.html"):
            return None
        base_path = path[: -len("elements/model.html")] + "views/"
        return f"{parsed.scheme}://{parsed.netloc}{base_path}"

    def _add_view_to_batch(self, view_data: dict) -> bool:
        """Add a parsed view to the batch list if not already present."""
        for existing in self.batch_views:
            if existing['view_id'] == view_data['view_id']:
                return False
        self.batch_views.append(view_data)
        item = QListWidgetItem(f"📊 {view_data['view_name']} ({len(view_data['elements'])} elements)")
        item.setData(Qt.ItemDataRole.UserRole, view_data['view_id'])
        self.batch_list.addItem(item)
        return True

    def _download_views_by_ids(self, view_ids: list[str], clear_batch: bool = False) -> tuple[int, int]:
        """Download and parse the selected views from the report."""
        views_base_url = self._get_views_base_url()
        if not views_base_url:
            QMessageBox.warning(
                self, "Error",
                "Unable to determine views URL base.\n"
                "Make sure the report is loaded and model.html was detected."
            )
            return 0, len(view_ids)

        if clear_batch:
            self.batch_views.clear()
            self.batch_list.clear()

        success_count = 0
        fail_count = 0
        total_views = len(view_ids)

        for i, view_id in enumerate(view_ids, 1):
            view_info = self.model_data.views.get(view_id, {})
            view_name = view_info.get('name', view_id)
            self.status_bar.showMessage(f"Processing view {i}/{total_views}: {view_name}...")
            QApplication.processEvents()

            view_url = f"{views_base_url}{view_id}.html"
            try:
                response = requests.get(
                    view_url,
                    headers={"User-Agent": self._get_user_agent()},
                    timeout=30,
                )
                response.raise_for_status()
                view_html = response.text
                view_data = ViewParser.parse(view_html)
                if view_data:
                    if self._add_view_to_batch(view_data):
                        success_count += 1
                        print(f"  [{i}/{total_views}] ✓ {view_name}")
                    else:
                        print(f"  [{i}/{total_views}] ↺ {view_name} (already in batch)")
                else:
                    fail_count += 1
                    print(f"  [{i}/{total_views}] ✗ {view_name} - No coordinates found")
            except Exception as exc:
                fail_count += 1
                print(f"  [{i}/{total_views}] ✗ {view_name} - Error: {exc}")

        self._update_batch_ui()
        return success_count, fail_count
    
    def _update_batch_ui(self):
        """Update the batch panel UI to reflect current state."""
        count = len(self.batch_views)
        if count == 0:
            self.batch_info_label.setText("No views added yet")
            self.export_batch_button.setEnabled(False)
            self.remove_selected_button.setEnabled(False)
            self.clear_batch_button.setEnabled(False)
        else:
            total_elements = sum(len(v['elements']) for v in self.batch_views)
            self.batch_info_label.setText(f"{count} view(s), ~{total_elements} elements")
            self.export_batch_button.setEnabled(True)
            self.remove_selected_button.setEnabled(True)
            self.clear_batch_button.setEnabled(True)
    
    def _on_go_clicked(self):
        """Handle Go button click."""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a URL.")
            return
        
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
            self.url_input.setText(url)
        
        # Determine base URL correctly
        # For http://example.com/report/index.html -> http://example.com/report/
        # For http://example.com/report/ -> http://example.com/report/
        parsed = urlparse(url)
        path = parsed.path
        
        # Remove the filename if present
        if path.endswith('.html') or path.endswith('.htm'):
            path = path.rsplit('/', 1)[0] + '/'
        elif not path.endswith('/'):
            path = path + '/'
        
        self.base_url = f"{parsed.scheme}://{parsed.netloc}{path}"
        
        print(f"URL: {url}")
        print(f"Base URL: {self.base_url}")
        
        # Reset the model data, model URL, and sniffer for the new report
        self.model_data = ModelDataParser()
        self.model_url = None
        self.model_sniffer.reset()
        
        self.status_bar.showMessage(f"Loading: {url} (listening for model.html...)")
        
        # Load the page - the interceptor will automatically capture model.html when requested
        self.web_view.setUrl(QUrl(url))
    
    @pyqtSlot(str)
    def _on_model_url_found(self, model_url):
        """Callback when the network sniffer detects a model.html request."""
        print(f"🎯 Network Sniffer captured model.html: {model_url}")
        self.model_url = model_url  # Store for Download All Views feature
        self.status_bar.showMessage(f"Fetching model data from: {model_url}...")

        if self.model_data.load_from_url(model_url, headers={"User-Agent": self._get_user_agent()}):
            elem_count = len(self.model_data.elements)
            folder_count = len(self.model_data.folders)
            view_count = len(self.model_data.views)
            doc_count = sum(1 for e in self.model_data.elements.values() if e.get('documentation'))
            self.status_bar.showMessage(
                f"✓ Model Loaded: {elem_count} elements, {folder_count} folders, {view_count} views"
            )
        else:
            self.status_bar.showMessage("⚠ Warning: Failed to load model.html. Documentation may be limited.")
    
    def _on_download_clicked(self):
        """Handle Download button click - single view mode."""
        if not self.base_url:
            QMessageBox.warning(self, "Error", "Please load a report first by entering a URL and clicking Go.")
            return
        
        # Model loading is handled automatically by the network interceptor
        
        self.status_bar.showMessage("Extracting view from iframe...")
        
        # JavaScript to get the iframe src
        js_code = """
        (function() {
            var iframe = document.querySelector('iframe[name="view"]');
            if (!iframe) {
                iframe = document.querySelector('iframe');
            }
            if (iframe && iframe.src) {
                return iframe.src;
            }
            return null;
        })();
        """
        
        self.web_view.page().runJavaScript(js_code, self._on_iframe_src_received_single)
    
    @pyqtSlot("QVariant")
    def _on_iframe_src_received_single(self, iframe_src):
        """Callback for single view download."""
        if not iframe_src:
            QMessageBox.warning(
                self, "Error", 
                "Could not find the view iframe. Make sure you're viewing an Archi HTML report."
            )
            return
        
        print(f"Iframe src: {iframe_src}")
        
        # Check if model data was captured by the network sniffer
        if not self.model_data.loaded:
            reply = QMessageBox.question(
                self, "Warning",
                "Model data was not loaded (network sniffer didn't detect model.html).\n"
                "Documentation and folder structure will be missing.\n\nContinue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        self.status_bar.showMessage(f"Downloading view: {iframe_src}")
        
        try:
            # Download the view HTML
            response = requests.get(
                iframe_src,
                headers={"User-Agent": self._get_user_agent()},
                timeout=30,
            )
            response.raise_for_status()
            view_html = response.text
            
            # Parse the view
            view_data = ViewParser.parse(view_html)
            if not view_data:
                QMessageBox.warning(self, "Error", "Failed to parse the view HTML. No coordinates found.")
                return
            
            print(f"View: {view_data['view_name']}")
            print(f"  Elements: {len(view_data['elements'])}")
            print(f"  Coordinates: {len(view_data['coordinates'])}")
            print(f"  Relationships: {len(view_data['relationships'])}")
            
            # Generate XML
            generator = ArchiMateXMLGenerator(self.model_data)
            xml_root = generator.create_single_view_xml(
                view_data,
                include_connections=self.include_connections_checkbox.isChecked(),
            )
            
            # Sanitize filename
            safe_name = sanitize_filename(view_data['view_name'])
            default_name = f"{safe_name}.xml"
            
            # Ask user where to save
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save ArchiMate XML",
                default_name,
                "ArchiMate XML Files (*.xml);;All Files (*)"
            )
            
            if file_path:
                ArchiMateXMLGenerator.save_xml(xml_root, file_path)
                self.status_bar.showMessage(f"✓ Saved: {file_path}")

                downloaded_images = 0
                skipped_images = 0
                if self.single_image_checkbox.isChecked():
                    base_guid = self._get_image_base_and_guid()
                    if not base_guid:
                        QMessageBox.warning(
                            self,
                            "Warning",
                            "Unable to determine image base URL from model.html.\n"
                            "Image was not downloaded."
                        )
                    else:
                        base_url, guid = base_guid
                        images_dir = Path(file_path).parent / "images"
                        downloaded_images, skipped_images = download_view_images(
                            base_url=base_url,
                            guid=guid,
                            views=[view_data],
                            output_dir=str(images_dir),
                            user_agent=self._get_user_agent(),
                        )

                # Count docs added
                doc_count = sum(1 for e in view_data['elements'].values() 
                               if self.model_data.get_element_documentation(e['id']))
                
                QMessageBox.information(
                    self, "Success",
                    f"ArchiMate XML saved to:\n{file_path}\n\n"
                    f"Elements: {len(view_data['elements'])}\n"
                    f"Relationships: {len(view_data['relationships'])}\n"
                    f"Documentation: {doc_count} elements\n\n"
                    f"Images downloaded: {downloaded_images} (skipped {skipped_images})\n\n"
                    "Import into Archi: File → Import → Model from Open Exchange File"
                )
            else:
                self.status_bar.showMessage("Save cancelled.")
        
        except requests.RequestException as e:
            QMessageBox.critical(self, "Error", f"Failed to download view:\n{e}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to convert view:\n{e}")
            import traceback
            traceback.print_exc()
    
    def _on_add_to_batch_clicked(self):
        """Handle Add to Batch button click."""
        if not self.base_url:
            QMessageBox.warning(self, "Error", "Please load a report first by entering a URL and clicking Go.")
            return
        
        self.status_bar.showMessage("Extracting view from iframe for batch...")
        
        js_code = """
        (function() {
            var iframe = document.querySelector('iframe[name="view"]');
            if (!iframe) {
                iframe = document.querySelector('iframe');
            }
            if (iframe && iframe.src) {
                return iframe.src;
            }
            return null;
        })();
        """
        
        self.web_view.page().runJavaScript(js_code, self._on_iframe_src_received_batch)
    
    @pyqtSlot("QVariant")
    def _on_iframe_src_received_batch(self, iframe_src):
        """Callback for adding view to batch."""
        if not iframe_src:
            QMessageBox.warning(
                self, "Error", 
                "Could not find the view iframe. Make sure you're viewing an Archi HTML report."
            )
            return
        
        print(f"Adding to batch - Iframe src: {iframe_src}")
        
        # Model loading is handled automatically by the network interceptor
        # If model isn't loaded, user will get warning on export
        
        self.status_bar.showMessage(f"Downloading view for batch: {iframe_src}")
        
        try:
            # Download the view HTML
            response = requests.get(
                iframe_src,
                headers={"User-Agent": self._get_user_agent()},
                timeout=30,
            )
            response.raise_for_status()
            view_html = response.text
            
            # Parse the view
            view_data = ViewParser.parse(view_html)
            if not view_data:
                QMessageBox.warning(self, "Error", "Failed to parse the view HTML. No coordinates found.")
                return
            
            # Check for duplicates
            for existing in self.batch_views:
                if existing['view_id'] == view_data['view_id']:
                    QMessageBox.information(
                        self, "Already Added",
                        f"View '{view_data['view_name']}' is already in the batch."
                    )
                    return
            
            # Add to batch
            self._add_view_to_batch(view_data)
            
            self._update_batch_ui()
            
            self.status_bar.showMessage(
                f"✓ Added to batch: {view_data['view_name']} ({len(self.batch_views)} views total)"
            )
        
        except requests.RequestException as e:
            QMessageBox.critical(self, "Error", f"Failed to download view:\n{e}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to parse view:\n{e}")
            import traceback
            traceback.print_exc()
    
    def _on_remove_selected_clicked(self):
        """Remove the selected view from the batch."""
        current_item = self.batch_list.currentItem()
        if not current_item:
            QMessageBox.information(self, "Info", "Please select a view to remove.")
            return
        
        view_id = current_item.data(Qt.ItemDataRole.UserRole)
        
        # Remove from batch_views
        self.batch_views = [v for v in self.batch_views if v['view_id'] != view_id]
        
        # Remove from list widget
        row = self.batch_list.row(current_item)
        self.batch_list.takeItem(row)
        
        self._update_batch_ui()
        self.status_bar.showMessage(f"Removed view from batch. {len(self.batch_views)} views remaining.")
    
    def _on_clear_batch_clicked(self):
        """Clear all views from the batch."""
        if not self.batch_views:
            return
        
        reply = QMessageBox.question(
            self, "Confirm Clear",
            f"Remove all {len(self.batch_views)} views from the batch?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.batch_views.clear()
            self.batch_list.clear()
            self._update_batch_ui()
            self.status_bar.showMessage("Batch cleared.")
    
    def _on_export_batch_clicked(self):
        """Export all batch views as a single master model XML."""
        if not self.batch_views:
            QMessageBox.warning(self, "Error", "No views in batch. Add views first.")
            return
        
        if not self.model_data.loaded:
            reply = QMessageBox.question(
                self, "Warning",
                "Model data is not loaded. Documentation and folder structure will be missing.\nContinue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        self.status_bar.showMessage("Generating master model XML...")
        
        try:
            # Generate merged XML using the batch views
            generator = ArchiMateXMLGenerator(self.model_data)
            xml_root = generator.create_merged_xml(
                self.batch_views,
                include_connections=self.include_connections_checkbox.isChecked(),
            )
            
            # Ask user where to save
            default_name = "master_model.xml"
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Master Model XML",
                default_name,
                "ArchiMate XML Files (*.xml);;All Files (*)"
            )
            
            if file_path:
                ArchiMateXMLGenerator.save_xml(xml_root, file_path)
                self.status_bar.showMessage(f"✓ Master model saved: {file_path}")

                downloaded_images = 0
                skipped_images = 0
                if self.download_images_checkbox.isChecked():
                    base_guid = self._get_image_base_and_guid()
                    if not base_guid:
                        QMessageBox.warning(
                            self,
                            "Warning",
                            "Unable to determine image base URL from model.html.\n"
                            "Images were not downloaded."
                        )
                    else:
                        base_url, guid = base_guid
                        images_dir = Path(file_path).parent / "images"
                        self.status_bar.showMessage("Downloading view images...")
                        QApplication.processEvents()
                        downloaded_images, skipped_images = download_view_images(
                            base_url=base_url,
                            guid=guid,
                            views=self.batch_views,
                            output_dir=str(images_dir),
                            user_agent=self._get_user_agent(),
                        )
                        self.status_bar.showMessage(
                            f"✓ Downloaded {downloaded_images} images (skipped {skipped_images})."
                        )

                # Calculate totals
                total_elements = len(set(
                    elem_id for v in self.batch_views 
                    for elem_id in v['elements'].keys()
                ))
                total_relationships = len(set(
                    rel['id'] for v in self.batch_views 
                    for rel in v['relationships']
                ))
                
                QMessageBox.information(
                    self, "Success",
                    f"Master Model XML saved to:\n{file_path}\n\n"
                    f"Views: {len(self.batch_views)}\n"
                    f"Unique Elements: {total_elements}\n"
                    f"Unique Relationships: {total_relationships}\n\n"
                    f"Images downloaded: {downloaded_images} (skipped {skipped_images})\n\n"
                    "Import into Archi: File → Import → Model from Open Exchange File"
                )
            else:
                self.status_bar.showMessage("Save cancelled.")
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate master model:\n{e}")
            import traceback
            traceback.print_exc()
    
    def _on_download_all_clicked(self):
        """Download ALL views from the model and export as master XML."""
        # Check prerequisites
        if not self.model_url:
            QMessageBox.warning(
                self, "Error",
                "Model URL not captured yet.\n\n"
                "Please load an Archi HTML report first and wait for the\n"
                "status bar to show 'Model Loaded'."
            )
            return
        
        if not self.model_data.loaded or not self.model_data.views:
            QMessageBox.warning(
                self, "Error",
                "No views found in model data.\n\n"
                "Make sure the model.html was loaded successfully."
            )
            return
        
        view_ids = list(self.model_data.views.keys())
        total_views = len(view_ids)
        
        # Confirm with user
        reply = QMessageBox.question(
            self, "Download All Views",
            f"Found {total_views} views in the model.\n\n"
            f"This will download and process all views.\n"
            f"Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.No:
            return

        success_count, fail_count = self._download_views_by_ids(view_ids, clear_batch=True)
        
        self.status_bar.showMessage(
            f"✓ Downloaded {success_count} views ({fail_count} failed). Ready to export."
        )
        
        if success_count == 0:
            QMessageBox.warning(self, "Warning", "No views were successfully downloaded.")
            return
        
        # Ask if user wants to export now
        reply = QMessageBox.question(
            self, "Export Now?",
            f"Successfully downloaded {success_count} views.\n\n"
            f"Export as Master Model XML now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._on_export_batch_clicked()

    def _get_image_base_and_guid(self):
        """Extract base URL and GUID from the captured model.html URL."""
        if not self.model_url:
            return None
        parsed = urlparse(self.model_url)
        match = re.search(r'(.*?/)(id-[A-Fa-f0-9-]+)/elements/model\.html$', parsed.path)
        if not match:
            return None
        base_path, guid = match.group(1), match.group(2)
        base_url = f"{parsed.scheme}://{parsed.netloc}{base_path}"
        return base_url, guid

    def _on_list_views_clicked(self):
        """Show a dialog listing all available views."""
        if not self.model_data.views:
            QMessageBox.information(self, "No Views", "No views found in model data.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Available Views")
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        for view_id, view in sorted(self.model_data.views.items(), key=lambda item: item[1].get('name', '').lower()):
            name = view.get('name', view_id)
            list_widget.addItem(f"{name} ({view_id})")
        layout.addWidget(list_widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _on_select_views_clicked(self):
        """Let the user select specific views to download."""
        if not self.model_data.views:
            QMessageBox.information(self, "No Views", "No views found in model data.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Select Views")
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        for view_id, view in sorted(self.model_data.views.items(), key=lambda item: item[1].get('name', '').lower()):
            name = view.get('name', view_id)
            item = QListWidgetItem(f"{name} ({view_id})")
            item.setData(Qt.ItemDataRole.UserRole, view_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_ids = []
        for idx in range(list_widget.count()):
            item = list_widget.item(idx)
            if item.checkState() == Qt.CheckState.Checked:
                selected_ids.append(item.data(Qt.ItemDataRole.UserRole))

        if not selected_ids:
            QMessageBox.information(self, "No Selection", "No views selected.")
            return

        success_count, fail_count = self._download_views_by_ids(selected_ids, clear_batch=False)
        QMessageBox.information(
            self,
            "Download Complete",
            f"Downloaded {success_count} view(s).\nFailed: {fail_count}."
        )

    def _on_load_local_clicked(self):
        """Load local model.html and view HTML files into the batch."""
        model_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select model.html",
            "",
            "HTML Files (*.html *.htm);;All Files (*)"
        )
        if not model_path:
            return

        view_files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select view HTML files",
            "",
            "HTML Files (*.html *.htm);;All Files (*)"
        )
        if not view_files:
            return

        self.model_data = ModelDataParser()
        self.model_url = None
        self.base_url = None

        if not self.model_data.load_from_file(model_path):
            QMessageBox.warning(
                self,
                "Warning",
                "Failed to load model.html. Documentation and folders may be missing."
            )

        added = 0
        skipped = 0
        for view_file in view_files:
            try:
                with open(view_file, 'r', encoding='utf-8') as handle:
                    view_html = handle.read()
                view_data = ViewParser.parse(view_html)
                if view_data and self._add_view_to_batch(view_data):
                    added += 1
                else:
                    skipped += 1
            except Exception as exc:
                skipped += 1
                print(f"Failed to load {view_file}: {exc}")

        self._update_batch_ui()
        QMessageBox.information(
            self,
            "Local Views Loaded",
            f"Added {added} view(s).\nSkipped: {skipped}."
        )

    def _on_convert_markdown_clicked(self):
        """Convert an ArchiMate XML file to Markdown output."""
        xml_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ArchiMate XML",
            "",
            "ArchiMate XML Files (*.xml);;All Files (*)"
        )
        if not xml_path:
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not output_dir:
            return

        try:
            model_name, elements, relationships, views = markdown_converter.parse_model(Path(xml_path))
            rel_index = markdown_converter.build_relationship_index(elements, relationships)
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            markdown_converter.write_readme(output_path, model_name, len(elements), len(relationships), len(views))
            markdown_converter.write_elements_files(elements, rel_index, output_path)
            markdown_converter.write_relationships(relationships, elements, output_path)
            markdown_converter.write_views(views, elements, output_path)
            QMessageBox.information(self, "Success", f"Markdown written to:\n{output_dir}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to convert XML:\n{exc}")


# ============================================================================
# Entry Point
# ============================================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = ArchiScraperApp()
    window.showMaximized()  # Start maximized
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

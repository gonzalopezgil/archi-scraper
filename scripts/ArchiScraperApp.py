"""
ArchiScraper - Archi HTML Report Browser and XML Exporter

A PyQt6-based GUI application that:
1. Loads Archi HTML reports from remote URLs or local files
2. Auto-fetches model.html to cache element/relationship/folder data
3. Lets users review views before export
4. Exports selected views as ArchiMate XML and/or JSON

Prerequisites:
    python -m pip install PyQt6 PyQt6-WebEngine requests beautifulsoup4
"""

import sys
import os
import re
import json
import tempfile
import xml.etree.ElementTree as ET
from importlib import metadata
from pathlib import Path
from urllib.parse import urlparse

import requests
from typing import Optional

from PyQt6.QtCore import QUrl, pyqtSlot, pyqtSignal, Qt
from PyQt6.QtGui import QDesktopServices, QIcon, QIntValidator, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QStatusBar,
    QListWidget, QLabel, QListWidgetItem, QCheckBox, QDialog,
    QDialogButtonBox, QProgressBar, QStackedWidget, QFrame, QRadioButton,
    QButtonGroup, QGridLayout, QGraphicsDropShadowEffect, QSplitter
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


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)


class ModelUrlSniffer(QWebEngineUrlRequestInterceptor):
    """Intercept browser requests to capture model.html URL."""

    model_url_found = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._already_captured = False

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        if re.search(r'model\.html(?:\?|$)', url, re.IGNORECASE) and not self._already_captured:
            self._already_captured = True
            self.model_url_found.emit(url)

    def reset(self):
        self._already_captured = False


class StepperWidget(QWidget):
    """Simple horizontal step indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dots = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        steps = ["Source", "Review", "Options", "Done"]
        for index, name in enumerate(steps, 1):
            dot = QLabel(str(index))
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setFixedSize(28, 28)
            title = QLabel(name)
            title.setObjectName("stepTitle")
            block = QVBoxLayout()
            block.setSpacing(4)
            block.addWidget(dot, alignment=Qt.AlignmentFlag.AlignCenter)
            block.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
            wrapper = QWidget()
            wrapper.setLayout(block)
            layout.addWidget(wrapper)
            self._dots.append(dot)
            if index < len(steps):
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFixedHeight(2)
                line.setStyleSheet("background: #d0d0d0; border: none;")
                layout.addWidget(line, 1)
        self.update_step(1)

    def update_step(self, current_step: int):
        for index, dot in enumerate(self._dots, 1):
            if index < current_step:
                dot.setText("✓")
                dot.setStyleSheet(
                    "background: #e8601c; color: white; border-radius: 14px; font-weight: 600;"
                )
            elif index == current_step:
                dot.setText(str(index))
                dot.setStyleSheet(
                    "background: white; color: #e8601c; border: 2px solid #e8601c; "
                    "border-radius: 14px; font-weight: 600;"
                )
            else:
                dot.setText(str(index))
                dot.setStyleSheet(
                    "background: #ededed; color: #777; border: 1px solid #d0d0d0; "
                    "border-radius: 14px; font-weight: 600;"
                )


class ReviewListItemWidget(QWidget):
    """Custom list row with a standard checkbox and secondary metadata."""

    def __init__(self, name: str, count: int, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        self.checkbox = QCheckBox()
        self.checkbox.setText(name)
        layout.addWidget(self.checkbox)

        self.count_label = QLabel(f"{count} elements")
        self.count_label.setProperty("subtle", True)
        layout.addWidget(self.count_label)
        layout.addStretch(1)


class SettingsDialog(QDialog):
    """Popup for request settings."""

    def __init__(self, user_agent: str, timeout: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("User-Agent"))
        self.user_agent_input = QLineEdit()
        self.user_agent_input.setPlaceholderText("Auto - random browser UA per session")
        self.user_agent_input.setText(user_agent)
        layout.addWidget(self.user_agent_input)

        layout.addWidget(QLabel("Timeout (seconds)"))
        self.timeout_input = QLineEdit(str(timeout))
        self.timeout_input.setValidator(QIntValidator(1, 600, self))
        layout.addWidget(self.timeout_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class PreviewDialog(QDialog):
    """Popup preview for a single view."""

    def __init__(self, title: str, url: QUrl, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 700)
        layout = QVBoxLayout(self)
        self.web_view = QWebEngineView()
        self.web_view.setUrl(url)
        layout.addWidget(self.web_view)


class ArchiScraperApp(QMainWindow):
    """Main application window for ArchiScraper."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ArchiScraper")
        self.setMinimumSize(700, 500)
        self.resize(800, 600)

        icon_path = resource_path("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.model_data = ModelDataParser()
        self.base_url = None
        self.model_url = None
        self.local_model_path = None
        self.session = requests.Session()
        self.available_views = []
        self.selected_view_ids = set()
        self.batch_views = []
        self.exported_files = []
        self.export_output_dir = None
        self.last_xml_path = None
        self.last_export_error = None
        self.pending_export = False
        self.current_source_url = None
        self.user_agent_input = QLineEdit()
        self.timeout_input = QLineEdit("60")

        self.model_sniffer = ModelUrlSniffer(self)
        self.model_sniffer.model_url_found.connect(self._on_model_url_found)
        self.hidden_web_view = QWebEngineView(self)
        self.hidden_web_view.setFixedSize(0, 0)
        self.hidden_web_view.setUrl(QUrl("about:blank"))
        self.hidden_web_view.page().profile().setUrlRequestInterceptor(self.model_sniffer)

        self._setup_ui()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #f5f5f5;
                color: #222;
                font-size: 13px;
            }
            QFrame[card="true"] {
                background: white;
                border: 1px solid #e6e6e6;
                border-radius: 8px;
            }
            QLabel[title="true"] {
                font-size: 28px;
                font-weight: 700;
            }
            QLabel[header="true"] {
                font-size: 18px;
                font-weight: 600;
            }
            QLabel[subtle="true"] {
                color: #666;
            }
            QPushButton {
                min-height: 36px;
                padding: 0 12px;
                border-radius: 8px;
                border: none;
            }
            QPushButton[primary="true"] {
                background: #e8601c;
                color: white;
                font-weight: 600;
            }
            QPushButton[secondary="true"] {
                background: #e8e8e8;
                color: #333;
                border: 1px solid #d0d0d0;
            }
            QPushButton[link="true"] {
                background: transparent;
                color: #666;
                padding: 0;
                min-height: 0;
                border: none;
                text-align: right;
            }
            QPushButton:disabled {
                background: #e9e9e9;
                color: #999;
            }
            QLineEdit, QListWidget {
                background: white;
                border: 1px solid #d7d7d7;
                border-radius: 8px;
                padding: 8px 10px;
            }
            QListWidget::indicator {
                width: 16px;
                height: 16px;
            }
            QListWidget::indicator:unchecked {
                background: white;
                border: 1px solid #bdbdbd;
                border-radius: 2px;
            }
            QListWidget::indicator:checked {
                background: palette(highlight);
                border: 1px solid palette(highlight);
                border-radius: 2px;
            }
            QProgressBar {
                background: #ededed;
                border: none;
                border-radius: 6px;
                text-align: center;
                min-height: 18px;
            }
            QProgressBar::chunk {
                background: #e8601c;
                border-radius: 6px;
            }
        """)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(24, 24, 24, 16)
        root_layout.setSpacing(16)

        self.stack = QStackedWidget()
        self.wizard_stack = self.stack
        root_layout.addWidget(self.stack, 1)

        self.page_source = self._build_source_page()
        self.page_review = self._build_review_page()
        self.page_options = self._build_options_page()
        self.page_done = self._build_done_page()

        self.stack.addWidget(self.page_source)
        self.stack.addWidget(self.page_review)
        self.stack.addWidget(self.page_options)
        self.stack.addWidget(self.page_done)

        self.batch_progress = QProgressBar()
        self.batch_progress.setVisible(False)
        root_layout.addWidget(self.batch_progress)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Load a report to begin.")

        self._go_to_step(1)
        self._update_selection_ui()

    def _build_card(self):
        card = QFrame()
        card.setProperty("card", True)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setOffset(0, 4)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 50))
        card.setGraphicsEffect(shadow)
        return card

    def _build_source_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)
        layout.addStretch(1)

        card = self._build_card()
        card.setMaximumWidth(500)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(12)

        self.title_label = QLabel("ArchiScraper")
        self.title_label.setProperty("title", True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("background: transparent;")
        card_layout.addWidget(self.title_label)

        title_accent = QFrame()
        title_accent.setFixedHeight(2)
        title_accent.setFixedWidth(72)
        title_accent.setStyleSheet("background: #e8601c; border: none; border-radius: 1px;")
        card_layout.addWidget(title_accent, alignment=Qt.AlignmentFlag.AlignHCenter)

        subtitle = QLabel("ArchiMate Report → XML / JSON")
        subtitle.setProperty("subtle", True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("background: transparent;")
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(4)

        content = QWidget()
        content.setFixedWidth(452)
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(24)

        url_row = QHBoxLayout()
        url_row.setSpacing(12)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter Archi HTML report URL")
        self.url_input.returnPressed.connect(self._on_go_clicked)
        url_row.addWidget(self.url_input, 1)

        self.go_button = QPushButton("Load")
        self.go_button.setProperty("primary", True)
        self.go_button.clicked.connect(self._on_go_clicked)
        url_row.addWidget(self.go_button)
        content_layout.addLayout(url_row)

        self.load_local_button = QPushButton("Open Local Files...")
        self.load_local_button.setProperty("secondary", True)
        self.load_local_button.setMinimumHeight(36)
        self.load_local_button.clicked.connect(self._on_load_local_clicked)
        content_layout.addWidget(self.load_local_button)

        footer_container = QWidget()
        footer_container.setStyleSheet("background: transparent;")
        footer_layout = QVBoxLayout(footer_container)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(12)

        footer_separator = QLabel()
        footer_separator.setFixedHeight(1)
        footer_separator.setStyleSheet("background-color: #d0d0d0; border: none; min-height: 1px; max-height: 1px; padding: 0; margin: 0;")
        footer_layout.addWidget(footer_separator)

        footer_row = QHBoxLayout()
        footer_row.setSpacing(12)
        self.version_label = QLabel(self._get_version_text())
        self.version_label.setProperty("subtle", True)
        footer_row.addWidget(self.version_label)
        footer_row.addStretch(1)
        self.settings_button = QPushButton("Settings")
        self.settings_button.setProperty("link", True)
        self.settings_button.clicked.connect(self._open_settings_dialog)
        footer_row.addWidget(self.settings_button)
        footer_layout.addLayout(footer_row)

        content_layout.addWidget(footer_container)
        card_layout.addWidget(content, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        return page

    def _build_review_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        card = self._build_card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        self.review_stepper = StepperWidget()
        card_layout.addWidget(self.review_stepper)

        self.review_header_label = QLabel("Model loaded successfully")
        self.review_header_label.setProperty("header", True)
        self.review_header_label.setStyleSheet(
            "background: #e6f4ea; padding: 8px; border-radius: 6px; border-left: 3px solid #34a853;"
        )
        card_layout.addWidget(self.review_header_label)

        self.review_stats_label = QLabel("")
        self.review_stats_label.setProperty("subtle", True)
        card_layout.addWidget(self.review_stats_label)

        self.review_selection_label = QLabel("")
        self.review_selection_label.setStyleSheet("font-weight: 600; color: #222;")
        card_layout.addWidget(self.review_selection_label)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.select_all_button = QPushButton("Select All")
        self.select_all_button.setProperty("secondary", True)
        self.select_all_button.clicked.connect(self._toggle_select_all_views)
        controls.addWidget(self.select_all_button)
        controls.addStretch(1)
        card_layout.addLayout(controls)

        self.review_filter_input = QLineEdit()
        self.review_filter_input.setPlaceholderText("Filter views...")
        self.review_filter_input.setClearButtonEnabled(True)
        self.review_filter_input.textChanged.connect(self._filter_review_list)
        card_layout.addWidget(self.review_filter_input)

        self.review_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.review_splitter.setChildrenCollapsible(False)

        self.view_list = QListWidget()
        self.view_list.currentItemChanged.connect(self._on_view_current_item_changed)
        self.review_splitter.addWidget(self.view_list)

        self.preview_container = QFrame()
        self.preview_container.setStyleSheet(
            "QFrame { background: white; border: 1px solid #e0e0e0; border-radius: 8px; }"
        )
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_stack = QStackedWidget()
        self.preview_placeholder = QLabel("Select a view to preview")
        self.preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_placeholder.setProperty("subtle", True)
        self.preview_stack.addWidget(self.preview_placeholder)

        self.review_preview = QWebEngineView()
        self.preview_stack.addWidget(self.review_preview)
        preview_layout.addWidget(self.preview_stack)
        self.review_splitter.addWidget(self.preview_container)
        self.review_splitter.setStretchFactor(0, 2)
        self.review_splitter.setStretchFactor(1, 3)
        card_layout.addWidget(self.review_splitter, 1)

        nav = QHBoxLayout()
        nav.setSpacing(12)
        self.review_back_button = QPushButton("← Back")
        self.review_back_button.setProperty("secondary", True)
        self.review_back_button.clicked.connect(lambda: self._go_to_step(1))
        nav.addWidget(self.review_back_button)
        nav.addStretch(1)
        self.review_next_button = QPushButton("Next →")
        self.review_next_button.setProperty("primary", True)
        self.review_next_button.setEnabled(False)
        self.review_next_button.clicked.connect(self._go_to_options_step)
        nav.addWidget(self.review_next_button)
        card_layout.addLayout(nav)

        layout.addWidget(card, 1)
        return page

    def _build_options_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        card = self._build_card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        self.options_stepper = StepperWidget()
        card_layout.addWidget(self.options_stepper)

        header = QLabel("Export options")
        header.setProperty("header", True)
        card_layout.addWidget(header)

        format_label = QLabel("Format")
        card_layout.addWidget(format_label)

        self.format_group = QButtonGroup(self)
        self.xml_radio = QRadioButton("XML")
        self.json_radio = QRadioButton("JSON")
        self.both_radio = QRadioButton("Both")
        self.both_radio.setChecked(True)
        self.format_group.addButton(self.xml_radio, 1)
        self.format_group.addButton(self.json_radio, 2)
        self.format_group.addButton(self.both_radio, 3)
        format_row = QHBoxLayout()
        format_row.setSpacing(16)
        format_row.addWidget(self.xml_radio)
        format_row.addWidget(self.json_radio)
        format_row.addWidget(self.both_radio)
        format_row.addStretch(1)
        card_layout.addLayout(format_row)

        self.markdown_checkbox = QCheckBox("Also generate Markdown summary")
        self.include_connections_checkbox = QCheckBox("Include connections in views")
        self.download_images_checkbox = QCheckBox("Download diagram images")
        card_layout.addWidget(self.markdown_checkbox)
        card_layout.addWidget(self.include_connections_checkbox)
        card_layout.addWidget(self.download_images_checkbox)

        output_grid = QGridLayout()
        output_grid.setHorizontalSpacing(12)
        output_grid.setVerticalSpacing(12)

        output_grid.addWidget(QLabel("Output directory"), 0, 0)
        self.output_dir_input = QLineEdit(os.getcwd())
        output_grid.addWidget(self.output_dir_input, 0, 1)
        self.output_dir_button = QPushButton("Browse...")
        self.output_dir_button.setProperty("secondary", True)
        self.output_dir_button.clicked.connect(self._browse_output_directory)
        output_grid.addWidget(self.output_dir_button, 0, 2)

        output_grid.addWidget(QLabel("Output filename"), 1, 0)
        self.output_name_input = QLineEdit("master_model")
        output_grid.addWidget(self.output_name_input, 1, 1, 1, 2)
        card_layout.addLayout(output_grid)

        nav = QHBoxLayout()
        nav.setSpacing(12)
        self.options_back_button = QPushButton("← Back")
        self.options_back_button.setProperty("secondary", True)
        self.options_back_button.clicked.connect(lambda: self._go_to_step(2))
        nav.addWidget(self.options_back_button)
        nav.addStretch(1)
        self.export_button = QPushButton("🟠 Export")
        self.export_button.setProperty("primary", True)
        self.export_button.clicked.connect(self._on_export_clicked)
        nav.addWidget(self.export_button)
        card_layout.addLayout(nav)

        layout.addWidget(card, 1)
        return page

    def _build_done_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        card = self._build_card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        self.done_stepper = StepperWidget()
        card_layout.addWidget(self.done_stepper)

        self.done_header_label = QLabel("Export complete")
        self.done_header_label.setProperty("header", True)
        card_layout.addWidget(self.done_header_label)

        self.done_summary_label = QLabel("")
        self.done_summary_label.setWordWrap(True)
        card_layout.addWidget(self.done_summary_label)

        self.done_files_label = QLabel("")
        self.done_files_label.setWordWrap(True)
        self.done_files_label.setProperty("subtle", True)
        card_layout.addWidget(self.done_files_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.setProperty("secondary", True)
        self.open_folder_button.clicked.connect(self._open_export_folder)
        buttons.addWidget(self.open_folder_button)

        self.validate_xml_button = QPushButton("Validate XML")
        self.validate_xml_button.setProperty("secondary", True)
        self.validate_xml_button.clicked.connect(self._on_validate_xml_clicked)
        buttons.addWidget(self.validate_xml_button)

        self.retry_export_button = QPushButton("Retry Export")
        self.retry_export_button.setProperty("secondary", True)
        self.retry_export_button.clicked.connect(self._retry_export)
        buttons.addWidget(self.retry_export_button)

        buttons.addStretch(1)

        self.new_export_button = QPushButton("New Export")
        self.new_export_button.setProperty("primary", True)
        self.new_export_button.clicked.connect(self._reset_to_source_step)
        buttons.addWidget(self.new_export_button)
        card_layout.addLayout(buttons)

        layout.addWidget(card, 1)
        return page

    def _get_version_text(self) -> str:
        try:
            return f"v{metadata.version('archi-scraper')}"
        except metadata.PackageNotFoundError:
            return "v1.4.0"

    def _open_settings_dialog(self):
        dialog = SettingsDialog(self.user_agent_input.text(), self._get_timeout(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.user_agent_input.setText(dialog.user_agent_input.text().strip())
        self.timeout_input.setText(dialog.timeout_input.text().strip() or "60")

    def _go_to_step(self, step: int):
        self.stack.setCurrentIndex(step - 1)
        self.review_stepper.update_step(2 if step >= 2 else 1)
        self.options_stepper.update_step(3 if step >= 3 else 2)
        self.done_stepper.update_step(4 if step >= 4 else 3)

    def _get_user_agent(self) -> str:
        user_agent = self.user_agent_input.text().strip()
        return user_agent or get_random_user_agent()

    def _get_timeout(self) -> int:
        raw_value = self.timeout_input.text().strip()
        try:
            timeout = int(raw_value)
            if timeout > 0:
                return timeout
        except ValueError:
            pass
        return 60

    def _set_busy(self, message: str, indeterminate: bool = False, total_steps: int = 0):
        self.status_bar.showMessage(message)
        if indeterminate:
            self.batch_progress.setRange(0, 0)
        else:
            self.batch_progress.setRange(0, max(total_steps, 1))
            self.batch_progress.setValue(0)
        self.batch_progress.setVisible(True)
        QApplication.processEvents()

    def _show_progress(self, total_steps: int) -> None:
        self._set_busy(self.status_bar.currentMessage(), indeterminate=False, total_steps=total_steps)

    def _update_progress(self, value: int) -> None:
        self.batch_progress.setValue(value)
        QApplication.processEvents()

    def _hide_progress(self) -> None:
        self.batch_progress.setVisible(False)
        self.batch_progress.setRange(0, 1)
        self.batch_progress.setValue(0)

    def _reset_runtime_state(self):
        self.model_data = ModelDataParser()
        self.base_url = None
        self.model_url = None
        self.local_model_path = None
        self.available_views = []
        self.selected_view_ids = set()
        self.batch_views = []
        self.exported_files = []
        self.export_output_dir = None
        self.last_xml_path = None
        self.last_export_error = None
        self.pending_export = False
        self.model_sniffer.reset()
        self.current_source_url = None

    def _reset_to_source_step(self):
        self._reset_runtime_state()
        self.view_list.clear()
        self.review_filter_input.clear()
        self.output_name_input.setText("master_model")
        self.output_dir_input.setText(os.getcwd())
        self.done_summary_label.clear()
        self.done_files_label.clear()
        self.status_bar.showMessage("Ready. Load a report to begin.")
        self._go_to_step(1)
        self._update_preview_panel()
        self._update_selection_ui()

    def _update_selection_ui(self):
        selected_count = len(self.selected_view_ids)
        total_count = len(self.available_views)
        self.review_next_button.setEnabled(selected_count > 0)
        self.review_selection_label.setText(f"{selected_count} of {total_count} views selected")
        if total_count and selected_count == total_count:
            self.select_all_button.setText("Deselect All")
        else:
            self.select_all_button.setText("Select All")

    def _build_review_list(self):
        self.view_list.blockSignals(True)
        self.view_list.clear()
        for view in self.available_views:
            name = view["view_name"]
            count = len(view.get("elements", {}))
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, view["view_id"])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.view_list.addItem(item)
            widget = ReviewListItemWidget(name, count, self.view_list)
            widget.checkbox.setChecked(view["view_id"] in self.selected_view_ids)
            widget.checkbox.toggled.connect(
                lambda checked, view_id=view["view_id"]: self._on_view_checkbox_toggled(view_id, checked)
            )
            self.view_list.setItemWidget(item, widget)
        self.view_list.blockSignals(False)
        if self.view_list.count():
            self.view_list.setCurrentRow(0)
        self._filter_review_list(self.review_filter_input.text())
        self._update_selection_ui()
        self._update_preview_panel()

    def _update_review_summary(self):
        element_count = len(self.model_data.elements)
        relationship_count = len(getattr(self.model_data, "relationships", {}))
        view_count = len(self.available_views)
        self.review_stats_label.setText(
            f"{element_count} elements • {relationship_count} relationships • {view_count} views"
        )

    def _enter_review_step(self):
        self.selected_view_ids = {view["view_id"] for view in self.available_views}
        self._update_review_summary()
        self._build_review_list()
        self.status_bar.showMessage("Step 2 of 4 — Review")
        self._go_to_step(2)
        self._set_review_splitter_sizes()

    def _enter_done_step(self, success: bool, summary: str, files_text: str):
        self.done_header_label.setText("Export complete" if success else "Export failed")
        self.done_summary_label.setText(summary)
        self.done_files_label.setText(files_text)
        self.open_folder_button.setEnabled(bool(self.export_output_dir))
        self.validate_xml_button.setEnabled(bool(self.last_xml_path))
        self.retry_export_button.setVisible(not success)
        self._go_to_step(4)

    def _toggle_select_all_views(self):
        should_select_all = len(self.selected_view_ids) != len(self.available_views)
        self.selected_view_ids.clear()
        for index in range(self.view_list.count()):
            item = self.view_list.item(index)
            widget = self.view_list.itemWidget(item)
            if not widget:
                continue
            widget.checkbox.blockSignals(True)
            widget.checkbox.setChecked(should_select_all)
            widget.checkbox.blockSignals(False)
            if should_select_all:
                self.selected_view_ids.add(item.data(Qt.ItemDataRole.UserRole))
        self._update_selection_ui()

    def _on_view_checkbox_toggled(self, view_id: str, checked: bool):
        if checked:
            self.selected_view_ids.add(view_id)
        else:
            self.selected_view_ids.discard(view_id)
        self._update_selection_ui()

    def _on_view_current_item_changed(self, current, previous):
        self._update_preview_panel()
        self._update_selection_ui()

    def _filter_review_list(self, text: str):
        filter_text = text.strip().lower()
        first_visible_row = None
        for index in range(self.view_list.count()):
            item = self.view_list.item(index)
            view_id = item.data(Qt.ItemDataRole.UserRole)
            view = next((entry for entry in self.available_views if entry["view_id"] == view_id), None)
            name = (view or {}).get("view_name", "").lower()
            is_hidden = bool(filter_text) and filter_text not in name
            item.setHidden(is_hidden)
            if not is_hidden and first_visible_row is None:
                first_visible_row = index
        current_item = self.view_list.currentItem()
        if current_item is None or current_item.isHidden():
            if first_visible_row is not None:
                self.view_list.setCurrentRow(first_visible_row)
            else:
                self.view_list.setCurrentItem(None)
        self._update_preview_panel()

    def _update_preview_panel(self):
        item = self.view_list.currentItem()
        if not item or item.isHidden():
            self.preview_stack.setCurrentWidget(self.preview_placeholder)
            return
        view_id = item.data(Qt.ItemDataRole.UserRole)
        view_data = next((view for view in self.available_views if view["view_id"] == view_id), None)
        preview_url = (view_data or {}).get("preview_url")
        if not preview_url:
            self.preview_stack.setCurrentWidget(self.preview_placeholder)
            return
        self.review_preview.setUrl(QUrl(preview_url))
        self.preview_stack.setCurrentWidget(self.review_preview)

    def _set_review_splitter_sizes(self):
        total_width = max(self.review_splitter.size().width(), 1000)
        self.review_splitter.setSizes([int(total_width * 0.4), int(total_width * 0.6)])

    def _go_to_options_step(self):
        if not self.selected_view_ids:
            QMessageBox.information(self, "No Views Selected", "Select at least one view to continue.")
            return
        self._go_to_step(3)

    def _browse_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.output_dir_input.text())
        if directory:
            self.output_dir_input.setText(directory)

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

    def _on_go_clicked(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a URL.")
            return

        self._reset_runtime_state()
        url = self._normalize_report_url(url)
        self.url_input.setText(url)
        self.current_source_url = url
        self._set_busy(f"Loading: {url} (waiting for model.html...)", indeterminate=True)
        self.hidden_web_view.setUrl(QUrl(url))

    @pyqtSlot(str)
    def _on_model_url_found(self, model_url):
        self.model_url = model_url
        self.status_bar.showMessage(f"Fetching model data from: {model_url}...")

        if not self.model_data.load_from_url(
            model_url,
            headers={"User-Agent": self._get_user_agent()},
            timeout=self._get_timeout(),
            session=self.session,
        ):
            self._hide_progress()
            QMessageBox.warning(self, "Error", "Failed to load model.html from the report.")
            self.status_bar.showMessage("Failed to load model.html.")
            return

        try:
            self._load_remote_views()
        except Exception as exc:
            self._hide_progress()
            QMessageBox.critical(self, "Error", f"Failed to load report views:\n{exc}")
            self.status_bar.showMessage("Failed to load report views.")
            return

        self._hide_progress()
        self._enter_review_step()

    def _get_views_base_url(self) -> Optional[str]:
        if not self.model_url:
            return None
        parsed = urlparse(self.model_url)
        path = parsed.path
        if not path.endswith("/elements/model.html"):
            return None
        base_path = path[:-len("elements/model.html")] + "views/"
        return f"{parsed.scheme}://{parsed.netloc}{base_path}"

    def _load_remote_views(self):
        views_base_url = self._get_views_base_url()
        if not views_base_url:
            raise RuntimeError("Unable to determine views URL base from model.html.")

        view_ids = list(self.model_data.views.keys())
        self._show_progress(max(len(view_ids), 1))
        self.available_views = []
        for index, view_id in enumerate(view_ids, 1):
            view_info = self.model_data.views.get(view_id, {})
            view_name = view_info.get("name", view_id)
            view_url = f"{views_base_url}{view_id}.html"
            view_data = {
                "view_id": view_id,
                "view_name": view_name,
                "elements": {},
                "relationships": [],
                "coordinates": {},
                "preview_url": view_url,
            }
            try:
                response = self.session.get(
                    view_url,
                    headers={"User-Agent": self._get_user_agent()},
                    timeout=self._get_timeout(),
                )
                response.raise_for_status()
                parsed = ViewParser.parse(response.text)
                if parsed:
                    parsed["preview_url"] = view_url
                    view_data = parsed
            except Exception:
                pass

            self.available_views.append(view_data)
            self._update_progress(index)

    def _load_local_files(self, selected_files: list[str]):
        model_candidates = [path for path in selected_files if Path(path).name.lower() == "model.html"]
        if not model_candidates:
            QMessageBox.warning(self, "Error", "Select a set of files that includes model.html.")
            return

        model_path = model_candidates[0]
        view_files = [path for path in selected_files if path != model_path]
        if not view_files:
            QMessageBox.warning(self, "Error", "Select at least one local view HTML file alongside model.html.")
            return

        self._reset_runtime_state()
        self.local_model_path = model_path
        self._set_busy("Loading local files...", indeterminate=False, total_steps=max(len(view_files), 1))
        self.model_data.load_from_file(model_path)

        self.available_views = []
        for index, view_file in enumerate(view_files, 1):
            try:
                with open(view_file, "r", encoding="utf-8") as handle:
                    view_html = handle.read()
                view_data = ViewParser.parse(view_html)
                if view_data:
                    view_data["preview_url"] = QUrl.fromLocalFile(view_file).toString()
                    view_data["local_path"] = view_file
                    self.available_views.append(view_data)
            except Exception:
                pass
            self._update_progress(index)

        self._hide_progress()
        if not self.available_views:
            QMessageBox.warning(self, "Error", "No local views could be parsed from the selected files.")
            self.status_bar.showMessage("No local views loaded.")
            return

        self._enter_review_step()

    def _on_load_local_clicked(self):
        selected_files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Local Archi HTML Files",
            "",
            "HTML Files (*.html *.htm);;All Files (*)"
        )
        if not selected_files:
            return
        self._load_local_files(selected_files)

    def _selected_views(self):
        return [view for view in self.available_views if view["view_id"] in self.selected_view_ids]

    def _build_export_targets(self):
        output_dir = Path(self.output_dir_input.text().strip() or os.getcwd())
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = self.output_name_input.text().strip() or "master_model"
        safe_base = sanitize_filename(base_name) or "master_model"
        selected_format = self.format_group.checkedId()
        xml_path = output_dir / f"{safe_base}.xml" if selected_format in (1, 3) else None
        json_path = output_dir / f"{safe_base}.json" if selected_format in (2, 3) else None
        markdown_dir = output_dir / f"{safe_base}_markdown" if self.markdown_checkbox.isChecked() else None
        return output_dir, xml_path, json_path, markdown_dir

    def _get_image_base_and_guid(self):
        if not self.model_url:
            return None
        parsed = urlparse(self.model_url)
        match = re.search(r"(.*?/)(id-[A-Fa-f0-9-]+)/elements/model\.html$", parsed.path)
        if not match:
            return None
        base_path, guid = match.group(1), match.group(2)
        base_url = f"{parsed.scheme}://{parsed.netloc}{base_path}"
        return base_url, guid

    def _generate_markdown(self, xml_path: Path, output_dir: Path):
        model_name, elements, relationships, views = markdown_converter.parse_model(xml_path)
        rel_index = markdown_converter.build_relationship_index(elements, relationships)
        output_dir.mkdir(parents=True, exist_ok=True)
        markdown_converter.write_readme(output_dir, model_name, len(elements), len(relationships), len(views))
        markdown_converter.write_elements_files(elements, rel_index, output_dir)
        markdown_converter.write_relationships(relationships, elements, output_dir)
        markdown_converter.write_views(views, elements, output_dir)

    def _summarize_export(self):
        total_elements = len(set(
            elem_id for view in self.batch_views for elem_id in view.get("elements", {}).keys()
        ))
        total_relationships = len(set(
            rel["id"] for view in self.batch_views for rel in view.get("relationships", []) if "id" in rel
        ))
        summary = (
            f"Views exported: {len(self.batch_views)}\n"
            f"Elements: {total_elements}\n"
            f"Relationships: {total_relationships}"
        )
        files_text = "\n".join(
            f"{Path(path).name} ({Path(path).stat().st_size} bytes)"
            for path in self.exported_files
            if Path(path).exists()
        )
        return summary, files_text

    def _on_export_clicked(self):
        self.pending_export = True
        self.batch_views = self._selected_views()
        if not self.batch_views:
            QMessageBox.warning(self, "Error", "Select at least one view to export.")
            return

        if not self.model_data.loaded:
            reply = QMessageBox.question(
                self,
                "Warning",
                "Model data is not loaded. Documentation and folder structure will be missing.\nContinue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        try:
            output_dir, xml_path, json_path, markdown_dir = self._build_export_targets()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to prepare output paths:\n{exc}")
            return

        self.export_output_dir = str(output_dir)
        self.exported_files = []
        self.last_xml_path = str(xml_path) if xml_path else None
        self.last_export_error = None

        total_steps = 1
        if xml_path:
            total_steps += 1
        if json_path:
            total_steps += 1
        if self.download_images_checkbox.isChecked():
            total_steps += 1
        if markdown_dir:
            total_steps += 1

        self.status_bar.showMessage("Generating export...")
        self._show_progress(total_steps)

        try:
            generator = ArchiMateXMLGenerator(self.model_data)
            xml_root = generator.create_merged_xml(
                self.batch_views,
                include_connections=self.include_connections_checkbox.isChecked(),
            )
            step = 1
            self._update_progress(step)

            if xml_path:
                ArchiMateXMLGenerator.save_xml(xml_root, str(xml_path))
                self.exported_files.append(str(xml_path))
                step += 1
                self._update_progress(step)

            if json_path:
                json_data = generator.export_json(xml_root)
                with open(json_path, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps(json_data, indent=2, ensure_ascii=False))
                self.exported_files.append(str(json_path))
                step += 1
                self._update_progress(step)

            if self.download_images_checkbox.isChecked():
                base_guid = self._get_image_base_and_guid()
                if base_guid:
                    base_url, guid = base_guid
                    images_dir = output_dir / "images"
                    download_view_images(
                        base_url=base_url,
                        guid=guid,
                        views=self.batch_views,
                        output_dir=str(images_dir),
                        user_agent=self._get_user_agent(),
                        timeout=self._get_timeout(),
                        session=self.session,
                    )
                    if images_dir.exists():
                        self.exported_files.append(str(images_dir))
                step += 1
                self._update_progress(step)

            if markdown_dir:
                markdown_source = xml_path
                temp_xml = None
                if markdown_source is None:
                    temp_handle = tempfile.NamedTemporaryFile(delete=False, suffix=".xml")
                    temp_handle.close()
                    temp_xml = Path(temp_handle.name)
                    ArchiMateXMLGenerator.save_xml(xml_root, str(temp_xml))
                    markdown_source = temp_xml
                self._generate_markdown(markdown_source, markdown_dir)
                self.exported_files.append(str(markdown_dir))
                step += 1
                self._update_progress(step)
                if temp_xml and temp_xml.exists():
                    temp_xml.unlink()

            summary, files_text = self._summarize_export()
            self.status_bar.showMessage("Export completed successfully.")
            self._enter_done_step(True, summary, files_text)
        except Exception as exc:
            self.last_export_error = str(exc)
            self.status_bar.showMessage("Export failed.")
            self._enter_done_step(False, f"{exc}", "Use Retry Export to try again.")
        finally:
            self._hide_progress()

    def _retry_export(self):
        if not self.pending_export:
            return
        self._go_to_step(3)
        self._on_export_clicked()

    def _open_export_folder(self):
        if not self.export_output_dir:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.export_output_dir))

    def _on_validate_xml_clicked(self):
        xml_path = self.last_xml_path
        if not xml_path:
            xml_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select ArchiMate XML",
                "",
                "ArchiMate XML Files (*.xml);;All Files (*)"
            )
        if not xml_path:
            return

        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            warnings = ArchiMateXMLGenerator.validate_xml(root)
            if warnings:
                QMessageBox.information(self, "XML Validation Warnings", "Warnings:\n" + "\n".join(warnings))
            else:
                QMessageBox.information(self, "XML Validation", "XML is valid - no issues found")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to validate XML:\n{exc}")

    def _on_convert_markdown_clicked(self):
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
            self._generate_markdown(Path(xml_path), Path(output_dir))
            QMessageBox.information(self, "Success", f"Markdown written to:\n{output_dir}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to convert XML:\n{exc}")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = ArchiScraperApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

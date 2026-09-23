"""
LogNeedle – Main Window (PySide6).

Layout:
  ┌─────────────────────────────────────────────────────────┐
  │  Toolbar: [Open] [1m][5m][10m][15m][1h][1d][1w] [Export]│
  ├────────────┬────────────────────────────────────────────┤
  │  Left pane │  Report pane (QTextBrowser – HTML)         │
  │  - search  │                                            │
  │  - filters │                                            │
  ├────────────┴────────────────────────────────────────────┤
  │  Console (QPlainTextEdit – real-time parse output)      │
  └─────────────────────────────────────────────────────────┘
  │  Status bar + progress                                  │
  └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..analysis.analyzer import Analyzer, Report
from ..export.exporter import ReportExporter
from ..ingest.loader import IngestPipeline
from ..store.db import EventStore
from .styles import DARK_STYLESHEET
from .worker import IngestWorker


class MainWindow(QMainWindow):
    """Primary application window for LogNeedle."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LogNeedle — Log Analysis & Timeline")
        self.setMinimumSize(1200, 700)
        self.setAcceptDrops(True)
        self.setStyleSheet(DARK_STYLESHEET)

        # ── state ───────────────────────────────────────────────────
        self.store: EventStore | None = None
        self.analyzer: Analyzer | None = None
        self.current_report: Report | None = None
        self._worker: IngestWorker | None = None
        self._active_window = "1d"
        self._ingesting = False

        # ── build UI ────────────────────────────────────────────────
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._set_post_ingest_enabled(False)

    # ================================================================
    #  UI CONSTRUCTION
    # ================================================================

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setStyleSheet("QToolBar { spacing: 6px; padding: 6px; }")
        self.addToolBar(tb)

        # Open button
        self.open_btn = QPushButton("📂 Open Zip / Folder")
        self.open_btn.setObjectName("openBtn")
        self.open_btn.clicked.connect(self._on_open)
        tb.addWidget(self.open_btn)
        tb.addSeparator()

        # Time window buttons
        self._window_btns: dict[str, QPushButton] = {}
        for key, label in [
            ("1m", "1 min"), ("5m", "5 min"), ("10m", "10 min"),
            ("15m", "15 min"), ("1h", "1 hour"), ("1d", "1 day"), ("1w", "1 week"),
        ]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == "1d")
            btn.clicked.connect(lambda checked, k=key: self._on_window_click(k))
            tb.addWidget(btn)
            self._window_btns[key] = btn

        tb.addSeparator()

        # Export button
        self.export_btn = QPushButton("💾 Export Report")
        self.export_btn.setObjectName("exportBtn")
        self.export_btn.clicked.connect(self._on_export)
        tb.addWidget(self.export_btn)

    def _build_central(self) -> None:
        # ── Outer vertical layout: [splitter] + [console] ────────
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        self.setCentralWidget(outer)

        # ── Top: left/right splitter ─────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # ── LEFT PANE ───────────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 4, 8)

        # Drop zone / open label
        self.drop_label = QLabel("Drag & drop\nZIP or folder here")
        self.drop_label.setObjectName("dropLabel")
        self.drop_label.setAlignment(Qt.AlignCenter)
        self.drop_label.setMinimumHeight(80)
        self.drop_label.setStyleSheet(
            "border: 2px dashed #45475a; border-radius: 10px; padding: 16px;"
        )
        left_layout.addWidget(self.drop_label)

        # Search
        search_box = QGroupBox("Search & Filters")
        search_lay = QVBoxLayout(search_box)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Find in timeline...")
        self.search_edit.returnPressed.connect(self._on_refresh_report)
        search_lay.addWidget(self.search_edit)

        # Level filter
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Level:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(["All", "ERROR", "WARN", "INFO", "UNKNOWN"])
        self.level_combo.currentIndexChanged.connect(self._on_refresh_report)
        row1.addWidget(self.level_combo)
        search_lay.addLayout(row1)

        # Source type filter
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Source:"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(["All", "evtx", "text"])
        self.source_combo.currentIndexChanged.connect(self._on_refresh_report)
        row2.addWidget(self.source_combo)
        search_lay.addLayout(row2)

        # Provider filter
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Provider:"))
        self.provider_edit = QLineEdit()
        self.provider_edit.setPlaceholderText("e.g. Kernel-Power")
        self.provider_edit.returnPressed.connect(self._on_refresh_report)
        row3.addWidget(self.provider_edit)
        search_lay.addLayout(row3)

        # File filter
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("File:"))
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("e.g. SmartShield")
        self.file_edit.returnPressed.connect(self._on_refresh_report)
        row4.addWidget(self.file_edit)
        search_lay.addLayout(row4)

        # Redact toggle
        self.redact_check = QCheckBox("Redact secrets")
        search_lay.addWidget(self.redact_check)
        self.redact_check.stateChanged.connect(self._on_refresh_report)

        left_layout.addWidget(search_box)

        # Ingested files list
        files_box = QGroupBox("Ingested Files")
        files_lay = QVBoxLayout(files_box)
        self.file_list = QListWidget()
        files_lay.addWidget(self.file_list)
        left_layout.addWidget(files_box)

        left_layout.addStretch()
        left.setMinimumWidth(260)
        left.setMaximumWidth(380)

        # ── RIGHT PANE (report) ─────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 8, 8, 8)

        self.report_browser = QTextBrowser()
        self.report_browser.setOpenExternalLinks(False)
        self.report_browser.setHtml(self._placeholder_html())
        right_layout.addWidget(self.report_browser)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        outer_layout.addWidget(splitter, stretch=1)

        # ── BOTTOM: Output Console ──────────────────────────────────
        console_label = QLabel("  📋 Output Console")
        console_label.setObjectName("consoleLabel")
        console_label.setStyleSheet(
            "color: #89b4fa; font-size: 11px; font-weight: bold; "
            "padding: 4px 0 0 0; background: #181825;"
        )
        outer_layout.addWidget(console_label)

        self.console = QPlainTextEdit()
        self.console.setObjectName("consoleOutput")
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(140)
        self.console.setMinimumHeight(80)
        mono_font = QFont("Consolas", 10)
        mono_font.setStyleHint(QFont.Monospace)
        self.console.setFont(mono_font)
        self.console.setPlaceholderText("Waiting for ingest…")
        outer_layout.addWidget(self.console)

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(300)
        sb.addPermanentWidget(self.progress_bar)

        self.status_label = QLabel("Ready – drag a zip or folder to begin")
        self.status_label.setObjectName("statusLabel")
        sb.addWidget(self.status_label)

    def _set_post_ingest_enabled(self, enabled: bool) -> None:
        for btn in self._window_btns.values():
            btn.setEnabled(enabled)
        self.export_btn.setEnabled(enabled)
        self.search_edit.setEnabled(enabled)
        self.level_combo.setEnabled(enabled)
        self.source_combo.setEnabled(enabled)
        self.provider_edit.setEnabled(enabled)
        self.file_edit.setEnabled(enabled)
        self.redact_check.setEnabled(enabled)

    # ================================================================
    #  DRAG & DROP
    # ================================================================

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        md: QMimeData = event.mimeData()
        if md.hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path:
            self._start_ingest(path)

    # ================================================================
    #  CONSOLE
    # ================================================================

    def _console_append(self, text: str) -> None:
        """Append a line to the output console and auto-scroll."""
        self.console.appendPlainText(text)
        self.console.verticalScrollBar().setValue(
            self.console.verticalScrollBar().maximum()
        )

    # ================================================================
    #  ACTIONS
    # ================================================================

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open log archive", "", "Zip archives (*.zip);;All files (*)"
        )
        if not path:
            # try folder
            path = QFileDialog.getExistingDirectory(self, "Open log folder")
        if path:
            self._start_ingest(path)

    def _on_window_click(self, key: str) -> None:
        self._active_window = key
        for k, btn in self._window_btns.items():
            btn.setChecked(k == key)
        # During ingest, tell the worker to use this window for next refresh
        if self._ingesting and self._worker:
            self._worker.set_window_key(key)
        else:
            self._on_refresh_report()

    def _on_export(self) -> None:
        if self.current_report is None:
            return
        path, filt = QFileDialog.getSaveFileName(
            self,
            "Export Report",
            f"logneedle_report_{self._active_window}",
            "Markdown (*.md);;HTML (*.html);;Plain text (*.txt)",
        )
        if not path:
            return
        fmt = "md"
        if path.endswith(".html"):
            fmt = "html"
        elif path.endswith(".txt"):
            fmt = "txt"
        exporter = ReportExporter(redact=self.redact_check.isChecked())
        exporter.save(self.current_report, path, fmt)
        self.status_label.setText(f"Report exported → {path}")

    # ================================================================
    #  INGEST
    # ================================================================

    def _start_ingest(self, path: str) -> None:
        self.store = EventStore()
        self.analyzer = Analyzer(self.store)
        exporter = ReportExporter(redact=self.redact_check.isChecked())

        pipeline = IngestPipeline(self.store)
        self._worker = IngestWorker(
            pipeline, path,
            analyzer=self.analyzer,
            exporter=exporter,
            window_key=self._active_window,
        )
        self._worker.progress.connect(self._on_ingest_progress)
        self._worker.log_message.connect(self._console_append)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.report_html.connect(self._on_live_report_html)
        self._worker.finished_with_report.connect(self._on_ingest_finished)
        self._worker.error.connect(self._on_ingest_error)

        # Clear console and report for new ingest
        self.console.clear()
        self._console_append(f"▶ Starting ingest: {path}")

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # indeterminate until we have total
        self.open_btn.setEnabled(False)
        self.status_label.setText(f"Ingesting {path} …")
        self.file_list.clear()
        self._ingesting = True

        # Enable controls early so user can see the live report
        self._set_post_ingest_enabled(True)

        self._worker.start()

    def _on_ingest_progress(self, msg: str, done: int, total: int) -> None:
        if total > 0 and done >= 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)
        self.status_label.setText(msg)

    def _on_file_done(self, filename: str, event_count: int) -> None:
        """Called after each file is fully parsed — add to file list."""
        self.file_list.addItem(f"{filename}  ({event_count:,} events)")

    def _on_live_report_html(self, html: str) -> None:
        """Display live report HTML generated on the worker thread."""
        if html:
            self.report_browser.setHtml(html)

    def _on_ingest_finished(self, final_html: str) -> None:
        self._ingesting = False
        self.progress_bar.setVisible(False)
        self.open_btn.setEnabled(True)
        self._set_post_ingest_enabled(True)

        # Show final report from worker thread
        if final_html:
            self.report_browser.setHtml(final_html)

        # Now safe to query DB from main thread (worker is done)
        if self.store:
            cnt = self.store.event_count()
            end = self.store.end_of_logs()
            self.status_label.setText(
                f"✓ Ingested {cnt:,} events  |  End of logs: {end}"
            )

    def _on_ingest_error(self, msg: str) -> None:
        self._ingesting = False
        self.progress_bar.setVisible(False)
        self.open_btn.setEnabled(True)
        self._console_append(f"❌ Error: {msg}")
        QMessageBox.warning(self, "Ingest error", msg)

    # ================================================================
    #  REPORT
    # ================================================================

    def _on_refresh_report(self) -> None:
        if self.analyzer is None:
            return

        level = self.level_combo.currentText()
        source = self.source_combo.currentText()

        report = self.analyzer.generate_report(
            self._active_window,
            level_filter=level if level != "All" else None,
            source_type_filter=source if source != "All" else None,
            provider_filter=self.provider_edit.text().strip() or None,
            file_filter=self.file_edit.text().strip() or None,
            search_text=self.search_edit.text().strip() or None,
        )
        self.current_report = report
        if report:
            exporter = ReportExporter(redact=self.redact_check.isChecked())
            html = exporter.to_html(report)
            self.report_browser.setHtml(html)
        else:
            self.report_browser.setHtml(
                "<p style='color:#f38ba8;'>No events found for this window.</p>"
            )

    # ================================================================
    #  HELPERS
    # ================================================================

    @staticmethod
    def _placeholder_html() -> str:
        return """
        <div style='text-align:center; padding: 60px 20px; color: #6c7086;'>
            <h2 style='color:#89b4fa;'>🔍 LogNeedle</h2>
            <p style='font-size:16px;'>
                Drag &amp; drop a <strong>.zip</strong> or folder of logs to begin analysis.<br>
                Supports <code>.evtx</code>, <code>.log</code>, <code>.txt</code>,
                <code>.csv</code>, <code>.jsonl</code> files.
            </p>
            <p style='font-size:13px; margin-top:30px;'>
                The app will parse all files, normalize timestamps to UTC,<br>
                and generate a structured timeline with evidence citations.
            </p>
        </div>
        """

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        if self.store:
            self.store.close()
        super().closeEvent(event)

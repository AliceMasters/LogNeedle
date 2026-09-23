"""
Worker thread for LogNeedle ingest and analysis.

Runs the IngestPipeline in a QThread and emits Qt signals
for progress, completion, and errors.

All DB access (including report generation) happens on this thread
to avoid DuckDB cross-thread issues.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QThread, Signal


class IngestWorker(QThread):
    """Background thread for ingesting logs."""

    progress = Signal(str, int, int)     # (status_msg, done, total)
    log_message = Signal(str)            # detailed console line
    file_done = Signal(str, int)         # (filename, event_count)
    report_html = Signal(str)            # live report HTML from worker thread
    finished_with_report = Signal(str)   # final report HTML on completion
    error = Signal(str)

    def __init__(self, pipeline, input_path: str, analyzer=None,
                 exporter=None, window_key: str = "1d", parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.input_path = input_path
        self.analyzer = analyzer
        self.exporter = exporter
        self.window_key = window_key
        self._cancelled = False
        self._last_report_time = 0.0

    def run(self) -> None:
        try:
            self.pipeline._progress = self._emit_progress
            self.pipeline._cancel = lambda: self._cancelled
            self.pipeline._log_cb = self._emit_log
            self.pipeline._file_done_cb = self._on_file_done
            self.pipeline.ingest(self.input_path)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            # Generate final report on worker thread
            html = self._generate_report_html()
            self.finished_with_report.emit(html)

    def cancel(self) -> None:
        self._cancelled = True

    def set_window_key(self, key: str) -> None:
        """Allow main thread to update the active window key."""
        self.window_key = key

    def _emit_progress(self, msg: str, done: int, total: int) -> None:
        self.progress.emit(msg, done, total)

    def _emit_log(self, msg: str) -> None:
        self.log_message.emit(msg)

    def _on_file_done(self, filename: str, event_count: int) -> None:
        self.file_done.emit(filename, event_count)
        # Generate live report at most every 5 seconds
        now = time.monotonic()
        if now - self._last_report_time >= 5.0:
            self._last_report_time = now
            html = self._generate_report_html()
            if html:
                self.report_html.emit(html)

    def _generate_report_html(self) -> str:
        """Generate report HTML on the worker thread (safe — same thread as DB writes)."""
        if self.analyzer is None or self.exporter is None:
            return ""
        try:
            report = self.analyzer.generate_report(self.window_key)
            if report:
                return self.exporter.to_html(report)
        except Exception:
            pass
        return ""

"""
Ingestion pipeline for LogNeedle.

Accepts a ZIP file or folder, enumerates files, classifies them,
and streams-parses them into the DuckDB event store.

Designed to run in a worker thread; emits Qt-compatible progress signals
via a simple callback interface.
"""

from __future__ import annotations

import os
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

from ..parsers.text_parser import TextLogParser
from ..parsers.evtx_parser import EvtxParser, HAS_EVTX
from ..store.db import EventStore

# Supported extensions
TEXT_EXTS = {".log", ".txt", ".csv", ".jsonl", ".out"}
EVTX_EXTS = {".evtx"}


class IngestPipeline:
    """Enumerate, classify, parse, and load log files into EventStore."""

    def __init__(
        self,
        store: EventStore,
        progress_cb: Callable[[str, int, int], None] | None = None,
        cancel_flag: Callable[[], bool] | None = None,
    ):
        """
        Parameters
        ----------
        store : EventStore
        progress_cb : optional (status_message, files_done, files_total)
        cancel_flag : optional callable returning True to abort
        """
        self.store = store
        self._progress: Callable[[str, int, int], None] = progress_cb or (lambda _s, _d, _t: None)
        self._cancel = cancel_flag or (lambda: False)
        self._log_cb: Callable[[str], None] | None = None
        self._file_done_cb: Callable[[str, int], None] | None = None
        self.total_warnings = 0
        self.files_processed: list[str] = []
        self.temp_dir: str | None = None

    def _log(self, msg: str) -> None:
        cb = self._log_cb
        if cb:
            cb(msg)

    # ── public API ──────────────────────────────────────────────────

    def ingest(self, path: str | Path) -> None:
        """Entry point: path can be a .zip or a directory."""
        p = Path(path)
        if p.is_file() and p.suffix.lower() == ".zip":
            self._ingest_zip(p)
        elif p.is_dir():
            self._ingest_folder(p, p)
        else:
            raise ValueError(f"Unsupported input: {p}")

    # ── zip handling ────────────────────────────────────────────────

    def _ingest_zip(self, zip_path: Path) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="logneedle_")
        self._progress(f"Extracting {zip_path.name}...", 0, 0)
        self._log(f"📦 Extracting {zip_path.name}...")

        with zipfile.ZipFile(str(zip_path), "r") as zf:
            zf.extractall(self.temp_dir)

        self._log(f"✓ Extraction complete")
        tmp_dir = self.temp_dir
        if tmp_dir is None:
            return
        root = Path(tmp_dir)
        self._ingest_folder(root, root)

    def _ingest_folder(self, root: Path, base: Path) -> None:
        # Collect files
        all_files: list[Path] = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                fp = Path(dirpath) / fn
                ext = fp.suffix.lower()
                if ext in TEXT_EXTS or ext in EVTX_EXTS:
                    all_files.append(fp)

        total = len(all_files)
        self._log(f"📂 Found {total} log files to parse")

        for idx, fp in enumerate(all_files):
            if self._cancel():
                self._log("⛔ Ingest cancelled by user")
                return
            rel = str(fp.relative_to(base))
            ext = fp.suffix.lower()
            self._progress(f"Parsing {rel}", idx, total)

            t0 = time.perf_counter()
            file_event_count = 0
            try:
                if ext in EVTX_EXTS:
                    file_event_count = self._parse_evtx(fp, rel)
                else:
                    file_event_count = self._parse_text(fp, rel)
            except Exception as exc:
                self.total_warnings += 1
                self._log(f"⚠ Error parsing {rel}: {exc}")

            elapsed = time.perf_counter() - t0
            self._log(
                f"  ✓ {rel} — {file_event_count:,} events ({elapsed:.1f}s)"
            )
            file_cb = self._file_done_cb
            if file_cb:
                file_cb(rel, file_event_count)

            self.files_processed.append(rel)

        self.store.flush()
        total_events = self.store.event_count()
        self._log(f"✅ Ingest complete — {total_events:,} total events from {total} files")
        self._progress("Ingest complete", total, total)

    # ── file-level parsers ──────────────────────────────────────────

    def _parse_text(self, fp: Path, label: str) -> int:
        def _on_lines(lines_read: int, events_so_far: int) -> None:
            self._log(f"    … {label}: {lines_read:,} lines read, {count:,} events")
            self._progress(f"Parsing {label} ({lines_read:,} lines)", -1, -1)

        parser = TextLogParser(fp, source_file_label=label, line_cb=_on_lines)
        count = 0
        for ev in parser.parse():
            self.store.insert_event(**ev)
            count += 1
        self.total_warnings += parser.warning_count
        return count

    def _parse_evtx(self, fp: Path, label: str) -> int:
        if not HAS_EVTX:
            self.total_warnings += 1
            self._log(f"⚠ python-evtx not installed, skipping {label}")
            return 0
        parser = EvtxParser(fp, source_file_label=label)
        count = 0
        for ev in parser.parse():
            self.store.insert_event(**ev)
            count += 1
        self.total_warnings += parser.warning_count
        return count

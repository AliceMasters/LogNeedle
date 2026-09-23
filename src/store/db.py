"""
DuckDB-backed event store for LogNeedle.

Provides streaming insert (batched appender), time-window queries,
storm detection, and analytics on the normalised event table.

Thread-safe: all database operations are protected by a reentrant lock
so the worker thread (writes) and the UI thread (reads) can coexist.
"""

from __future__ import annotations

import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import uuid  # noqa: F401 — DuckDB internally requires this module
import duckdb

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY DEFAULT(nextval('event_seq')),
    event_time_utc  TIMESTAMP,
    event_time_str  VARCHAR,
    source_type     VARCHAR,          -- 'evtx' | 'text'
    source_file     VARCHAR,
    line_start      INTEGER,
    line_end        INTEGER,
    evtx_log_name   VARCHAR,
    evtx_record_id  BIGINT,
    provider        VARCHAR,
    event_id        INTEGER,
    level           VARCHAR,          -- 'ERROR','WARN','INFO','UNKNOWN'
    message         VARCHAR,
    message_raw     VARCHAR,
    tags            VARCHAR           -- comma-separated tags
);
"""


class EventStore:
    """Thin wrapper around a DuckDB connection for the LogNeedle event table."""

    def __init__(self, db_path: str | None = None):
        self._tmp_dir: str | None = None
        if db_path is None:
            tmp_dir = tempfile.mkdtemp(prefix="logneedle_db_")
            db_path = os.path.join(tmp_dir, "events.duckdb")
            self._tmp_dir = tmp_dir
        self.db_path = db_path
        self.con = duckdb.connect(db_path)
        self.con.execute("CREATE SEQUENCE IF NOT EXISTS event_seq START 1;")
        self.con.execute(_SCHEMA_DDL)
        self._batch: list[tuple] = []
        self._batch_size = 5000
        self._lock = threading.RLock()

    # ── insert ──────────────────────────────────────────────────────────

    def insert_event(self, **kw: Any) -> None:
        """Buffer a single event; auto-flushes every _batch_size rows."""
        row = (
            kw.get("event_time_utc"),
            kw.get("event_time_str", ""),
            kw.get("source_type", "text"),
            kw.get("source_file", ""),
            kw.get("line_start"),
            kw.get("line_end"),
            kw.get("evtx_log_name"),
            kw.get("evtx_record_id"),
            kw.get("provider"),
            kw.get("event_id"),
            kw.get("level", "UNKNOWN"),
            kw.get("message", ""),
            kw.get("message_raw"),
            kw.get("tags", ""),
        )
        with self._lock:
            self._batch.append(row)
            if len(self._batch) >= self._batch_size:
                self._flush_unlocked()

    def flush(self) -> None:
        with self._lock:
            self._flush_unlocked()

    def _flush_unlocked(self) -> None:
        """Internal flush — caller must hold self._lock."""
        if not self._batch:
            return
        self.con.executemany(
            """INSERT INTO events (
                   event_time_utc, event_time_str, source_type, source_file,
                   line_start, line_end, evtx_log_name, evtx_record_id,
                   provider, event_id, level, message, message_raw, tags
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            self._batch,
        )
        self._batch.clear()

    # ── queries ─────────────────────────────────────────────────────────

    def end_of_logs(self) -> Optional[datetime]:
        """Return the newest event_time_utc across all ingested events."""
        with self._lock:
            self._flush_unlocked()
            row = self.con.execute(
                "SELECT MAX(event_time_utc) FROM events"
            ).fetchone()
            return row[0] if row and row[0] else None

    def event_count(self) -> int:
        with self._lock:
            self._flush_unlocked()
            row = self.con.execute("SELECT COUNT(*) FROM events").fetchone()
            return row[0] if row else 0

    def query_window(
        self,
        end_time: datetime,
        window: timedelta,
        *,
        level_filter: str | None = None,
        source_type_filter: str | None = None,
        provider_filter: str | None = None,
        event_id_filter: int | None = None,
        file_filter: str | None = None,
        search_text: str | None = None,
        limit: int = 10000,
    ) -> list[dict]:
        """Return events in [end_time - window, end_time] newest-first."""
        with self._lock:
            self._flush_unlocked()
            start_time = end_time - window
            clauses = ["event_time_utc BETWEEN ? AND ?"]
            params: list[Any] = [start_time, end_time]

            if level_filter:
                clauses.append("level = ?")
                params.append(level_filter.upper())
            if source_type_filter:
                clauses.append("source_type = ?")
                params.append(source_type_filter)
            if provider_filter:
                clauses.append("provider ILIKE ?")
                params.append(f"%{provider_filter}%")
            if event_id_filter is not None:
                clauses.append("event_id = ?")
                params.append(event_id_filter)
            if file_filter:
                clauses.append("source_file ILIKE ?")
                params.append(f"%{file_filter}%")
            if search_text:
                clauses.append("(message ILIKE ? OR message_raw ILIKE ?)")
                params.extend([f"%{search_text}%", f"%{search_text}%"])

            where = " AND ".join(clauses)
            params.append(limit)
            sql = f"""
                SELECT * FROM events
                WHERE {where}
                ORDER BY event_time_utc DESC
                LIMIT ?
            """
            cols = [d[0] for d in self.con.execute(sql, params).description]
            rows = self.con.execute(sql, params).fetchall()
            return [dict(zip(cols, r)) for r in rows]

    def storm_groups(
        self,
        end_time: datetime,
        window: timedelta,
        threshold: int = 50,
    ) -> list[dict]:
        """Detect repeating message storms within a time window."""
        with self._lock:
            self._flush_unlocked()
            start_time = end_time - window
            sql = """
                SELECT
                    message,
                    source_file,
                    provider,
                    event_id,
                    level,
                    COUNT(*) as cnt,
                    MIN(event_time_utc) as first_seen,
                    MAX(event_time_utc) as last_seen,
                    MIN(id) as first_id,
                    MAX(id) as last_id
                FROM events
                WHERE event_time_utc BETWEEN ? AND ?
                GROUP BY message, source_file, provider, event_id, level
                HAVING COUNT(*) >= ?
                ORDER BY cnt DESC
                LIMIT 100
            """
            cols = [d[0] for d in self.con.execute(sql, [start_time, end_time, threshold]).description]
            rows = self.con.execute(sql, [start_time, end_time, threshold]).fetchall()
            results = []
            for row in rows:
                d = dict(zip(cols, row))
                samples_sql = """
                    SELECT source_file, line_start, line_end,
                           evtx_log_name, evtx_record_id, provider, event_id,
                           event_time_utc, source_type
                    FROM events
                    WHERE message = ? AND event_time_utc BETWEEN ? AND ?
                    ORDER BY event_time_utc
                """
                all_matches = self.con.execute(
                    samples_sql, [d["message"], start_time, end_time]
                ).fetchall()
                sample_cols = [
                    "source_file", "line_start", "line_end",
                    "evtx_log_name", "evtx_record_id", "provider", "event_id",
                    "event_time_utc", "source_type",
                ]
                if all_matches:
                    indices = [0, len(all_matches) // 2, len(all_matches) - 1]
                    d["samples"] = [
                        dict(zip(sample_cols, all_matches[i]))
                        for i in sorted(set(indices))
                    ]
                results.append(d)
            return results

    def last_errors(
        self,
        end_time: datetime,
        window: timedelta,
        top_n: int = 5,
    ) -> list[dict]:
        """Find the last unique error signatures within a window."""
        with self._lock:
            self._flush_unlocked()
            start_time = end_time - window
            sql = """
                WITH ranked AS (
                    SELECT *,
                        ROW_NUMBER() OVER (
                            PARTITION BY COALESCE(provider,'') || '::' || message
                            ORDER BY event_time_utc DESC
                        ) AS rn
                    FROM events
                    WHERE event_time_utc BETWEEN ? AND ?
                      AND (level = 'ERROR'
                           OR message ILIKE '%failed%'
                           OR message ILIKE '%crash%'
                           OR message ILIKE '%exception%'
                           OR message ILIKE '%timeout%'
                           OR message ILIKE '%bugcheck%'
                           OR message ILIKE '%cannot communicate%'
                           OR message ILIKE '%driver%error%')
                )
                SELECT * FROM ranked WHERE rn = 1
                ORDER BY event_time_utc DESC
                LIMIT ?
            """
            cols = [
                d[0]
                for d in self.con.execute(sql, [start_time, end_time, top_n]).description
            ]
            rows = self.con.execute(sql, [start_time, end_time, top_n]).fetchall()
            return [dict(zip(cols, r)) for r in rows]

    def source_files(self) -> list[str]:
        """List distinct source_file values."""
        with self._lock:
            self._flush_unlocked()
            rows = self.con.execute(
                "SELECT DISTINCT source_file FROM events ORDER BY source_file"
            ).fetchall()
            return [r[0] for r in rows]

    def providers(self) -> list[str]:
        """List distinct provider values (EVTX)."""
        with self._lock:
            self._flush_unlocked()
            rows = self.con.execute(
                "SELECT DISTINCT provider FROM events WHERE provider IS NOT NULL ORDER BY provider"
            ).fetchall()
            return [r[0] for r in rows]

    def try_lock(self) -> bool:
        """Non-blocking lock acquire. Returns True if acquired."""
        return self._lock.acquire(blocking=False)

    def release_lock(self) -> None:
        """Release a previously acquired lock."""
        self._lock.release()

    def close(self) -> None:
        with self._lock:
            self._flush_unlocked()
            self.con.close()
        tmp = self._tmp_dir
        if tmp and os.path.exists(self.db_path):
            try:
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)
            except OSError:
                pass



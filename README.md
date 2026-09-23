# LogNeedle

**Log Analysis & Timeline** — a Windows desktop app that turns a bundle of logs into a
clean, evidence-backed timeline and "needle in the haystack" findings.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![PySide6](https://img.shields.io/badge/GUI-PySide6-green)
![DuckDB](https://img.shields.io/badge/storage-DuckDB-yellow)

---

## Quick Start (Windows)

```powershell
# 1. Clone / unzip this repo
cd LogNeedle

# 2. Create a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch
python -m src.main
```

## Features

| Feature | Description |
|---------|-------------|
| **Drag & Drop** | Drop a `.zip` or folder of logs onto the app window |
| **Multi-format** | Parses `.evtx`, `.log`, `.txt`, `.csv`, `.jsonl`, `.out` |
| **Time Windows** | 1 min / 5 min / 10 min / 15 min / 1 hour / 1 day / 1 week |
| **Storm Detection** | Collapses repeating errors with count + sample citations |
| **Last Error** | Highlights the last unique error signatures before end-of-logs |
| **Boot/Shutdown** | Detects Kernel-Power 41, EventLog 6005/6006/6008, BugCheck |
| **Evidence Citations** | Every bullet references source file + line or EVTX record |
| **Export** | Markdown, HTML (dark-themed), and Plain Text |
| **Redact Secrets** | Toggle to mask GUIDs, bearer tokens, API keys, emails |
| **Search & Filter** | By level, source type, provider, file name, free text |

## Architecture

```
src/
├── main.py              # Entry point
├── store/db.py          # DuckDB event store (batched insert, queries)
├── parsers/
│   ├── timestamp.py     # Regex timestamp battery
│   ├── text_parser.py   # Streaming text/CSV/JSONL parser
│   └── evtx_parser.py   # python-evtx XML parser
├── ingest/loader.py     # Zip extraction, file walker, pipeline
├── analysis/analyzer.py # Storm detection, causal errors, boot/shutdown
├── export/exporter.py   # Markdown / HTML / text report generation
├── ui/
│   ├── main_window.py   # PySide6 main window
│   ├── styles.py        # Dark theme stylesheet
│   └── worker.py        # QThread worker for background ingest
└── utils/redact.py      # Secret redaction patterns
```

## Assumptions & Defaults

- **Timezone**: When a log line has no timezone info, it is assumed to be in
  the local timezone of the machine running the analysis and labelled
  `(assumed local time)` in the report. Internally all events are stored as UTC.
- **Multi-line merging**: Lines without a leading timestamp are appended to the
  previous event (for stack traces, etc.).
- **Storm threshold**: An identical message repeating ≥ 50 times within a window
  is flagged as a storm. Adjustable in code (`EventStore.storm_groups`).
- **Large files**: Events are streamed and batch-inserted (5 000 rows at a time)
  to keep memory usage low.
- **Encoding**: Files are probed with `chardet`; unreadable bytes are replaced
  with the Unicode replacement character rather than crashing.

## Running Tests

```powershell
python tests/test_timestamp.py
python tests/test_text_parser.py
python tests/test_storm.py
python tests/test_redact.py
```

## Building a Standalone .exe

```powershell
pip install pyinstaller
pyinstaller logneedle.spec
```

The resulting `dist/LogNeedle/LogNeedle.exe` is a self-contained application.

## License

MIT

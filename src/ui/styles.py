"""
Dark-theme stylesheet for LogNeedle (Catppuccin-Mocha inspired palette).
"""

DARK_STYLESHEET = """
/* ── global ─────────────────────────────────────────────────────── */
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Consolas', system-ui;
    font-size: 13px;
}

/* ── main window ────────────────────────────────────────────────── */
QMainWindow {
    background-color: #1e1e2e;
}

/* ── group boxes / panels ───────────────────────────────────────── */
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 16px;
    font-weight: bold;
    color: #89b4fa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

/* ── buttons ────────────────────────────────────────────────────── */
QPushButton {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 5px;
    padding: 6px 14px;
    color: #cdd6f4;
    min-height: 22px;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #89b4fa;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton:checked {
    background-color: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
}
QPushButton:disabled {
    background-color: #181825;
    color: #585b70;
}

/* special classes */
QPushButton#openBtn {
    background-color: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
    font-size: 14px;
    padding: 10px 20px;
    border-radius: 8px;
}
QPushButton#openBtn:hover {
    background-color: #b4d0fb;
}
QPushButton#exportBtn {
    background-color: #a6e3a1;
    color: #1e1e2e;
    font-weight: bold;
}
QPushButton#exportBtn:hover {
    background-color: #c6f0c0;
}

/* ── line edits / search ────────────────────────────────────────── */
QLineEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 5px;
    padding: 5px 10px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
}
QLineEdit:focus {
    border-color: #89b4fa;
}

/* ── combo boxes ────────────────────────────────────────────────── */
QComboBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 5px;
    padding: 4px 8px;
    color: #cdd6f4;
}
QComboBox:hover {
    border-color: #89b4fa;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #313244;
    border: 1px solid #45475a;
    color: #cdd6f4;
    selection-background-color: #585b70;
}

/* ── check boxes ────────────────────────────────────────────────── */
QCheckBox {
    spacing: 6px;
    color: #cdd6f4;
}
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #45475a;
    border-radius: 3px;
    background: #313244;
}
QCheckBox::indicator:checked {
    background: #89b4fa;
    border-color: #89b4fa;
}

/* ── list widget ────────────────────────────────────────────────── */
QListWidget {
    background-color: #181825;
    border: 1px solid #45475a;
    border-radius: 5px;
    color: #cdd6f4;
    font-size: 12px;
}
QListWidget::item {
    padding: 3px 6px;
}
QListWidget::item:selected {
    background-color: #313244;
    color: #89b4fa;
}

/* ── progress bar ───────────────────────────────────────────────── */
QProgressBar {
    border: 1px solid #45475a;
    border-radius: 5px;
    text-align: center;
    color: #1e1e2e;
    background: #313244;
    height: 22px;
    font-weight: bold;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #89b4fa, stop:1 #b4d0fb);
    border-radius: 4px;
}

/* ── text browser / report ──────────────────────────────────────── */
QTextBrowser {
    background-color: #181825;
    border: 1px solid #45475a;
    border-radius: 6px;
    color: #cdd6f4;
    padding: 10px;
    font-size: 13px;
    line-height: 1.5;
}

/* ── splitter ───────────────────────────────────────────────────── */
QSplitter::handle {
    background-color: #45475a;
    width: 2px;
}

/* ── labels ─────────────────────────────────────────────────────── */
QLabel {
    color: #cdd6f4;
}
QLabel#dropLabel {
    color: #6c7086;
    font-size: 18px;
    font-weight: bold;
}
QLabel#statusLabel {
    color: #a6adc8;
    font-size: 12px;
}

/* ── scroll area ────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #181825;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #45475a;
    min-height: 30px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #585b70;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #181825;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #45475a;
    min-width: 30px;
    border-radius: 5px;
}

/* ── output console ────────────────────────────────────────────── */
QPlainTextEdit#consoleOutput {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 0;
    color: #a6adc8;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
    padding: 6px 10px;
    selection-background-color: #45475a;
}
"""
